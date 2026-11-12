# Contract and changelog

This file is the agreement between the API (BE) and the dashboard (FE). The Pydantic models in
`src/student_workflow/contract.py` are the code version of it. `contract.py`, the mock
(`data/mock/workflow.mock.json`) and this file change together in one pull request, and everyone
is told.

Status labels used below:

- **Live**: exists in the code on `main` today.
- **Agreed**: shape agreed, built later (the day is given).
- **Proposed**: BE's suggestion. Not final until FE (and AI, where noted) agree in review.

## Ground rules that shape the API

From the build plan:

- **Nothing is stored on the server.** No database, no session store. The dashboard keeps the
  student's profile in `st.session_state` and sends it with every request.
- **Code decides task status.** The engine computes every status from the profile and the
  "as of" date. The AI only maps requests, explains and drafts.
- **The workflow fetch is never cached.** After any action that changes state, the dashboard
  calls `st.rerun()` so the screen shows the fresh workflow.

## Endpoints

| Method and path | Status | What it does |
| --- | --- | --- |
| `GET /health` | Live | Returns `{"status": "ok"}`. |
| `GET /workflow` | Live | Returns the fixed demo workflow (the mock while `USE_MOCK=true`). Kept for the tests and `scripts/check_no_sample.py`. |
| `POST /workflow` | Planned, built Day 3 (request shape proposed) | Takes a profile, returns that student's computed workflow. |
| `POST /tasks/{task_id}/resolve` | Proposed, Day 3 | "Resolve blocker": drafts the email and marks the task as awaiting a reply. |
| `POST /tasks/{task_id}/complete` | Proposed, Day 3 | "Mark done": adds the task to the student's completed tasks. |

There is no `/api/` prefix, to match the live endpoints.

## The Workflow response (Live)

Every endpoint that returns a workflow returns this shape. It is the same shape `GET /workflow`
returns today.

These tables describe the JSON shape of the current models. "Required" means the field must
be supplied when validating an object; otherwise the model fills in the listed default.
Dates are `YYYY-MM-DD` strings. An "array of strings" looks like `["task_school_checkin"]`.

### Workflow (top level)

| Field | JSON type | Required or default |
| --- | --- | --- |
| `schema_version` | string | Required |
| `is_mock` | boolean | `false` |
| `as_of` | date string | Required |
| `student_profile` | StudentProfile object (below) | Required |
| `workflow` | array of Task objects | Required |

`is_mock: true` means sample data: FE shows the sample-data banner. `false` alone does not
prove that every rule is verified. `schema_version` is a string; the model does not restrict
it to `"1.0"`.

### StudentProfile

| Field | JSON type | Required or default |
| --- | --- | --- |
| `student_id` | string | Required |
| `institution` | string | Required |
| `visa_type` | string | Required |
| `arrival_date` | date string | Required |
| `has_ssn` | boolean | Required |
| `completed_tasks` | array of strings (task IDs) | `[]` |

`visa_type` is a string in the current model; `"F-1"` in the examples is not an enforced
list of allowed values.

### Task (each item in `workflow`)

| Field | JSON type | Required or default |
| --- | --- | --- |
| `id` | string | Required |
| `title` | string | Required |
| `status` | string: `Blocked`, `Ready`, `In Progress`, or `Completed` | Required |
| `priority` | string: `Required`, `Recommended`, or `Optional` | Required |
| `prerequisites` | array of strings (task IDs) | `[]` |
| `missing_prerequisites` | array of strings (task IDs) | `[]` |
| `next_action` | NextAction object or null | `null` |
| `blockers` | array of Blocker objects | `[]` |
| `before_you_go` | BeforeYouGo object or null | `null` |
| `sources` | array of Source objects | `[]` |

### NextAction

| Field | JSON type | Required or default |
| --- | --- | --- |
| `task_id` | string | Required |
| `text` | string | Required |

### Blocker

| Field | JSON type | Required or default |
| --- | --- | --- |
| `type` | string: `timing`, `missing_prerequisite`, or `document` | Required |
| `rule_id` | string | Required |
| `unlocks_on` | date string or null | `null` |
| `verification_status` | string: `verified` or `needs_verification` | Required |
| `explanation` | string | Required |

### BeforeYouGo

| Field | JSON type | Required or default |
| --- | --- | --- |
| `required_documents` | array of strings | `[]` |
| `fees` | string or null | `null` |
| `hours` | string or null | `null` |
| `appointment_rules` | string or null | `null` |
| `phone` | string or null | `null` |
| `official_url` | string or null | `null` |
| `warnings` | array of strings | `[]` |

### Source

| Field | JSON type | Required or default |
| --- | --- | --- |
| `rule_id` | string | Required |
| `url` | string or null | `null` |
| `last_verified` | date string or null | `null` |

### Missing values and verification

- `next_action: null` means no next action was supplied. It does not say whether the task's
  requirements are verified.
- `before_you_go: null` means no readiness details were supplied. FE shows "Not verified"
  for that missing guidance, rather than claiming there is nothing to prepare.
- Null values for `fees`, `hours`, `appointment_rules`, `phone`, or `official_url` mean that
  detail is not verified or available. FE shows "Not verified", never a guessed value.
- `unlocks_on: null` means no unlock date was supplied. Do not invent a date; for a timing
  blocker, FE shows "Not verified" for the missing date.
- `Source.url: null` or `Source.last_verified: null` means the source URL or verification
  date is missing. FE shows "Not verified" for that missing evidence.
