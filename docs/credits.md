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

- STU-D05-BE (Nov 16 2026): AI assistance (Claude Code) drafted the warm-up script
  (`scripts/warm_up.py`), the git-history key audit (`scripts/audit_secrets.py`) and its tests,
  the unverified-rules warning in `scripts/check_no_sample.py`, `docs/release-checklist.md`
  and the README updates, and ran the audit recorded there. A second Claude Code agent
  reviewed the change before it was opened. Reviewed by the BE owner.

- STU-D05-BE follow-up (Nov 16 2026): AI assistance (Codex) changed the rate limit to one
  allowance shared across all endpoints and task IDs (`src/student_workflow/api.py`), made the
  key audit (`scripts/audit_secrets.py`) recognize digit-free and quoted literal secrets and
  Render `key:`/`value:` pairs while skipping placeholders and code references, and added
  regression tests (`tests/test_api.py`, `tests/test_audit_secrets.py`). AI assistance
  (Claude Code) updated `docs/contract.md`, `README.md`, `docs/deploy.md` and
  `docs/release-checklist.md`: what is on `main` versus in review, real request and response
  examples generated from the code, the readiness and AI-integration gaps, the enrollment-date
  proposal, and the audit's limits. The audit is a heuristic check, not proof that no secret
  or personal data is present. Pending the BE owner's review.

- STU-D05-BE-before-you-go (Nov 16 2026): AI assistance (Claude Code) drafted support for
  cited visit details: the rules-file `before_you_go` models (`src/student_workflow/rules.py`),
  the school filter and the additive `citations` in the resolver (`engine.py`, `contract.py`,
  `schools.py`), their tests (`tests/test_engine.py`) and the matching `docs/contract.md`
  sections. It was tested against ENG's draft rules with visit details, which is not part of
  this change. A second Claude Code agent reviewed the change, and its findings were fixed.
  Pending the BE owner's review.

- STU-D05-BE-before-you-go merge review (Nov 16 2026): AI assistance (Codex) kept rules
  cited only by visit details from adding timing blockers, while preserving their sources
  and guidance. Added a regression test in `tests/test_engine.py` and corrected the branch
  status table in `docs/contract.md`. Pending the BE owner's review.

- STU-D03-BE merge review (Nov 16 2026): AI assistance (Codex) addressed the requested
  performance fix with linear duplicate counting and a 1,000-item limit on each profile
  progress list. Added API regression tests for early rejection and the limit boundary,
  and documented the limits in `docs/contract.md`. Pending the BE owner's review.

- STU-D03-ENG content (Nov 14 2026): ChatGPT/Codex assisted with official-source research,
  before-you-go content and separate student-facing wording for California REAL ID and CRC arrival reporting, source notes
  and compatibility checks against the existing BeforeYouGo model. Current source
  retrieval is recorded separately from the August demo dates. Codex also prepared the cited rule entries and ran integration checks. Human review
  of the visit details and frontend citation rendering remain pending.
- STU-D05-BE-docs-status (Nov 16 2026): AI assistance (Claude Code) updated the status wording
  in `docs/contract.md`, `README.md`, `docs/deploy.md` and `docs/release-checklist.md` after
  #20, #21 and #22 merged. Documentation only. Pending the BE owner's review.
- STU-D04-AI (Nov 16 2026): AI assistance (Claude) drafted `scripts/run_ai_questions.py`,
  `data/ai_test_questions.json`, `docs/cost-and-scale.md` and `docs/ai-readme-section.md`.
  The English word-list bug was found by running the real model. Token numbers are measured
  by the runner; the price is from OpenAI's pricing page.

- STU-D03-AI (Nov 16 2026): AI assistance (Codex) drafted the citation validator,
  engine-grounded task explanations, placeholder email drafts, and regression tests
  in `src/student_workflow/ai_day3.py` and `tests/test_ai_day3.py`.

- PR #15 pre-merge review (Nov 16 2026): Codex assisted with teammate-comment
  verification, SEVIS-status and tuition-wording regressions, rules-derived risk
  in the manual evaluator, and intent contract corrections.

