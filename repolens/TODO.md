# Fix: Console Window Closes Immediately & Dashboard Not Working

## Steps:

1. [x] Add `start` CLI command to `repolens/src/repolens/cli/__init__.py`
   - Initializes runtime if not already initialized
   - Starts uvicorn server in foreground (blocking, keeps console open)
   - Opens browser to dashboard automatically
   - Shows status screen with URL and shutdown instructions
   - Handles graceful Ctrl+C shutdown

2. [x] Update `packaging/windows/RepoLens.iss`
   - Change shortcuts to use `start` command
   - Change `[Run]` section to run `start` in foreground (visible)
   - Remove separate `init` and `daemon` steps
