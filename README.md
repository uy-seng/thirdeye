<p align="center">
  <img src="assets/logo.png" alt="thirdeye logo" width="280">
</p>

`thirdeye` is a macOS screen capture app with built-in LLM capabilities for live transcription and summary.

The intended way to use this project is as a source-built macOS application. The Python backend runs from the repository virtual environment, and `thirdeye.app` starts the local services it needs.

## Prototype Demo

<a href="https://youtu.be/i6yKtiUTftY" target="_blank" rel="noopener noreferrer">Watch the prototype demo on YouTube</a>

This video shows a prototype version of `thirdeye` being used during a real-time seminar. The final macOS application works similarly, with additional functionality such as local screen capture.

Backstory: I used this for my personal use after needing to attend a Google early career seminar that overlapped with my study schedule. The app lets me record and transcribe meetings so I can review the key information later.

## Author's Note

This project might or might not be useful for you depending on your goals.

The reason why I created this tool is because I wished there exist a tool that allows me to join a meeting, get transcript and keep track of what the meeting is about through summaries while not listening to any of the meeting and focus on other things.

Some meetings and sessions does not allow recordings and using AI notetaker such as `otter.ai` is annoying because it notifies the host. That gives me an idea to create this tool.

I personally uses this tool in several ways:

- Joining informational sessions through isolated docker browser so that it won't distract me while I continue to work on other tasks.
- Joining meetings where I don't need to speak much using my local desktop and I can still mute the meeting and listen to music while still keeping track of what is being discussed in meetings.
- Joining meetings and record transcript for my personal use and get summaries so I don't have to take notes.

This project is created with technologies usage that minimize the cost you have to pay to run it.

## Limitations

I noticed that this app is not working well on Zoom or Teams application or other applications where the Audio is transmitted in a different processes other than the core application. For app like chrome, the audio is transimitted in the same process family, hence it works. It is recommended that you run everything through browser to get the best results of your need.

## Technologies

The application is built using the following technologies:

- **Tauri**: it allows me to build a native desktop application using web languages such as React.
- **Openclaw**: this is mainly used as a gateway for LLM communication. Openclaw allows me to use my `codex subscription` through its `codex cli wrapper`. This means I use my `openai subscription` for API calls instead of their separate `API Billing` which incur extra cost. You can swap out this component if you want to use direct API calls for your LLM provider. In my setup, I am running this through `docker` for security purpose, but you can run it through anywhere.
- **ScreenCaptureKit**: this is a mac native tool built using swift that allows me to do screen capture in mac.
- **Docker**: optional; it allows me to setup an isolated desktop that I can control without using any of my local browser for screen capture.
- **Deepgram**: I use this for `speech-to-text` API for transcription. Deepgram gives you 200 dollars credit which I think is awesome. It cost about `0.46$` to do about 1 hour recording. So you can get pretty far with Deepgram API. I find the quality to be acceptable.

## Architecture

- **thirdeye.app**: macOS app and main user interface, built with Tauri.
- **macos-capture-agent**: FastAPI agent on `127.0.0.1:8791` for local macOS displays, applications, and windows.
- **controller-api**: FastAPI service on `127.0.0.1:8788` for auth, job lifecycle, Deepgram relay, transcript rebroadcast, summaries, artifacts, and recovery.
- **desktop**: optional Dockerized Chromium desktop with KasmVNC on `127.0.0.1:3000`, a desktop control API on `127.0.0.1:8790`, and the `ffmpeg` capture scripts.
- **openclaw**: optional Docker helper on `127.0.0.1:18789` that act as a gateway for LLM calls.

Recording and live transcription are decoupled:

- Pipeline A records the X11 display and Pulse monitor to MP4 inside `desktop`.
- Pipeline A can alternatively record a macOS display, application, or window through ScreenCaptureKit via `macos-capture-agent`.
- Pipeline B captures monitor audio, converts it to `16k` mono PCM, and streams it to Deepgram from `controller-api`.

## Prerequisites

Install these on the host machine before starting setup:

