# OpenClaw Canonical Summary Design

**Date:** 2026-04-18

**Goal:** Remove the fake and legacy summary generation paths so canonical `summary.md` artifacts are always produced by the real OpenClaw-backed LLM flow.

## Current State

The codebase has two separate summary systems:

1. `CaptureRuntime.stop_capture()` in `controller/app/jobs.py` calls `Summarizer.summarize()` to write the canonical `summary.md`.
2. `TranscriptPromptService` in `controller/app/transcript_prompt_service.py` uses `OpenClawClient.generate_transcript_summary()` for transcript-prompt generation and for the `Re-run Summary` action.

The legacy `Summarizer` still supports a fake branch and a separate HTTP configuration surface (`SUMMARY_PROVIDER`, `SUMMARY_BASE_URL`, `SUMMARY_API_KEY`, `SUMMARY_MODEL`). Separately, `OpenClawClient.generate_transcript_summary()` also returns fake output when `FAKE_MODE=true`.

This means the application can appear to support LLM summaries while still producing fake summary output in both the stop flow and OpenClaw client flow.

## Approved Direction

Canonical summary generation will be unified onto the existing OpenClaw transcript summary path.

That means:

- `stop_capture()` will no longer use the legacy `Summarizer`.
- Canonical `summary.md` generation and `Re-run Summary` will both use `TranscriptPromptService.rewrite_canonical_summary()`.
- `OpenClawClient.generate_transcript_summary()` will always call the real OpenClaw LLM endpoint and will no longer short-circuit to fake output.
- The legacy summary configuration surface will be removed from settings and defaults.
- The `summary_model` job field will remain, but it will represent the OpenClaw summary model to avoid an unnecessary schema migration.

## Design

### 1. Unify canonical summary generation

`CaptureRuntime` will depend on `TranscriptPromptService` for canonical recap generation. After transcript compilation completes, the stop flow will call `rewrite_canonical_summary(job_id=job.id)` and persist the returned summary path on the job, instead of calling `self.summarizer.summarize(...)`.

This keeps one summary implementation for:

- canonical summary generation during stop
- manual canonical summary regeneration from the UI

The stop flow will continue to treat summary failures as stop failures, preserving the current operator-visible behavior and error propagation path.

### 2. Delete fake summary behavior

`OpenClawClient.generate_transcript_summary()` will stop checking `settings.fake_mode` for summary generation. `FAKE_MODE` may continue to affect desktop, Deepgram, and health behavior elsewhere in the app, but it will no longer affect summaries.

This keeps the meaning narrow and explicit: fake runtime helpers remain where needed for capture simulation, but summaries are always real LLM requests.

### 3. Remove the legacy summary client surface

The `Summarizer` class and its separate configuration path will be removed. Settings fields and environment variables that only exist to support that path will be removed from `controller/app/settings.py`.

The remaining summary configuration source will be:

- `OPENCLAW_BASE_URL`
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_SUMMARY_MODEL`
- `OPENCLAW_SUMMARY_TIMEOUT_SECONDS`

`summary_model` stored on a job will default to the OpenClaw summary model so existing responses and metadata stay structurally stable.

### 4. Testing strategy

Tests will be updated so the real contract is explicit:

- stop-flow tests will stub `runtime.transcript_prompts.rewrite_canonical_summary()` or `runtime.openclaw.generate_transcript_summary()`, not `runtime.capture.summarizer.summarize()`
- rerun-summary tests will continue asserting that the OpenClaw path is used
- any tests that rely on `fake-summary` defaults will be updated to expect the OpenClaw model instead

The regression focus is:

- stop writes `summary.md` through the unified OpenClaw-backed path
- rerun still writes the canonical summary correctly
- fake summary output is no longer reachable

## Files Expected To Change

- `controller/app/jobs.py`
- `controller/app/main.py`
- `controller/app/openclaw_client.py`
- `controller/app/settings.py`
- `controller/app/models.py`
- `controller/tests/conftest.py`
- `controller/tests/test_jobs.py`
- `controller/tests/test_transcript_summary_api.py`
- `controller/tests/test_openclaw_client.py`
- any docs or README references to fake or legacy summary configuration

## Error Handling

Summary generation will continue to fail closed:

- if OpenClaw returns an error, the stop flow will fail with the surfaced LLM error
- if OpenClaw returns no text, the existing `RuntimeError("OpenClaw LLM returned no text")` behavior remains valid

No silent fallback to fake summary output will remain.

## Non-Goals

- changing the structure of the canonical summary prompt
- changing notification delivery behavior
- removing `FAKE_MODE` from unrelated parts of the system
- introducing a database migration for `summary_model`
