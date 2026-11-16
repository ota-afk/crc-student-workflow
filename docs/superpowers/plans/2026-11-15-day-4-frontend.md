# Day 4 frontend implementation plan

Goal: email draft preview/copy, resilient workflow states, phone layout checks,
and Render deployment preparation in the existing Streamlit app.

Spec: the revised `output/frontend-guides/frontend_state_and_prompting_guide.md`
in the project planning workspace, sections 1, 5 and 6; `docs/ai-data-policy.md`.

Policy: planning=compact; context_depth=dependency; verification_depth=impact;
delegation=none. Allowed scope: frontend helpers/views/app, email fixture,
frontend tests, FE 4 documentation and deployment preparation.

Decisions: keep existing Streamlit components and widget keys. Use a separate
email renderer and a fixed placeholder template, explicitly labeled sample.
No live email adapter until BE/AI agree and implement its request/response.
Use Streamlit's native code copy control with wrapped plain text and manual
selection fallback. Draft only on a button click; clear it when selected task,
profile or workflow context changes. Never set task status or send email.
Assume hackathon-scale data, transient Streamlit session state, no uploads,
identifiers, model calls, new dependencies or draft persistence.

1. Add AppTest tests for explicit preview generation, placeholders, blocked-only
   availability, no repeated generation, context invalidation, failures/retries
   and retained document inventory. Observe failures; implement in
   `frontend_email.py` with `data/mock/email.mock.json` and wire into Task details.
2. Add workflow failure/malformed-response/retry tests, observe failures, then
   add loading feedback, boundary validation and friendly errors in the app.
   Retain existing empty-state and verification behavior.
3. Verify the real copy control and narrow/desktop layouts in a browser. Add
   only wrapping fixes justified by observed behavior. Run full pytest and Ruff.
4. Document Render build/start/environment/health settings and outstanding
   backend contracts. Deploy only after service details arrive and the code is
   approved for commit/push. The owner approved commit/push on November 15, 2026;
   teammate review proceeds through the PR.

Review focus: stale drafts after context changes; draft failures resetting
checklists; accidental status changes; raw backend errors; long draft/source
text overflowing a phone viewport. Browser clipboard checks and deployed smoke
tests are separate evidence from AppTest.
