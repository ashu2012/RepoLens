# RepoLens Bootstrap Implementation

**Version:** 1.0

## Overview

The bootstrap process initializes RepoLens on first run.

Goals:

- Zero configuration for most users.
- Cross-platform (Windows, Linux, macOS).
- OS-specific recommended runtime locations.
- Single daemon instance.
- Interactive only on first run (or `repolens init --wizard`).
- Fully scriptable using defaults.

---

# Bootstrap Responsibilities

```
+--------------------------------------------------+
| RepoLensBootstrap                                |
+--------------------------------------------------+
| Detect Platform                                  |
| Detect Existing Installation                     |
| Create Runtime Directory                         |
| Generate Configuration                           |
| Create Directory Structure                       |
| Initialize Logging                               |
| Initialize IPC                                   |
| Initialize Lock Files                            |
| Start Daemon                                     |
+--------------------------------------------------+
```

---

# Bootstrap Flow

```
                    repolens

                        │

         ┌──────── Is initialized? ────────┐

         │                                  │

        Yes                                No

         │                                  │

         ▼                                  ▼

   Load Configuration                Welcome Wizard

         │                                  │

         ▼                                  ▼

 Validate Runtime               Ask Installation Questions

         │                                  │

         ▼                                  ▼

  Runtime Exists?                  Create Directories

         │                                  │

         ▼                                  ▼

    Start Daemon                   Save Configuration

         │                                  │

         └──────────────► Start Daemon
```

---

# Default Runtime Locations

## Windows

```
%LOCALAPPDATA%\RepoLens\
```

Example

```
C:\Users\John\AppData\Local\RepoLens\
```

---

## Linux

```
~/.local/state/repolens/
```

---

## macOS

```
~/Library/Application Support/RepoLens/
```

---

# Runtime Directory Structure

```
RepoLens/

├── config.yaml
├── install.json

├── repolens.lock

├── daemon.pid

├── ipc/
│   ├── daemon.sock
│   └── metadata.json

├── logs/
│   ├── daemon.log
│   ├── indexing.log
│   └── bootstrap.log

├── cache/
│   ├── embeddings/
│   ├── ast/
│   ├── symbols/
│   └── vector/

├── repositories/
│   └── registry.db

├── plugins/

└── temp/
```

---

# First Run Wizard

```
---------------------------------------------------
Welcome to RepoLens
---------------------------------------------------

RepoLens runs a background daemon
that indexes repositories and serves
semantic search requests.

Recommended runtime directory

Windows
    C:\Users\<user>\AppData\Local\RepoLens

Linux
    ~/.local/state/repolens

macOS
    ~/Library/Application Support/RepoLens

Use recommended location?

[Y] Yes (Recommended)
[N] Choose another

Default: Yes
```

---

## Custom Runtime

```
Enter runtime directory

> /mnt/ssd/repolens
```

Validation

- Writable
- Exists (or create)
- Sufficient disk space

---

## Auto Start

```
Start RepoLens automatically
when user logs in?

[Y] Yes (Recommended)

[N] No
```

---

## Cache Size

```
Maximum cache size

1) 2 GB

2) 5 GB (Recommended)

3) 10 GB

4) Unlimited
```

---

## CPU Usage

```
CPU usage while indexing

1) Low

2) Medium

3) High (Recommended)
```

---

## Telemetry

```
Enable anonymous crash reports?

[Y] Yes

[N] No (Recommended)
```

---

# Generated config.yaml

```yaml
version: 1

runtime_dir: ~/.local/state/repolens

log_dir: logs

cache_dir: cache

ipc:

  transport: auto

  endpoint: daemon.sock

daemon:

  auto_start: true

  cpu_profile: high

cache:

  max_size_gb: 5

telemetry:

  enabled: false
```

---

# install.json

```json
{
    "version": "1.0.0",
    "initialized": true,
    "platform": "linux",
    "runtime": "~/.local/state/repolens",
    "installed_at": "2026-07-26T12:00:00Z"
}
```

---

# Bootstrap Class Design

