from __future__ import annotations

from pathlib import Path


def test_service_status_reports_core_macos_app_services(monkeypatch, tmp_path: Path) -> None:
    from core import local_services

    monkeypatch.setattr(
        local_services,
        "is_port_open",
        lambda port: port in {local_services.CONTROLLER_API_PORT, local_services.MACOS_CAPTURE_PORT},
    )

    status = local_services.service_status(runtime_root=tmp_path)

    assert status["runtime_root"] == str(tmp_path)
    assert status["controller_api_url"] == "http://127.0.0.1:8788"
    assert [report["name"] for report in status["reports"]] == [
        "Controller API",
        "This Mac capture",
        "Isolated desktop",
        "OpenClaw",
    ]
    assert status["reports"][0]["running"] is True
    assert status["reports"][1]["running"] is True
    assert status["reports"][2]["running"] is False


def test_start_services_uses_supervisor_without_starting_next_or_docker(monkeypatch, tmp_path: Path) -> None:
    from core import local_services

    calls: list[tuple[str, str]] = []
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "Makefile").write_text("help:\n", encoding="utf-8")
    (repo_root / "infra").mkdir()
    (repo_root / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(local_services, "is_port_open", lambda port: False)
    monkeypatch.setattr(
        local_services,
        "ensure_macos_capture_helper",
        lambda repo_root: repo_root / "services" / "macos-capture-agent" / "bin" / "helper",
    )
    monkeypatch.setattr(local_services, "wait_for_port_open", lambda port, name: None)

    def fake_spawn_service(*, repo_root: Path, runtime_root: Path, name: str, command: str) -> None:
        calls.append((name, command))

    def fake_run_shell(repo_root: Path, command: str) -> None:
        calls.append(("shell", command))

    monkeypatch.setattr(local_services, "spawn_service", fake_spawn_service)
    monkeypatch.setattr(local_services, "run_shell", fake_run_shell)

    result = local_services.start_services(repo_root=repo_root, runtime_root=tmp_path / "runtime", include_desktop=False)

    assert result["ok"] is True
    assert [name for name, _ in calls] == ["macos-capture-agent", "controller-api"]
    legacy_web_path = "apps" + "/web"
    assert all(legacy_web_path not in command for _, command in calls)
    assert all("docker compose" not in command for _, command in calls)


def test_start_services_passes_runtime_root_to_desktop_compose(monkeypatch, tmp_path: Path) -> None:
    from core import local_services

    calls: list[tuple[str, str]] = []
    repo_root = tmp_path / "repo"
    runtime_root = tmp_path / "runtime root"
    repo_root.mkdir()
    (repo_root / "Makefile").write_text("help:\n", encoding="utf-8")
    (repo_root / "infra").mkdir()
    (repo_root / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(local_services, "is_port_open", lambda port: False)
    monkeypatch.setattr(
        local_services,
        "ensure_macos_capture_helper",
        lambda repo_root: repo_root / "services" / "macos-capture-agent" / "bin" / "helper",
    )
    monkeypatch.setattr(local_services, "wait_for_port_open", lambda port, name: None)
    monkeypatch.setattr(
        local_services,
        "spawn_service",
        lambda *, repo_root, runtime_root, name, command: calls.append((name, command)),
    )
    monkeypatch.setattr(local_services, "run_shell", lambda repo_root, command: calls.append(("shell", command)))

    result = local_services.start_services(repo_root=repo_root, runtime_root=runtime_root, include_desktop=True)

    assert result["ok"] is True
    assert calls[0] == (
        "shell",
        f"THIRDEYE_RUNTIME_ROOT={local_services.shell_escape(runtime_root)} "
        "docker compose --env-file .env -f infra/compose.yaml up -d --remove-orphans",
    )


def test_start_services_restarts_supervised_macos_agent_after_permission_denial(monkeypatch, tmp_path: Path) -> None:
    from core import local_services

    calls: list[tuple[str, str] | tuple[str, int] | tuple[str, str, str]] = []
    repo_root = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    supervisor_dir = runtime_root / "supervisor"
    repo_root.mkdir()
    supervisor_dir.mkdir(parents=True)
    (repo_root / "Makefile").write_text("help:\n", encoding="utf-8")
    (repo_root / "infra").mkdir()
    (repo_root / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (supervisor_dir / "macos-capture-agent.pid").write_text("1234", encoding="utf-8")

    open_ports = {local_services.CONTROLLER_API_PORT, local_services.MACOS_CAPTURE_PORT}

    def fake_is_port_open(port: int) -> bool:
        return port in open_ports

    def fake_stop_supervised_service(selected_runtime_root: Path, name: str) -> None:
        calls.append(("stop", name))
        open_ports.discard(local_services.MACOS_CAPTURE_PORT)

    def fake_spawn_service(*, repo_root: Path, runtime_root: Path, name: str, command: str) -> None:
        calls.append(("spawn", name, command))
        if name == "macos-capture-agent":
            open_ports.add(local_services.MACOS_CAPTURE_PORT)

    monkeypatch.setattr(local_services, "is_port_open", fake_is_port_open)
    monkeypatch.setattr(
        local_services,
        "ensure_macos_capture_helper",
        lambda repo_root: repo_root / "services" / "macos-capture-agent" / "bin" / "helper",
    )
    monkeypatch.setattr(local_services, "macos_capture_permission_denied", lambda: True, raising=False)
    monkeypatch.setattr(local_services, "stop_supervised_service", fake_stop_supervised_service, raising=False)
    monkeypatch.setattr(local_services, "wait_for_port_closed", lambda port: calls.append(("wait", port)), raising=False)
    monkeypatch.setattr(local_services, "spawn_service", fake_spawn_service)

    result = local_services.start_services(repo_root=repo_root, runtime_root=runtime_root, include_desktop=False)

    assert result["ok"] is True
    assert calls[0] == ("stop", "macos-capture-agent")
    assert calls[1] == ("wait", local_services.MACOS_CAPTURE_PORT)
    assert calls[2][0:2] == ("spawn", "macos-capture-agent")


def test_start_services_fails_when_spawned_macos_agent_never_opens_port(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from core import local_services

    repo_root = tmp_path / "repo"
    runtime_root = tmp_path / "runtime"
    repo_root.mkdir()
    (repo_root / "Makefile").write_text("help:\n", encoding="utf-8")
    (repo_root / "infra").mkdir()
    (repo_root / "infra" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr(local_services, "is_port_open", lambda port: False)
    monkeypatch.setattr(
        local_services,
        "ensure_macos_capture_helper",
        lambda repo_root: repo_root / "services" / "macos-capture-agent" / "bin" / "helper",
    )
    monkeypatch.setattr(local_services, "spawn_service", lambda **kwargs: None)
    monkeypatch.setenv("THIRDEYE_SERVICE_STARTUP_TIMEOUT_SECONDS", "0.01")

    with pytest.raises(RuntimeError, match="macos-capture-agent did not start listening"):
        local_services.start_services(repo_root=repo_root, runtime_root=runtime_root, include_desktop=False)


def test_controller_api_command_uses_host_openclaw_gateway(tmp_path: Path) -> None:
    from core import local_services

    command = local_services.controller_api_command(tmp_path / "runtime")

    assert "OPENCLAW_BASE_URL=${LOCAL_OPENCLAW_BASE_URL:-http://127.0.0.1:18789}" in command
    assert command.index("set +a;") < command.index("OPENCLAW_BASE_URL=")


def test_doctor_report_uses_single_setup_contract(monkeypatch, tmp_path: Path) -> None:
    from core import local_services

    monkeypatch.setattr(local_services, "tool_available", lambda name: name in {"python3", "node", "npm"})

    report = local_services.doctor_report(repo_root=tmp_path, runtime_root=tmp_path / "runtime")

    assert report["ok"] is False
    assert {check["name"] for check in report["checks"]} >= {"python3", "node", "npm", "docker", "runtime directories"}
    assert next(check for check in report["checks"] if check["name"] == "runtime directories")["ok"] is False
