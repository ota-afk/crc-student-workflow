# STU-D03-FE: readiness and assistant

## Scope and plan correction

The owner confirmed the **5-Day Build Plan (Nov 11, 2026)** as the feature schedule.
Day 3 FE is task details, document checkboxes, before-you-go information, dated
source links and chat. Older repository references to a six-day plan do not define
this ticket. This implementation extends the existing Streamlit app; it does not
migrate the project to the plan's React/SQLite architecture.

Current `GET /workflow` remains the source for tasks, next actions, prerequisites,
blockers, document requirements and visit details. The current contract has no
full `steps` list, so task details show the supplied next action and prerequisites
instead of inventing agency instructions. Missing data remains visibly unverified.

The checklist is a local inventory of listed documents, not the backend readiness
decision. It never changes task status. Selections are keyed by task and document
text, survive task changes, and remain in Streamlit session memory only. Updated
document lists require checking newly added items. There are no uploads.

Sources without the new `verification_status` use the legacy v1 URL/date rule.
When that field is present, only `verified` counts as verified. This supports the
pending STU-D02-BE contract without modifying or merging its branch. Links and
source dates remain visible for unverified sources with an explicit warning.

## Proposed assistant adapter: pending BE/AI agreement

The five-day plan explicitly requires AI and FE to agree on the answer JSON before
live chat integration. No such endpoint or agreed schema exists on main. The UI
therefore uses `data/mock/assistant.mock.json`, a fixed preview that does not answer
the user's question. It is always marked sample and unverified.

The following shape is a **proposal**, not an existing backend API. BE/AI must
review it before enabling `ASSISTANT_MODE=live`. Current main returns 404, which
the UI handles without a traceback or loss of document selections.

`POST /api/assistant/ask` (the endpoint from the confirmed five-day plan):

```json
{
  "question": "What should I do next?",
  "task_id": "task_dmv_id",
  "student_profile": {
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-11-09",
    "has_ssn": false
  }
}
```

`question`: trimmed, 1–500 characters. `task_id`: selected task ID, or null when
there are no tasks. Optional profile `school_id` is forwarded when available.
No student ID, document selections, completed-task list or chat history is sent.
Free-text privacy scrubbing and high-risk routing must be enforced by BE/AI;
the frontend warning alone is not a privacy or safety boundary.

Required response fields (example is illustrative, not verified advice):

```json
{
  "answer": "I cannot verify this requirement. Ask your DSO.",
  "steps": [],
  "sources": [],
  "verified": false,
  "contact": "Your international student office (DSO)",
  "task_id": null,
  "is_mock": false
}
```

Each source has `rule_id: string`, `url: string|null`,
`last_verified: YYYY-MM-DD|null`, and
`verification_status: verified|needs_verification|re-checking`.
`contact` and `task_id` are nullable strings. Boolean fields must be actual booleans.
Missing fields, malformed types and unexpected fields fail validation.

The client uses a 30-second timeout and no automatic retry. A rerender never
resubmits a question. Failed requests show a retry message without presenting a
fabricated answer. History is bounded to 40 messages per session and can be cleared.
The UI warns on answers without complete verified sources even if `verified=true`.

## Remaining integration work owned by BE/AI

- Agree on this request/answer proposal or adjust the adapter to the agreed shape.
- Implement the assistant endpoint, retrieval, privacy filtering and high-risk referrals.
- Supply live readiness, complete steps and verified visit data through the API.
- Verify the State ID demo against live data; the preview is not an end-to-end AI demo.

## Verification

`uv sync --locked`, `uv run --locked ruff check .`, `uv run --locked pytest`.
AppTest exercises document selection, missing guidance, task switching, source
status/URL handling, sample chat, request payload, failures, history and isolation.
No real LLM calls or messages to other people are made by these checks.
