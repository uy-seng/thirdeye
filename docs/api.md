# API

## Stable Local Controller API

The source-built macOS app talks directly to `controller-api` on `127.0.0.1:8788`. Routes are intended for loopback-only local use and do not require a thirdeye login.

- `POST /api/jobs/start`
- `POST /api/jobs/{job_id}/stop`
- `POST /api/jobs/{job_id}/recover`
- `POST /api/jobs/{job_id}/summary/rerun`
- `POST /api/jobs/{job_id}/transcript-summary/generate`
- `POST /api/jobs/{job_id}/transcript-summary/save`
- `POST /api/jobs/{job_id}/cleanup`
- `POST /api/jobs/{job_id}/delete`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/live/stream`
- `GET /api/artifacts`
- `GET /api/capture/targets?backend={docker_desktop|macos_local}`
- `WS /ws/jobs/{job_id}/live`
- `GET /api/health`
- `GET /api/settings/health`
- `GET /api/settings/test/{deepgram|openclaw|desktop}`
- `GET /artifacts/{job_id}/{filename}`

## Capture Agent API

- `GET /health`
- `GET /status`
- `GET /targets`
- `POST /recording/start`
- `POST /recording/stop`
- `POST /live-audio/start`
- `POST /live-audio/stop`
- `GET /live-audio/stream`

Both capture services implement this contract through the shared `capture_contracts.agent` helpers.
