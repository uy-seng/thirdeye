from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROMPTS_ROOT = ROOT / "prompts"


def test_application_prompt_files_live_under_root_prompts() -> None:
    expected_prompt_files = [
        "canonical_summary.txt",
        "openclaw_transcript_summary_instructions.txt",
        "openclaw_transcript_summary_input.txt",
        "live_summary_default.txt",
        "voice_note_summary_default.txt",
    ]

    missing = [name for name in expected_prompt_files if not (PROMPTS_ROOT / name).is_file()]

    assert missing == []


def test_backend_prompt_code_loads_files_instead_of_embedding_prompt_text() -> None:
    prompt_service_source = (ROOT / "services/controller-api/src/transcripts/prompt_service.py").read_text(encoding="utf-8")
    openclaw_source = (ROOT / "services/controller-api/src/integrations/openclaw_client.py").read_text(encoding="utf-8")

    assert "DEFAULT_CANONICAL_SUMMARY_PROMPT = " not in prompt_service_source
    assert "prompt: str = DEFAULT_CANONICAL_SUMMARY_PROMPT" not in prompt_service_source

    for line in (PROMPTS_ROOT / "canonical_summary.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            assert line not in prompt_service_source

    for prompt_file in ["openclaw_transcript_summary_instructions.txt", "openclaw_transcript_summary_input.txt"]:
        for line in (PROMPTS_ROOT / prompt_file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert line not in openclaw_source

    assert "render_prompt_template" in openclaw_source
