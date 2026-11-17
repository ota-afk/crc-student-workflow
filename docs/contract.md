# Contract and changelog

This file is the agreement between the API (BE) and the dashboard (FE). The Pydantic models in
`src/student_workflow/contract.py` are the code version of it. `contract.py`, the mock
(`data/mock/workflow.mock.json`) and this file change together in one pull request, and everyone
is told.

Status labels used below:

- **On main**: merged to `main`.
- **In review (PR #N)**: built and tested on a BE branch, but not merged. It can still change in
  review, and nothing on `main` (or a deploy from `main`) has it yet.
- **Deployed**: running on the live host. Nothing is deployed yet (see `docs/deploy.md`).
- **Agreed**: shape agreed, built later.
- **Proposed**: BE's suggestion. Not final until FE (and AI or ENG, where noted) agree.

State on 2026-11-16 (check `git log origin/main` and the PRs for anything newer):

| Ticket | Where | Merge commit | State |
| --- | --- | --- | --- |
| Resolver, school search (STU-D02-BE) | PR #13 | `e094490` | On main |
| Live endpoints, API key, rate limit (STU-D03-BE) | PR #20 | `e0798da` | On main |
| Smoke test, CI end-to-end job, Render setup (STU-D04-BE) | PR #21 | `bb914ac` | On main |
| Warm-up, key audit, release checklist and shared rate allowance (STU-D05-BE) | PR #22 | `f84654f` | On main |
| Cited visit details (STU-D05-BE-before-you-go) | PR #23 | not merged | In review |
| Deploy to Render | `docs/deploy.md` | | Not deployed yet |

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
| `GET /health` | On main | Returns `{"status": "ok"}`. No API key and no rate limit, so hosts and warm-up pings can call it. |
| `GET /workflow` | On main | The fixed demo student. `USE_MOCK=true` (the local default): the mock file. `USE_MOCK=false`: the mock's demo profile and "as of" date run through the live engine. |
| `GET /schools?q=&limit=20` | On main | Searches ENG's California F-1 school CSV (`data/schools/sevp_schools_ca.csv`, merged in #14) by name or city. `503` only if that file can't be read. |
| `POST /workflow` | On main | Takes a profile, returns that student's computed workflow. Always the live engine. |
| `POST /tasks/{task_id}/resolve` | On main, draft in review | "Resolve blocker": marks the blocked task's next action as awaiting a reply (`In Progress`) and returns a draft when available. |
| `POST /tasks/{task_id}/complete` | On main | "Mark done": adds the task to the student's completed tasks. |

There is no `/api/` prefix. Every endpoint except `/health` needs the API key header (when the
server sets `API_KEY`) and counts toward the rate limit (see "Access" below). No AI or assistant
route exists on any BE branch (see "AI integration").

## The Workflow response

**Status: on main.**

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
| `completed_tasks` | array of strings (task IDs), at most 1,000 | `[]` |
| `awaiting_reply` | array of strings (task IDs), at most 1,000; set by `POST /tasks/{id}/resolve` | `[]` |
| `school_id` | string or null | `null` |
| `school_verified` | boolean, computed by the resolver | `false` |

A profile with a key not in this table is rejected (`422`), so a typo like `"completed_task"`
fails loudly instead of being ignored.
`awaiting_reply` lists the tasks whose office the student has written to and is waiting on. A
task cannot be in both `completed_tasks` and `awaiting_reply`.

`school_id` is the stable identifier shared by the school directory and school-specific
rules. `institution` stays the display name; the resolver never guesses an ID from that name.
**Proposed, pending ENG agreement:** this branch uses `crc` as the internal identifier for
the existing CRC rule. It is not an official SEVP code.
The resolver recomputes `school_verified` rather than trusting a value sent by a client.
It is true only when every school step the student sees comes from that school's own rules
and all of those rules are verified. If any task falls back to the generic steps, it is false.

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
| `citations` | array of Citation objects (in review, STU-D05-BE-before-you-go) | `[]` |

**Citation** (one per fact above, in field order):

| Field | JSON type | Meaning |
| --- | --- | --- |
| `field` | string: one of the seven field names above | Which field the fact is in |
| `text` | string | The fact, exactly as shown in that field |
| `rule_id` | string | The rule the fact comes from (also listed in the task's `sources`) |
| `verification_status` | string: `verified` or `needs_verification` | That rule's state |

The string fields stay as they were, so a dashboard that reads them keeps working. `citations`
is added beside them; no dashboard reads it yet. **Proposed for FE:** show each fact from
`citations` (field and text together, since two facts can share the same text) and label it
"Not verified" unless its `verification_status` is `verified`. Until then, the cited rules
are also in the task's `sources`, which FE already labels. An empty `citations` (the mock, or
an older response) means no per-fact source was supplied, so every fact counts as unverified.

### Source

| Field | JSON type | Required or default |
| --- | --- | --- |
| `rule_id` | string | Required |
| `url` | string or null | `null` |
| `last_verified` | date string or null | `null` |
| `verification_status` | string: `verified`, `needs_verification`, or null | `null` |

`verification_status: null` means no verification state was supplied and must be treated as
unverified. A source's date may describe an earlier check even when the rule now needs
verification; a URL and date alone never establish that it is currently verified.

**On main since FE PR #16:** the dashboard checks a source's usable URL, date and explicit
`Source.verification_status` before treating it as verified. Per-fact citation rendering
remains a separate FE integration step.

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
  and source's `verification_status`; never treat a sample value as a verified rule.
- `student_profile.school_verified: false` means we have not verified this school's own
  steps. The plan has FE label generic tasks "Not verified for your school" with a prompt to
  confirm with the DSO (FE's Day 2 work).

## POST /workflow

**Status: on main (PR #20).**

The dashboard sends the profile it keeps in `st.session_state` and gets that student's computed
workflow back. `POST /workflow` always runs the live engine on `data/rules/rules.json`;
`USE_MOCK` only changes `GET /workflow`. The request shape was BE's Day 1 proposal (merged in
PR #4); its code version is `WorkflowRequest` in `contract.py`. Unknown keys are rejected with a
`422`, at the top level and inside `student_profile`.

### Try it

Start the API (`uv run uvicorn student_workflow.api:app --port 8000`), then send the demo
student. If the API has an `API_KEY`, add `-H "X-API-Key: $API_KEY"`. On Windows, use the
"Try it out" button at <http://localhost:8000/docs> instead.

```bash
curl -s -X POST http://localhost:8000/workflow -H 'Content-Type: application/json' --data @- <<'EOF'
{
  "as_of": "2026-08-14",
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "school_id": "crc",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"]
  }
}
EOF
```

### The request, field by field

- **`as_of`** (optional date). The day the workflow is computed for, so the demo can say
  "arrived 3 days ago" and tests repeat. **Proposed, pending FE agreement:** when it is
  omitted, the API uses today's date in California (`America/Los_Angeles`), because a hosted
  server's clock is often on UTC. One action uses one date for both its check and its answer.
  FE should keep one `as_of` per session and send it on every call; otherwise a session that
  crosses midnight can change statuses between clicks.
- **`student_id`** (required string): a **made-up label** such as `demo_001`. The API never
  checks its format and only echoes it back. Never a name, email, passport number, SEVIS ID or
  real student ID. The profile has no field for a name, and an unknown key such as `"name"` is
  rejected with `422`.
- **`institution`** (required string): display only. The resolver never reads it.
- **`school_id`** (string or null): picks the school's rules; use the `school_id` from
  `GET /schools`. `null` or left out gives the shared federal and California tasks plus ENG's
  generic check-in steps (7 tasks today; `crc` gets 8). An ID with no rules of its own also gets
  the generic steps: the API does not check it against the school directory.
- **State.** There is no state field. School search returns California schools only, and every
  profile gets the California rules (REAL ID and the rest), even if its `school_id` were from
  another state. The product is California-only for now (see "Open questions").
- **`visa_type`** (required string) and **`has_ssn`** (required boolean): stored and echoed;
  no rule in `rules.json` uses them yet. `visa_type` is not checked against a list.
- **`arrival_date`** (required date): used only by `timing` rules. `rules.json` has none today.
- **`completed_tasks`**, **`awaiting_reply`** (task-ID lists, default `[]`): the student's
  progress. Every ID must be a task in this student's workflow, listed once, and not in both.
- **`school_verified`**: may be sent (the dashboard sends back what it got) but is ignored and
  recomputed.

### The response

`200` with a Workflow (above). The example is real output, generated on 2026-11-16 from ENG's
`rules.json` on `main` (`a405852`, PR #18), trimmed to 2 of the demo student's 8 tasks. Every
rule is still `needs_verification`, so the dashboard must label these facts "Not verified".

```json
{
  "schema_version": "1.0",
  "is_mock": false,
  "as_of": "2026-08-14",
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"],
    "awaiting_reply": [],
    "school_id": "crc",
    "school_verified": false
  },
  "workflow": [
    {
      "id": "task_proof_of_residency",
      "title": "Gather residency evidence for California REAL ID",
      "status": "Ready",
      "priority": "Recommended",
      "prerequisites": [],
      "missing_prerequisites": [],
      "next_action": null,
      "blockers": [],
      "before_you_go": null,
      "sources": [
        {
          "rule_id": "rule_california_real_id_residency",
          "url": "https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/",
          "last_verified": null,
          "verification_status": "needs_verification"
        }
      ]
    },
    {
      "id": "task_dmv_id",
      "title": "Apply for a California REAL ID card",
      "status": "Blocked",
      "priority": "Recommended",
      "prerequisites": ["task_proof_of_residency"],
      "missing_prerequisites": ["task_proof_of_residency"],
      "next_action": {
        "task_id": "task_proof_of_residency",
        "text": "Finish \"Gather residency evidence for California REAL ID\" first."
      },
      "blockers": [],
      "before_you_go": null,
      "sources": [
        {
          "rule_id": "rule_california_id_application",
          "url": "https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/identification-id-cards/",
          "last_verified": null,
          "verification_status": "needs_verification"
        }
      ]
    }
  ]
}
```

What the nulls and empty lists mean here (the full list is in "Missing values and
verification" above):

- `next_action: null`: the task isn't blocked by a missing prerequisite.
- `blockers: []` on the DMV task: it is blocked only by its missing prerequisite. ENG's rules
  have no waiting period, so there is no `timing` blocker and no unlock date.
- `before_you_go: null`: `rules.json` on `main` has no visit details. Once ENG adds them and
  this branch's support merges, they appear here with `citations` (see "The rules file").
- `last_verified: null` with `needs_verification`: no human check recorded yet.

### Errors

Every workflow endpoint uses the same ones. These are real answers from the API:

| Code | When | Example `detail` |
| --- | --- | --- |
| `401` | `X-API-Key` missing or wrong (only when the server has an `API_KEY` set) | `"Missing or invalid API key"` |
| `404` | Task actions only: `task_id` is not in this student's workflow | `"Task task_typo is not in this workflow"` |
| `409` | Task actions only: the task is not in a state the action allows (see below) | `"Task task_dmv_id is Blocked, so it cannot be marked done"` |
| `422` | The request fails `WorkflowRequest` (missing field, bad date, unknown key, either progress list over 1,000 items) | FastAPI's list, e.g. `"type": "extra_forbidden"` with `"loc": ["body", "student_profile", "completed_task"]` |
| `422` | The profile breaks a resolver rule (unknown task ID, a task listed twice, completed before its prerequisites, both completed and awaiting a reply) | `"completed_tasks has unknown task ids: task_typo"` |
| `429` | Rate limit reached | slowapi's message |
| `500` | A bug in our code (the engine built an invalid workflow) | `"Internal error"`; details only in the server log |
| `503` | The rules file is missing, invalid, or can't build a workflow for this school; or (`GET /workflow` only) the demo profile no longer fits the rules | `"Workflow is temporarily unavailable"`; details only in the server log |

A `422` always means the client can fix the request. Our own problems are `500` or `503`, so a
student never sees our errors described as their mistake.

## Task actions

**Status: on main (PR #20).**

Both take the same request body as `POST /workflow`. Code decides every status; the client
never sends one.

### The stateless round trip

The server stores nothing, so each answer carries the new profile, and **FE replaces its stored
profile with the returned one before the next call**. Sending the old profile again would lose
the change. The demo path on ENG's rules, with the same `as_of` (`2026-08-14`) each time:

1. `POST /workflow` with the demo profile: residency `Ready`, DMV `Blocked`, `awaiting_reply: []`.
2. `POST /tasks/task_dmv_id/resolve` with the profile from step 1: residency `In Progress`,
   DMV still `Blocked`, `awaiting_reply: ["task_proof_of_residency"]`.
3. `POST /tasks/task_proof_of_residency/complete` with the profile from step 2: residency
   `Completed`, DMV `Ready`, `awaiting_reply: []`.

`scripts/smoke_test.py` runs exactly this against a running API (PR #21), and CI runs it on
every pull request.

### `POST /tasks/{task_id}/resolve` ("Resolve blocker")

Returns the full `Workflow` and an optional `EmailDraft`. This step 2 example shows the profile
and two demo task statuses:

```json
{
  "workflow": {
    "student_profile": {
      "student_id": "demo_001",
      "institution": "Cosumnes River College",
      "visa_type": "F-1",
      "arrival_date": "2026-08-11",
      "has_ssn": false,
      "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"],
      "awaiting_reply": ["task_proof_of_residency"],
      "school_id": "crc",
      "school_verified": false
    },
    "workflow": [
      {"id": "task_proof_of_residency", "status": "In Progress", "missing_prerequisites": [], "next_action": null},
      {
        "id": "task_dmv_id",
        "status": "Blocked",
        "missing_prerequisites": ["task_proof_of_residency"],
        "next_action": {
          "task_id": "task_proof_of_residency",
          "text": "Finish \"Gather residency evidence for California REAL ID\" first."
        }
      }
    ]
  },
  "email_draft": {
    "subject": "Request for guidance: Apply for a California REAL ID card",
    "body": "Dear [Office or DSO],\n\nI am working on this task: Apply for a California REAL ID card. My checklist shows a pending step:\nGather residency evidence for California REAL ID\n\nCould you confirm the applicable requirements, the next step, and the right office to contact?\n\nThank you,\n[Your Name]\n[Student ID]"
  }
}
```

- `task_id` is the **blocked** task (the one with the button). Allowed when it is `Blocked` by a
  missing prerequisite. It adds that task's `next_action.task_id` (its first missing
  prerequisite) to `awaiting_reply`, which shows that prerequisite as `In Progress` ("awaiting
  a reply"). Resolving again changes nothing.
- It never makes a task `Ready`: the blocked task stays `Blocked` until its prerequisite is
  marked done, or a date passes.
- `409` when the task is not `Blocked`; when it is blocked only by a date (no office to write
  to, the student waits); or when its next action is itself `Blocked` (a chain: c needs b, b
  needs a, so the student resolves b first). ENG's rules have no chain today. A task blocked by
  both a prerequisite and a date can be resolved; the date still holds.
- In this review branch, `email_draft` is `{"subject": string, "body": string}` or `null`.
  The API builds the draft from the blocked task and its current next-action prerequisite.
  If a draft is unavailable, including a drafting error or timeout, the API returns the
  updated workflow with `email_draft: null`. The student reviews, completes, and sends
  the draft. The explicit resolve request controls progress.

### `POST /tasks/{task_id}/complete` ("Mark done")

Returns a Workflow. Real answer for step 3, trimmed the same way:

```json
{
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee", "task_proof_of_residency"],
    "awaiting_reply": [],
    "school_id": "crc",
    "school_verified": false
  },
  "workflow": [
    {"id": "task_proof_of_residency", "status": "Completed", "missing_prerequisites": [], "next_action": null},
    {"id": "task_dmv_id", "status": "Ready", "missing_prerequisites": [], "next_action": null}
  ]
}
```

- Allowed when the task is `Ready` or `In Progress`. It adds `task_id` to `completed_tasks`
  and removes it from `awaiting_reply`. Tasks that needed it can become `Ready`.
- `409` when the task is `Completed` already, or `Blocked` (by a missing prerequisite or by a
  date that hasn't arrived): a student can't finish a step the workflow says they can't start.
- Completing a task is the student's own statement ("I did this"). No office or source
  confirms it.

## Access: API key and rate limit

**Status: on main (PRs #20, #21 and #22).** The deployed API isn't running yet.

- **API key (#20).** When the server's `API_KEY` setting is not empty, every endpoint except
  `/health` needs the header `X-API-Key: <that value>`, or it returns `401`. FastAPI's own pages
  (`/docs`, `/redoc`, `/openapi.json`) stay open: they show the API's shape, never any data, and
  `/docs` still needs the key to call an endpoint. When `API_KEY` is empty (local development and
  tests), the check is off and the server logs a warning at startup. The deployed API must set it.
  The dashboard sends the header from its own `API_KEY` setting on every request (workflow,
  school search and task actions); set the same value in the dashboard's service settings. The key lives in each host's secret settings, never
  in code or a page.
- **Rate limit.** `RATE_LIMIT` (default `60/minute`), over it `429`; `/health` is exempt and
  keeps answering after the limit is reached.
  - Requests with the right key (the dashboard's server) share one allowance; every other
    request is counted by client address, so requests without the key can't use up the
    dashboard's allowance (#21).
  - The allowance is shared across **all** endpoints and task IDs, so changing the path or the
    task ID doesn't give a fresh allowance (#22; before it, each URL had its own allowance).
  - An invalid `RATE_LIMIT` stops the API at startup instead of failing every request (#20).

## Readiness: what "Ready" means

**Status: a known gap.** Item 1 of the proposal at the end is built in review
(STU-D05-BE-before-you-go); items 2 and 3 are not.

The plan's readiness check ("Are you ready, and when will you be?") isn't fully supported yet:

- **`before_you_go` is `null` on every task with `rules.json` on `main`**, which has no visit
  details. ENG has a draft with visit details for the check-in and DMV tasks. The backend can
  read that shape once this branch merges; before that, the current models reject it, so it
  must not merge first.
- **No request field says which documents the student has.** The dashboard (FE's #16, on `main`)
  keeps a local checklist (`documents_on_hand`) that never reaches the API, and the plan's readiness
  uses checkboxes like "I have my passport". The `document` blocker type exists in the model, but
  the resolver never produces it.
- So **`Ready` means only this**: every prerequisite in `rules.json` is completed and no timing
  rule is waiting. It says nothing about documents or an office's requirements. Missing
  guidance, `null`, or an empty list is **not** proof of readiness, and FE shows "Not verified"
  for missing guidance.

**Proposed, pending ENG, FE and BE agreement:**

1. *(Built in review.)* ENG adds sourced visit details per task to `rules.json`, each fact
   citing its rule, and the resolver copies them into `before_you_go` with `citations`.
2. The profile gains `documents_on_hand: dict[str, list[str]]` (task ID to the documents the
   student ticked). This widens the student inputs, so the team decides it with the ground
   rules in mind.
3. A task whose sourced `required_documents` aren't all ticked gets a `document` blocker naming
   what's missing. When `required_documents` isn't supplied, readiness stays unknown, never
   "ready".

## AI integration

**Status: draft integration in review.** This branch connects the local placeholder
template to "Resolve blocker". The assistant route and its HTTP response remain to be agreed.

| Plan item | Where | State |
| --- | --- | --- |
| Intent mapping: `map_intent(text, tasks) -> IntentResult` (`matched`, `no_match`, `dso_referral`, `error`) | AI's PR #15, `ai_assistant.py` | Helper in PR #15; not called by the API. |
| Privacy filtering | #15: `has_name()` and `has_sensitive_data()` refuse detected personal details; `scrub()` adds backup redaction and a length cap | Review regressions covered; patterns cannot guarantee all personal data is detected. Use presets for the demo. |
| High-risk referral | #15: `is_high_risk(text)` patterns give `dso_referral`; so does a matched task with `high_risk: true` | Missing or non-bool risk flags return `error` before a model call. SEVIS state and employment patterns refer before a model call. API integration remains pending. |
| Timeout | #15: `timeout=30` on the OpenAI client it creates | Exists in #15. |
| One retry | #15 sets `max_retries=0` | **Missing** (the plan asks for one retry). |
| Cited explanations and the citation validator | `src/student_workflow/ai_day3.py` | Available to BE as a helper. The assistant route is pending. |
| `generate_email()` | `src/student_workflow/ai_day3.py` | "Resolve blocker" returns its placeholder draft in this review branch. |
| Caching of AI explanations | No branch | **Missing** (the plan's only allowed cache). |
| Assistant route | No BE route. The dashboard (#16, on `main`) calls only an explicitly set `ASSISTANT_ENDPOINT` (no default) when `ASSISTANT_MODE=live` | **Not agreed.** |

**Open assistant decisions for AI, FE and BE:**

- The assistant route's name (no `/api/` prefix) and request: which profile fields reach the
  model. FE's client sends `institution`, `visa_type`, `arrival_date`, `has_ssn` and
  `school_id`; never `student_id`.
- The answer shape. FE's #16 proposes an `AssistantAnswer` (answer, steps, sources with
  verification state, `verified`, contact, task ID, `is_mock`); AI and BE haven't agreed.
- Where `high_risk` comes from. BE's proposal: the API fills it from the rules each task cites,
  and a missing flag never counts as safe.
- Where the timeout, the one retry and the explanation cache live (AI's module or the API).

### Intent mapping helper (PR #15)

`map_intent(text, tasks)` in `src/student_workflow/ai_assistant.py` turns a
student's sentence into one task ID. `tasks` is a list of dicts with `id`,
`title` and `high_risk` (bool, required). Tasks missing an ID or title are skipped;
any remaining task with a missing or non-bool risk flag returns `error` before a
model call. The caller derives risk from the rules each task cites.
`scripts/run_ai_questions.py` does this using the validated rules file, including
`RULES_PATH` overrides. It returns an `IntentResult`:

| Field | Type | Meaning |
|-------|------|---------|
| `outcome` | string | One of the four outcomes below |
| `task_id` | string or null | Set only when `outcome` is `matched` |
| `message` | string or null | Text to show the student for every outcome except `matched` |

Outcomes:

- `matched`: the model picked a task ID that exists in the list. Show that task.
- `no_match`: nothing fits, the model answered `none` or an unknown ID, or the
  text had personal details, or was not in English, and the student is asked to rephrase. Show `message`.
- `dso_referral`: an immigration-status or work-authorization question, or the
  matched task has `high_risk: true`. Show `message`. No answer is given.
- `error`: the model was unavailable, a key or model was missing, or the
  call failed. Show `message` and let the student pick a task from the list.

Code decides task status. The model only picks a task ID. SEVIS record-state
questions are referred before a model call, regardless of the task the model
might pick. “Work out” in a tuition question does not itself trigger referral;
separate employment or status wording still does.

Known limits of free text: patterns cannot catch every name (a lowercase name
or one at the start of a sentence can pass). For a demo that must never send a
name to the model, use the preset questions (`PRESET_QUESTIONS` in
`ai_assistant.py`) instead of free text.

Demo integration remains pending: FE/BE should offer only the five preset
questions before enabling free text, and verify each button opens the intended
task. The existing preset tests verify input filtering with a fake model; they
do not establish real-model routing accuracy or enforce a preset-only API.

## The rules file: `data/rules/rules.json`

**Status: on main.**

ENG writes this file; BE's resolver reads it. `src/student_workflow/rules.py` is the code version
of this section. Loading the file **rejects unknown keys**, so a typo like `"timming"` fails
loudly instead of being ignored. A new field is added here, in `rules.py`, and in the file in the
same pull request.

The file has two lists: `tasks` and `rules`.

### Rules-file task

| Field | JSON type | Required or default |
| --- | --- | --- |
| `id` | string, unique | Required |
| `title` | string | Required |
| `priority` | string: `Required`, `Recommended`, or `Optional` | Required |
| `prerequisites` | array of task IDs from this file | `[]` |
| `rule_ids` | array of rule IDs from this file, at least one | Required |
| `before_you_go` | object or null (in review, STU-D05-BE-before-you-go) | `null` |

`before_you_go` has the same seven fields as the response's BeforeYouGo, but **every fact
cites its rule**: `{"text": "...", "rule_id": "..."}`. `required_documents` and `warnings` are
lists of these; the other five are one each or `null`. Unknown keys are rejected, and every
`rule_id` must be a rule in this file. A cited rule doesn't have to be in the task's `rule_ids`.

Example task (trimmed):

```json
{
  "id": "task_dmv_id",
  "before_you_go": {
    "fees": {"text": "$40 for a regular original ID card.", "rule_id": "rule_dmv_id_fee"},
    "required_documents": [
      {
        "text": "Bring two different printed California address documents.",
        "rule_id": "rule_california_real_id_residency"
      }
    ]
  }
}
```

What the resolver does with it:

- It keeps only facts whose rule applies to this student: federal and California rules always;
  a school rule only if it is the student's own school's, or a `_generic` rule while the task
  uses the generic steps. So a CRC phone number never reaches a student at another school. A
  task with no school rules at all uses the generic steps for everyone, so its `_generic` facts
  reach every student (and keep `school_verified` false, like any generic step).
- `required_documents` and `warnings` can't repeat the same fact (same text and rule); that is
  rejected as a likely copy-paste slip.
- It copies each kept fact's `text` into the response's matching field, and adds a `citations`
  entry with the rule's `verification_status`. Each cited rule is also added to the task's
  `sources` (after the task's own rules, without repeats).
- If no fact is left, `before_you_go` is `null`.
- `school_verified` counts the school rules behind kept facts too: a shown CRC fact that isn't
  verified keeps `school_verified` false.
- Visit details never change a task's status.

### Rule

| Field | JSON type | Required or default |
| --- | --- | --- |
| `rule_id` | string, unique | Required |
| `statement` | string: the rule in plain words | Required |
| `layer` | string: `federal`, `california`, or `school` | Required |
| `school_id` | string or null | `null` |
| `high_risk` | boolean | Required |
| `verification_status` | string: `verified` or `needs_verification` | Required |
| `source_url` | string or null | `null` |
| `evidence` | string or null: the sentence on the source page | `null` |
| `last_checked` | date string or null | `null` |
| `last_verified` | date string or null | `null` |
| `verified_by` | string or null | `null` |
| `second_checker` | string or null | `null` |
| `second_check_date` | date string or null | `null` |
| `changed` | boolean or null (Day 4 source checker) | `null` |
| `timing` | Timing object or null (**Proposed**, below) | `null` |

`high_risk` is required, not defaulted, because a missing flag must never quietly mean "safe".
School rules require a nonblank `school_id`. Use `_generic` for generic check-in guidance.
Federal and California rules require `school_id: null`.

Every task cites at least one rule, so nothing appears on screen without a source. Unfinished
research still gets a rule, marked `needs_verification`. A task can cite both a generic rule
and a school's own rule for the same step, for example
`"rule_ids": ["rule_generic_checkin", "rule_crc_checkin"]`; see the resolver section below.

A rule can only be `verified` when `source_url`, `evidence`, `last_verified`, `verified_by` and
`second_checker` are all filled in (the plan's "Rules start as `needs_verification` and change
only when all of these are filled"). Loading fails otherwise.
Whitespace-only evidence and checker names count as missing. The two checker names must
identify different people; matching names after whitespace and case normalization are rejected.

### Timing

**Status: proposed, pending ENG agreement.** The resolver supports it; `rules.json` uses it
nowhere.

A rule with `timing` blocks its task until a date worked out from the student's profile:

```json
{"timing": {"from": "arrival_date", "days": 10}}
```

| Field | JSON type | Required or default |
| --- | --- | --- |
| `from` | string: `arrival_date` (the only profile date today) | Required |
| `days` | whole number, 0 or more | Required |

The unlock date is `from` + `days`. A rule without `timing` never blocks on its own. The 10 days
above is an example, not a verified rule. `enrollment_date` can be added to `from` once the team
decides on that profile field (see open questions).

## School search

**Status: on main.**

The endpoint path, query parameters, CSV columns, and internal IDs below are BE's implemented
proposal for FE and ENG to review together; the build plan does not specify their exact names.

`GET /schools?q=&limit=20` returns an array of school objects with `school_id`, `institution`,
`city`, `state` (`CA`), and the computed `school_verified` flag. Search matches part of the
name or city, ignoring case and surrounding whitespace. An empty query lists schools in file
order. `limit` is between 1 and 100; `q` is at most 100 characters. No matches returns `[]`.

ENG supplies `data/schools/sevp_schools_ca.csv`, or sets `SCHOOLS_PATH` to another file.
Its exact columns are `school_id,institution,city,state`. Rows must already be filtered to
California schools approved for F-1 students from the official SEVP list. IDs must be unique;
`_generic` is reserved for rules and cannot identify a directory entry. Being on this list
does not mean we have verified the school's check-in requirements.

The CSV is not in the repo yet. No records are invented to fill that gap. Missing or invalid
school data or rules returns `503`; invalid query parameters return `422`. The endpoint makes
no external requests. ENG must add and credit the sourced directory before statewide search
is available.

## Dependency resolver

**Status: on main.** The API calls it on every workflow request (#20).

`src/student_workflow/engine.py`:

```python
resolve(rules: RulesFile, profile: StudentProfile, as_of: date) -> Workflow
```

`as_of` is always passed in (the plan's injected "as of" date), so the demo can say "arrived
3 days ago" and tests repeat. `rules.load_rules(path=None)` reads the rules file; with no path it
uses `RULES_PATH`, default `data/rules/rules.json`.

How each task's status is decided (code decides status, never the AI):

First, select the applicable rules, **task by task**:

- Federal and California rules always apply.
- If the task cites a rule for the student's `school_id`, that school's rules apply and the
  task's `_generic` rules do not. Otherwise the task's `_generic` rules apply.
- Another school's rules never apply.
- A task with no applicable rules is not part of this student's workflow.

So a school's own rule replaces the generic step only for that one task; its other tasks keep
their generic steps until ENG adds a school version. Task IDs are the same for every school,
so prerequisites such as "DMV needs check-in" work everywhere. If a task in the workflow needs
a task that is not, the resolver fails instead of dropping that prerequisite. A completed task
must belong to the selected workflow. No applicable tasks, or a prerequisite that does not
apply to the school, raises `RulesError` (a kind of `ValueError` meaning the rules file is at
fault, so the API answers `503`, not `422`). Generic check-in
content is supplied by ENG in the rules file; the resolver invents none when it is absent. A
profile with no school ID (or `_generic`) gets only shared and generic steps.

1. In `completed_tasks` → `Completed`.
2. Otherwise `missing_prerequisites` = its prerequisites that are not completed, in file order.
3. For each of its rules with `timing`: if `as_of` is before the unlock date, add a `timing`
   blocker with that `unlocks_on`, the rule's `verification_status`, and its `statement` as the
   explanation. On the unlock date itself, the task is no longer blocked.
4. Any missing prerequisite or timing blocker → `Blocked`.
5. Otherwise, in `awaiting_reply` → `In Progress`; otherwise `Ready`. `Blocked` wins over
   `In Progress`: waiting on an office does not let a student skip a prerequisite or a date.

Other fields on each task:

- `next_action`: for a task blocked by a missing prerequisite, points at the first one with the
  text `Finish "<title>" first.`; otherwise `null`.
- `sources`: one per applicable rule, with its `source_url`, `last_verified`, and explicit
  `verification_status`, including after a timing blocker expires or a task is completed.
- `before_you_go`: the task's visit details from the rules file, filtered to this student's
  school, with `citations` (see "The rules file"); `null` when there are none.

The result is a Workflow with `schema_version: "1.0"` and `is_mock: false`, tasks in file order.
It passes the same consistency checks as the mock.

Invalid rules or profiles raise `ValueError`, so bad input fails loudly. Loading a missing or
unreadable rules file raises the corresponding file error.

- Rules file: an unknown key, a duplicate task or rule ID, a task with no rules, a prerequisite
  or `rule_id` that does not exist, a prerequisite loop (A needs B, B needs A), invalid school
  scope, or a `verified` rule with missing evidence or identical checkers.
- Profile: a `completed_tasks` or `awaiting_reply` ID that is not in this student's workflow or
  is listed twice, a task marked completed before its prerequisites, a task both completed
  and awaiting a reply, no applicable tasks, or a dependency unavailable for that school.

## Answers to FE's Day 1 questions

1. **Task status updates: PATCH or POST?** POST. The build plan names "two POST endpoints
   (resolve a blocker, mark a task done)" on Day 3, not Day 2. Neither the build plan nor the
   setup guide mentions
   `PATCH /api/tasks/{task_id}/status`. The guide's `/tasks/{id}/resolve` is marked as an
   example, so the names above are proposed. The client never sets a status directly, because
   code decides status. The request and response are in "Task actions" above.
2. **Session identity?** There is none on the server. No `session_id`, no server memory, no
   SQLite. `st.session_state` keeps the profile across Streamlit reruns in the same browser tab.
   A page refresh or a new tab starts a new session, so the student onboards again, which is
   fine for the demo.

## Open questions for the team

- **Enrollment date (ENG, FE and the team).** ENG's handoff merged with #18
  (`docs/day2-rules-handoff.md`) asks BE to "add optional enrollment_date and a separate
  deadline field": for the agreed demo, enrolling on August 13 means payment is due August 14
  under the CRC fee rule (`rule_crc_fall_2026_payment_deadline`), and a missing enrollment date
  must not fall back to `arrival_date`. Today the contract has neither field. Because the
  profile rejects unknown keys (#20), sending `enrollment_date` now gets a `422`; the fee task
  shows its source but no date. It isn't built because the plan's ground rules list what a
  student gives us (school, state, visa type, arrival date, whether they have an SSN), and this
  widens that list. **Proposed, pending ENG, FE and team agreement:**
  - `student_profile.enrollment_date: date | null` (default `null` = not given: no deadline is
    shown, and it is never estimated from `arrival_date`).
  - `Task.due_on: date | null`, filled only when the rule has a deadline and the date is given.
  - A rules-file `deadline` field such as `{"from": "enrollment_date", "days": 1}`; ENG confirms
    that "the next day" means one calendar day.
  - A deadline never blocks a task or changes its status. It is shown beside the task, with
    the rule's verification state.
- **State.** School search returns California rows only, the profile has no state field, and
  every profile gets the California rules. Supporting other states needs a contract decision.
- **Unknown `school_id`.** It is accepted and gets the generic steps (`school_verified:
  false`). BE could instead reject an ID that isn't in the school directory with a `422`.
  Proposed, pending FE agreement.
- **Readiness inputs.** See "Readiness" above: visit details from ENG, and whether the profile
  carries the student's document checkboxes.
- **Assistant route and response.** See "AI integration" above.

## Changelog

- 2026-11-16, PR #15 pre-merge review: clarify required intent risk flags and
  free-text limits; refer SEVIS state questions before model calls; allow tuition
  “work out” wording. The manual evaluator derives task risk from cited rules.

- 2026-11-16, STU-D05-BE-docs-status: #20, #21 and #22 are merged, so every "in review" label
  for them now says "on main". No API or model change.

- 2026-11-16, STU-D03-BE review fix: count duplicate task IDs in one pass and cap each
  `completed_tasks` and `awaiting_reply` list at 1,000 items. Larger lists return `422`
  before the resolver runs; existing duplicate-ID errors keep the same message.

- 2026-11-16, STU-D05-BE-before-you-go (in review): a rules-file task can carry
  `before_you_go`, each fact citing a rule. The resolver keeps only facts whose rule applies to
  the student's school, adds the cited rules to `sources`, and the response's BeforeYouGo gains
  `citations` (additive; the string fields are unchanged). `school_verified` counts the school
  rules behind shown facts.
- 2026-11-16, STU-D05-BE docs: status labels now say what is on `main`, in review, deployed or
  proposed (D03 to D05 are open PRs, nothing is deployed). Real request and response examples
  for `POST /workflow` and both task actions, a field-by-field request guide, the stateless round
  trip, the readiness gap, and what exists for AI. The rate limit is one allowance across all
  endpoints (Codex). The enrollment-date request from ENG's handoff is reconciled as a proposal.
- 2026-11-16, STU-D04-BE: requests with the right API key share one rate-limit allowance;
  other requests are counted by address, so they can't use up the dashboard's. No shape
  changes.
- 2026-11-15, STU-D03-BE: wire the resolver into the API. `POST /workflow` and the two task
  actions are live; `GET /workflow` with `USE_MOCK=false` runs the demo profile through the live
  engine. The profile gains `awaiting_reply`, which produces `In Progress`. Request models reject
  unknown keys (`422`), which settles that open question. Add the `X-API-Key` check and the rate
  limit. `422` now means only a client mistake; our own faults are `500` or `503`. Resolve
  returns `409` when the next action is itself blocked. Proposed, pending agreement: the
  California default for `as_of` (FE) and `email_draft: null` (AI and FE).
- 2026-11-14, STU-D02-BE review fixes (PR #13): choose school or generic rules per task, so one
  school rule no longer hides the generic steps for that school's other tasks; `school_verified`
  is false while any task uses generic steps. Every task must cite at least one rule.
- 2026-11-13, STU-D02-BE: document the rules-file shape the resolver reads (unknown keys
  rejected; `verified` needs full evidence from two different checkers; school rules need a
  `school_id`), propose the `timing` field, and document the dependency resolver with school
  scoping and ENG's `_generic` fallback. Add `school_id` and `school_verified` to the profile and
  `verification_status` to Source, in the contract and the mock. Add school search, pending
  ENG's sourced CSV. Proposed, pending agreement: the internal ID `crc` (ENG) and reading
  `Source.verification_status` in the dashboard (FE). The Workflow API stays mock-only.
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
