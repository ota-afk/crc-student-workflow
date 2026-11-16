# Credits: third-party code, AI-assisted code, and reused patterns

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

- STU-D02-ENG (Nov 13 2026): school/campus research uses the official
  [DHS SEVP School Search](https://studyinthestates.dhs.gov/school-search)
  and the [NCES IPEDS HD2024 directory](https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip).
  Classification crosswalks also use the official college/district sources listed in
  `docs/school-list-notes.md` and the inclusion file.
  ChatGPT/Codex assisted with the importer, source crosswalks, data preparation,
  documentation and validation. Human review and school-specific workflow verification
  remain pending; AI assistance does not count as a human source checker.

- STU-D02-BE (Nov 13 2026): AI assistance (Claude Code) drafted the rules-file models
  (`src/student_workflow/rules.py`), the dependency resolver (`src/student_workflow/engine.py`),
  their tests (`tests/test_engine.py`), and the matching `docs/contract.md` sections.
  Reviewed by the BE owner.

- STU-D02-BE review fixes (Nov 13 2026): Codex preserved source verification in the shared
  contract, added school scoping and CSV search support, strengthened two-person
  evidence checks, and added regression tests and documentation. The CRC rule's internal
  school ID was set to `crc`; its statement and verification state were not changed.

- STU-D03-FE (Nov 13 2026): Codex assisted with task details, session-only document
  checkboxes, dated sources, a sample assistant preview and proposed API adapter,
  interaction tests, and documentation. Live BE/AI integration remains pending.

- STU-D02-ENG rules (Nov 14 2026): ChatGPT/Codex assisted with converting official-source
  research into task rules, preparing source notes and the handoff, and validating against
  the merged BE resolver. Sources include USAGov, ICE/DHS, California DMV, CFPB and CRC;
  exact pages and excerpts are recorded in `docs/sources.md` and `data/rules/rules.json`.
  Integration tests cover the actual task data. AI assistance does not count as a human
  source checker; verification states and the existing CRC fee-rule checker metadata
  are preserved.

- STU-D03-BE (Nov 15 2026): AI assistance (Claude Code) drafted the live workflow endpoints
  (`POST /workflow`, `POST /tasks/{task_id}/complete`, `POST /tasks/{task_id}/resolve`), the
  `awaiting_reply` state in the resolver, the `X-API-Key` check, the rate limit (slowapi),
  their tests (`tests/test_api.py`, `tests/conftest.py`, additions to `tests/test_engine.py`),
  and the matching `docs/contract.md` and README sections. A second Claude Code agent reviewed
  the change before it was opened. Reviewed by the BE owner.

- STU-D04-FE (Nov 15 2026): Codex assisted with the labeled email template preview,
  native copy control, workflow loading/validation/error handling, regression tests
  and Render deployment preparation. No live email service or deployment is claimed.

- STU-D03-FE review (Nov 15 2026): Codex assisted with explicit source/blocker
  verification, state/school search preparation, task navigation, readiness inventory
  dialog, profile-context resets, task-labeled chat, tests and documentation. Live
  workflow/actions remain blocked on the BE/AI contract and implementation.

- STU-D04-BE (Nov 16 2026): AI assistance (Claude Code) drafted the end-to-end smoke test
  (`scripts/smoke_test.py`) and its CI job, the Render Blueprint (`render.yaml`),
  `docs/deploy.md`, and the rate-limit change that gives the dashboard's key its own
  allowance. Render's behaviour was checked against its official docs (render.com/docs).
  A second Claude Code agent reviewed the change before it was opened. Reviewed by the BE
  owner.

- STU-D03-BE merge review (Nov 16 2026): AI assistance (Codex) addressed the requested
  performance fix with linear duplicate counting and a 1,000-item limit on each profile
  progress list. Added API regression tests for early rejection and the limit boundary,
  and documented the limits in `docs/contract.md`. Pending the BE owner's review.
