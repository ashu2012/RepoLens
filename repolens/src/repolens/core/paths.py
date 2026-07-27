"""Repository path helpers for safe default behavior."""

from __future__ import annotations

import os
import shutil
import gc
import time
from pathlib import Path


def repolens_index_dir(repo_root: str | Path) -> Path:
    """Return the repository-local RepoLens metadata directory."""
    return Path(repo_root).expanduser().resolve() / ".repolens"


def repolens_active_index_pointer(repo_root: str | Path) -> Path:
    """Return the pointer file that names the active durable index."""
    return repolens_index_dir(repo_root) / "index.active"


def repolens_versioned_index_root(repo_root: str | Path) -> Path:
    """Return the directory that stores published and staged index versions."""
    return repolens_index_dir(repo_root) / "versions"


def repolens_staging_index_path(repo_root: str | Path, build_id: str) -> Path:
    """Return a staging path for a fresh index build."""
    return repolens_index_dir(repo_root) / "staging" / build_id / "index.db"


def repolens_staging_root(repo_root: str | Path) -> Path:
    """Return the root directory that contains per-build staging copies."""
    return repolens_index_dir(repo_root) / "staging"


def repolens_published_index_path(repo_root: str | Path) -> Path:
    """Return the canonical durable index path for a repository."""
    return repolens_index_dir(repo_root) / "index.db"


def repolens_architecture_snapshot_path(repo_root: str | Path) -> Path:
    """Return the cached architecture snapshot path."""
    return repolens_index_dir(repo_root) / "architecture.json"


def _resolve_pointer(pointer: Path, repo_root: Path) -> Path | None:
    try:
        target_text = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not target_text:
        return None
    candidate = Path(target_text)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    return candidate if candidate.exists() else None


def repolens_current_index_path(repo_root: str | Path) -> Path | None:
    """Resolve the active durable index file for a repository, if one exists."""
    root = Path(repo_root).expanduser().resolve()
    pointer = repolens_active_index_pointer(root)
    if pointer.exists():
        active = _resolve_pointer(pointer, root)
        if active is not None:
            return active
    legacy = repolens_index_dir(root) / "index.db"
    if legacy.exists():
        return legacy
    versions_root = repolens_versioned_index_root(root)
    if versions_root.exists():
        candidates = sorted(
            (candidate for candidate in versions_root.rglob("index.db") if candidate.is_file()),
            key=lambda candidate: candidate.stat().st_mtime_ns,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def repolens_publish_active_index(repo_root: str | Path, index_path: str | Path) -> Path:
    """Atomically publish a staged index to the canonical path and update the pointer."""
    root = Path(repo_root).expanduser().resolve()
    target = Path(index_path).expanduser().resolve()
    published = repolens_published_index_path(root)
    pointer = repolens_active_index_pointer(root)
    from repolens.core.graph.store import GraphStore

    published.parent.mkdir(parents=True, exist_ok=True)
    source_store = GraphStore(target, read_only=True)
    destination_store = GraphStore(published)
    with source_store._connect() as source, destination_store._connect() as destination:
        source.backup(destination)
    del source_store, destination_store

    pointer.parent.mkdir(parents=True, exist_ok=True)
    tmp_pointer = pointer.with_name(
        f"{pointer.name}.{os.getpid()}.{published.stat().st_mtime_ns}.tmp"
    )
    tmp_pointer.write_text(str(published), encoding="utf-8")
    os.replace(tmp_pointer, pointer)
    return published


def repolens_cleanup_staging_indexes(repo_root: str | Path) -> int:
    """Delete leftover staging copies for a repository."""
    staging_root = repolens_staging_root(repo_root)
    if not staging_root.exists():
        return 0
    removed = sum(1 for child in staging_root.iterdir() if child.is_dir())
    gc.collect()
    for attempt in range(8):
        try:
            shutil.rmtree(staging_root)
            return removed
        except PermissionError:
            if attempt == 7:
                break
            time.sleep(0.05 * (attempt + 1))
    shutil.rmtree(staging_root, ignore_errors=True)
    return removed


def repolens_package_root() -> Path:
    """Return the installed RepoLens package root.

    This resolves to the package directory itself, not the caller's current
    working directory, so it is safe to use as a fallback when a user did not
    explicitly choose a repository to index.
    """
    return Path(__file__).resolve().parents[1]


def repolens_project_root() -> Path:
    """Return the source checkout root when available, otherwise the package root."""
    package_root = repolens_package_root()
    for candidate in [package_root.parent, *package_root.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return package_root
