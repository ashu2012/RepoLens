"""Filesystem MCP tools for local agent workflows."""

from __future__ import annotations

import fnmatch
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .server import mcp


def _root() -> Path:
    return Path.cwd().resolve()


def _safe_resolve(path: str) -> Path:
    root = _root()
    candidate = (root / path).expanduser().resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path '{path}' resolves outside the allowed workspace root.")
    return candidate


def _rel(path: Path) -> str:
    root = _root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _platform_label() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macOS"
    if system == "windows":
        return "Windows"
    return system or "unknown"


@mcp.tool()
async def list_directory(path: str = ".") -> str:
    target = _safe_resolve(path)
    if not target.exists():
        return f"Error: '{path}' does not exist."
    if not target.is_dir():
        return f"Error: '{path}' is not a directory."

    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    if not entries:
        return f"'{path}' is empty."

    lines = []
    for entry in entries:
        kind = "DIR " if entry.is_dir() else "FILE"
        size = "" if entry.is_dir() else f" ({entry.stat().st_size} bytes)"
        lines.append(f"[{kind}] {entry.name}{size}")
    return "\n".join(lines)


@mcp.tool()
async def read_file(path: str) -> str:
    target = _safe_resolve(path)
    if not target.exists():
        return f"Error: '{path}' does not exist."
    if not target.is_file():
        return f"Error: '{path}' is not a file."
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' does not appear to be a text file (binary content)."


@mcp.tool()
async def write_file(path: str, content: str, mode: str = "overwrite") -> str:
    if mode not in ("overwrite", "append"):
        return "Error: mode must be 'overwrite' or 'append'."
    target = _safe_resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    file_mode = "a" if mode == "append" else "w"
    with open(target, file_mode, encoding="utf-8") as handle:
        handle.write(content)
    action = "Appended to" if mode == "append" else "Wrote"
    return f"{action} '{_rel(target)}' ({len(content)} characters)."


@mcp.tool()
async def create_directory(path: str) -> str:
    target = _safe_resolve(path)
    if target.exists():
        return f"'{path}' already exists."
    target.mkdir(parents=True, exist_ok=True)
    return f"Created directory '{_rel(target)}'."


@mcp.tool()
async def delete_file(path: str) -> str:
    target = _safe_resolve(path)
    if not target.exists():
        return f"Error: '{path}' does not exist."
    if target.is_dir():
        return f"Error: '{path}' is a directory. Use delete_directory instead."
    target.unlink()
    return f"Deleted file '{_rel(target)}'."


@mcp.tool()
async def delete_directory(path: str, recursive: bool = False) -> str:
    target = _safe_resolve(path)
    if target == _root():
        return "Error: refusing to delete the workspace root directory."
    if not target.exists():
        return f"Error: '{path}' does not exist."
    if not target.is_dir():
        return f"Error: '{path}' is not a directory."
    if recursive:
        shutil.rmtree(target)
        return f"Deleted directory '{_rel(target)}' and all its contents."
    try:
        target.rmdir()
        return f"Deleted empty directory '{_rel(target)}'."
    except OSError:
        return f"Error: '{path}' is not empty. Pass recursive=True to delete it anyway."


@mcp.tool()
async def move_path(source: str, destination: str) -> str:
    src = _safe_resolve(source)
    dst = _safe_resolve(destination)
    if not src.exists():
        return f"Error: '{source}' does not exist."
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved '{_rel(src)}' to '{_rel(dst)}'."


@mcp.tool()
async def get_file_info(path: str) -> str:
    target = _safe_resolve(path)
    if not target.exists():
        return f"Error: '{path}' does not exist."
    stat = target.stat()
    kind = "directory" if target.is_dir() else "file"
    modified = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    created = datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds")
    lines = [
        f"Path: {_rel(target)}",
        f"Type: {kind}",
        f"Modified: {modified}",
        f"Created: {created}",
    ]
    if target.is_file():
        lines.append(f"Size: {stat.st_size} bytes")
    return "\n".join(lines)


@mcp.tool()
async def search_files(pattern: str, path: str = ".") -> str:
    start = _safe_resolve(path)
    if not start.exists() or not start.is_dir():
        return f"Error: '{path}' is not a valid directory."

    matches: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(start):
        for name in filenames:
            if fnmatch.fnmatch(name, pattern):
                matches.append(_rel(Path(dirpath) / name))

    if not matches:
        return f"No files matching '{pattern}' found under '{path}'."
    return "\n".join(sorted(matches))


@mcp.tool()
async def create_venv(path: str, python_executable: str = "") -> str:
    target = _safe_resolve(path)
    if target.exists() and any(target.iterdir()):
        return f"Error: '{path}' already exists and is not empty."
    target.parent.mkdir(parents=True, exist_ok=True)

    interpreter = python_executable or sys.executable
    try:
        result = subprocess.run(
            [interpreter, "-m", "venv", str(target)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        return f"Error: python executable '{interpreter}' not found."
    except subprocess.TimeoutExpired:
        return "Error: venv creation timed out after 180s."

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return f"Error creating venv (exit code {result.returncode}):\n{stderr}"

    label = _platform_label()
    if label == "Windows":
        activate_ps1 = f"{_rel(target)}\\Scripts\\Activate.ps1"
        activate_cmd = f"{_rel(target)}\\Scripts\\activate.bat"
        activate_bash = f"source {_rel(target)}/Scripts/activate"
    else:
        activate_ps1 = f"source {_rel(target)}/bin/activate"
        activate_cmd = f"source {_rel(target)}/bin/activate"
        activate_bash = f"source {_rel(target)}/bin/activate"

    return (
        f"Created virtual environment at '{_rel(target)}' using '{interpreter}'.\n"
        f"Platform: {label}\n"
        f"Activate it with:\n"
        f"  PowerShell: {activate_ps1}\n"
        f"  cmd/bash:   {activate_cmd}\n"
        f"  shell:      {activate_bash}"
    )
