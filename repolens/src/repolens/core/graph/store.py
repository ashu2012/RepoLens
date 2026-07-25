"""Durable repository index backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import networkx as nx


class GraphStore:
    def __init__(self, db_path: str | Path, read_only: bool = False):
        self.db_path = Path(db_path)
        self.read_only = read_only
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            conn = sqlite3.connect(
                f"{self.db_path.resolve().as_uri()}?mode=ro",
                timeout=30,
                uri=True,
            )
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            columns = conn.execute("PRAGMA table_info(nodes)").fetchall()
            if columns and any(row["name"] == "id" and row["type"] == "INTEGER" for row in columns):
                # Index data is reproducible. Migrate the pre-alpha integer schema
                # by rebuilding it rather than retaining ambiguous name-only ids.
                conn.executescript(
                    """DROP TABLE IF EXISTS nodes;
                       DROP TABLE IF EXISTS edges;
                       DROP TABLE IF EXISTS chunks;"""
                )
            conn.executescript(
                """CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    language TEXT,
                    parent_name TEXT,
                    content_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    raw_target TEXT,
                    kind TEXT NOT NULL,
                    file_path TEXT,
                    line INTEGER,
                    confidence TEXT,
                    UNIQUE(source, target, kind, file_path, line)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    symbol_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    symbol_kind TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    language TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    embedding TEXT,
                    embedding_model TEXT
                );
                CREATE TABLE IF NOT EXISTS file_state (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    language TEXT,
                    indexed_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
                CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
                CREATE INDEX IF NOT EXISTS idx_nodes_qualified ON nodes(qualified_name);
                CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source, kind);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target, kind);
                CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path);"""
            )

    @staticmethod
    def _node_rows(graph: nx.DiGraph) -> list[tuple]:
        rows = []
        for node_id, data in graph.nodes(data=True):
            if data.get("kind") is None or data.get("file_path") is None:
                continue
            rows.append(
                (
                    node_id,
                    data.get("name", node_id),
                    data.get("qualified_name", data.get("name", node_id)),
                    str(data["kind"]),
                    data["file_path"],
                    data.get("line_start"),
                    data.get("line_end"),
                    data.get("language"),
                    data.get("parent_name"),
                    data.get("content_hash"),
                )
            )
        return rows

    @staticmethod
    def _edge_rows(graph: nx.DiGraph) -> list[tuple]:
        rows = []
        for source, target, data in graph.edges(data=True):
            rows.append(
                (
                    source,
                    target,
                    data.get("raw_target"),
                    str(data.get("kind", "references")),
                    data.get("file_path"),
                    data.get("line"),
                    str(data.get("confidence", "extracted")),
                )
            )
        return rows

    @staticmethod
    def _chunk_rows(
        chunks: Iterable,
        embeddings: dict[str, list[float]] | None = None,
        embedding_model: str = "repolens-hash-v1",
    ) -> list[tuple]:
        embeddings = embeddings or {}
        return [
            (
                chunk.id,
                chunk.id,
                chunk.content,
                chunk.file_path,
                chunk.symbol_name,
                chunk.symbol_kind,
                chunk.line_start,
                chunk.line_end,
                chunk.language,
                json.dumps(chunk.metadata),
                json.dumps(embeddings[chunk.id]) if chunk.id in embeddings else None,
                embedding_model if chunk.id in embeddings else None,
            )
            for chunk in chunks
        ]

    def replace_index(
        self,
        graph: nx.DiGraph,
        chunks: list,
        file_states: dict[str, tuple[str, str | None, float]],
        embeddings: dict[str, list[float]] | None = None,
        embedding_model: str = "repolens-hash-v1",
    ) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM file_state")
            self._insert(conn, graph, chunks, embeddings, embedding_model)
            conn.executemany(
                """INSERT INTO file_state(file_path, content_hash, language, indexed_at)
                   VALUES (?, ?, ?, ?)""",
                [(path, *state) for path, state in file_states.items()],
            )
        self.reconcile_edges()

    def apply_incremental(
        self,
        changed_paths: set[str],
        graph: nx.DiGraph,
        chunks: list,
        file_states: dict[str, tuple[str, str | None, float]],
        embeddings: dict[str, list[float]] | None = None,
        embedding_model: str = "repolens-hash-v1",
    ) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for path in changed_paths:
                node_ids = [
                    row[0] for row in conn.execute(
                        "SELECT id FROM nodes WHERE file_path = ?", (path,)
                    ).fetchall()
                ]
                conn.execute("DELETE FROM nodes WHERE file_path = ?", (path,))
                conn.execute("DELETE FROM chunks WHERE file_path = ?", (path,))
                conn.execute("DELETE FROM edges WHERE file_path = ?", (path,))
                if node_ids:
                    placeholders = ",".join("?" for _ in node_ids)
                    conn.execute(
                        f"""UPDATE edges SET target = raw_target
                            WHERE target IN ({placeholders}) AND raw_target IS NOT NULL""",
                        node_ids,
                    )
                    conn.execute(
                        f"DELETE FROM edges WHERE source IN ({placeholders})",
                        node_ids,
                    )
                conn.execute("DELETE FROM file_state WHERE file_path = ?", (path,))
            self._insert(conn, graph, chunks, embeddings, embedding_model)
            conn.executemany(
                """INSERT OR REPLACE INTO file_state
                   (file_path, content_hash, language, indexed_at) VALUES (?, ?, ?, ?)""",
                [(path, *state) for path, state in file_states.items()],
            )
        self.reconcile_edges()

    def _insert(
        self,
        conn: sqlite3.Connection,
        graph: nx.DiGraph,
        chunks: list,
        embeddings: dict[str, list[float]] | None,
        embedding_model: str = "repolens-hash-v1",
    ) -> None:
        conn.executemany(
            """INSERT OR REPLACE INTO nodes
               (id, name, qualified_name, kind, file_path, line_start, line_end,
                language, parent_name, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._node_rows(graph),
        )
        conn.executemany(
            """INSERT OR IGNORE INTO edges
               (source, target, raw_target, kind, file_path, line, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            self._edge_rows(graph),
        )
        conn.executemany(
            """INSERT OR REPLACE INTO chunks
               (id, symbol_id, content, file_path, symbol_name, symbol_kind,
                line_start, line_end, language, metadata, embedding, embedding_model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._chunk_rows(chunks, embeddings, embedding_model),
        )

    # Backward-compatible helpers used by small unit tests.
    def save_graph(self, graph: nx.DiGraph) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
            self._insert(conn, graph, [], None)

    def save_chunks(self, chunks: list) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.executemany(
                """INSERT INTO chunks
                   (id, symbol_id, content, file_path, symbol_name, symbol_kind,
                    line_start, line_end, language, metadata, embedding, embedding_model)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._chunk_rows(chunks),
            )

    def load_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM nodes"):
                data = dict(row)
                node_id = data.pop("id")
                graph.add_node(node_id, **data)
            for row in conn.execute("SELECT * FROM edges"):
                data = dict(row)
                data.pop("id")
                source, target = data.pop("source"), data.pop("target")
                graph.add_edge(source, target, **data)
        return graph

    def get_file_states(self) -> dict[str, str]:
        with self._connect() as conn:
            return {
                row["file_path"]: row["content_hash"]
                for row in conn.execute("SELECT file_path, content_hash FROM file_state")
            }

    def load_chunks(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM chunks").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"] or "{}")
            item["embedding"] = json.loads(item["embedding"]) if item["embedding"] else None
            result.append(item)
        return result

    def find_symbols(self, name: str, kind: str | None = None, limit: int = 50) -> list[dict]:
        pattern = f"%{name}%"
        with self._connect() as conn:
            if kind:
                rows = conn.execute(
                    """SELECT * FROM nodes
                       WHERE (name LIKE ? OR qualified_name LIKE ?) AND lower(kind) = lower(?)
                       ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, qualified_name LIMIT ?""",
                    (pattern, pattern, kind, name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM nodes WHERE name LIKE ? OR qualified_name LIKE ?
                       ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, qualified_name LIMIT ?""",
                    (pattern, pattern, name, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_symbol(self, symbol_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE id = ?", (symbol_id,)).fetchone()
        return dict(row) if row else None

    def list_nodes(self, exclude_paths: set[str] | None = None) -> list[dict]:
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM nodes").fetchall()]
        if exclude_paths:
            rows = [row for row in rows if row["file_path"] not in exclude_paths]
        return rows

    def related(self, symbol: str, direction: str, kind: str | None = None) -> list[dict]:
        matches = self.find_symbols(symbol, limit=10)
        ids = {match["id"] for match in matches}
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        endpoint = "source" if direction == "out" else "target"
        other = "target" if direction == "out" else "source"
        query = f"""SELECT e.*, n.name, n.qualified_name, n.file_path,
                           n.line_start, n.line_end, n.kind AS node_kind
                    FROM edges e LEFT JOIN nodes n ON n.id = e.{other}
                    WHERE e.{endpoint} IN ({placeholders})"""
        params: list[Any] = list(ids)
        if kind:
            query += " AND lower(e.kind) = lower(?)"
            params.append(kind)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def reconcile_edges(self) -> int:
        """Resolve previously unknown raw call targets after incremental changes."""
        updated = 0
        with self._connect() as conn:
            symbols = conn.execute("SELECT id, name, file_path FROM nodes").fetchall()
            by_name: dict[str, list[sqlite3.Row]] = {}
            for symbol in symbols:
                by_name.setdefault(symbol["name"], []).append(symbol)
            edges = conn.execute(
                """SELECT id, raw_target, file_path FROM edges
                   WHERE raw_target IS NOT NULL
                     AND target NOT IN (SELECT id FROM nodes)"""
            ).fetchall()
            for edge in edges:
                raw = edge["raw_target"].split("(")[0].strip()
                candidate_name = raw.split(".")[-1]
                candidates = by_name.get(candidate_name, [])
                if not candidates:
                    continue
                same_file = [item for item in candidates if item["file_path"] == edge["file_path"]]
                target = (same_file or candidates)[0]
                conn.execute(
                    "UPDATE edges SET target = ?, confidence = 'inferred' WHERE id = ?",
                    (target["id"], edge["id"]),
                )
                updated += 1
        return updated

    def remove_file_data(self, file_path: str) -> None:
        self.apply_incremental({file_path}, nx.DiGraph(), [], {})

    def get_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "total_nodes": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
                "total_edges": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
                "total_chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "total_vectors": conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
                ).fetchone()[0],
                "total_files": conn.execute("SELECT COUNT(*) FROM file_state").fetchone()[0],
            }