| Prerequisite | Why it is needed | Notes |
| --- | --- | --- |
| Docker Desktop or Docker Engine with Compose v2 | Runs the optional isolated desktop and optional OpenClaw gateway | `docker compose` must be available only if you use those features |
| GNU Make | Wraps the common build and run commands | Used by the repo `Makefile` |
| Bash-compatible shell | Required by the repo scripts |  |
| Python 3.12+ | Creates the repository `.venv` and runs the local FastAPI services | Python 3.14 is recommended for local development |
| Node.js 20.19+ | Runs the Tauri frontend tooling | `.nvmrc` pins the source-built app version |
| npm | Installs frontend dependencies | Ships with Node.js |
| Rust toolchain | Builds the macOS app shell | Required for `make macos-app-dev` and `make macos-app-build` |
| Xcode command line tools | Builds Swift and macOS app components | Required for ScreenCaptureKit helper builds |
| Localhost ports | Exposes the local services | `8788`, `8791`, optionally `3000`, `8790`, and `18789` |

## Requirements

You will need the following runtime requirements configured before real captures will work:

- A Deepgram API key in `.env` as `DEEPGRAM_API_KEY`.
- Controller credentials in `.env` as `CONTROLLER_USERNAME`, `CONTROLLER_PASSWORD`, and `SESSION_SECRET`.
- Desktop login credentials in `.env` as `DESKTOP_USER` and `DESKTOP_PASSWORD`.
- If you want OpenClaw-backed summaries, a readable host config file at `~/.openclaw/openclaw.json` containing `gateway.auth.token`.

## Security

`thirdeye` is designed to run locally on your Mac. The app stores recordings, transcripts, summaries, artifacts, logs, and runtime state on your computer, not in a thirdeye-hosted cloud service.

See [docs/security.md](docs/security.md) for the local runtime model, storage locations, macOS permissions, and external provider notes.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `apps/` | Tauri shell and React UI for running thirdeye as a macOS app |
| `services/controller-api/` | FastAPI backend package and Python requirements |
| `services/desktop-agent/` | Docker desktop agent package and capture scripts |
| `services/macos-capture-agent/` | macOS capture agent package and ScreenCaptureKit helper |
| `packages/capture_contracts/` | Shared capture request and target contracts |
| `infra/` | Docker Compose file and desktop image/s6 configuration |
| `tests/python/` | Python test suite |
| `config/` | Seed configuration files for desktop helper services |
| `runtime/` | Host-mounted runtime state, recordings, artifacts, SQLite DB, and logs |
| `scripts/` | Bootstrap, smoke test, export, and OpenClaw remediation scripts |
| `docs/` | Architecture, API, security, operations, and troubleshooting notes |

## One-Time Setup

### 1. Create the Python virtual environment and install the app

All Python dependencies should live in the repository virtual environment at `.venv`. Do not install the backend dependencies into your global Python.

This command copies `.env.example` to `.env` if needed, creates runtime directories, creates `.venv`, installs Python dependencies into `.venv`, and installs the macOS app dependencies under `apps/`.

```bash
make setup
make doctor
```

After setup, any manual Python command should either run through `make` or use the virtual environment directly:

```bash
source .venv/bin/activate
python -m pytest tests/python -q
```

### 2. Review and edit `.env`

At minimum, update these values before real use:

- `CONTROLLER_PASSWORD`
- `SESSION_SECRET`
- `DEEPGRAM_API_KEY`

If you use the optional isolated Docker desktop, also update:

- `DESKTOP_PASSWORD`
- `PUID` and `PGID` to match your host user and group IDs

You can get the host IDs with:

```bash
id -u
id -g
```

