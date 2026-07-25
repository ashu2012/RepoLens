# Contributing to RepoLens

Thanks for helping build repository intelligence for AI coding agents. Contributions of every
size are welcome: bug reports, parser fixtures, documentation, tests, design feedback, and code.

## Good places to start

- Reproduce indexing on a repository and report the language and result counts.
- Add Tree-sitter fixtures for an existing or new language.
- Connect persisted chunks to BM25 or vector retrieval.
- Replace an MCP stub with an index-backed implementation.
- Improve setup documentation or Windows/macOS/Linux compatibility.

Before a large architectural change, open an issue or discussion so contributors can align on
scope. For a focused fix, a pull request with a clear explanation and regression test is welcome.

## Development

```bash
cd repolens
python -m venv .venv
python -m pip install -e .
python -m pip install pytest pytest-asyncio
python -m pytest
```

Keep feature claims consistent with the status table in the top-level README. A capability should
be marked complete only when its end-to-end path is implemented and tested.

## Pull requests

- Keep changes focused and explain the user-visible outcome.
- Add or update tests when behavior changes.
- Update the roadmap or documentation when feature readiness changes.
- Do not include generated indexes, credentials, or private repository content.

By contributing, you agree that your contribution is licensed under the project's Apache-2.0
license.
