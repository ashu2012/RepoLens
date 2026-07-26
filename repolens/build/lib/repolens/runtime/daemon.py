"""Single-instance RepoLens daemon supervisor."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import uvicorn
from filelock import FileLock, Timeout

from .bootstrap import RepoLensBootstrap
from .ipc import IPCClient, IPCServer


def run_daemon(runtime_dir: str | Path | None = None, host: str = "127.0.0.1", port: int = 38451) -> int:
    runtime = RepoLensBootstrap(runtime_dir).initialize()
    lock = FileLock(str(runtime / "repolens.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return 0 if IPCClient(runtime).ping() else 2

    (runtime / "daemon.pid").write_text(str(os.getpid()), encoding="ascii")
    ipc = IPCServer(runtime)
    thread = threading.Thread(target=ipc.serve_forever, name="repolens-ipc", daemon=True)
    thread.start()
    try:
        uvicorn.run("repolens.server.app:create_app", host=host, port=port, factory=True)
    finally:
        ipc.stop()
        thread.join(timeout=2)
        (runtime / "daemon.pid").unlink(missing_ok=True)
        lock.release()
    return 0
