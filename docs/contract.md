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
| `GET /health` | Live | Returns `{"status": "ok"}`. No API key and no rate limit, so hosts and warm-up pings can call it. |
| `GET /workflow` | Live | The fixed demo student. `USE_MOCK=true`: the mock file. `USE_MOCK=false`: the mock's demo profile and "as of" date run through the live engine. Kept for the tests and `scripts/check_no_sample.py`. |
| `GET /schools?q=&limit=20` | Live (Day 2) | Searches ENG's California F-1 school CSV by name or city. Returns 503 if that file is unavailable. |
| `POST /workflow` | Live (Day 3) | Takes a profile, returns that student's computed workflow. Always the live engine. |
| `POST /tasks/{task_id}/resolve` | Live (Day 3) | "Resolve blocker": marks the blocked task's next action as awaiting a reply (`In Progress`). |
| `POST /tasks/{task_id}/complete` | Live (Day 3) | "Mark done": adds the task to the student's completed tasks. |

There is no `/api/` prefix, to match the live endpoints. Every endpoint except `/health` needs
the API key header and counts toward the rate limit (see "Access" below).

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
| `awaiting_reply` | array of strings (task IDs), set by `POST /tasks/{id}/resolve` | `[]` |
| `school_id` | string or null | `null` |
| `school_verified` | boolean, computed by the resolver | `false` |

A profile with a key not in this table is rejected (`422`), so a typo like `"completed_task"`
fails loudly instead of being ignored. `awaiting_reply` lists the tasks whose office the student
has written to and is waiting on. A task cannot be in both `completed_tasks` and
`awaiting_reply`.

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

**Pending FE integration:** the current dashboard checks source URLs and dates but does not
yet read `Source.verification_status`. FE needs to apply that check before live workflows are
enabled, so an unverified rule cannot look verified after its timing blocker expires. This
branch carries the verification state in the response; the dashboard change remains FE's work.

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

## POST /workflow (Live, Day 3)

The dashboard sends the profile it keeps in `st.session_state`. The plan requires the engine
to accept an injected "as of" date so the demo can show a fixed day ("arrived 3 days ago").
`POST /workflow` always runs the live engine on `data/rules/rules.json`; `USE_MOCK` only changes
`GET /workflow`.

The request shape below was BE's Day 1 proposal (merged in PR #4). The code version is
`WorkflowRequest` in `contract.py`. Unknown keys are rejected with a `422`, at the top level and
inside `student_profile`.

**Proposed, pending FE agreement:** `as_of` is optional. When it is omitted, the API uses today's
date in California (`America/Los_Angeles`), because the students are in California and the
server's own clock may be on UTC. The demo always sends `as_of` explicitly.

Request:

```json
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
```

The request leaves out `school_verified`: the resolver computes it, and ignores any value sent.
`awaiting_reply` can be left out too (it defaults to `[]`).

Response: `200` with a Workflow (above). The example below is **sample data**, trimmed to one
task. Its check-in task, priority, prerequisites, and status are illustrative and unverified;
they do not establish CRC requirements. A live response uses `is_mock: false` and must visibly
label any unverified facts.