- STU-D06-FE-assistant (Nov 17 2026): AI assistance (Claude Code) connected the dashboard's
  Assistant tab to `POST /assistant` (#32) in `src/student_workflow/frontend.py`,
  `src/student_workflow/frontend_views.py` and `app/streamlit_app.py`, with the same key and
  timeout as #30, the workflow's `as_of` and progress, and a timeout message. Updated the
  assistant tests and added round-trip tests in `tests/test_live_api.py`. Done by BE in FE's
  files at the owner's request. Pending the BE owner's review.

- Flyover frontend (Nov 17 2026): the user supplied the logo, page sketches and
  travel photo references. Codex implemented the travel layout, backend-connected
  sequential workflow, readiness and session-only handoff template. The built-in
  imagegen tool generated the three city illustrations; prompts and provenance
  are recorded in `app/assets/flyover/README.md`.
- Flyover revision (Nov 17 2026): Claude restyled both pages to the user's sketches
  (sticky header, departures-board step title, readiness tables, quote card), drew the
  low-poly airplane as SVG, and built the scroll-driven flight into Airshow and its
  handoff template.

- STU-D06-BE-flyover-live (Nov 17 2026): AI assistance (Claude Code) connected Flyover to the
  live API: "Resolve blocker" with the API's email draft, and "Ask Airshow" on
  `POST /assistant`, in `src/student_workflow/flyover.py` and `flyover_client.py` (FE's
  files, at the owner's request). Added `tests/test_flyover_live_api.py` and client tests;
  updated two Airshow wording tests. Pending FE's review.

- STU-D06-FE-completion-feedback (Nov 17 2026): AI assistance (Claude Code) routed Flyover's
  "Mark this step completed" through the status selector's success path (`_record_update` in
  `src/student_workflow/flyover.py`, FE's file, at the owner's request), so both give the same
  message and one-time confetti. Tests in `tests/test_flyover_live_api.py`. Pending FE review.

- STU-D06-FE-contrast-fix (Nov 17 2026): AI assistance (Claude Code) measured every colour pair
  in `app/assets/flyover/style.css` (FE's file, at the owner's request) and fixed the seven
  below the WCAG minimum: header AI text, hover, settings icon and focus ring, the step
  label, the Next button and the quote footer. `tests/test_flyover_contrast.py` checks them
  from the stylesheet itself. Pending FE review.

- STU-D06-FE-other-office (Nov 17 2026): AI assistance (Claude Code) added the "Office name"
  field for "Another office" in Flyover's handoff (`src/student_workflow/flyover.py`, FE's
  file, under the team's advance approval of the v2 plan), with Markdown-safe export and
  tests in `tests/test_flyover_app.py`.

- STU-D06-BE-assistant-page-context (Nov 17 2026): AI assistance (Claude Code) added the
  optional `page_context` hint to `POST /assistant` (`contract.py`, `assistant.py`,
  `docs/contract.md`) and its tests in `tests/test_api_assistant.py`.

- STU-D06-FE-airshow-popup (Nov 17 2026): AI assistance (Claude Code) moved Flyover's live chat
  into an "AI Help" dropdown (`st.popover`) under a new logo traced from the owner's sketch
  (`app/assets/flyover/ai-help-icon.svg`, `ai-help.svg`), sending `page_context`; the
  Airshow section is now the template handoff only. Files: `flyover.py`, `flyover_art.py`,
  `flyover_client.py`, `style.css` (FE's, under the team's advance approval of the v2 plan),
  tests and READMEs.

- STU-D06-FE-chat-loading (Nov 17 2026): AI assistance (Claude Code) moved the AI Help chat's
  request out of the Send callback into the redraw, under an "Airshow is thinking…" spinner,
  and made the question box multi-line (`src/student_workflow/flyover.py`). Tests in
  `tests/test_flyover_live_api.py`.

- STU-D06-FE-fresh-start (Nov 17 2026): AI assistance (Claude Code) made Flyover start a new
  visitor with no completed steps (`fetch_fresh_workflow` in `flyover_client.py`, used by
  `flyover.py`), instead of the shared demo's two completed tasks. Tests in
  `tests/test_flyover.py` and `tests/test_flyover_live_api.py`.

- STU-D06-FE-task-order (Nov 17 2026): AI assistance (Claude Code) added Flyover's task queue
  (`task_queue` in `flyover_state.py`: Required first, prerequisites before what needs them
  and inheriting its priority, then Ready/In Progress/Blocked) and the "Now" / "Up next"
  cards in Before you take off (`flyover.py`, `style.css`). Tests in `tests/test_flyover.py`
  and `tests/test_flyover_live_api.py`.

- STU-D06-BE-assistant-fallback (Nov 17 2026): AI assistance (Claude Code) added one intent
  retry and the selected-step fallback to `POST /assistant` (`assistant.py`), Flyover's 15-second
  chat timeout (`flyover_client.py`), the contract text and tests in `tests/test_api_assistant.py`.

- STU-D06-FE-boarding-transition (Nov 17 2026): AI assistance (Claude Code) added the
  departures board shown once after a confirmed completion, tied the title flip to that event,
  and made "Step N of M" count progress (`flyover.py`, `style.css`, `reduce-motion.css`).
  Tests in `tests/test_flyover_live_api.py`.

- STU-D06-FE-appointment-notices (Nov 17 2026): AI assistance (Claude Code) added Flyover's
  appointment notice and session-only weekly free times (`flyover_appointments.py`,
  `flyover.py`, `style.css`), with tests in `tests/test_flyover_appointments.py` and
  `tests/test_flyover_live_api.py`. Guidance only; matching waits for structured office hours.
