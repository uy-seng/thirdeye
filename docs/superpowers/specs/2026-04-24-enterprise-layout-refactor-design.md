# Enterprise Layout Refactor Design

## Goal

Move the repository to an enterprise-style monorepo layout while keeping the existing app behavior, command surface, and importable Python module names working.

## Target Layout

- `apps/macos/` remains the Tauri macOS product app.
- `apps/web/` becomes the home for the legacy/development Next.js controller UI.
- `services/controller/` owns the FastAPI controller package and its Python requirements.
- `services/desktop-agent/` owns the Docker desktop agent package and runtime scripts.
- `services/macos-capture-agent/` owns the macOS capture agent, Swift helper source, and helper build output.
- `infra/compose.yaml` and `infra/docker/desktop/` own Docker composition and image files.
- `tests/python/` owns the Python test suite.

## Compatibility Strategy

The Python module names stay stable: `controller.app`, `desktop.agent`, and `macos_capture.agent`. Runtime commands will set `PYTHONPATH` to the service roots instead of depending on packages at the repository root. This avoids broad application import rewrites while still moving code into service-owned directories.

Hard-coded paths will be replaced or updated in the Makefile, local service supervisor, macOS launch script, Tauri resource mapping, Dockerfile, pytest config, requirements file, tests, and docs that assert physical paths.

## Verification

Run the Python suite, macOS app typecheck/tests, and web UI typecheck/node tests after the move. Docker build and full Tauri build are path-sensitive but heavier; run them if local toolchains allow after the core checks are green.
