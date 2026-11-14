# Day 3 frontend implementation plan

Goal: implement the confirmed five-day plan's task details, document checklist,
before-you-go information, dated sources and assistant panel on the existing Streamlit app.

Policy: planning=compact; context_depth=dependency; verification_depth=impact;
delegation=none. Scope: frontend helpers, app, tests, fixture and documentation.

The user confirmed the five-day plan on Nov 13. Its feature scope takes precedence
over the repository's references to a six-day plan. Keep the working Streamlit
architecture to build on day 2; a React/SQLite migration is a separate project.

Assumptions: hackathon-sized workflows; session-only document selections and chat;
no uploads, identity fields, persistence or email sending. Network requests have a
30-second timeout. Existing status badges and typography remain consistent.

Decisions: use a Task details tab and a task picker, with checklist before visit
details. Show sources alongside their dates. Do not let checked documents change
server-owned status or make an unverified task look ready. The assistant starts in
explicit sample-preview mode because no live endpoint or agreed answer schema
exists. A documented opt-in client supports the proposed five-day-plan endpoint.
No live AI integration is claimed until BE/AI agree and implement that contract.

1. Add AppTest coverage for task selection, missing documents, retained selections,
   unverified/blocked readiness and dated source links. Observe failures, then build
   the detail view and reusable frontend helpers.
2. Add client and AppTest coverage for sample chat, live request shape, invalid
   responses, timeouts, referral answers and session isolation. Observe failures,
   then build the assistant panel and client using a labeled fixture.
3. Document the proposed assistant contract, current integration limits, demo steps
   and AI attribution. Run the exact CI commands, inspect the UI, commit, push and
   open a draft PR to run GitHub CI. Leave review and merge to the team.

Review focus: missing guidance must not mean ready; checked documents never unlock
tasks; invalid URLs never become links; failed chat calls never produce an answer;
sample replies never masquerade as AI or verified advice.
