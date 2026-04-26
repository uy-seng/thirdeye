# Enterprise Layout Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the repository into an enterprise monorepo layout without breaking app startup, tests, or package imports.

**Architecture:** Keep Python module names stable and move their package roots under service directories. Use explicit `PYTHONPATH` construction for local supervisors, launch scripts, Docker, pytest, and Tauri-spawned services so runtime behavior no longer depends on old root-level package directories.

**Tech Stack:** Python 3.12+, pytest, FastAPI/uvicorn, Next.js, Vite/React, Tauri/Rust, Docker Compose.

---

### Task 1: Add Layout Contract Tests

**Files:**
- Create: `controller/tests/test_enterprise_layout.py`

- [ ] Add a failing test that asserts `apps/web`, `services/controller`, `services/desktop-agent`, `services/macos-capture-agent`, `infra/compose.yaml`, and `tests/python` exist, and that old root-level service directories no longer exist.
- [ ] Run `python -m pytest controller/tests/test_enterprise_layout.py -q` and verify it fails on the current layout.

### Task 2: Move Directories

**Files:**
- Move: `controller/app` to `services/controller/controller/app`
- Move: `controller/requirements.txt` to `services/controller-api/requirements.txt`
- Move: `controller/tests` to `tests/python`
- Move: `controller/web` to `apps/web`
- Move: `desktop/agent`, `desktop/scripts`, `desktop/__init__.py` to `services/desktop-agent/desktop` and `services/desktop-agent/scripts`
- Move: `macos_capture` to `services/macos-capture-agent/macos_capture`
- Move: `compose.yaml` to `infra/compose.yaml`
- Move: `desktop/Dockerfile` and `desktop/s6-rc.d` to `infra/docker/desktop`

- [ ] Use `mkdir -p` and `git mv` so history follows the moved files.
- [ ] Remove empty legacy directories after moves.

### Task 3: Update Path Contracts

**Files:**
- Modify: `Makefile`
- Modify: `requirements.txt`
- Modify: `pytest.ini`
- Modify: `pyproject.toml`
- Modify: `services/controller/controller/app/local_services.py`
- Modify: `scripts/build_macos_capture_helper.sh`
- Modify: `scripts/macos_capture_agent.sh`
- Modify: `apps/macos/package.json`
- Modify: `apps/macos/src-tauri/tauri.conf.json`
- Modify: `apps/macos/src-tauri/src/lib.rs`
- Modify: `infra/compose.yaml`
- Modify: `infra/docker/desktop/Dockerfile`
- Modify: `infra/docker/desktop/s6-rc.d/svc-desktop-agent/run`

- [ ] Set pytest test paths to `tests/python`.
- [ ] Set Python search paths to `services/controller`, `services/desktop-agent`, and `services/macos-capture-agent`.
- [ ] Update helper paths to `services/macos-capture-agent/bin/macos_capture_helper`.
- [ ] Update Docker paths to the new `infra` and `services` locations.
- [ ] Keep Tauri bundled resource destination as `macos_capture/bin/macos_capture_helper`, but update the source path.

### Task 4: Update Tests and Docs

**Files:**
- Modify path-sensitive Python tests under `tests/python`
- Modify path-sensitive Node tests under `apps/web/tests-node` and `apps/macos/src`
- Modify docs that describe repository layout and common commands

- [ ] Replace old physical paths with the new layout.
- [ ] Keep runtime strings like `controller.app.main:create_app` unchanged where they are module import names.

### Task 5: Verify

- [ ] Run `python -m pytest tests/python -q`.
- [ ] Run `cd apps/macos && npm run typecheck && npm test`.
- [ ] Run `cd apps/web && npm run typecheck && npm run test:node`.
- [ ] Run targeted path searches with `rg` to confirm old hard-coded physical paths are gone except historical docs under `docs/superpowers`.
