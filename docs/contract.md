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
| `GET /schools?q=&limit=20` | Day 2 | Searches ENG's California F-1 school CSV by name or city. Returns 503 until that file is available. |
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
| `school_id` | string or null | `null` |
| `school_verified` | boolean, computed by the resolver | `false` |

`school_id` is the stable identifier shared by the school directory and school-specific
rules. `institution` stays the display name; the resolver never guesses an ID from that name.
**Proposed, pending ENG agreement:** this branch uses `crc` as the internal identifier for
the existing CRC rule. It is not an official SEVP code.
The resolver recomputes `school_verified` rather than trusting a value sent by a client.
It is true only when the selected school has applicable school-specific rules and all those
rules are verified. Generic rules never make a school's own requirements verified.

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
    "school_id": "crc",
    "visa_type": "F-1",
    "arrival_date": "2026-08-11",
    "has_ssn": false,
    "completed_tasks": ["task_i94_retrieval", "task_sevis_fee"]
  }
}
```

The request leaves out `school_verified`: the resolver computes it, and ignores any value sent.

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
| `rule_ids` | array of rule IDs from this file | `[]` |

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

## Dependency resolver (Live, Day 2; not wired to the API until Day 3)

`src/student_workflow/engine.py`:

```python
resolve(rules: RulesFile, profile: StudentProfile, as_of: date) -> Workflow
```

`as_of` is always passed in (the plan's injected "as of" date), so the demo can say "arrived
3 days ago" and tests repeat. `rules.load_rules(path=None)` reads the rules file; with no path it
uses `RULES_PATH`, default `data/rules/rules.json`.

How each task's status is decided (code decides status, never the AI):

First, select the applicable rules. Federal and California rules are shared. School rules
must match `student_profile.school_id`; when no school-specific rules match, use available
`_generic` rules. A task is excluded if any of its rules belongs to a different school. If an
included task depends on an excluded task, fail instead of dropping that prerequisite. A
completed task must belong to the selected workflow. No applicable tasks raises `ValueError`.
Generic check-in content is supplied by ENG in the rules file; the resolver invents none when
it is absent. A profile with no school ID can receive only shared and generic tasks.

1. In `completed_tasks` → `Completed`.
2. Otherwise `missing_prerequisites` = its prerequisites that are not completed, in file order.
3. For each of its rules with `timing`: if `as_of` is before the unlock date, add a `timing`
   blocker with that `unlocks_on`, the rule's `verification_status`, and its `statement` as the
   explanation. On the unlock date itself, the task is no longer blocked.
4. Any missing prerequisite or timing blocker → `Blocked`; otherwise `Ready`.
5. `In Progress` is never produced yet: it needs the Day 3 "awaiting reply" state.

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

- Rules file: an unknown key, a duplicate task or rule ID, a prerequisite or `rule_id` that does
  not exist, a prerequisite loop (A needs B, B needs A), invalid school scope, or a `verified`
  rule with missing evidence or identical checkers.
- Profile: a `completed_tasks` ID that is not in the rules file, or a task marked completed
  before its prerequisites, no applicable tasks, or a dependency unavailable for that school.

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
- **Unknown keys.** Pydantic ignores keys it does not know, so a typo like `"enrolment_date"`
  disappears silently. BE proposes making request models reject unknown keys (a `422`) when the
  POST endpoints are built.

## Changelog

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
