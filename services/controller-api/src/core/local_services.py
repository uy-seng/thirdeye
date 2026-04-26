from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.settings import THIRDEYE_APPLICATION_SUPPORT_ROOT


CONTROLLER_API_PORT = 8788
MACOS_CAPTURE_PORT = 8791
DESKTOP_AGENT_PORT = 8790
OPENCLAW_PORT = 18789
PYTHON_SERVICE_DIRS = (
    Path("services/controller-api/src"),
    Path("services/desktop-agent/src"),
    Path("services/macos-capture-agent/src"),
    Path("packages"),
)
COMPOSE_FILE = Path("infra/compose.yaml")
MACOS_CAPTURE_HELPER_RELATIVE_PATH = Path("services/macos-capture-agent/bin/macos_capture_helper")
BUILD_REPO_ROOT: str | None = os.environ.get("THIRDEYE_REPO_ROOT")


def application_support_root() -> Path:
    return Path(os.environ.get("THIRDEYE_RUNTIME_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT))).expanduser()


def discover_repo_root(start: Path | None = None) -> Path:
    env_root = os.environ.get("THIRDEYE_REPO_ROOT") or BUILD_REPO_ROOT
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.joinpath("Makefile").exists() and candidate.joinpath(COMPOSE_FILE).exists():
            return candidate

    selected_start = (start or Path.cwd()).resolve()
    for ancestor in (selected_start, *selected_start.parents):
        if ancestor.joinpath("Makefile").exists() and ancestor.joinpath(COMPOSE_FILE).exists():
            return ancestor
    raise RuntimeError("Set THIRDEYE_REPO_ROOT to the repository folder.")


def runtime_dirs(runtime_root: Path) -> list[Path]:
    return [
        runtime_root / "controller",
        runtime_root / "controller-events",
        runtime_root / "artifacts",
        runtime_root / "recordings",
        runtime_root / "logs",
        runtime_root / "macos-capture-runtime",
        runtime_root / "supervisor",
    ]


def ensure_runtime_dirs(runtime_root: Path) -> None:
    for directory in runtime_dirs(runtime_root):
        directory.mkdir(parents=True, exist_ok=True)


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def service_report(name: str, port: int) -> dict[str, Any]:
    running = is_port_open(port)
    return {
        "name": name,
        "running": running,
        "detail": f"{'Listening' if running else 'Not listening'} on 127.0.0.1:{port}",
    }


def supervisor_pid_file(runtime_root: Path, name: str) -> Path:
    return runtime_root / "supervisor" / f"{name}.pid"


def supervised_service_pid(runtime_root: Path, name: str) -> int | None:
    pid_file = supervisor_pid_file(runtime_root, name)
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def stop_supervised_service(runtime_root: Path, name: str) -> None:
    pid_file = supervisor_pid_file(runtime_root, name)
    pid = supervised_service_pid(runtime_root, name)
    if pid is not None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    pid_file.unlink(missing_ok=True)


def wait_for_port_closed(port: int, timeout_seconds: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_port_open(port):
            return
        time.sleep(0.05)


def wait_for_port_open(port: int, name: str, timeout_seconds: float | None = None) -> None:
    timeout = timeout_seconds
    if timeout is None:
        timeout = float(os.environ.get("THIRDEYE_SERVICE_STARTUP_TIMEOUT_SECONDS", "10.0"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_port_open(port):
            return
        time.sleep(0.05)
    raise RuntimeError(f"{name} did not start listening on 127.0.0.1:{port}")


def macos_capture_permission_denied() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{MACOS_CAPTURE_PORT}/targets", timeout=2.0):
            return False
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return "screen_recording_permission_denied" in body
    except urllib.error.URLError:
        return False


def service_status(runtime_root: Path | None = None) -> dict[str, Any]:
    selected_runtime_root = runtime_root or application_support_root()
    return {
        "runtime_root": str(selected_runtime_root),
        "controller_api_url": f"http://127.0.0.1:{CONTROLLER_API_PORT}",
        "reports": [
            service_report("Controller API", CONTROLLER_API_PORT),
            service_report("This Mac capture", MACOS_CAPTURE_PORT),
            service_report("Isolated desktop", DESKTOP_AGENT_PORT),
            service_report("OpenClaw", OPENCLAW_PORT),
        ],
    }


def shell_escape(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "'\\''") + "'"


def service_pythonpath(repo_root: Path) -> str:
    return ":".join(str(repo_root / directory) for directory in PYTHON_SERVICE_DIRS)


def pythonpath_assignment(repo_root: Path) -> str:
    return "PYTHONPATH='" + service_pythonpath(repo_root).replace("'", "'\\''") + "' "


def run_shell(repo_root: Path, command: str) -> None:
    result = subprocess.run(["/bin/bash", "-lc", command], cwd=repo_root, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"`{command}` exited with status {result.returncode}")


def spawn_service(*, repo_root: Path, runtime_root: Path, name: str, command: str) -> None:
    ensure_runtime_dirs(runtime_root)
    log_path = runtime_root / "logs" / f"{name}.log"
    pid_path = runtime_root / "supervisor" / f"{name}.pid"
    stdout = log_path.open("ab")
    stderr = stdout
    child = subprocess.Popen(
        ["/bin/bash", "-lc", command],
        cwd=repo_root,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    pid_path.write_text(str(child.pid), encoding="utf-8")


def ensure_macos_capture_helper(repo_root: Path) -> Path:
    configured = os.environ.get("MACOS_CAPTURE_HELPER_BIN")
    if configured:
        helper = Path(configured).expanduser()
        if helper.exists():
            return helper
    helper = repo_root / MACOS_CAPTURE_HELPER_RELATIVE_PATH
    if helper.exists():
        return helper
    run_shell(repo_root, "./scripts/build_macos_capture_helper.sh")
    if helper.exists():
        return helper
    raise RuntimeError(f"macOS capture helper is missing at {helper}")


def controller_api_command(runtime_root: Path, repo_root: Path | None = None) -> str:
    selected_repo_root = repo_root or discover_repo_root()
    return (
        "set -a; [ ! -f .env ] || . ./.env; set +a; "
        f"{pythonpath_assignment(selected_repo_root)}"
        f"CONTROLLER_BASE_URL=http://127.0.0.1:{CONTROLLER_API_PORT} "
        "CONTROLLER_CORS_ORIGINS=http://127.0.0.1:1420,tauri://localhost "
        f"CONTROLLER_DB_PATH={shell_escape(runtime_root / 'controller' / 'controller.db')} "
        f"ARTIFACTS_ROOT={shell_escape(runtime_root / 'artifacts')} "
        f"RECORDINGS_ROOT={shell_escape(runtime_root / 'recordings')} "
        f"CONTROLLER_EVENTS_ROOT={shell_escape(runtime_root / 'controller-events')} "
        f"MACOS_CAPTURE_BASE_URL=http://127.0.0.1:{MACOS_CAPTURE_PORT} "
        f"OPENCLAW_BASE_URL=${{LOCAL_OPENCLAW_BASE_URL:-http://127.0.0.1:{OPENCLAW_PORT}}} "
        ".venv/bin/uvicorn api.main:create_app --factory --host 127.0.0.1 --port 8788"
    )


def macos_capture_command(runtime_root: Path, helper_bin: Path, repo_root: Path | None = None) -> str:
    selected_repo_root = repo_root or discover_repo_root()
    return (
        "set -a; [ ! -f .env ] || . ./.env; set +a; "
        f"{pythonpath_assignment(selected_repo_root)}"
        f"MACOS_CAPTURE_RUNTIME_DIR={shell_escape(runtime_root / 'macos-capture-runtime')} "
        f"MACOS_CAPTURE_HELPER_BIN={shell_escape(helper_bin)} "
        "PYTHONUNBUFFERED=1 "
        ".venv/bin/python -m uvicorn thirdeye_macos_capture.agent.main:app --host 127.0.0.1 --port 8791"
    )


def start_services(*, repo_root: Path | None = None, runtime_root: Path | None = None, include_desktop: bool = False) -> dict[str, Any]:
    selected_repo_root = repo_root or discover_repo_root()
    selected_runtime_root = runtime_root or application_support_root()
    ensure_runtime_dirs(selected_runtime_root)
    helper_bin = ensure_macos_capture_helper(selected_repo_root)

    if include_desktop:
        run_shell(
            selected_repo_root,
            f"THIRDEYE_RUNTIME_ROOT={shell_escape(selected_runtime_root)} "
            f"docker compose --env-file .env -f {COMPOSE_FILE.as_posix()} up -d --remove-orphans",
        )

    if (
        is_port_open(MACOS_CAPTURE_PORT)
        and supervised_service_pid(selected_runtime_root, "macos-capture-agent") is not None
        and macos_capture_permission_denied()
    ):
        stop_supervised_service(selected_runtime_root, "macos-capture-agent")
        wait_for_port_closed(MACOS_CAPTURE_PORT)

    if not is_port_open(MACOS_CAPTURE_PORT):
        spawn_service(
            repo_root=selected_repo_root,
            runtime_root=selected_runtime_root,
            name="macos-capture-agent",
            command=macos_capture_command(selected_runtime_root, helper_bin, selected_repo_root),
        )
        wait_for_port_open(MACOS_CAPTURE_PORT, "macos-capture-agent")

    if not is_port_open(CONTROLLER_API_PORT):
        spawn_service(
            repo_root=selected_repo_root,
            runtime_root=selected_runtime_root,
            name="controller-api",
            command=controller_api_command(selected_runtime_root, selected_repo_root),
        )
        wait_for_port_open(CONTROLLER_API_PORT, "controller-api")

    return {
        "ok": True,
        "detail": "Local services are starting.",
        "runtime_root": str(selected_runtime_root),
        "controller_api_url": f"http://127.0.0.1:{CONTROLLER_API_PORT}",
    }


def stop_services(*, runtime_root: Path | None = None, include_desktop: bool = False, repo_root: Path | None = None) -> dict[str, Any]:
    selected_runtime_root = runtime_root or application_support_root()
    supervisor_dir = selected_runtime_root / "supervisor"
    for pid_file in supervisor_dir.glob("*.pid"):
        stop_supervised_service(selected_runtime_root, pid_file.stem)

    if include_desktop:
        run_shell(
            repo_root or discover_repo_root(),
            f"THIRDEYE_RUNTIME_ROOT={shell_escape(selected_runtime_root)} "
            f"docker compose --env-file .env -f {COMPOSE_FILE.as_posix()} down",
        )

    return {
        "ok": True,
        "detail": "Local services started by thirdeye were stopped.",
        "runtime_root": str(selected_runtime_root),
    }


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def doctor_report(*, repo_root: Path | None = None, runtime_root: Path | None = None) -> dict[str, Any]:
    selected_runtime_root = runtime_root or application_support_root()
    checks = [
        {"name": "python3", "ok": tool_available("python3"), "detail": "Required for setup and tests."},
        {"name": "node", "ok": tool_available("node"), "detail": "Required for the Tauri frontend."},
        {"name": "npm", "ok": tool_available("npm"), "detail": "Required for JavaScript dependencies."},
        {"name": "docker", "ok": tool_available("docker"), "detail": "Optional for isolated desktop capture."},
        {
            "name": "runtime directories",
            "ok": all(directory.exists() for directory in runtime_dirs(selected_runtime_root)),
            "detail": str(selected_runtime_root),
        },
    ]
    return {"ok": all(check["ok"] for check in checks if check["name"] != "docker"), "checks": checks}


def setup_workspace(*, repo_root: Path | None = None, runtime_root: Path | None = None) -> dict[str, Any]:
    selected_repo_root = repo_root or discover_repo_root()
    selected_runtime_root = runtime_root or application_support_root()
    ensure_runtime_dirs(selected_runtime_root)
    if not selected_repo_root.joinpath(".env").exists():
        shutil.copyfile(selected_repo_root / ".env.example", selected_repo_root / ".env")
    if not selected_repo_root.joinpath(".venv").exists():
        run_shell(selected_repo_root, "python3 -m venv .venv")
    run_shell(selected_repo_root, ".venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt")
    run_shell(selected_repo_root, "cd apps && npm install")
    return {"ok": True, "detail": "Workspace setup complete.", "runtime_root": str(selected_runtime_root)}


def _print(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        print(payload.get("detail") or json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="thirdeye local service supervisor")
    parser.add_argument("command", choices=["start", "stop", "status", "doctor", "setup"])
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--desktop", action="store_true", help="Include optional Docker desktop services.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "start":
            payload = start_services(repo_root=args.repo_root, runtime_root=args.runtime_root, include_desktop=args.desktop)
        elif args.command == "stop":
            payload = stop_services(repo_root=args.repo_root, runtime_root=args.runtime_root, include_desktop=args.desktop)
        elif args.command == "status":
            payload = service_status(runtime_root=args.runtime_root)
        elif args.command == "doctor":
            payload = doctor_report(repo_root=args.repo_root, runtime_root=args.runtime_root)
        else:
            payload = setup_workspace(repo_root=args.repo_root, runtime_root=args.runtime_root)
    except Exception as exc:
        payload = {
            "ok": False,
            "detail": str(exc),
            "runtime_root": str(args.runtime_root or application_support_root()),
        }
        _print(payload, as_json=args.json)
        return 1

    _print(payload, as_json=args.json)
    return 0 if payload.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
