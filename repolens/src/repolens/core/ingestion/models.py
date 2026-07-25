"""Data models for the core ingestion pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class NodeKind(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    TYPE = "type"
    TEST = "test"

class EdgeKind(str, Enum):
    CALLS = "calls"
    IMPORTS_FROM = "imports_from"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CONTAINS = "contains"
    TESTED_BY = "tested_by"
    REFERENCES = "references"

class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"

class Confidence(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"

@dataclass
class NodeInfo:
    kind: NodeKind
    name: str
    file_path: str
    line_start: int
    line_end: int
    language: str
    parent_name: Optional[str]
    params: List[str]
    return_type: Optional[str]
    modifiers: List[str]
    is_test: bool
    content_hash: str
    id: str = ""
    qualified_name: str = ""

@dataclass
class EdgeInfo:
    kind: EdgeKind
    source: str
    target: str
    file_path: str
    line: int
    confidence: Confidence
    raw_target: Optional[str] = None

@dataclass
class ChunkInfo:
    id: str
    content: str
    file_path: str
    symbol_name: str
    symbol_kind: str
    line_start: int
    line_end: int
    language: str
    metadata: Dict[str, Any]

@dataclass
class FileChange:
    path: str
    change_type: ChangeType
    content_hash: Optional[str]