Important environment variables from `.env.example`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `CONTROLLER_USERNAME` / `CONTROLLER_PASSWORD` | Yes | Login for the local controller |
| `SESSION_SECRET` | Yes | Cookie/session signing secret |
| `DESKTOP_USER` / `DESKTOP_PASSWORD` | Yes | Credentials for the isolated desktop |
| `PUID` / `PGID` | Recommended | Host UID and GID for Docker volume ownership |
| `TZ` | Yes | Host and container timezone |
| `MACOS_CAPTURE_BASE_URL` | Optional | Base URL for the host-local macOS capture agent |
| `DEEPGRAM_API_KEY` | Yes for real transcription | Deepgram live transcription auth |
| `OPENCLAW_BASE_URL` | Optional | Base URL for the helper gateway |
| `OPENCLAW_SUMMARY_MODEL` | Optional | Summary model used via OpenClaw |
| `RECORDING_FPS`, `RECORDING_WIDTH`, `RECORDING_HEIGHT` | Optional | Desktop recording defaults |
| `MAX_DURATION_MINUTES`, `SILENCE_TIMEOUT_MINUTES`, `ENABLE_AUTO_STOP` | Optional | Capture stopping behavior |

### 3. Manual virtual environment setup

`make setup` does this for you. If multiple Python versions are installed and you want to create `.venv` yourself, use your Python 3.12+ executable explicitly, then run `make setup` afterward to finish the rest of the app setup.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
make setup
```

The root `requirements.txt` installs:

- controller backend dependencies from `services/controller-api/requirements.txt`
- `pytest` for the Python test suite

### 4. Build the macOS capture helper

If you want to capture a local app, window, or display on this Mac, build the ScreenCaptureKit helper once:

```bash
make macos-capture-build
```

This produces `services/macos-capture-agent/bin/macos_capture_helper`.

## macOS App

The Tauri app is the main product UI and the recommended way to run thirdeye. It starts the FastAPI controller and the macOS capture agent from `.venv`, then talks directly to the local API at `127.0.0.1:8788`.

Run the source-built macOS app:

```bash
make macos-app-dev
```

Build the macOS app bundle:

```bash
make macos-app-build
```

The app bundle and DMG are created by Tauri under `apps/tauri/target/release/bundle/`.

Runtime data created by the app is stored under:

```text
~/Library/Application Support/thirdeye/
```

Use the app's capture settings button when macOS blocks local screen, app, window, or muted app-audio capture. The packaged app bundles the ScreenCaptureKit helper inside `thirdeye.app`, so the normal permission entry to allow is `thirdeye` in Screen & System Audio Recording. The first app build uses ad-hoc signing for local use; Developer ID signing and notarization are separate distribution steps.

## Advanced Startup

The controller is local-first. The app-managed macOS flow does not require Docker or manually starting the API services. Only the optional isolated desktop and optional OpenClaw gateway run in Docker.

Use this section when you want to run individual services from the terminal instead of letting `thirdeye.app` manage them.

### 1. Optional: build the Docker image

```bash
make build
```

### 2. Optional: start the isolated desktop

```bash
make up
```

This starts:

- `desktop` on `127.0.0.1:3000`
- desktop control API on `127.0.0.1:8790`

### 3. Start the optional OpenClaw helper

If you want summaries:

```bash
make up-openclaw
```

Notes:

- This command reads the token from `~/.openclaw/openclaw.json`.
- The helper listens on `127.0.0.1:18789`.
- If you only want to verify the token source or print a fresh dashboard URL, run:

```bash
make openclaw-sync
```

### 4. Start the local API

In a new terminal:

```bash
source .venv/bin/activate
make dev-api
```

`make dev-api`:

- loads `.env` when present
- creates missing runtime directories
- starts FastAPI on `127.0.0.1:8788`
- points the API at `runtime/controller/controller.db`
- writes artifacts under `runtime/artifacts`
- shares recordings from `runtime/recordings`

### 5. Optional: start the macOS capture agent

If you want `This Mac` to appear in the start-capture form:

```bash
make macos-capture-up
```

This builds the ScreenCaptureKit helper if needed and starts `macos-capture-agent` as a background user service on `127.0.0.1:8791`.

Useful commands:

```bash
make macos-capture-status
make macos-capture-logs
make macos-capture-permissions
make macos-capture-down
```

On first use through `thirdeye.app`, macOS may ask for Screen & System Audio Recording permission. Grant it to `thirdeye`, quit and reopen the app if macOS asks, then refresh the target list in the controller UI. If you start the capture agent directly from Terminal with `make macos-capture-up`, macOS can still attribute permission to the Terminal/Python launch path.

## Access URLs

Once the stack is up:

- Controller API: [http://127.0.0.1:8788](http://127.0.0.1:8788)
- Controller API docs: [http://127.0.0.1:8788/docs](http://127.0.0.1:8788/docs)
- Isolated desktop: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Desktop agent health: [http://127.0.0.1:8790/health](http://127.0.0.1:8790/health)
- macOS capture agent health: [http://127.0.0.1:8791/health](http://127.0.0.1:8791/health)
- Optional OpenClaw health: [http://127.0.0.1:18789/healthz](http://127.0.0.1:18789/healthz)

## Verification

### Manual health checks

```bash
curl -fsS http://127.0.0.1:8788/api/health
curl -fsS http://127.0.0.1:8790/health
curl -fsS http://127.0.0.1:8788/api/settings/test/desktop
curl -fsS http://127.0.0.1:8791/health
```

If OpenClaw is enabled:

```bash
curl -fsS http://127.0.0.1:18789/healthz
curl -fsS http://127.0.0.1:8788/api/settings/test/openclaw
```

### Smoke test

After the app-managed services and optional desktop are running:

```bash
make smoke
```

The smoke test checks:

- controller API health
- desktop agent health
- desktop UI reachability
- session login
- controller settings health
- desktop integration
- Deepgram integration
- optional OpenClaw integration when enabled

## Choosing A Capture Target

The start form now supports two capture surfaces:

- `Isolated desktop`: the original Docker desktop workflow.
- `This Mac`: local macOS capture through ScreenCaptureKit.

When `This Mac` is selected, the controller loads grouped targets from `macos-capture-agent`:

- `Screens`
- `Apps`
- `Windows`

The UI requires an explicit local target before starting the job. The job metadata records both the backend and the selected target so recovery and stop actions return to the same backend later.

## Daily Development Workflow

On a normal day, the startup sequence is:

```bash
make macos-app-dev
```

This is the main workflow. It builds the macOS capture helper, starts the Tauri app, and lets the app manage the local Python services from `.venv`.

Optional, when you are running the services manually and need `This Mac` capture targets:

```bash
make macos-capture-up
```

Optional, when you need the isolated Docker desktop:

```bash
make up
```

Optional:

```bash
make up-openclaw
```

To stop the Docker services:

```bash
make down
```

## Testing

### Python tests

```bash
source .venv/bin/activate
make test
```

### Full source-built app tests

```bash
make test-all
```

## Start Capture Workflow

1. Open `thirdeye.app` and sign in with `CONTROLLER_USERNAME` and `CONTROLLER_PASSWORD`.
2. Click `Start Capture`.
3. Choose `This Mac` for a local screen, app, or window, or choose `Isolated desktop` if you started the optional Docker desktop.
4. Start playback yourself if needed.
5. The controller starts recording and the Deepgram relay in parallel.
6. Monitor the live transcript in the app.

## Runtime Data

The command-line development workflow stores state in the repo:

| Path | Contents |
| --- | --- |
| `runtime/desktop-config/` | Desktop container config |
| `runtime/recordings/` | Shared recording output |
| `runtime/artifacts/jobs/<job_id>/` | Final job artifacts |
| `runtime/controller/controller.db` | SQLite controller database |
| `runtime/controller-events/` | Controller event logs |

The macOS app workflow stores controller state, recordings, artifacts, logs, and capture runtime files under `~/Library/Application Support/thirdeye/`.

Final job artifacts are written to:

```text
runtime/artifacts/jobs/<job_id>/
  recording.mp4
  transcript.txt
  transcript.md
  transcript.json
  summary.md
  metadata.json
  deepgram-events.jsonl
  controller-events.jsonl
```

## License

This project is licensed for personal, non-commercial use only. See [LICENSE](LICENSE) for details.
