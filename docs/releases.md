# Downloads and releases

## Windows downloads

Open the [latest RepoLens release](https://github.com/ashu2012/RepoLens/releases/latest)
and download one of:

- `RepoLens-<version>-Setup-x64.exe` — recommended installer. It installs
  RepoLens under Program Files, initializes the user runtime, starts the server,
  streams logs in the console, creates shortcuts, and opens the dashboard once
  the server is ready. Indexing runs on a staged local copy and publishes by
  hot swap so search keeps using the last good index while new builds finish.
- `RepoLens.exe` — portable executable. Run `RepoLens.exe init` once, followed
  by `RepoLens.exe daemon`.
- `SHA256SUMS.txt` — checksums for verifying both downloads.

Windows SmartScreen may warn for unsigned development releases. Verify the
checksum and release origin before continuing. Production releases should be
Authenticode-signed before publication.

## Verify a download

```powershell
Get-FileHash .\RepoLens.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

The calculated value must match the corresponding line in `SHA256SUMS.txt`.

## Creating a release

The workflow at `.github/workflows/release-windows.yml` supports two modes:

1. Push a semantic version tag such as `v0.2.0`. Tests run, the portable EXE
   and installer are built, checksums are generated, and all three files are
   attached to a GitHub Release with generated release notes.
2. Run **Release Windows installer** manually from the Actions page and supply
   a version. This creates downloadable workflow artifacts without publishing
   a GitHub Release, which is useful for release candidates.

```bash
git tag v0.2.0
git push origin v0.2.0
```

Before tagging, update the version in `repolens/pyproject.toml` and
`repolens/src/repolens/__init__.py`, then run the test suite.

## Local Windows installer build

Install Python 3.11, Git, a C compiler supported by Nuitka, and
[Inno Setup 6](https://jrsoftware.org/isinfo.php). From the repository root:

```powershell
cd repolens
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& t:\development\RepoLens\repolens\.venv\Scripts\Activate.ps1)
python -m venv .venv-release
.\.venv-release\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel
python -m pip install . nuitka ordered-set zstandard
.\packaging\windows\build-windows.ps1 -Version 0.2.0 -Python python
```

Outputs are written to `repolens/dist/`:

- `RepoLens.exe`
- `RepoLens-0.2.0-Setup-x64.exe`

Test both artifacts on a clean Windows VM before publishing. Code-sign the
portable executable first and the installer second when signing credentials
are available.
