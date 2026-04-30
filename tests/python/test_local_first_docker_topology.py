from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_export_artifacts_script_copies_from_host_runtime(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    source = runtime_root / "artifacts" / "jobs" / "job-123" / "summary.md"
    source.parent.mkdir(parents=True)
    source.write_text("summary\n", encoding="utf-8")
    destination = tmp_path / "exported-artifacts"

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "export_artifacts.sh"), str(destination)],
        env=os.environ | {"RUNTIME_ROOT": str(runtime_root)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (destination / "jobs" / "job-123" / "summary.md").read_text(encoding="utf-8") == "summary\n"


def test_desktop_dockerfile_uses_lsiopy_pip_and_only_installs_ffmpeg() -> None:
    dockerfile = (ROOT / "infra" / "docker" / "desktop" / "Dockerfile").read_text(encoding="utf-8")

    assert "apt-get install -y --no-install-recommends ffmpeg" in dockerfile
    assert "python3-pip" not in dockerfile
    assert "pulseaudio-utils" not in dockerfile
    assert "curl" not in dockerfile
    assert "RUN /lsiopy/bin/pip3 install --no-cache-dir" in dockerfile


def test_compose_uses_thirdeye_project_identity() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert 'COMPOSE_PROJECT_NAME=thirdeye' in env_example
    assert '  capture_net:' in compose
    assert '${HOME}/.openclaw:/home/node/.openclaw' in compose
    assert '  openclaw_data:' not in compose
    assert 'name: thirdeye_' not in compose


def test_compose_does_not_enable_isolated_desktop_basic_auth() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CUSTOM_USER" not in compose
    assert "PASSWORD: ${DESKTOP_PASSWORD}" not in compose
    assert "DESKTOP_USER" not in env_example
    assert "DESKTOP_PASSWORD" not in env_example


def test_compose_mounts_desktop_recordings_from_configured_runtime_root() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert '"${THIRDEYE_RUNTIME_ROOT:-../runtime}/desktop-config:/config"' in compose
    assert '"${THIRDEYE_RUNTIME_ROOT:-../runtime}/recordings:/recordings"' in compose
    assert 'THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" $(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" up -d --remove-orphans' in makefile
    assert "$(COMPOSE) --env-file .env -f" in makefile


def test_compose_desktop_healthcheck_supports_old_and_new_agent_paths() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")

    assert "CMD-SHELL" in compose
    assert "/opt/capture/services/desktop-agent/scripts/healthcheck.sh" in compose
    assert "/opt/capture/desktop/scripts/healthcheck.sh" in compose


def test_architecture_doc_describes_local_first_controller_topology() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "three containers" not in architecture
    assert "- `controller`" not in architecture
    assert "`controller-api`" in architecture
    legacy_web_name = "`controller-" + "web`"
    assert legacy_web_name not in architecture
