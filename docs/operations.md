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
make dev-api
```

Optional OpenClaw helper:

```bash
make up-openclaw
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
make services-stop
```

The macOS app's Stop services button stops app-managed local services. On-demand desktops should be destroyed from the app. Use `docker compose --profile openclaw -f infra/compose.yaml down` only when you need to stop the optional OpenClaw helper.
