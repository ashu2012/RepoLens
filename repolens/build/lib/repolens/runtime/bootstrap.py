"""Atomic, cross-platform first-run initialization."""

from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from repolens import __version__


RUNTIME_DIRECTORIES = (
    "ipc", "logs", "cache/embeddings", "cache/ast", "cache/symbols",
    "cache/vector", "repositories", "plugins", "temp",
)


class PlatformDetector:
    @staticmethod
    def detect_platform() -> str:
        name = platform.system().lower()
        return "macos" if name == "darwin" else name

    @classmethod
    def is_windows(cls) -> bool:
        return cls.detect_platform() == "windows"

    @classmethod
    def is_linux(cls) -> bool:
        return cls.detect_platform() == "linux"

    @classmethod
    def is_macos(cls) -> bool:
        return cls.detect_platform() == "macos"


class RuntimeLocator:
    @staticmethod
    def default_runtime() -> Path:
        override = os.getenv("REPOLENS_DATA_DIR")
        if override:
            return Path(override).expanduser().resolve()
        system = PlatformDetector.detect_platform()
        if system == "windows":
            root = os.getenv("LOCALAPPDATA")
            return (Path(root) if root else Path.home() / "AppData" / "Local") / "RepoLens"
        if system == "macos":
            return Path.home() / "Library" / "Application Support" / "RepoLens"
        return Path.home() / ".local" / "state" / "repolens"

    @staticmethod
    def validate_runtime(path: str | Path) -> Path:
        target = Path(path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError(f"Runtime directory is not writable: {target}") from exc
        if shutil.disk_usage(target).free < 100 * 1024 * 1024:
            raise ValueError(f"Runtime directory has less than 100 MB free: {target}")
        return target


class InstallationDetector:
    def __init__(self, runtime_dir: str | Path):
        self.runtime_dir = Path(runtime_dir)

    def installation_state(self) -> dict[str, bool]:
        return {
            "runtime": self.runtime_dir.is_dir(),
            "install": (self.runtime_dir / "install.json").is_file(),
            "config": (self.runtime_dir / "config.yaml").is_file(),
        }

    def is_initialized(self) -> bool:
        return all(self.installation_state().values())


@dataclass(frozen=True)
class BootstrapOptions:
    runtime_dir: Path
    auto_start: bool = True
    cache_size_gb: int | None = 5
    cpu_profile: str = "high"
    telemetry: bool = False

    def __post_init__(self) -> None:
        if self.cpu_profile not in {"low", "medium", "high"}:
            raise ValueError("cpu_profile must be low, medium, or high")
        if self.cache_size_gb is not None and self.cache_size_gb <= 0:
            raise ValueError("cache_size_gb must be positive or None")


class RuntimeInitializer:
    @staticmethod
    def initialize(runtime_dir: Path) -> None:
        for relative in RUNTIME_DIRECTORIES:
            (runtime_dir / relative).mkdir(parents=True, exist_ok=True)
        for log in ("bootstrap.log", "daemon.log", "indexing.log"):
            (runtime_dir / "logs" / log).touch(exist_ok=True)
        (runtime_dir / "repositories" / "registry.db").touch(exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            Path(temp_name).unlink()
        except FileNotFoundError:
            pass


class ConfigurationWriter:
    @staticmethod
    def write(options: BootstrapOptions) -> None:
        runtime = str(options.runtime_dir)
        config: dict[str, Any] = {
            "version": 1,
            "runtime_dir": runtime,
            "log_dir": "logs",
            "cache_dir": "cache",
            "ipc": {"transport": "auto", "endpoint": "daemon.sock"},
            "daemon": {"auto_start": options.auto_start, "cpu_profile": options.cpu_profile},
            "cache": {"max_size_gb": options.cache_size_gb},
            "telemetry": {"enabled": options.telemetry},
            "server": {"host": "127.0.0.1", "port": 38451, "mcp_transport": "stdio"},
        }
        install = {
            "version": __version__,
            "initialized": True,
            "platform": PlatformDetector.detect_platform(),
            "runtime": runtime,
            "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _atomic_write(options.runtime_dir / "config.yaml", yaml.safe_dump(config, sort_keys=False))
        _atomic_write(options.runtime_dir / "install.json", json.dumps(install, indent=2) + "\n")


class RepoLensBootstrap:
    def __init__(self, runtime_dir: str | Path | None = None):
        self.runtime_dir = Path(runtime_dir) if runtime_dir else RuntimeLocator.default_runtime()

    @property
    def detector(self) -> InstallationDetector:
        return InstallationDetector(self.runtime_dir)

    def initialize(self, options: BootstrapOptions | None = None, force: bool = False) -> Path:
        options = options or BootstrapOptions(runtime_dir=self.runtime_dir)
        runtime = RuntimeLocator.validate_runtime(options.runtime_dir)
        if self.detector.is_initialized() and not force:
            return runtime
        RuntimeInitializer.initialize(runtime)
        ConfigurationWriter.write(BootstrapOptions(**{**asdict(options), "runtime_dir": runtime}))
        metadata = {
            "transport": "tcp" if PlatformDetector.is_windows() else "ipc",
            "endpoint": "tcp://127.0.0.1:38452" if PlatformDetector.is_windows()
            else f"ipc://{(runtime / 'ipc' / 'daemon.sock').as_posix()}",
            "dashboard": "http://127.0.0.1:38451",
        }
        _atomic_write(runtime / "ipc" / "metadata.json", json.dumps(metadata, indent=2) + "\n")
        with (runtime / "logs" / "bootstrap.log").open("a", encoding="utf-8") as log:
            log.write(f"{datetime.now(timezone.utc).isoformat()} initialized {runtime}\n")
        return runtime
