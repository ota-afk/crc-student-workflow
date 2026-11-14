# Credits: third-party code, AI-assisted code, and reused patterns

- STU-D03-FE (Nov 13 2026): Codex assisted with task details, session-only document
  checkboxes, dated sources, a sample assistant preview and proposed API adapter,
  interaction tests, and documentation. Live BE/AI integration remains pending.

- Day 1 skeleton (Nov 11 2026): the files were created from the team's Final Repo Setup Guide
  with AI assistance (Claude Code), which ran the setup commands and wrote the README.
- STU-D01-BE (Nov 12 2026): AI assistance (Claude Code) drafted `docs/contract.md`, the README's
  "How we work" section, and added beautifulsoup4 to the dependencies. Reviewed by the BE owner.
- STU-D01-BE review (Nov 12 2026): Codex reviewed the branch and revised `docs/contract.md`
  to clarify sample data, model fields and missing values, current endpoint behavior, and
  proposed request details.
- STU-D01-AI-setup (Nov 12 2026): ChatGPT assisted with drafting
  `scripts/smoke_test_openai.py` and `docs/ai-data-policy.md`.
  The smoke test uses the OpenAI Python SDK, Pydantic, and python-dotenv.
  A local live test with `gpt-6-luna` passed schema validation and
  classification for a synthetic California ID request.
  Application-wide privacy and guardrail enforcement remains future work.
- STU-D01-FE (Nov 12 2026): AI assistance (Antigravity with Gemini) created the Profile,
  Workflow, and Readiness dashboard views and test suite in `app/streamlit_app.py` and
  `tests/test_streamlit.py`.
- STU-D02-FE (Nov 12 2026): AI assistance (Antigravity with Gemini, and Claude) addressed
  review items for blocker-aware verification notes, oldest evidence date display,
  unsourced task verification states, contextual gap labels, whitespace cleanup,
  dynamic test counts, and regression tests.
- STU-D01-AI-followup (Nov 13 2026): ChatGPT assisted with the README smoke-test
  instructions, environment-variable support, student ID policy clarification,
  and cleanup following PR #8 review.
