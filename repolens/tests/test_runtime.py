"""Bootstrap, IPC, installer, and CLI lifecycle coverage."""

from __future__ import annotations

import json
import threading
import time

import yaml
from click.testing import CliRunner


def test_bootstrap_creates_complete_runtime_atomically(tmp_path):
    from repolens.runtime.bootstrap import BootstrapOptions, RepoLensBootstrap

    runtime = tmp_path / "runtime"
    result = RepoLensBootstrap(runtime).initialize(
        BootstrapOptions(runtime, auto_start=False, cache_size_gb=2, cpu_profile="medium")
    )

    assert result == runtime.resolve()
    for relative in (
        "config.yaml", "install.json", "ipc/metadata.json", "logs/daemon.log",
        "cache/embeddings", "cache/ast", "cache/symbols", "cache/vector",
        "repositories/registry.db", "plugins", "temp",
    ):
        assert (runtime / relative).exists(), relative
    config = yaml.safe_load((runtime / "config.yaml").read_text(encoding="utf-8"))
    install = json.loads((runtime / "install.json").read_text(encoding="utf-8"))
    assert config["server"]["port"] == 38451
    assert config["daemon"] == {"auto_start": False, "cpu_profile": "medium"}
    assert install["initialized"] is True


def test_bootstrap_is_idempotent(tmp_path):
    from repolens.runtime.bootstrap import RepoLensBootstrap

    runtime = tmp_path / "runtime"
    bootstrap = RepoLensBootstrap(runtime)
    bootstrap.initialize()
    marker = (runtime / "install.json").read_text(encoding="utf-8")
    bootstrap.initialize()
    assert (runtime / "install.json").read_text(encoding="utf-8") == marker


def test_ipc_request_reply(tmp_path):
    from repolens.runtime.bootstrap import RepoLensBootstrap
    from repolens.runtime.ipc import IPCClient, IPCServer

    runtime = RepoLensBootstrap(tmp_path / "runtime").initialize()
    metadata = runtime / "ipc" / "metadata.json"
    metadata.write_text(json.dumps({"endpoint": "tcp://127.0.0.1:38592"}), encoding="utf-8")
    server = IPCServer(runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = IPCClient(runtime)
    for _ in range(20):
        if client.ping():
            break
        time.sleep(0.02)
    assert client.request("ping")["service"] == "repolens"
    assert client.request("invalid")["status"] == "error"
    server.stop()
    thread.join(timeout=2)


def test_dynamic_mcp_configuration_uses_actual_paths(tmp_path):
    from repolens.server.installer import generate_mcp_config

    config = generate_mcp_config("claude", tmp_path / "custom", tmp_path / "state")
    server = config["mcpServers"]["repolens"]
    assert str(tmp_path / "custom") in server["command"]
    assert server["env"]["REPOLENS_DATA_DIR"] == str((tmp_path / "state").resolve())


def test_init_and_reset_cli(tmp_path):
    from repolens.cli import cli

    runtime = tmp_path / "runtime"
    runner = CliRunner()
    initialized = runner.invoke(cli, ["init", "--runtime-dir", str(runtime)])
    assert initialized.exit_code == 0, initialized.output
    assert (runtime / "install.json").exists()
    reset = runner.invoke(cli, ["reset", "--runtime-dir", str(runtime), "--yes"])
    assert reset.exit_code == 0, reset.output
    assert not runtime.exists()


def test_installer_api_exposes_supported_clients():
    from fastapi.testclient import TestClient
    from repolens.server.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/installer/mcp-config/vscode")
    assert response.status_code == 200
    assert "servers" in response.json()
