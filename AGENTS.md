# Frontend Guidelines

- Use `shadcn/ui` as the default source for UI components.
- Default to a black-and-white visual theme.
- If the background is black, use white text.
- If the background is white, use black text.
- Keep badges and supporting UI elements colorful by default. Do not default badges, tags, highlights, or similar components to only black and white.
- Prioritize user experience in layouts, flows, states, and copy.
- Use plain, clear, user-friendly language in the frontend. Avoid technical wording, engineering jargon, and internal system terms in anything users read.

## Session Logs

- When using the `log-session-work` skill in this repository, write session logs under `logs/` at the project root.
- Run the session log script from the repository root and pass `--log-dir logs` instead of using the default `.codex/session-logs/` location.
- Keep log entries concise and focused on visible actions, decisions, commands, files, outcomes, and short rationale.

## Capture Debug Logs

- Controller debugging artifacts are exposed through the app artifact API but live under the configured logs root, normally `runtime/logs/jobs/{job_id}/`.
- For a capture, look there for `controller-events.jsonl`, `deepgram-events.jsonl`, and `transcript.json`.
- The user-facing transcript file remains under the artifact root as `transcript.md`.
- `metadata.json` is an internal file only and must not be exposed as a downloadable artifact or frontend item.
