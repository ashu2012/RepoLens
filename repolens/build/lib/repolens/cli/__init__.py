"""RepoLens command-line interface."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


@click.group()
@click.version_option(package_name="repolens")
def cli() -> None:
    """RepoLens local code intelligence platform."""


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--name", "-n")
@click.option("--wizard", is_flag=True, help="Interactively customize the user runtime")
@click.option("--runtime-dir", type=click.Path(file_okay=False))
@click.option("--no-auto-start", is_flag=True)
@click.option("--force", is_flag=True, help="Regenerate runtime configuration")
def init(path: str | None, name: str | None, wizard: bool, runtime_dir: str | None,
         no_auto_start: bool, force: bool) -> None:
    """Initialize the user runtime, and optionally a repository."""
    from repolens.runtime.bootstrap import BootstrapOptions, RepoLensBootstrap, RuntimeLocator

    selected = Path(runtime_dir).expanduser() if runtime_dir else RuntimeLocator.default_runtime()
    auto_start, cache_size, cpu, telemetry = not no_auto_start, 5, "high", False
    if wizard:
        console.print(Panel.fit("RepoLens runs a local background daemon and dashboard.",
                                title="Welcome to RepoLens"))
        if not click.confirm(f"Use recommended runtime directory?\n{selected}", default=True):
            selected = Path(click.prompt("Runtime directory", type=click.Path(file_okay=False)))
        auto_start = click.confirm("Start RepoLens when you log in?", default=True)
        cache_size = click.prompt("Maximum cache size (GB, 0 for unlimited)", default=5, type=int)
        cpu = click.prompt("CPU profile", default="high",
                           type=click.Choice(["low", "medium", "high"]))
        telemetry = click.confirm("Enable anonymous crash reports?", default=False)
    runtime = RepoLensBootstrap(selected).initialize(
        BootstrapOptions(selected, auto_start, cache_size or None, cpu, telemetry), force=force
    )
    console.print(f"[green]OK[/] RepoLens runtime initialized: {runtime}")
    if path:
        repository = Path(path).resolve()
        (repository / ".repolens").mkdir(exist_ok=True)
        console.print(f"[green]OK[/] Repository initialized: {name or repository.name}")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n")
def add(path: str, name: str | None) -> None:
    """Register a local repository."""
    from repolens.core.persistence.registry import registry

    repository = Path(path).resolve()
    existing = registry.find_repo_by_path(str(repository))
    result = existing or registry.add_repo({
        "id": uuid.uuid4().hex[:12],
        "name": name or repository.name,
        "local_path": str(repository),
        "status": "registered",
        "files_count": 0,
        "is_git": (repository / ".git").exists(),
    })
    console.print_json(json.dumps(result, default=str))


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--full", is_flag=True)
def index(path: str | None, full: bool) -> None:
    """Index a repository and wait for the durable job."""
    from repolens.core.pipeline.service import indexing_service

    result = indexing_service.index_directory(Path(path or ".").resolve(),
                                                mode="full" if full else "auto")
    console.print(f"Job {result['job_id']} started")
    console.print_json(json.dumps(indexing_service.wait(result["job_id"]), default=str))


@cli.command()
@click.argument("query")
@click.option("--top-k", "-k", default=10, type=int)
def search(query: str, top_k: int) -> None:
    """Search the first registered repository."""
    from repolens.core.persistence.registry import registry
    from repolens.core.search.repository import RepositorySearch

    repositories = registry.list_repos()
    if not repositories:
        raise click.ClickException("No repositories registered; run repolens add PATH")
    results = asyncio.run(
        RepositorySearch(repositories[0]["local_path"]).search(query, top_k=top_k)
    )
    console.print_json(json.dumps(results, default=str))


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", "-p", default=38451, type=int)
def serve(host: str, port: int) -> None:
    """Run the HTTP API and dashboard in the foreground."""
    import uvicorn
    console.print(f"Dashboard: http://{host}:{port}/dashboard")
    uvicorn.run("repolens.server.app:create_app", host=host, port=port, factory=True)


@cli.command()
def mcp() -> None:
    """Run the MCP stdio server."""
    from repolens.server.mcp.server import run_stdio
    asyncio.run(run_stdio())


@cli.command()
@click.option("--runtime-dir", type=click.Path(file_okay=False))
@click.option("--foreground", is_flag=True)
def daemon(runtime_dir: str | None, foreground: bool) -> None:
    """Start the single-instance daemon."""
    from repolens.runtime.bootstrap import RepoLensBootstrap
    from repolens.runtime.daemon import run_daemon
    from repolens.runtime.ipc import IPCClient

    runtime = RepoLensBootstrap(runtime_dir).initialize()
    if IPCClient(runtime).ping():
        console.print("[green]RepoLens daemon is already running.[/]")
        return
    if foreground:
        raise SystemExit(run_daemon(runtime))
    subprocess.Popen(
        [sys.executable, "-m", "repolens", "daemon", "--foreground", "--runtime-dir", str(runtime)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        start_new_session=os.name != "nt",
    )
    for _ in range(40):
        if IPCClient(runtime, timeout_ms=250).ping():
            console.print("[green]OK[/] RepoLens daemon started.")
            return
        time.sleep(0.1)
    raise click.ClickException("Daemon did not become ready; inspect logs/daemon.log")


@cli.command()
@click.option("--no-open", is_flag=True)
def dashboard(no_open: bool) -> None:
    """Open the local dashboard."""
    url = "http://127.0.0.1:38451/dashboard"
    console.print(url)
    if not no_open:
        webbrowser.open(url)


@cli.command("mcp-config")
@click.argument("client", type=click.Choice(
    ["claude", "codex", "cursor", "vscode", "continue", "gemini", "windsurf"]))
@click.option("--install-path", type=click.Path())
@click.option("--runtime-dir", type=click.Path(file_okay=False))
def mcp_config(client: str, install_path: str | None, runtime_dir: str | None) -> None:
    """Print MCP configuration without modifying client files."""
    from repolens.server.installer import generate_mcp_config
    console.print_json(json.dumps(generate_mcp_config(client, install_path, runtime_dir)))


@cli.command()
@click.option("--runtime-dir", type=click.Path(file_okay=False))
def status(runtime_dir: str | None) -> None:
    """Show runtime and daemon status."""
    from repolens.runtime.bootstrap import InstallationDetector, RuntimeLocator
    from repolens.runtime.ipc import IPCClient

    runtime = Path(runtime_dir) if runtime_dir else RuntimeLocator.default_runtime()
    state = InstallationDetector(runtime).installation_state()
    state.update(path=str(runtime), daemon=IPCClient(runtime).ping() if runtime.exists() else False)
    console.print_json(json.dumps(state))


@cli.command()
@click.option("--runtime-dir", type=click.Path(file_okay=False))
def diagnostics(runtime_dir: str | None) -> None:
    """Run installation and dependency diagnostics."""
    from repolens.runtime.bootstrap import InstallationDetector, RuntimeLocator
    from repolens.runtime.ipc import IPCClient
    from repolens.server.installer import run_diagnostics

    runtime = Path(runtime_dir) if runtime_dir else RuntimeLocator.default_runtime()
    result = run_diagnostics()
    result["runtime"] = {
        "path": str(runtime), **InstallationDetector(runtime).installation_state(),
        "daemon": IPCClient(runtime).ping() if runtime.exists() else False,
    }
    console.print_json(json.dumps(result, default=str))


@cli.command()
@click.option("--runtime-dir", type=click.Path(file_okay=False))
@click.option("--preserve-repositories", is_flag=True)
@click.option("--yes", is_flag=True)
def reset(runtime_dir: str | None, preserve_repositories: bool, yes: bool) -> None:
    """Remove runtime state after confirmation."""
    from repolens.runtime.bootstrap import RuntimeLocator

    runtime = (Path(runtime_dir) if runtime_dir else RuntimeLocator.default_runtime()).resolve()
    if not runtime.exists():
        console.print("RepoLens is not initialized.")
        return
    if not yes and not click.confirm(f"Delete RepoLens runtime at {runtime}?"):
        return
    preserved = Path(str(runtime) + ".repositories-preserved")
    if preserve_repositories and (runtime / "repositories").exists():
        if preserved.exists():
            raise click.ClickException(f"Preservation target exists: {preserved}")
        shutil.move(runtime / "repositories", preserved)
    shutil.rmtree(runtime)
    if preserved.exists():
        runtime.mkdir(parents=True)
        shutil.move(preserved, runtime / "repositories")
    console.print(f"[green]OK[/] Removed RepoLens runtime: {runtime}")


if __name__ == "__main__":
    cli()
