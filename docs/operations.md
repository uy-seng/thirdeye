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
make up
make dev-api
```

## Health

- Controller: `curl -fsS http://127.0.0.1:8788/api/health`
- Desktop agent: `curl -fsS http://127.0.0.1:8790/health`
- Desktop via controller API: `curl -fsS http://127.0.0.1:8788/api/settings/test/desktop`
- OpenClaw: `curl -fsS http://127.0.0.1:18789/healthz`
- Supervisor: `make services-status`

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

The macOS app's Stop services button stops app-managed local services. Optional Docker services can be stopped with `make down`.
