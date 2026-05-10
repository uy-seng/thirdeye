# Architecture

The stack is a macOS desktop app with local services behind it:

- `thirdeye.app` is the canonical Tauri macOS app and user interface.
- `controller-api` runs locally on `127.0.0.1:8788` and owns job state, Deepgram streaming, transcript rebroadcast, summarization, artifact serving, and recovery.
- `macos-capture-agent` is an app-managed host-local process that exposes the recording/live-audio contract for local macOS displays, applications, and windows.
- On-demand isolated desktops are optional Docker containers. Each desktop owns its browser session, display, Pulse monitor source, desktop agent, and both `ffmpeg` pipelines.
- `openclaw` is an optional Docker helper used for local summary requests.

Key rules:

- `python -m core.local_services` is the source of truth for app-managed ports, paths, status, start, stop, setup, and doctor checks.
- The Tauri app calls the local service supervisor instead of duplicating service commands in Rust.
- Docker manages on-demand isolated desktop sessions and the optional `openclaw` helper.
- Recording happens inside the selected isolated desktop for `docker_desktop` jobs and inside `macos-capture-agent` for `macos_local` jobs.
- Controller state, artifacts, debug logs, and SQLite data live under `./runtime` on the host.
- When launched from `thirdeye.app`, local runtime data lives under `~/Library/Application Support/thirdeye`.
- Deepgram is backend-only.
- All published ports bind to `127.0.0.1`.
- Recording artifacts are preserved on failure.
- The runtime uses real provider settings. Local and CI tests use explicit doubles under `tests/support`, injected by test fixtures.
- The supported user interface is the Tauri app. Retired browser UI surfaces are not part of the current architecture.
