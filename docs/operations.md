# Operations

## Start

Source-built macOS app:

```bash
make setup
make doctor
make macos-app-dev
```

Command-line service development:

```bash
make build
make dev-api
```

## Service Checks

- Controller: `curl -fsS http://127.0.0.1:8788/api/health`
- Desktop sessions: `curl -fsS http://127.0.0.1:8788/api/desktops`
- OpenClaw: `curl -fsS http://127.0.0.1:18789/healthz`
- Supervisor: `make services-status`

These are service endpoints and CLI checks, not browser diagnostic pages. Development tests use explicit doubles under `tests/support`; provider simulation is not enabled from `.env`.

## Smoke Test

```bash
make smoke
```

## Full Test

```bash
make test-all
```

## Stop

```bash
make down
```

The macOS app's Stop services button stops app-managed local services. On-demand desktops should be destroyed from the app.
