"""Watcher for git repository changes."""

import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

import pathspec
import structlog
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger(__name__)


class _GitEventHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[], None], ignore_spec: pathspec.PathSpec, repo_path: Path):
        self.callback = callback
        self.ignore_spec = ignore_spec
        self.repo_path = repo_path
        self._last_trigger = 0.0
        self._debounce_seconds = 2.0

    def _should_ignore(self, event: FileSystemEvent) -> bool:
        if event.is_directory:
            return True
        
        try:
            path = Path(event.src_path)
            rel_path = str(path.relative_to(self.repo_path))
            
            if ".git" in Path(rel_path).parts:
                return True
                
            return self.ignore_spec.match_file(rel_path)
        except ValueError:
            return True

    def on_any_event(self, event: FileSystemEvent) -> None:
        if self._should_ignore(event):
            return
            
        now = time.time()
        if now - self._last_trigger >= self._debounce_seconds:
            self._last_trigger = now
            self.callback()


class GitWatcher:
    """Watches a git repository for file system changes and tracks HEAD."""

    def __init__(self) -> None:
        self._observer: Optional[Observer] = None

    def _get_ignore_spec(self, repo_path: Path) -> pathspec.PathSpec:
        ignore_lines = []
        gitignore_path = repo_path / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                ignore_lines = f.readlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", ignore_lines)

    def watch(self, repo_path: str | Path, callback: Callable[[], None]) -> None:
        """Watch the repository for file system events."""
        repo_path = Path(repo_path)
        ignore_spec = self._get_ignore_spec(repo_path)
        
        event_handler = _GitEventHandler(callback, ignore_spec, repo_path)
        self._observer = Observer()
        self._observer.schedule(event_handler, str(repo_path), recursive=True)
        self._observer.start()
        logger.info("Started watching repository", path=str(repo_path))

    def stop(self) -> None:
        """Stop watching the repository."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("Stopped watching repository")

    def poll(self, repo_path: str | Path, stored_commit: Optional[str]) -> Optional[str]:
        """Poll the repository to check if HEAD has changed."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            current_head = result.stdout.strip()
            if current_head != stored_commit:
                return current_head
            return None
        except subprocess.CalledProcessError as e:
            logger.error("Failed to parse HEAD", error=e.stderr)
            return None
