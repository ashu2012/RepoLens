# RepoLens Installer & Post-Installation Implementation

## Overview

This document defines the recommended cross-platform installer
architecture for RepoLens.

### Goals

-   Native installers for Windows, macOS, and Linux
-   Bundle Python runtime (users never install Python)
-   Install and start RepoLens daemon
-   Launch local dashboard after installation
-   Display a Quick Start page
-   Generate MCP configuration snippets dynamically from the
    installation directory
-   Never modify Claude/Codex configuration automatically

------------------------------------------------------------------------

# Installation Flow

``` text
RepoLens Installer
        │
        ▼
Select Installation Directory
        │
        ▼
Install RepoLens
        │
        ▼
Create Runtime Directories
        │
        ▼
Register Daemon / Service
        │
        ▼
Start Daemon
        │
        ▼
Launch Dashboard
http://localhost:38451
        │
        ▼
Installation Complete Dialog
```

------------------------------------------------------------------------

# Packaging Strategy

  Platform   Build               Installer
  ---------- ------------------- ----------------------
  Windows    Nuitka              WiX MSI
  macOS      Nuitka App Bundle   Signed DMG / PKG
  Linux      Nuitka              DEB / RPM / AppImage

Python runtime is bundled with every package.

------------------------------------------------------------------------

# Installation Locations

## Windows

``` text
Application
C:\Program Files\RepoLens

Runtime
%LOCALAPPDATA%\RepoLens
```

## Linux

``` text
Application
/usr/local/bin/repolens

Runtime
~/.local/state/repolens
```

## macOS

``` text
Application
/Applications/RepoLens.app

Runtime
~/Library/Application Support/RepoLens
```

------------------------------------------------------------------------

# Installer Responsibilities

-   Install application
-   Bundle Python runtime
-   Register daemon
-   Create runtime/config/cache folders
-   Start daemon
-   Create shortcuts
-   Open dashboard
-   Show Quick Start

The installer **must not** edit any AI client configuration files.

------------------------------------------------------------------------

# Installation Complete Dialog

    RepoLens Installed Successfully

    Installation Directory
    <actual install path>

    Dashboard
    http://localhost:38451

    The dashboard has been opened.
    Please bookmark it.

    ------------------------------------

    Quick Start

    1. Configure your AI client
    2. Restart your AI client
    3. Verify the connection

    ------------------------------------

    Claude Desktop

    Copy this MCP configuration

    {
      "mcpServers": {
        "repolens": {
          "command": "<install-path>"
        }
      }
    }

    [Copy Claude Config]

    ------------------------------------

    Codex

    Copy this MCP configuration

    {
      "mcpServers": {
        "repolens": {
          "command": "<install-path>"
        }
      }
    }

    [Copy Codex Config]

    ------------------------------------

    [Open Dashboard]

    [Finish]

------------------------------------------------------------------------

# Dynamic MCP Configuration

The installer determines the actual installation directory and generates
configuration dynamically.

Example:

``` json
{
  "mcpServers": {
    "repolens": {
      "command": "C:\\Program Files\\RepoLens\\RepoLens.exe"
    }
  }
}
```

If the user installs elsewhere, the generated command changes
automatically.

The installer never hardcodes paths.

------------------------------------------------------------------------

# Dashboard

The installer opens:

    http://localhost:38451

The dashboard is the permanent administration console.

Sections:

-   Home
-   Configure MCP
-   Diagnostics
-   Logs
-   Settings
-   Updates
-   Documentation
-   About

------------------------------------------------------------------------

# Configure MCP

Supported clients:

-   Claude Desktop
-   Codex CLI
-   Cursor
-   VS Code
-   Continue.dev
-   Gemini CLI
-   Windsurf

Each page provides:

-   Config file location
-   Generated JSON
-   Copy button
-   Open Config Folder
-   Test Connection

No automatic configuration changes are performed.

------------------------------------------------------------------------

# Dashboard Shortcuts

Provide multiple ways to reopen the dashboard:

-   Start Menu → RepoLens Dashboard
-   Desktop shortcut (optional)
-   System tray
-   CLI

```{=html}
<!-- -->
```
    repolens dashboard

------------------------------------------------------------------------

# Design Principles

-   Native OS installers
-   Embedded Python runtime
-   No Python prerequisite
-   Localhost web dashboard
-   User-controlled MCP configuration
-   Dynamic configuration generation
-   Offline documentation
-   Future AI client support without installer changes

------------------------------------------------------------------------

# Implementation Status (Completed 2026-07-26)

The application and post-install contract are implemented:

- `packaging/build.py` creates Nuitka standalone/one-file payloads per target OS.
- `packaging/README.md` documents the WiX, DMG/PKG, and DEB/RPM/AppImage handoff.
- The permanent dashboard is `http://127.0.0.1:38451`; `repolens dashboard`
  reopens it and `repolens daemon` starts the single-instance service.
- Dynamic snippets for Claude, Codex, Cursor, VS Code, Continue.dev, Gemini CLI,
  and Windsurf are exposed by the CLI and installer API.
- Actual install/runtime paths are used, and AI-client files are never modified.
- `repolens diagnostics` reports platform, dependency, runtime, and daemon health.

Signing certificates and release-store credentials remain deployment inputs.
