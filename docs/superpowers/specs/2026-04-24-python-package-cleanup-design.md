# Python Package Cleanup Design

## Goal

Remove duplicate package nesting such as `services/controller/controller/app` and replace it with service-owned `src/` packages and focused controller subpackages.

## Target Layout

- `services/controller-api/src/` owns the FastAPI controller packages.
- `services/desktop-agent/src/thirdeye_desktop_agent/` owns the Docker desktop agent.
- `services/macos-capture-agent/src/thirdeye_macos_capture/` owns the macOS capture agent.
- `packages/capture_contracts/` owns shared capture schemas and capture-agent helper code used by all agents.

The controller package will use focused folders:

- `api/` for FastAPI entrypoints and API schemas.
- `core/` for settings, auth, logging, local supervisor, and utility code.
- `db/` for database setup and ORM models.
- `jobs/` for job lifecycle, state, recovery, artifacts, and job-facing models.
- `capture/` for capture backend orchestration and desktop execution.
- `transcripts/` for Deepgram, live transcript, transcript storage, and summary prompt code.
- `integrations/` for OpenClaw and page monitor clients.
- `notifications/` for email notification composition.
- `web_assets/` for legacy FastAPI templates and static assets.

## Compatibility Strategy

Runtime entrypoints will change from old package names to explicit package names:

- `api.main:create_app`
- `thirdeye_desktop_agent.main:app`
- `thirdeye_macos_capture.agent.main:app`

`PYTHONPATH` will include all service/package `src` roots. Tests, Tauri, Docker, scripts, docs, and Make targets will be updated to these names.
