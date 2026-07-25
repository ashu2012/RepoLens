# Getting started

## Requirements

- Python 3.11 or newer
- Git
- A local repository containing at least one supported source file

## Install from source

```bash
git clone https://github.com/ashu2012/RepoLens.git
cd RepoLens/repolens
python -m venv .venv
python -m pip install -e .
```

Activate `.venv` using your platform's standard command, then start RepoLens:

```bash
repolens serve
```

The dashboard is at `http://127.0.0.1:8420/dashboard` and OpenAPI documentation is at
`http://127.0.0.1:8420/api/docs`.

Set `REPOLENS_DATA_DIR` to choose where the persistent repository registry and job history live:

```bash
REPOLENS_DATA_DIR=/path/to/repolens-data repolens serve
```

## Index a repository from the Web UI

1. Select **Add repository**.
2. Enter an absolute local path visible to the RepoLens process.
3. Select **Full index**.
4. Wait for `complete` and confirm non-zero file, symbol, chunk, and vector counts.
5. Verify that `<your-repository>/.repolens/index.db` exists.

If the phase changes to `error`, inspect the displayed error or server log. A missing
Tree-sitter language pack, unreadable file, unsupported-only repository, or parse failure will
not be disguised as success.

## Development checks

```bash
python -m pip install pytest pytest-asyncio
python -m pytest
```

Configuration defaults live in `repolens/config.yaml` and can be overridden with environment
variables using the `REPOLENS_` prefix and `__` for nesting.
