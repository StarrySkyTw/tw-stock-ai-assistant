# Native No-Docker Launch Plan

Goal: let StockAI open as a local Windows app without requiring Docker Desktop.

## Current State

- The current production launcher is `stockai-app.ps1` with Docker Compose.
- Docker Compose runs three services: Postgres, FastAPI API, and Next.js web.
- The API already supports SQLite through `DATABASE_URL`.
- When SQLite is used, the FastAPI startup path creates tables with `Base.metadata.create_all()`.

## Implemented Prototype

`stockai-native-app.ps1` is a no-Docker launcher prototype.
`stockai-native-app.cmd` is a small Windows wrapper for shortcuts and double-click launch, because Windows often blocks direct `.ps1` execution through Execution Policy.

It does the following:

- Uses SQLite instead of the Postgres container.
- Starts FastAPI on `http://127.0.0.1:18000` by default, so it does not collide with the Docker API on port 8000.
- Serves `apps/web/out` from FastAPI when a static export exists.
- Falls back to a Next.js server on `http://127.0.0.1:13000` only when static export is unavailable and Node/npm exists.
- Opens the app in an Edge app window.
- Stops API and web process trees after the Edge app window closes.
- Supports portable runtime paths before falling back to PATH:
  - `.runtime/python/python.exe`
  - `.runtime/node/npm.cmd`
  - `.runtime/nodejs/npm.cmd`
- Ignores the Windows Store `python.exe` alias because it is not a real bundled runtime.
- Supports `-CheckRequirements` so the launcher can report missing native requirements without installing dependencies or starting services.
- Can be checked with `stockai-native-app.cmd -CheckRequirements`.
- Can be smoke-tested without opening Edge with `stockai-native-app.cmd -SmokeTest -SkipInstall`.

## What Is Still Needed

This machine currently does not expose native Python, Node, or npm on PATH, so a fully self-contained no-Docker launch still needs a bundled Python runtime or a packaged app.

Required pieces:

- Portable Python 3.12 runtime.
- Static frontend export at `apps/web/out`.
- First-run setup cache:
  - `.native/api-venv`
- Optional fallback only: `apps/web/node_modules` and `apps/web/.next`.
- A `.lnk` shortcut or small `.exe` wrapper that launches `stockai-native-app.ps1`.

## Recommended Direction

Short term:

- Keep the Docker launcher as a fallback.
- Use `stockai-native-app.ps1 -CheckRequirements` to prove whether a machine can run native mode.

Medium term:

- Bundle portable Python under `.runtime`.
- Produce `apps/web/out` during release packaging.
- Run native first-run setup once.
- Update the user-facing shortcut to launch `stockai-native-app.ps1`.

Long term:

- Package the app as a real Windows desktop shell, likely Tauri or Electron.
- Keep the product boundary as a research and discipline assistant, not an automatic trading tool.
