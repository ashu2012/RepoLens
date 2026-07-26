"""Index-backed repository search API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from repolens.core.persistence import registry
from repolens.core.search.repository import RepositorySearch

router = APIRouter()


class SearchQuery(BaseModel):
    query: str = Field(min_length=1)
    repo_id: str | None = None
    mode: str = "hybrid"
    top_k: int = Field(10, ge=1, le=100)


def select_repo(repo_id: str | None) -> dict:
    if repo_id:
        repo = registry.get_repo(repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
        return repo
    indexed = [repo for repo in registry.list_repos() if repo["status"] == "indexed"]
    if len(indexed) != 1:
        raise HTTPException(
            status_code=400,
            detail="repo_id is required unless exactly one indexed repository is registered",
        )
    return indexed[0]


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
async def search_symbols(repo_id: str, name: str, kind: str | None = None, limit: int = 50):
    repo = select_repo(repo_id)
    try:
        results = RepositorySearch(repo["local_path"]).symbols(name, kind, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"repo_id": repo_id, "count": len(results), "results": results}
