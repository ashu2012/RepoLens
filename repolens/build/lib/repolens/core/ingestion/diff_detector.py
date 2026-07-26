"""Detects file changes and expands the blast radius of those changes."""

import hashlib
import subprocess
from pathlib import Path
from typing import Any, List, Optional

import structlog

from repolens.core.ingestion.models import ChangeType, FileChange

logger = structlog.get_logger(__name__)


class DiffDetector:
    """Detects changes in a git repository."""

    def __init__(self) -> None:
        pass

    def _run_git_command(self, cmd: List[str], repo_path: str) -> str:
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error("Git command timed out", cmd=" ".join(cmd))
            return ""
        except subprocess.CalledProcessError as e:
            logger.error("Git command failed", cmd=" ".join(cmd), error=e.stderr)
            return ""

    def _hash_file(self, path: Path) -> Optional[str]:
        if not path.is_file():
            return None
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    def detect_changes(self, repo_path: str | Path, last_commit: Optional[str] = None) -> List[FileChange]:
        """Detect changes in the repository.

        Uses git diff and git status to find committed and uncommitted changes.
        """
        repo_path = str(repo_path)
        changes: List[FileChange] = []
        seen_paths = set()

        if last_commit:
            # Committed changes
            diff_out = self._run_git_command(
                ["git", "diff", "--name-status", last_commit, "HEAD"], repo_path
            )
            if diff_out:
                for line in diff_out.splitlines():
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        status, path = parts
                        seen_paths.add(path)
                        ctype = ChangeType.MODIFIED
                        if status.startswith("A"):
                            ctype = ChangeType.ADDED
                        elif status.startswith("D"):
                            ctype = ChangeType.DELETED
                            
                        abs_path = Path(repo_path) / path
                        content_hash = self._hash_file(abs_path) if ctype != ChangeType.DELETED else None
                        changes.append(FileChange(path=path, change_type=ctype, content_hash=content_hash))

        # Uncommitted changes
        status_out = self._run_git_command(["git", "status", "--porcelain"], repo_path)
        if status_out:
            for line in status_out.splitlines():
                if len(line) > 3:
                    status = line[:2]
                    path = line[3:]
                    if path in seen_paths:
                        continue
                        
                    seen_paths.add(path)
                    ctype = ChangeType.MODIFIED
                    if "??" in status or "A" in status:
                        ctype = ChangeType.ADDED
                    elif "D" in status:
                        ctype = ChangeType.DELETED
                        
                    abs_path = Path(repo_path) / path
                    content_hash = self._hash_file(abs_path) if ctype != ChangeType.DELETED else None
                    
                    # Update if already in changes, else append
                    existing = next((c for c in changes if c.path == path), None)
                    if existing:
                        existing.change_type = ctype
                        existing.content_hash = content_hash
                    else:
                        changes.append(FileChange(path=path, change_type=ctype, content_hash=content_hash))

        return changes

    def expand_blast_radius(self, changes: List[FileChange], graph_store: Any, max_hops: int = 2) -> List[FileChange]:
        """Expand the blast radius of changes to include reverse dependents."""
        # Stub implementation
        return changes
