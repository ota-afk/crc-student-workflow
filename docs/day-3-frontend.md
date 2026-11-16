# STU-D03-FE: task details, school selection and assistant preview

This frontend extends the team's Streamlit app. FastAPI stores no profile or
progress; Streamlit keeps transient profile/UI state in `st.session_state`.
The shared BE/FE decisions remain in [contract.md](contract.md). This document
records frontend implementation and outstanding integration, not a different
team plan or a new API agreement.

## Verification and task details

Task details shows the supplied next action, navigable missing prerequisites,
document inventory, blocker explanations/dates and before-you-go/source data.
There is no full steps list in the current model; the UI invents none.
Every blocker whose verification status is not exactly `verified` is visibly
labeled **Not verified**, including its listed unlock date. A missing timing date
is unknown. A source needs an explicit `verified` status, usable URL and date;
missing/null/unrecognized status never qualifies. There is no legacy exception.

Each workflow card has **View checklist**. Prerequisite buttons open that task's
checklist, keep the Task details tab selected and preserve inventory when switching
between tasks. Document selections live in `documents_on_hand[task_id][document]`,
separate from transient widget keys. Checking everything never changes task status,
removes a timing blocker or establishes eligibility. **View readiness** opens a
modal showing current status and missing listed documents. It is a local inventory
summary, not a backend readiness decision. Unknown document requirements remain
unknown. **Resolve blocker** and **Mark done** are disabled until their contracts
and actual endpoints exist; no request or invented success is shown.

## State → school profile preparation

The Profile tab now starts with an explicit California-only state selector and
school search through the existing `GET /schools?q=&limit=20` contract. Search
runs on an explicit click, shows loading/no-results/retry states and validates
responses. Changing the state or search clears incompatible selected schools and
profile drafts. Other states are clearly unsupported. **My school is not listed**
is available without claiming that an omitted school is ineligible. Listing a
school does not verify its requirements; unverified school context is labeled
**Not verified for your school** with a DSO reminder.

Visa type, arrival date and the has-SSN yes/no choice prepare a session-only draft.
There is no real-ID field. **Generate workflow** remains disabled and the page
says these edits are not applied to the current workflow. No profile is POSTed
against a guessed interface. This does not claim completed onboarding.

When the confirmed workflow profile changes school, institution, synthetic user,
visa, arrival date or has-SSN context, old inventory, document widget values, chat
and email drafts are cleared before rendering; users are told to reconfirm.
Progress-only changes do not clear documents. Merely preparing an unapplied
profile draft leaves the current workflow/inventory unchanged. Failed directory
requests preserve the current workflow and selections.

## Assistant preview and proposed adapter

The default `ASSISTANT_MODE=mock` reads fixed UTF-8 JSON from
`data/mock/assistant.mock.json`. It is visibly sample/unverified and is not a
question-answering service. The panel shows the active task title; each user and
assistant message retains the task title at submission so switching tasks does
not relabel old guidance. Chat is bounded to 40 entries and can be cleared without
clearing document inventory. Confirmed profile-context changes clear stale chat.

BE and AI must agree on the endpoint and sourced-answer response before live
use. The team uses no `/api/` prefix. This frontend no longer chooses a route:
`ASSISTANT_ENDPOINT` has no default and must be explicitly set to the agreed full
URL before `ASSISTANT_MODE=live` can make a request. Without that configuration,
live mode explains the missing integration and makes no assistant request.
Configuring a URL does not itself establish that the route/contract exists.

The existing request/response adapter remains **proposed**, not a shared contract:

```json
{
  "question": "What should I do next?",
  "task_id": "task_dmv_id",
  "student_profile": {
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "school_id": "crc"
  }
}
```

Proposed response:

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

The adapter trims questions (1–500 characters), allowlists the basic profile
context and uses a 30-second timeout without automatic retries. Each proposed
source requires `rule_id`, nullable `url`/`last_verified`, and
`verification_status` (`verified`, `needs_verification`, `re-checking`). Nullable
contact/task IDs and actual boolean flags are required; unexpected response
fields fail validation. Failed calls never produce a fabricated answer or clear
inventory. Raw free text still requires BE/AI privacy filtering before a model
call; a frontend warning/allowlist is not complete privacy enforcement.

## Outstanding checkpoint / questions for BE, AI and DATA

The user confirmed there is no newer BE contract to integrate at this review.
Current registered routes are GET health, workflow and schools; `POST /workflow`
and the two task POST routes are not implemented. The whole real-call demo path
is therefore **not complete**. Keep these dependencies explicit:

| Dependency | Needed from teammates before FE enables it |
| --- | --- |
| Profile → `POST /workflow` | BE: finalize request/model including `as_of`, synthetic ID, CA scope, optional fields, errors and returned profile. Existing body is still proposed in contract.md. |
| `POST /tasks/{task_id}/complete` | BE: confirm request/Workflow response, server validation and progress retention/recompute. FE must never set task status directly. |
| `POST /tasks/{task_id}/resolve` | BE + AI: agree awaiting-reply state and `generate_email()` result, response envelope, failure semantics and what explicit action changes progress. Drafting must not imply an email was sent. |
| Backend readiness | BE + DATA: agree documents/prerequisites/unknown-state inputs and output; supply complete sourced requirements. Current modal is inventory only. |
| Cited explanations / email | BE + AI: agree no-prefix route(s), request/answer/email shapes, minimum workflow context, filtering, referrals and timeout behavior. No assistant route is inferred from the plan. |
| School-specific guidance | DATA: confirm CRC/Sacramento State/generic coverage, source states/dates and reviewed contacts. A directory row is not verified school procedure data. |

BE and FE must settle changes in `docs/contract.md` before introducing new shared
fields/routes. These FE fixes restore that file to main's agreement rather than
unilaterally marking proposed shapes as agreed. No team-chat message is sent by
the app. This review's PR response asks for the concrete missing examples/owners.

## Validation

Use unit/adapter tests, Streamlit AppTest, actual API checks and real browser
checks at 320px, 375px, 768px and desktop widths. Browser evidence and remaining
limits are in [day-3-review-verification.md](day-3-review-verification.md).
AppTest is not evidence of a real mobile keyboard or deployed integration.

The frontend view modules remain separate from backend imports. `frontend.py`
contains no Streamlit import, and importing `student_workflow.api` does not import
Streamlit. Moving all view files was considered but deferred to keep the review
focused; the API has no import dependency on the views.
