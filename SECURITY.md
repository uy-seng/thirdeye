# Security

`thirdeye` is designed for local use on your Mac. It is not a hosted service, and it does not send recordings, transcripts, summaries, settings, or job artifacts to any thirdeye-owned cloud service.

## Local-Only Runtime

The macOS app starts local services on loopback addresses only:

| Service | Address | Purpose |
| --- | --- | --- |
| Controller API | `127.0.0.1:8788` | Capture jobs, transcripts, summaries, artifacts, and recovery |
| macOS capture agent | `127.0.0.1:8791` | Local screen, app, window, and audio capture targets |
| Isolated desktop agent | `127.0.0.1:8790` | Optional Docker desktop control API |
| OpenClaw gateway | `127.0.0.1:18789` | Optional local gateway for summaries |

These ports are intended to be reachable only from the same computer. Do not expose them to a public network or bind them to `0.0.0.0`.

## Local Data Storage

Data created by the macOS app stays on your local computer. The app workflow stores controller state, recordings, transcripts, summaries, artifacts, logs, and capture runtime files under:

```text
~/Library/Application Support/thirdeye/
```

The command-line development workflow stores runtime data in the repository under:

```text
runtime/
```

Your `.env` file also stays local. It can contain Deepgram credentials and other local runtime settings. Do not commit `.env` or share it.

## External Providers

The app itself is local-first, but some optional features use services you configure:

- Live transcription uses `DEEPGRAM_API_KEY` and sends the captured audio stream to Deepgram.
- OpenClaw-backed summaries use your configured OpenClaw gateway.
- The optional isolated desktop may access websites you open inside it.

If you require a strict no-network workflow, do not configure external transcription or summary providers and do not start the optional Docker desktop.

## macOS Permissions

Local capture depends on macOS Screen & System Audio Recording permissions. Grant access only to `thirdeye` when using the packaged app. If you start the capture agent directly from Terminal, macOS may attribute permissions to Terminal or the Python launch path instead.

## User Responsibility

Only capture meetings, sessions, screens, apps, windows, and audio that you are allowed to capture. This project does not bypass platform permissions, login requirements, DRM, or consent controls.