```
RepoLensBootstrap

│

├── PlatformDetector

├── RuntimeLocator

├── InstallationDetector

├── RuntimeInitializer

├── ConfigurationWizard

├── ConfigurationWriter

├── LoggingInitializer

├── IPCInitializer

├── DaemonLauncher
```

---

# Class Responsibilities

## PlatformDetector

Responsible for:

- Detect Windows
- Detect Linux
- Detect macOS

Methods

```
detect_platform()

is_windows()

is_linux()

is_macos()
```

---

## RuntimeLocator

Responsible for returning recommended runtime path.

Methods

```
default_runtime()

validate_runtime(path)
```

---

## InstallationDetector

Checks

```
install.json exists

config.yaml exists

runtime exists

lock exists
```

Methods

```
is_initialized()

installation_state()
```

---

## ConfigurationWizard

Collects user preferences.

Questions

- Runtime directory
- Auto start
- Cache size
- CPU profile
- Telemetry

---

## RuntimeInitializer

Creates

```
logs/

cache/

ipc/

plugins/

repositories/

temp/
```

---

## ConfigurationWriter

Creates

```
config.yaml

install.json
```

---

## LoggingInitializer

Creates

```
bootstrap.log

daemon.log

indexing.log
```

---

## IPCInitializer

Creates IPC endpoint.

Platform mapping

### Linux

```
ipc/daemon.sock
```

### macOS

```
ipc/daemon.sock
```

### Windows

```
Named Pipe

\\.\pipe\RepoLens
```

Metadata

```
ipc/metadata.json
```

---

## DaemonLauncher

Responsibilities

```
Acquire lock

↓

Become server

↓

Write daemon.pid

↓

Start IPC listener
```

---

# Startup Algorithm

```
RepoLens

│

▼

Load install.json

│

▼

Exists?

│

├── No

│      Bootstrap

│

└── Yes

       │

       ▼

Load config.yaml

       │

       ▼

Runtime exists?

       │

       ├── No

       │      Bootstrap

       │

       └── Yes

              │

              ▼

Try IPC Connection

              │

      Connected?

       │

       ├── Yes

       │      Client Mode

       │

       └── No

              │

              ▼

Acquire repolens.lock

              │

       Success?

       │

       ├── Yes

       │

       │     Become Daemon

       │

       └── No

              │

              ▼

Wait

Retry IPC
```

---

# Single Instance Strategy

1. Attempt IPC connection.
2. If connected, operate as client.
3. If not connected:
   - Acquire `repolens.lock`.
4. If lock acquired:
   - Become daemon.
5. Otherwise:
   - Retry IPC until daemon becomes available.

This avoids race conditions when multiple RepoLens processes start simultaneously.

---

# Non-Interactive Installation

```
repolens init
```

Automatically:

- Uses recommended runtime directory.
- Creates configuration.
- Uses recommended cache.
- Enables daemon auto-start.
- Disables telemetry.

---

# Interactive Installation

```
repolens init --wizard
```

Allows customizing every installation option.

---

# Reset Installation

```
repolens reset
```

Actions:

- Stop daemon.
- Remove runtime directory.
- Delete configuration.
- Preserve indexed repositories only if requested.

---

# Design Principles

- Cross-platform.
- Zero configuration by default.
- Interactive only when requested.
- No administrator privileges required.
- User-scoped runtime directory.
- Single daemon per user.
- Atomic bootstrap process.
- Recoverable after crashes.
- Safe for concurrent startup.
- Future-proof for plugins and additional runtime services.

---

# Implementation Status (Completed 2026-07-26)

Implemented in `src/repolens/runtime/`: platform detection, recommended paths,
installation detection, writable-space validation, atomic configuration,
the complete runtime tree, logs, IPC metadata, lock/PID lifecycle, and daemon
launch. `repolens init` uses recommended defaults, `--wizard` exposes all
documented choices, and `repolens reset` supports repository preservation.

Validation: the complete suite reports `49 passed`, including bootstrap
idempotency and CLI init/reset coverage.
