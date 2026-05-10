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


def test_dynamic_desktop_dockerfile_uses_lsiopy_pip_and_only_installs_ffmpeg() -> None:
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
    assert '../config/openclaw.json:/seed/openclaw.json:ro' in compose
    assert '  openclaw_data:' not in compose
    assert 'name: thirdeye_' not in compose


def test_openclaw_restart_uses_thirdeye_compose_project_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".openclaw" / "openclaw.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"gateway":{"auth":{"token":"test-token"}}}\n', encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker-args.log"
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "${DOCKER_LOG}"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    openclaw = bin_dir / "openclaw"
    openclaw.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    openclaw.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "remediate_openclaw_gateway.sh"), "--restart"],
        env=os.environ
        | {
            "DOCKER_LOG": str(docker_log),
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    docker_calls = docker_log.read_text(encoding="utf-8").splitlines()
    assert (
        "compose --project-name infra -f infra/compose.yaml --profile openclaw down --remove-orphans"
        in docker_calls
    )
    assert (
        "compose --project-name thirdeye -f infra/compose.yaml --profile openclaw up -d --force-recreate --no-deps openclaw"
        in docker_calls
    )


def test_compose_does_not_enable_isolated_desktop_basic_auth() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CUSTOM_USER" not in compose
    assert "PASSWORD: ${DESKTOP_PASSWORD}" not in compose
    assert "DESKTOP_USER" not in env_example
    assert "DESKTOP_PASSWORD" not in env_example


def test_compose_no_longer_runs_fixed_desktop_service() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")

    assert "\n  desktop:" not in compose
    assert "BROWSER_" + "CDP_URL" not in compose
    assert "/opt/capture/" + "desktop/scripts/healthcheck.sh" not in compose
    assert 'depends_on:' not in compose


def test_compose_openclaw_helper_is_the_only_service() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")

    assert "services:\n  openclaw:" in compose
    assert "profiles:" in compose
    assert "start_period: 90s" in compose


def test_architecture_doc_describes_local_first_controller_topology() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "three containers" not in architecture
    assert "- `controller`" not in architecture
    assert "`controller-api`" in architecture
    legacy_web_name = "`controller-" + "web`"
    assert legacy_web_name not in architecture
