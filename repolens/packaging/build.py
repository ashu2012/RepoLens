"""Build the platform application bundle with Nuitka."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--onefile", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, "-m", "nuitka", "--assume-yes-for-downloads", "--follow-imports",
        f"--include-data-dir={project / 'templates'}=templates",
        f"--output-dir={project / args.output_dir}", "--output-filename=RepoLens",
        "--onefile" if args.onefile else "--standalone",
        str(project / "src" / "repolens" / "__main__.py"),
    ]
    return subprocess.call(command, cwd=project)


if __name__ == "__main__":
    raise SystemExit(main())
