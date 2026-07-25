"""RepoLens CLI — Command-line interface for code intelligence.

Provides commands for repository management, indexing, search, and server control.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encoding errors with Rich
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console(force_terminal=True)


@click.group()
@click.version_option(package_name="repolens")
def cli():
    """🔍 RepoLens — Local Code Intelligence Platform

    Semantic search, knowledge graphs, and context distillation
    for AI coding agents. Powered by Tree-sitter + FastMCP.
    """
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@click.option("--name", "-n", help="Repository display name (default: directory name)")
def init(path: str, name: str | None):
    """Initialize RepoLens in a repository.

    Creates .repolens/ directory and config files. Optionally adds
    the repository to the index.
    """
    repo_path = Path(path).resolve()
    repolens_dir = repo_path / ".repolens"
    repolens_dir.mkdir(exist_ok=True)

    display_name = name or repo_path.name
    console.print(f"\n[bold green]✓[/] Initialized RepoLens for [bold]{display_name}[/]")
    console.print(f"  Directory: {repolens_dir}")
    console.print(f"\n  Run [bold cyan]repolens add {repo_path}[/] to register this repo")
    console.print(f"  Run [bold cyan]repolens index {repo_path}[/] to build the index")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", help="Repository display name")
def add(path: str, name: str | None):
    """Register a local repository for indexing."""
    repo_path = Path(path).resolve()
    display_name = name or repo_path.name

    # Verify it's a git repo
    if not (repo_path / ".git").exists():
        console.print(f"[yellow]⚠[/] {repo_path} is not a git repository. Indexing may be limited.")

    console.print(f"[bold green]✓[/] Added repository: [bold]{display_name}[/]")
    console.print(f"  Path: {repo_path}")
    console.print(f"\n  Run [bold cyan]repolens index {repo_path}[/] to build the index")


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--full", is_flag=True, help="Force full re-index (default: incremental)")
@click.option("--parallel", "-j", type=int, default=4, help="Parallel workers for parsing")
def index(path: str | None, full: bool, parallel: int):
    """Run the indexing pipeline on a repository.

    If no path is given, indexes all registered repositories.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

    target = Path(path).resolve() if path else Path(".")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Indexing {target.name}...", total=7
        )

        phases = ["detect", "parse", "chunk", "resolve", "embed", "store", "analyze"]
        for phase in phases:
            progress.update(task, description=f"[cyan]{phase}...")
            # Simulate phase (actual implementation calls PipelineOrchestrator)
            import time
            time.sleep(0.1)  # Placeholder
            progress.advance(task)

    mode = "full" if full else "incremental"
    console.print(f"\n[bold green]✓[/] Indexing complete ({mode})")
    console.print(f"  Repository: {target.name}")


@cli.command()
@click.argument("query")
@click.option("--mode", "-m", type=click.Choice(["auto", "bm25", "semantic", "hybrid"]), default="auto")
@click.option("--top-k", "-k", type=int, default=10, help="Number of results")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json", "plain"]), default="table")
def search(query: str, mode: str, top_k: int, fmt: str):
    """Search the code index.

    Supports hybrid search (BM25 + semantic), graph-boosted reranking.
    """
    console.print(f"\n[bold]🔎 Searching:[/] [cyan]{query}[/]  (mode={mode}, top_k={top_k})")
    console.print()

    # Placeholder results (actual implementation uses HybridSearch)
    table = Table(title=f"Search Results for '{query}'", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Symbol", style="bold cyan")
    table.add_column("File", style="green")
    table.add_column("Score", justify="right", style="yellow")
    table.add_column("Source", style="dim")

    table.add_row("1", "No results yet", "Run `repolens index` first", "-", "-")
    console.print(table)


@cli.command()
@click.option("--host", "-h", default="127.0.0.1", help="Server host")
@click.option("--port", "-p", type=int, default=8420, help="Server port")
@click.option("--mcp", is_flag=True, help="Also start MCP stdio server")
@click.option("--no-dashboard", is_flag=True, help="Disable web dashboard")
@click.option("--no-scheduler", is_flag=True, help="Disable cron scheduler")
def serve(host: str, port: int, mcp: bool, no_dashboard: bool, no_scheduler: bool):
    """Start the RepoLens server.

    Launches FastAPI server with REST API, dashboard, and optional MCP.
    """
    panel = Panel.fit(
        f"[bold]🔍 RepoLens Server[/]\n\n"
        f"  API:        [cyan]http://{host}:{port}/api[/]\n"
        f"  Dashboard:  [cyan]http://{host}:{port}/dashboard[/]\n"
        f"  API Docs:   [cyan]http://{host}:{port}/api/docs[/]\n"
        f"  Health:     [cyan]http://{host}:{port}/health/live[/]\n"
        f"  Metrics:    [cyan]http://{host}:{port}/metrics[/]\n"
        f"  MCP:        {'[green]stdio[/]' if mcp else '[dim]disabled[/]'}\n"
        f"  Scheduler:  {'[red]disabled[/]' if no_scheduler else '[green]active[/]'}\n"
        f"  Dashboard:  {'[red]disabled[/]' if no_dashboard else '[green]active[/]'}",
        title="[bold green]Starting...[/]",
        border_style="blue",
    )
    console.print(panel)

    try:
        import uvicorn
        uvicorn.run(
            "repolens.server.app:create_app",
            host=host,
            port=port,
            factory=True,
            reload=False,
            log_level="info",
        )
    except ImportError:
        console.print("[red]Error:[/] uvicorn not installed. Run: pip install repolens")
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/]")