- Empty arrays mean no items were supplied, not proof that there are no requirements.
- A non-null value can still be unverified, as in the mock. Check `is_mock` and each blocker's
  `verification_status`; never treat a sample value as a verified rule.

## POST /workflow (planned for Day 3; request shape proposed)

The dashboard sends the profile it keeps in `st.session_state`. The plan requires the engine
to accept an injected "as of" date so the demo can show a fixed day ("arrived 3 days ago").

The whole request shape below is BE's proposal for FE to review on Day 1; the plan only says
the dashboard sends the profile. It becomes "Agreed" once FE approves it.

**Proposed request detail, pending FE agreement:** make `as_of` optional and use today when it
is omitted. The plan does not specify that default. The example supplies `as_of` explicitly;
there is no POST request model or route in the code yet.

Request:

```json
{
  "as_of": "2026-08-14",
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"]
  }
}
```

Planned response: `200` with a Workflow (above). The example below is **sample data**, trimmed
to one task. Its check-in task, priority, prerequisites, and status are illustrative and
unverified; they do not establish CRC requirements. A live response will use `is_mock: false`
and must visibly label any unverified facts.

```json
{
  "schema_version": "1.0",
  "is_mock": true,
  "as_of": "2026-08-14",
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"]
  },
  "workflow": [
    {
      "id": "task_school_checkin",
      "title": "Complete CRC international student check-in (sample)",
      "status": "Ready",
      "priority": "Required",
      "prerequisites": ["task_i94_retrieval", "task_sevis_fee"],
      "missing_prerequisites": [],
      "next_action": null,
      "blockers": [],
      "before_you_go": null,
      "sources": []
    }
  ]
}
```

Current behavior, before Day 3:

- `POST /workflow` returns `405 Method Not Allowed`: only the GET route exists today.
- `GET /workflow` returns `501` when `USE_MOCK=false`, because the live engine is not built yet.

**Proposed validation response once POST is implemented:** `422` for a request that fails
the future request model (for example, a missing required field or an invalid date). Until
that model exists, only the request's `student_profile` can be checked against StudentProfile;
the full request body cannot be validated against an existing model. The response example
can be checked against Workflow now.

`student_id` is a made-up ID such as `demo_001`. Never a name, passport number or SEVIS ID.

## Day 3 task actions (Proposed)

Both take the same request body as `POST /workflow` and return the updated Workflow. The returned
`student_profile` is the new state: FE saves it back into `st.session_state`, then calls
`st.rerun()`. Because the server stores nothing, this is how a change survives the next click.

- `POST /tasks/{task_id}/complete` adds `task_id` to `completed_tasks`. Tasks that depended on it
  can now become `Ready`.
- `POST /tasks/{task_id}/resolve` drafts the email and moves the next action to `In Progress`
  (awaiting reply). It never makes a task `Ready` on its own: only completed prerequisites, or
  the "as of" date passing, do that.
  - Open: the profile needs a place to remember "awaiting reply" between requests. BE proposes
    a new `student_profile` field `awaiting_reply: list[str]` (task IDs). That is a contract
    change, made in its own pull request.
  - Open: the response also needs the email draft. Its fields belong to AI (`generate_email()`),
    so AI and BE agree on them on Day 3.
- `404` if `task_id` is not a task in the workflow.

## Answers to FE's Day 1 questions

1. **Task status updates: PATCH or POST?** POST. The build plan names "two POST endpoints
   (resolve a blocker, mark a task done)" on Day 3, not Day 2. Neither the build plan nor the
   setup guide mentions
   `PATCH /api/tasks/{task_id}/status`. The guide's `/tasks/{id}/resolve` is marked as an
   example, so the names above are proposed. The client never sets a status directly, because
   code decides status. The request and response are in "Day 3 task actions" above.
2. **Session identity?** There is none on the server. No `session_id`, no server memory, no
   SQLite. `st.session_state` keeps the profile across Streamlit reruns in the same browser tab.
   A page refresh or a new tab starts a new session, so the student onboards again, which is
   fine for the demo.

## Open questions for the team

- **Enrollment date.** ENG's fee-payment rule (`docs/sources.md`; rule
  `rule_crc_fall_2026_payment_deadline` in `data/rules/rules.json`) is calculated from the
  enrollment date, but `student_profile` has no such field. The plan's ground rules list what a
  student gives us: school, state, visa type, arrival date, and whether they have an SSN. Adding
  `enrollment_date: date | None` (`None` = not given, so no deadline is shown) widens that list,
  so the team decides first.
- **State.** The ground rules list "state" as an input, but `student_profile` has no state field.
  The Day 2 school-list change (`school_id`, `school_verified`) may cover it.
- **Unknown keys.** Pydantic ignores keys it does not know, so a typo like `"enrolment_date"`
  disappears silently. BE proposes making request models reject unknown keys (a `422`) when the
  POST endpoints are built.

## Changelog

- 2026-11-12, STU-D01-BE second review: label the `POST /workflow` request shape as proposed
  (FE has not agreed it yet) and point the enrollment-date question to the rule in `rules.json`.
  Documentation only.
- 2026-11-12, STU-D01-BE review fixes: label the response example as sample data; document all
  current model fields, types, defaults, and missing-value meanings; correct the current POST
  response to 405; and label the optional `as_of` default and future validation as proposed.
  Documentation only; no API or model changes.
- 2026-11-12, STU-D01-BE: first version. Documents the live contract, the `POST /workflow`
  example, proposed Day 3 task actions, and answers to FE's questions. No code change.
- 2026-11-11, Day 1 skeleton: `contract.py` and the mock created from the Final Repo Setup Guide.
