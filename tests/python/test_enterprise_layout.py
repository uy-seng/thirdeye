from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_repository_uses_enterprise_service_layout() -> None:
    expected_paths = [
        ROOT / "apps" / "package.json",
        ROOT / "apps" / "tauri" / "Cargo.toml",
        ROOT / "services" / "controller-api" / "src" / "api" / "main.py",
        ROOT / "services" / "controller-api" / "src" / "core" / "settings.py",
        ROOT / "services" / "controller-api" / "src" / "jobs" / "jobs.py",
        ROOT / "services" / "controller-api" / "src" / "transcripts" / "deepgram_client.py",
        ROOT / "services" / "desktop-agent" / "src" / "thirdeye_desktop_agent" / "main.py",
        ROOT / "services" / "macos-capture-agent" / "src" / "thirdeye_macos_capture" / "agent" / "main.py",
        ROOT / "packages" / "capture_contracts" / "contracts.py",
        ROOT / "infra" / "compose.yaml",
        ROOT / "infra" / "docker" / "desktop" / "Dockerfile",
        ROOT / "tests" / "python",
    ]

    for path in expected_paths:
        assert path.exists(), f"Expected enterprise layout path to exist: {path.relative_to(ROOT)}"

    legacy_paths = [
        ROOT / "controller" / "app",
        ROOT / "controller" / "web",
        ROOT / "controller" / "tests",
        ROOT / "apps" / "macos",
        ROOT / "services" / "controller" / "controller",
        ROOT / "services" / "controller-api" / "src" / "thirdeye_controller",
        ROOT / "services" / "controller-api" / "src" / "thirdeye_controller" / "app",
        ROOT / "services" / "desktop-agent" / "desktop",
        ROOT / "services" / "macos-capture-agent" / "macos_capture" / "agent",
        ROOT / "packages" / "capture-contracts",
        ROOT / "packages" / "capture-contracts" / "capture_contracts",
        ROOT / "packages" / "capture-contracts" / "src",
        ROOT / "packages" / "capture-contracts" / "thirdeye_capture_contracts",
        ROOT / "desktop" / "agent",
        ROOT / "macos_capture" / "agent",
        ROOT / "compose.yaml",
    ]

    for path in legacy_paths:
        assert not path.exists(), f"Legacy layout path should be removed: {path.relative_to(ROOT)}"
