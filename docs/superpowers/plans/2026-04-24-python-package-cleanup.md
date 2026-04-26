# Python Package Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace nested Python service packages with clear `src/` package names and focused controller subpackages.

**Architecture:** Move shared capture contracts into `packages/capture_contracts`, move each service package under its own `src/`, and rewrite runtime entrypoints to import explicit `thirdeye_*` packages. Keep behavior unchanged and verify through Python, Node, Rust, and Compose checks.

**Tech Stack:** Python 3.12+, pytest, FastAPI/uvicorn, Tauri/Rust, Docker Compose.

---

### Task 1: Package Layout Contract

**Files:**
- Modify: `tests/python/test_enterprise_layout.py`

- [x] Assert the new service/package roots and controller subfolders exist.
- [x] Assert old duplicate package paths do not exist.
- [x] Run the test and verify it fails before moving files.

### Task 2: Move Python Packages

**Files:**
- Move controller modules from `services/controller/controller/app` to `services/controller-api/src/*`
- Move shared files to `packages/capture_contracts/*`
- Move desktop agent to `services/desktop-agent/src/thirdeye_desktop_agent`
- Move macOS capture agent to `services/macos-capture-agent/src/thirdeye_macos_capture`

- [x] Use `git mv` so history follows files.
- [x] Keep macOS helper source and build output outside package code under `services/macos-capture-agent/helper` and `services/macos-capture-agent/bin`.

### Task 3: Rewrite Imports and Entrypoints

**Files:**
- Modify Python source and tests.
- Modify `Makefile`, `pytest.ini`, `pyproject.toml`, scripts, Dockerfile, Compose references, and Tauri Rust launch strings.

- [x] Replace `controller.app.*`, `desktop.agent.*`, and `macos_capture.agent.*` imports.
- [x] Replace uvicorn paths with `api.main:create_app`, `thirdeye_desktop_agent.main:app`, and `thirdeye_macos_capture.agent.main:app`.
- [x] Update `PYTHONPATH` roots to `src` directories.

### Task 4: Verify

- [x] Run `python -m pytest tests/python -q`.
- [x] Run `cd apps/macos && npm run typecheck && npm test`.
- [x] Run `cd apps/macos/src-tauri && cargo check && cargo test`.
- [x] Run `cd apps/web && npm run typecheck && npm run test:node`.
- [x] Run `docker compose -f infra/compose.yaml config --quiet`.
- [x] Run path searches for stale old package names.
