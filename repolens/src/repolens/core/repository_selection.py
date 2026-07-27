"""Shared repository selection logic for MCP and HTTP surfaces."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from repolens.core.paths import (
    repolens_current_index_path,
    repolens_package_root,
    repolens_project_root,
)

_STATUS_PRIORITY = {
    "indexed": 0,
    "indexing": 1,
    "registered": 2,
}


def _repo_path(repo: dict[str, Any]) -> Path:
    return Path(repo["local_path"]).expanduser().resolve()


def _contains(outer: Path, inner: Path) -> bool:
    try:
        inner.relative_to(outer)
        return True
    except ValueError:
        return False


def _score_repo(repo: dict[str, Any], cwd: Path, *, prefer_active_index: bool = True) -> tuple:
    repo_path = _repo_path(repo)
    active_index = repolens_current_index_path(repo_path) is not None
    workspace_match = _contains(repo_path, cwd)
    install_root = repolens_project_root().resolve()
    package_root = repolens_package_root().resolve()
    install_match = repo_path in {install_root, package_root}
    status = str(repo.get("status") or "")
    return (
        0 if prefer_active_index and active_index else 1,
        0 if workspace_match else 1,
        -len(repo_path.parts) if workspace_match else 0,
        0 if install_match else 1,
        _STATUS_PRIORITY.get(status, 3),
        -(repo.get("last_indexed") or 0),
        -(repo.get("updated_at") or 0),
        -(repo.get("created_at") or 0),
        repo_path.as_posix().lower(),
    )


def select_repository(
    registry,
    repo_id: str | None = None,
    *,
    cwd: str | Path | None = None,
    session_id: str | None = None,
    require_indexed: bool = True,
) -> dict[str, Any] | None:
    """Return the best repository candidate for the current call."""
    def _best(candidates: list[dict[str, Any]], workspace: Path) -> dict[str, Any] | None:
        if not candidates:
            return None
        return sorted(candidates, key=lambda repo: _score_repo(repo, workspace))[0]

    def _indexed(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            repo for repo in candidates
            if repolens_current_index_path(repo["local_path"]) is not None
        ]

    if repo_id:
        repo = registry.get_repo(repo_id)
        if repo is None:
            raise ValueError(f"Unknown repository: {repo_id}")
        if require_indexed and repolens_current_index_path(repo["local_path"]) is None:
            raise ValueError(f"Repository is not indexed: {repo['local_path']}")
        return repo

    workspace = Path(cwd or Path.cwd()).expanduser().resolve()
    repos = list(registry.list_repos())
    if not repos:
        return None

    if session_id:
        session = registry.get_mcp_session(session_id)
        if session and session.get("repo_id"):
            session_repo = registry.get_repo(session["repo_id"])
            if session_repo:
                if require_indexed and repolens_current_index_path(session_repo["local_path"]) is None:
                    raise ValueError(f"Repository is not indexed: {session_repo['local_path']}")
                return session_repo

    env_repo_id = os.environ.get("REPOLENS_DEFAULT_REPO_ID")
    if env_repo_id:
        repo = registry.get_repo(env_repo_id)
        if repo is not None:
            if require_indexed and repolens_current_index_path(repo["local_path"]) is None:
                raise ValueError(f"Repository is not indexed: {repo['local_path']}")
            return repo

    env_workspace = os.environ.get("REPOLENS_WORKSPACE") or os.environ.get("REPOLENS_REPO_PATH")
    if env_workspace:
        env_path = Path(env_workspace).expanduser().resolve()
        env_matches = [repo for repo in repos if _contains(_repo_path(repo), env_path)]
        if env_matches:
            if require_indexed:
                indexed = _indexed(env_matches)
                if not indexed:
                    raise ValueError(
                        f"Repository at '{env_path}' is not indexed; index it first or switch to another repository"
                    )
                return _best(indexed, env_path)
            return _best(env_matches, env_path)

    cwd_matches = [repo for repo in repos if _contains(_repo_path(repo), workspace)]
    if cwd_matches:
        if require_indexed:
            indexed = _indexed(cwd_matches)
            if not indexed:
                raise ValueError(
                    f"Repository at '{workspace}' is not indexed; index it first or switch to another repository"
                )
            return _best(indexed, workspace)
        return _best(cwd_matches, workspace)

    install_roots = {
        repolens_project_root().resolve(),
        repolens_package_root().resolve(),
    }
    install_matches = [repo for repo in repos if _repo_path(repo) in install_roots]
    if install_matches:
        if require_indexed:
            indexed = _indexed(install_matches)
            if not indexed:
                raise ValueError(
                    "RepoLens install directory is not indexed; index it first or switch to another repository"
                )
            return _best(indexed, workspace)
        return _best(install_matches, workspace)

    if require_indexed:
        indexed = _indexed(repos)
        if indexed:
            return _best(indexed, workspace)
    else:
        if len(repos) == 1:
            return repos[0]

    return None


def select_repository_by_path(
    registry,
    *,
    repo_id: str | None = None,
    cwd: str | Path | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the best repository for recording activity."""
    workspace = Path(cwd or Path.cwd()).expanduser().resolve()
    if repo_id:
        return registry.get_repo(repo_id)

    if session_id:
        session = registry.get_mcp_session(session_id)
        if session and session.get("repo_id"):
            session_repo = registry.get_repo(session["repo_id"])
            if session_repo is not None:
                return session_repo

    repos = list(registry.list_repos())
    if not repos:
        return None

    cwd_matches = [repo for repo in repos if _contains(_repo_path(repo), workspace)]
    if cwd_matches:
        return sorted(cwd_matches, key=lambda repo: _score_repo(repo, workspace))[0]

    return select_repository(registry, cwd=workspace, require_indexed=False)
