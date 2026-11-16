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
- STU-D02-AI (Nov 13 2026): AI assistance (Claude) drafted `src/student_workflow/ai_assistant.py`
  and `tests/test_ai_assistant.py` (intent mapping with Structured Outputs, DSO referral for
  high-risk questions, and tests that use a fake model). It follows the client setup in
  `scripts/smoke_test_openai.py`. The high-risk phrase list is a first draft. Reviewed and run
  by the AI owner.

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

- STU-D02-ENG rules (Nov 14 2026): ChatGPT/Codex assisted with converting official-source
  research into task rules, preparing source notes and the handoff, and validating against
  the merged BE resolver. Sources include USAGov, ICE/DHS, California DMV, CFPB and CRC;
  exact pages and excerpts are recorded in `docs/sources.md` and `data/rules/rules.json`.
  Integration tests cover the actual task data. AI assistance does not count as a human
  source checker; verification states and the existing CRC fee-rule checker metadata
  are preserved.
