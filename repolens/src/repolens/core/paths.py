"""Repository path helpers for safe default behavior."""

from __future__ import annotations

from pathlib import Path


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
