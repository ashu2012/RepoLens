"""Index-backed repository search API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from repolens.core.repository_selection import select_repository
from repolens.core.persistence import registry
from repolens.core.search.repository import RepositorySearch

router = APIRouter()


class SearchQuery(BaseModel):
    query: str = Field(min_length=1)
    repo_id: str | None = None
    mode: str = "hybrid"
    top_k: int = Field(10, ge=1, le=100)


def select_repo(repo_id: str | None) -> dict:
    try:
        repo = select_repository(registry, repo_id=repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if repo is None:
        raise HTTPException(
            status_code=400,
            detail="No indexed repository is available; register or index a repository first",
        )
    return repo


@router.post("")
async def search(query: SearchQuery):
    repo = select_repo(query.repo_id)
    try:
        results = await RepositorySearch(repo["local_path"]).search(
            query.query, mode=query.mode, top_k=query.top_k
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "repo_id": repo["id"],
        "query": query.query,
        "mode": query.mode,
        "count": len(results),
        "results": results,
    }


@router.get("")
async def search_get(
    query: str,
    repo_id: str | None = None,
    mode: str = "hybrid",
    top_k: int = 10,
):
    """Browser-friendly search using URL query parameters."""
    return await search(
        SearchQuery(query=query, repo_id=repo_id, mode=mode, top_k=top_k)
    )


@router.get("/symbols")
async def search_symbols(
    name: str,
    repo_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
):
    repo = select_repo(repo_id)
    try:
        results = RepositorySearch(repo["local_path"]).symbols(name, kind, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"repo_id": repo["id"], "count": len(results), "results": results}
