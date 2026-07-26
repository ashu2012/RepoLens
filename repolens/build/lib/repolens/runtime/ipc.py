"""ZeroMQ request/reply IPC used for daemon control and diagnostics."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

import zmq


def endpoint_from_runtime(runtime_dir: str | Path) -> str:
    metadata = Path(runtime_dir) / "ipc" / "metadata.json"
    if metadata.exists():
        return json.loads(metadata.read_text(encoding="utf-8"))["endpoint"]
    return "tcp://127.0.0.1:38452"


class IPCClient:
    def __init__(self, runtime_dir: str | Path, timeout_ms: int = 1000):
        self.endpoint = endpoint_from_runtime(runtime_dir)
        self.timeout_ms = timeout_ms

    def request(self, command: str, **params) -> dict:
        context = zmq.Context.instance()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        try:
            socket.connect(self.endpoint)
            socket.send_json({"command": command, "params": params})
            return socket.recv_json()
        except zmq.ZMQError as exc:
            raise ConnectionError(f"RepoLens daemon is unavailable at {self.endpoint}") from exc
        finally:
            socket.close()

    def ping(self) -> bool:
        try:
            return self.request("ping").get("status") == "ok"
        except ConnectionError:
            return False


class IPCServer:
    def __init__(self, runtime_dir: str | Path, handler: Callable[[dict], dict] | None = None):
        self.endpoint = endpoint_from_runtime(runtime_dir)
        self.handler = handler or self._default_handler
        self._stop = threading.Event()

    @staticmethod
    def _default_handler(message: dict) -> dict:
        command = message.get("command")
        if command == "ping":
            return {"status": "ok", "service": "repolens"}
        return {"status": "error", "error": f"unknown command: {command}"}

    def serve_forever(self) -> None:
        context = zmq.Context.instance()
        socket = context.socket(zmq.REP)
        socket.setsockopt(zmq.LINGER, 0)
        socket.bind(self.endpoint)
        try:
            while not self._stop.is_set():
                if socket.poll(200):
                    try:
                        socket.send_json(self.handler(socket.recv_json()))
                    except Exception as exc:
                        socket.send_json({"status": "error", "error": str(exc)})
        finally:
            socket.close()

    def stop(self) -> None:
        self._stop.set()
