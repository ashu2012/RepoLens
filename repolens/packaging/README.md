# Native packaging

For the complete end-user download, GitHub Release, checksum, tagging, and
Windows installer procedure, see [`../../docs/releases.md`](../../docs/releases.md).

Build on each target operating system:

```bash
python -m pip install nuitka
python packaging/build.py
```

Windows maintainers can generate both the portable executable and guided
installer in one command:

```powershell
winget install --exact --id JRSoftware.InnoSetup
.\packaging\windows\build-windows.ps1 -Version 0.2.0 -Python python
.\packaging\windows\build-windows.ps1 `
  -Version 0.2.0 `
  -Python python `
  -Iscc "C:\Path\To\Inno Setup 6\ISCC.exe"
```

The generated `dist` application includes Python and dashboard assets. Use it
as the payload for WiX (Windows), a signed DMG/PKG (macOS), or
DEB/RPM/AppImage tooling (Linux). The installer runs `RepoLens start` as
its finish action, which automatically initializes the runtime (if needed),
streams server logs in the console, and opens
`http://127.0.0.1:38451/dashboard` in the default browser once the server is
ready. The console window stays open and ends with a clear ready banner until
the user presses Ctrl+C.

RepoLens never edits an AI client's configuration. Obtain snippets from
`RepoLens mcp-config CLIENT` or
`GET /api/installer/mcp-config/{client}`.