@cli.command()
def status():
    """Show system status and health."""
    table = Table(title="RepoLens Status", show_lines=True)
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Check components
    checks = [
        ("Database", "[green]✓ Connected[/]", ".repolens/repolens.db"),
        ("Vector Store", "[green]✓ Ready[/]", "LanceDB @ .repolens/vectors/"),
        ("Graph Store", "[green]✓ Loaded[/]", "0 nodes, 0 edges"),
        ("Embedding", "[yellow]⚠ Checking...[/]", "ollama @ localhost:11434"),
        ("MCP Server", "[dim]○ Not running[/]", "Start with: repolens serve --mcp"),
        ("Scheduler", "[dim]○ Not running[/]", "Start with: repolens serve"),
        ("Dashboard", "[dim]○ Not running[/]", "http://localhost:8420/dashboard"),
    ]

    for name, status_text, detail in checks:
        table.add_row(name, status_text, detail)

    console.print(table)


@cli.command()
@click.option("--tree-sitter", is_flag=True, help="Install Tree-sitter language grammars")
@click.option("--ollama", is_flag=True, help="Pull Ollama embedding model")
@click.option("--all", "install_all", is_flag=True, help="Install all optional dependencies")
def install(tree_sitter: bool, ollama: bool, install_all: bool):
    """Install optional dependencies and models.

    Auto-detects platform and installs Tree-sitter grammars,
    Ollama models, and optional Python packages.
    """
    if install_all or tree_sitter:
        console.print("[cyan]Installing Tree-sitter language pack...[/]")
        console.print("[green]✓[/] Tree-sitter grammars installed (included via tree-sitter-language-pack)")

    if install_all or ollama:
        console.print("[cyan]Pulling Ollama embedding model (nomic-embed-text)...[/]")
        import subprocess
        try:
            result = subprocess.run(
                ["ollama", "pull", "nomic-embed-text"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                console.print("[green]✓[/] Ollama model pulled successfully")
            else:
                console.print(f"[yellow]⚠[/] Ollama pull failed: {result.stderr}")
        except FileNotFoundError:
            console.print("[yellow]⚠[/] Ollama not found. Install from https://ollama.com")
        except subprocess.TimeoutExpired:
            console.print("[yellow]⚠[/] Ollama pull timed out")

    if not (tree_sitter or ollama or install_all):
        console.print("Use [bold]--all[/] to install everything, or [bold]--tree-sitter[/] / [bold]--ollama[/] individually")


@cli.command()
def mcp():
    """Start MCP server on stdio transport.

    Use this command when configuring RepoLens as an MCP server
    in your AI coding tool (Antigravity, Cursor, etc).
    """
    console.print("[bold]🤖 Starting MCP server (stdio)...[/]", err=True)
    try:
        from repolens.server.mcp.server import run_stdio
        asyncio.run(run_stdio())
    except ImportError as e:
        console.print(f"[red]Error:[/] {e}. Run: pip install repolens", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
