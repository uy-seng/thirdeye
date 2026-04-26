# Architecture

The stack is a macOS desktop app with local services behind it:

- `thirdeye.app` is the canonical Tauri macOS app and user interface.
- `controller-api` runs locally on `127.0.0.1:8788` and owns job state, Deepgram streaming, transcript rebroadcast, summarization, email, artifact serving, and recovery.
- `macos-capture-agent` is an app-managed host-local process that exposes the recording/live-audio contract for local macOS displays, applications, and windows.
- `desktop` is optional and owns the Docker browser session, display, Pulse monitor source, and both `ffmpeg` pipelines.
- `openclaw` is an optional Docker helper that attaches to the desktop browser over remote CDP.

Key rules:

- `python -m core.local_services` is the source of truth for app-managed ports, paths, status, start, stop, setup, and doctor checks.
- The Tauri app calls the local service supervisor instead of duplicating service commands in Rust.
- Docker only manages optional `desktop` and optional `openclaw`.
- Recording happens inside `desktop` for `docker_desktop` jobs and inside `macos-capture-agent` for `macos_local` jobs.
- Controller state, artifacts, events, and SQLite data live under `./runtime` on the host.
- When launched from `thirdeye.app`, local runtime data lives under `~/Library/Application Support/thirdeye`.
- Deepgram is backend-only.
- All published ports bind to `127.0.0.1`.
- Recording artifacts are preserved on failure.
