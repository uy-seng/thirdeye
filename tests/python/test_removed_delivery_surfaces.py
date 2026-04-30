from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".py", ".rs", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml"}


def test_runtime_code_has_no_removed_delivery_surfaces() -> None:
    checked_paths = [
        ROOT / "services/controller-api/src",
        ROOT / "apps/src",
        ROOT / "apps/tauri/src",
        ROOT / ".env.example",
        ROOT / "docs/architecture.md",
    ]
    banned_terms = [
        "notify" + "_" + "e" + "mail",
        "sm" + "tp",
        "em" + "ail delivery",
        "em" + "ail,",
    ]

    offenders: list[str] = []
    for path in checked_paths:
        files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file() and item.suffix in TEXT_SUFFIXES]
        for file_path in files:
            content = file_path.read_text(encoding="utf-8").lower()
            for term in banned_terms:
                if term in content:
                    offenders.append(f"{file_path.relative_to(ROOT)} contains {term}")

    assert offenders == []
