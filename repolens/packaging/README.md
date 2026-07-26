# Native packaging

Build on each target operating system:

```bash
python -m pip install nuitka
python packaging/build.py
```

The generated `dist` application includes Python and dashboard assets. Use it
as the payload for WiX (Windows), a signed DMG/PKG (macOS), or
DEB/RPM/AppImage tooling (Linux). Finish actions run `RepoLens init`, then
`RepoLens daemon`, and open `http://127.0.0.1:38451/dashboard`.

RepoLens never edits an AI client's configuration. Obtain snippets from
`RepoLens mcp-config CLIENT` or
`GET /api/installer/mcp-config/{client}`.
