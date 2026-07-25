"""Git-aware MCP change tools."""

import json
import subprocess
from pathlib import Path
from typing import Optional

from repolens.core.ingestion.diff_detector import DiffDetector

from .server import mcp, state


@mcp.tool()
async def recent_changes(since: Optional[str] = None, repo_id: str | None = None) -> str:
    repo = state.repository(repo_id)
    command = ["git", "diff", "--stat", since] if since else ["git", "status", "--short"]
    try:
        result = subprocess.run(
            command,
            cwd=repo["local_path"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout or "No changes."
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Git change inspection failed: {exc}"


@mcp.tool()
async def detect_changes(repo_id: str | None = None) -> str:
    repo = state.repository(repo_id)
    changes = DiffDetector().detect_changes(repo["local_path"])
    return json.dumps(
        [
            {
                "path": change.path,
                "change_type": change.change_type.value,
                "content_hash": change.content_hash,
            }
            for change in changes
        ],
        indent=2,
    )
