"""Tree-sitter multi-language AST parser for structural code extraction."""

import hashlib
from pathlib import Path
from typing import List, Tuple

import structlog

from repolens.core.ingestion.models import (
    Confidence,
    EdgeInfo,
    EdgeKind,
    NodeInfo,
    NodeKind,
)

logger = structlog.get_logger(__name__)


class CodeParser:
    """Parses code files into structural nodes and edges using tree-sitter."""

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".rb": "ruby",
        ".kt": "kotlin",
        ".cs": "csharp",
        ".php": "php",
        ".swift": "swift",
        ".scala": "scala",
        ".sh": "bash",
        ".bash": "bash",
    }

    def __init__(self) -> None:
        """Initialize the CodeParser with multi-language support."""
        self._parsers = {}

    def _get_parser(self, language: str):
        if language not in self._parsers:
            try:
                from tree_sitter_language_pack import get_parser
            except ImportError as exc:
                raise RuntimeError(
                    "tree-sitter-language-pack is required for AST indexing"
                ) from exc
            self._parsers[language] = get_parser(language)
        return self._parsers[language]

    def _detect_language(self, path: Path) -> str | None:
        """Detect the language of a file based on its extension or shebang."""
        ext = path.suffix.lower()
        if ext in self.SUPPORTED_EXTENSIONS:
            return self.SUPPORTED_EXTENSIONS[ext]

        try:
            with open(path, "rb") as f:
                first_line = f.readline().decode("utf-8", errors="ignore")
                if first_line.startswith("#!"):
                    if "python" in first_line:
                        return "python"
                    if "node" in first_line:
                        return "javascript"
                    if "bash" in first_line or "sh" in first_line:
                        return "bash"
                    if "ruby" in first_line:
                        return "ruby"
        except IOError:
            pass

        return None

    def parse_file(
        self, path: str | Path, repo_root: str | Path | None = None
    ) -> Tuple[List[NodeInfo], List[EdgeInfo]]:
        """Parse a source file and extract structural nodes and edges.

        Args:
            path: The path to the file to parse.

        Returns:
            A tuple containing a list of NodeInfo and a list of EdgeInfo.
        """
        path = Path(path)
        nodes: List[NodeInfo] = []
        edges: List[EdgeInfo] = []

        language = self._detect_language(path)
        if not language:
            logger.debug("Unsupported language", path=str(path))
            return nodes, edges

        try:
            source = path.read_bytes()
            tree = self._get_parser(language).parse(source)
            root = Path(repo_root).resolve() if repo_root else None
            try:
                relative_path = path.resolve().relative_to(root).as_posix() if root else path.as_posix()
            except ValueError:
                relative_path = path.as_posix()

            definitions = {
                "class_definition": NodeKind.CLASS,
                "class_declaration": NodeKind.CLASS,
                "function_definition": NodeKind.FUNCTION,
                "function_declaration": NodeKind.FUNCTION,
                "method_definition": NodeKind.METHOD,
                "method_declaration": NodeKind.METHOD,
                "interface_declaration": NodeKind.TYPE,
                "type_alias_declaration": NodeKind.TYPE,
                "struct_item": NodeKind.TYPE,
                "struct_specifier": NodeKind.TYPE,
                "enum_declaration": NodeKind.TYPE,
                "enum_item": NodeKind.TYPE,
            }

            def text(node) -> str:
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

            def symbol_name(node) -> str:
                name_node = node.child_by_field_name("name")
                if name_node:
                    return text(name_node)
                for child in node.named_children:
                    if child.type in {"identifier", "type_identifier", "property_identifier"}:
                        return text(child)
                return f"<anonymous:{node.start_point[0] + 1}>"

            def stable_id(qualified_name: str, kind: NodeKind) -> str:
                identity = f"{relative_path}:{qualified_name}:{kind.value}".encode("utf-8")
                return hashlib.sha256(identity).hexdigest()[:24]

            def visit(
                node,
                parent_name: str | None = None,
                parent_qualified: str | None = None,
                parent_id: str | None = None,
            ) -> None:
                current_name = parent_name
                current_qualified = parent_qualified
                current_id = parent_id
                kind = definitions.get(node.type)
                if kind:
                    name = symbol_name(node)
                    if kind == NodeKind.FUNCTION and parent_name:
                        kind = NodeKind.METHOD
                    qualified_name = f"{parent_qualified}.{name}" if parent_qualified else name
                    node_id = stable_id(qualified_name, kind)
                    body = text(node)
                    nodes.append(
                        NodeInfo(
                            kind=kind,
                            name=name,
                            file_path=relative_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            language=language,
                            parent_name=parent_name,
                            params=[],
                            return_type=None,
                            modifiers=[],
                            is_test=("test" in name.lower() or "test" in path.parts),
                            content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                            id=node_id,
                            qualified_name=qualified_name,
                        )
                    )
                    if parent_id:
                        edges.append(
                            EdgeInfo(
                                kind=EdgeKind.CONTAINS,
                                source=parent_id,
                                target=node_id,
                                file_path=relative_path,
                                line=node.start_point[0] + 1,
                                confidence=Confidence.EXTRACTED,
                            )
                        )
                    current_name = name
                    current_qualified = qualified_name
                    current_id = node_id

                if node.type in {
                    "import_statement", "import_from_statement", "import_declaration",
                    "use_declaration", "use_declaration_item",
                }:
                    edges.append(
                        EdgeInfo(
                            kind=EdgeKind.IMPORTS_FROM,
                            source=parent_id or f"file:{relative_path}",
                            target=" ".join(text(node).split())[:300],
                            file_path=relative_path,
                            line=node.start_point[0] + 1,
                            confidence=Confidence.EXTRACTED,
                        )
                    )

                if node.type in {"call", "call_expression", "invocation_expression"}:
                    function = node.child_by_field_name("function")
                    if function is None:
                        function = node.child_by_field_name("name")
                    if function is not None:
                        edges.append(
                            EdgeInfo(
                            kind=EdgeKind.CALLS,
                                source=parent_id or f"file:{relative_path}",
                                target=text(function)[:300],
                                file_path=relative_path,
                                line=node.start_point[0] + 1,
                                confidence=Confidence.EXTRACTED,
                            )
                        )

                for child in node.named_children:
                    visit(child, current_name, current_qualified, current_id)

            visit(tree.root_node)
        except Exception as e:
            logger.error("Failed to parse file", path=str(path), error=str(e))
            raise

        return nodes, edges
