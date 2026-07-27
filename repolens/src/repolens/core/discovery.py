"""Filesystem discovery helpers for indexable source files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".repolens",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".cache",
        "build",
        "dist",
        "out",
        "target",
        "node_modules",
        "site-packages",
        "dist-packages",
        "pip-wheel-metadata",
    }
)

DEFAULT_IGNORED_PREFIXES = (".venv", "venv", "env")


def is_ignored_directory(name: str, extra_ignored: Iterable[str] = ()) -> bool:
    """Return ``True`` when a directory name should be skipped during scans."""
    lowered = name.lower()
    ignored = {item.lower() for item in extra_ignored}
    return (
        lowered in DEFAULT_IGNORED_DIRS
        or lowered in ignored
        or any(lowered.startswith(prefix) for prefix in DEFAULT_IGNORED_PREFIXES)
    )


def iter_indexable_files(
    root: str | Path,
    supported_extensions: Iterable[str],
    *,
    extra_ignored_dirs: Iterable[str] = (),
) -> Iterator[Path]:
    """Yield indexable files while pruning build and virtual-environment trees."""
    root_path = Path(root).expanduser().resolve()
    if is_ignored_directory(root_path.name, extra_ignored_dirs):
        return

    supported = {extension.lower() for extension in supported_extensions}
    ignored = {item.lower() for item in extra_ignored_dirs}
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [name for name in dirnames if not is_ignored_directory(name, ignored)]
        current = Path(dirpath)
        for filename in filenames:
            candidate = current / filename
            if candidate.suffix.lower() in supported:
                yield candidate


def count_indexable_files(
    root: str | Path,
    supported_extensions: Iterable[str],
    *,
    extra_ignored_dirs: Iterable[str] = (),
) -> int:
    """Count indexable files without descending into ignored directories."""
    return sum(1 for _ in iter_indexable_files(root, supported_extensions, extra_ignored_dirs=extra_ignored_dirs))
