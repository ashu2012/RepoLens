"""Platform-specific auto-installer for RepoLens dependencies.

Detects the OS and installs Tree-sitter grammars, Ollama models,
and optional Python packages with minimal user intervention.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def detect_platform() -> dict:
    """Detect the current platform and available tools."""
    info = {
        "os": platform.system().lower(),
        "arch": platform.machine().lower(),
        "python": sys.version,
        "python_path": sys.executable,
    }

    # Check for Ollama
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        info["ollama"] = result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        info["ollama"] = None

    # Check for git
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        info["git"] = result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        info["git"] = None

    return info


def install_python_extras(extras: list[str]) -> bool:
    """Install optional Python package groups.

    Args:
        extras: List of extra groups to install (e.g., ['metrics', 'communities']).

    Returns:
        True if installation succeeded.
    """
    for extra in extras:
        logger.info("installing_extra", extra=extra)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", f"repolens[{extra}]"],
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            logger.error("install_failed", extra=extra, error=str(e))
            return False
    return True


def pull_ollama_model(model: str = "nomic-embed-text") -> bool:
    """Pull an embedding model from Ollama.

    Args:
        model: Model name to pull.

    Returns:
        True if pull succeeded.
    """
    logger.info("pulling_ollama_model", model=model)
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("ollama_pull_failed", model=model)
        return False


def check_ollama_model_available(model: str = "nomic-embed-text") -> bool:
    """Check if a specific Ollama model is already downloaded."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return model in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def ensure_data_directory(base_path: Path | None = None) -> Path:
    """Create the .repolens data directory if it doesn't exist."""
    if base_path is None:
        base_path = Path.cwd()
    data_dir = base_path / ".repolens"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "vectors").mkdir(exist_ok=True)
    return data_dir


def run_diagnostics() -> dict:
    """Run full system diagnostics for troubleshooting."""
    platform_info = detect_platform()

    diag = {
        "platform": platform_info,
        "checks": {},
    }

    # Check Python version
    py_ver = sys.version_info
    diag["checks"]["python_311"] = py_ver >= (3, 11)

    # Check required packages
    required = ["tree_sitter", "networkx", "sqlalchemy", "fastapi", "fastmcp", "click"]
    for pkg in required:
        try:
            __import__(pkg)
            diag["checks"][f"pkg_{pkg}"] = True
        except ImportError:
            diag["checks"][f"pkg_{pkg}"] = False

    # Check Ollama
    diag["checks"]["ollama_installed"] = platform_info.get("ollama") is not None
    if diag["checks"]["ollama_installed"]:
        diag["checks"]["ollama_model"] = check_ollama_model_available()

    # Check git
    diag["checks"]["git_installed"] = platform_info.get("git") is not None

    return diag
