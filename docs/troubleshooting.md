# Troubleshooting

## OpenClaw token drift or auth lockout

- Run `make openclaw-sync` to verify the repo can read the token from
  `~/.openclaw/openclaw.json` and print a fresh tokenized dashboard URL.
- Run `make up-openclaw` to stop the host gateway and recreate the Docker
  gateway with the same token as the host OpenClaw config.
- If the dashboard was already open, reload the printed tokenized URL instead of
  reusing a stale tab with an older token or device identity.

## No audio monitor source

- Run `services/desktop-agent/scripts/detect_audio_source.sh` inside the desktop container.
- Set `PULSE_SOURCE_OVERRIDE` if the auto-detected source is wrong.

## Deepgram degraded mid-job

- Recording continues.
- For internal debugging, check `runtime/artifacts/jobs/{job_id}/metadata.json` and `runtime/logs/jobs/{job_id}/deepgram-events.jsonl`.
- Retry summary or notification after the recording stops.

## Controller restart during capture

- The controller reconciles active jobs on startup using DB state and desktop status.
- If relay recovery is safe, it restarts the live relay.