```json
{
  "schema_version": "1.0",
  "is_mock": true,
  "as_of": "2026-08-14",
  "student_profile": {
    "student_id": "demo_001",
    "institution": "Cosumnes River College",
    "school_id": "crc",
    "school_verified": false,
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

Errors (every workflow endpoint uses the same ones):

| Code | When | `detail` |
| --- | --- | --- |
| `401` | `X-API-Key` missing or wrong (only when the server has an `API_KEY` set) | `Missing or invalid API key` |
| `404` | Task actions only: `task_id` is not in this student's workflow | Names the task ID |
| `409` | Task actions only: the task is not in a state the action allows (see below) | Says why |
| `422` | The request fails `WorkflowRequest` (missing field, bad date, unknown key), or the profile breaks a resolver rule (an unknown task ID, a task listed twice, a task completed before its prerequisites, a task both completed and awaiting a reply) | FastAPI's field errors, or the resolver's message |
| `429` | Rate limit reached | slowapi's message |
| `500` | A bug in our code (the engine built an invalid workflow) | `Internal error`; the details go to the server log only |
| `503` | The rules file is missing, invalid, or cannot build a workflow for this school; or (`GET /workflow` only) the demo profile no longer fits the rules | `Workflow is temporarily unavailable`; the real reason goes to the server log only |

A `422` always means the request can be fixed by the client. Problems on our side are `500` or
`503`, so a student never sees our internal errors described as their mistake.

`student_id` is a made-up ID such as `demo_001`. Never a name, passport number or SEVIS ID.

## Task actions (Live, Day 3)

Both take the same request body as `POST /workflow`. The returned `student_profile` is the new
state: FE saves it back into `st.session_state`, then calls `st.rerun()`. Because the server
stores nothing, this is how a change survives the next click.

The demo path on ENG's rules: the DMV task is `Blocked`, and its next action is proof of
residency. "Resolve blocker" on the DMV task moves residency to `In Progress`. "Mark done" on
residency makes the DMV task `Ready`.

**`POST /tasks/{task_id}/complete`** returns a Workflow.

- Allowed when the task is `Ready` or `In Progress`. It adds `task_id` to `completed_tasks` and
  removes it from `awaiting_reply`. Tasks that depended on it can now become `Ready`.
- `409` when the task is `Completed` already, or `Blocked` (by a missing prerequisite or by a
  date that has not arrived). A student cannot finish a step the workflow says they cannot start.

**`POST /tasks/{task_id}/resolve`** returns `{"workflow": Workflow, "email_draft": null}`.

- `task_id` is the blocked task (the one with the "Resolve blocker" button). Allowed when it is
  `Blocked` by a missing prerequisite. It adds that task's `next_action.task_id` (its first
  missing prerequisite) to `awaiting_reply`, which shows that prerequisite as `In Progress`.
  Resolving again is allowed and changes nothing.
- It never makes a task `Ready`: only completed prerequisites, or the "as of" date passing, do
  that. The blocked task stays `Blocked` until the prerequisite is marked done.
- `409` when the task is not `Blocked`, or is blocked only by a date (there is no office to
  write to; the student waits for `unlocks_on`). A task blocked by both a missing prerequisite
  and a date can be resolved: the prerequisite moves to `In Progress`, and the date still holds.
- `409` when the next action is itself `Blocked` (a chain: c needs b, b needs a). Marking b as
  awaiting a reply would show nothing, because `Blocked` wins. The student resolves b first.
  ENG's rules today have no chain (only DMV needs residency).
- `email_draft` is always `null` for now: `null` = no draft is available, so FE shows "Email
  draft not available yet" and never a made-up one. AI's `generate_email()` does not exist yet;
  its fields are agreed with AI before this becomes an object. **Proposed, pending AI and FE
  agreement.**

## Access: API key and rate limit (Live, Day 3)

- **API key.** When the server's `API_KEY` setting is not empty, every endpoint except `/health`
  needs the header `X-API-Key: <that value>`, or it returns `401`. FastAPI's own pages (`/docs`,
  `/redoc`, `/openapi.json`) stay open: they show the API's shape, never any data, and the
  interactive `/docs` page still needs the key to call an endpoint. When `API_KEY` is empty (local
  development and the tests), the check is off and the server logs a warning at startup. The
  deployed API must set it. FE sends the header from its own `API_KEY` setting. The key is a
  shared secret between our two services, so it lives in each host's secret settings, never in
  the code or the dashboard's page.
- **Rate limit.** `RATE_LIMIT` (default `60/minute`) applies to every endpoint except
  `/health`. Over the limit returns `429`. Requests with the right key (the dashboard's server)
  share one allowance; every other request is counted by client address, so requests without
  the key can never use up the dashboard's allowance (STU-D04-BE). That caps the whole
  dashboard's traffic, which protects the OpenAI budget from someone hammering the endpoint.
  An invalid `RATE_LIMIT` stops the API at startup instead of failing every request.

## The rules file: `data/rules/rules.json` (Live, Day 2)

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

### Timing (Proposed, pending ENG agreement)

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

## School search (Day 2)

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

## Dependency resolver (Live, Day 2; used by the API since Day 3)

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
- `before_you_go`: `null` (the rules file has no visit details yet).

The result is a Workflow with `schema_version: "1.0"` and `is_mock: false`, tasks in file order.
It passes the same consistency checks as the mock.

Invalid rules or profiles raise `ValueError`, so bad input fails loudly. Loading a missing or
unreadable rules file raises the corresponding file error.

- Rules file: an unknown key, a duplicate task or rule ID, a task with no rules, a prerequisite
  or `rule_id` that does not exist, a prerequisite loop (A needs B, B needs A), invalid school
  scope, or a `verified` rule with missing evidence or identical checkers.
- Profile: a `completed_tasks` or `awaiting_reply` ID that is not in this student's workflow or
  is listed twice, a task marked completed before its prerequisites, a task both completed and awaiting a reply, no
  applicable tasks, or a dependency unavailable for that school.

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
- **State.** School search currently accepts California rows only. The profile has no state
  field; support for other states still requires a contract decision.
- **Email draft.** `POST /tasks/{id}/resolve` returns `email_draft: null` until AI's
  `generate_email()` exists and AI, FE and BE agree on its fields.

## Changelog

- 2026-11-16, STU-D04-BE: requests with the right API key share one rate-limit allowance;
  other requests are counted by address, so they can't use up the dashboard's. No shape
  changes.
- 2026-11-15, STU-D03-BE: wire the resolver into the API. `POST /workflow` and the two task
  actions are live; `GET /workflow` with `USE_MOCK=false` runs the demo profile through the live
  engine. The profile gains `awaiting_reply`, which produces `In Progress`. Request models reject
  unknown keys (`422`), which settles that open question. Add the `X-API-Key` check and the rate
  limit. `422` now means only a client mistake; our own faults are `500` or `503`. Resolve
  returns `409` when the next action is itself blocked. Proposed, pending agreement: the California default for `as_of` (FE) and
  `email_draft: null` (AI and FE).

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
