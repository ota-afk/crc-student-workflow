# CRC Hacks Student Workflow Platform

A dashboard that shows an international student at Cosumnes River College which arrival tasks
are done, ready, in progress or blocked, and what to do next. A FastAPI backend serves the
workflow and a Streamlit dashboard displays it.

**Status (2026-11-16):** `main` has the resolver, ENG's rules, school search, the live
workflow endpoints, the API key, the rate limit, the CI end-to-end test and the deploy setup
(#20, #21 and #22). Cited visit details are in review (#23). Nothing is deployed yet.
[docs/contract.md](docs/contract.md) marks what is on `main`, in review, or proposed.

How it works:

- The **API** computes each student's workflow from ENG's rules file (`data/rules/rules.json`)
  and the profile the dashboard sends: code decides every status, never the AI. The server
  stores nothing between requests. Request and response shapes are in
  [docs/contract.md](docs/contract.md).
- Every fact carries its source and verification state. Today every rule is still
  `needs_verification`, so the dashboard must label it "Not verified".
- `GET /workflow` serves the sample file (`data/mock/workflow.mock.json`, `is_mock: true`) while
  `USE_MOCK=true`, the local default. `POST /assistant` uses OpenAI when the API has
  `OPENAI_API_KEY` and `OPENAI_MODEL`, and returns a safe fallback message without them.
- Set up for Render's free plan ([docs/deploy.md](docs/deploy.md)); the live URLs go there
  after the first deploy.

## First-time setup

Install [Git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/). uv installs
Python 3.12 for you.

```bash
git clone https://github.com/ota-afk/crc-student-workflow.git
cd crc-student-workflow
uv sync --locked
cp .env.example .env
```

On Windows PowerShell use `Copy-Item .env.example .env`. The API and dashboard run without any
keys. An OpenAI key is only needed for the manual OpenAI smoke test below. Never commit `.env`.

## Run the API

### Flyover design frontend

The travel-inspired frontend combines profile setup and sequential workflow steps,
with readiness/checklists and an Airshow preview on separate screens. From this checkout,
start these in two terminals:

```bash
USE_MOCK=false uv run --locked uvicorn student_workflow.api:app --reload --host 127.0.0.1 --port 8001
```

```bash
API_URL=http://127.0.0.1:8001 uv run --locked streamlit run app/flyover_app.py --server.address 127.0.0.1 --server.port 8502
```

Open [Flyover](http://127.0.0.1:8502). `.streamlit/config.toml` supplies the light theme
and palette. Render runs Flyover at the live dashboard link
(https://crc-workflow-dashboard.onrender.com). The original dashboard remains at
`app/streamlit_app.py` for local runs; its setup and Day 3/4 preview behavior are documented
below. After editing files under
`src/`, restart Streamlit: it does not reload those modules on its own.

Flyover has two pages. Page 1 is profile setup over the travel banner and the workflow, one
step at a time: the step title flips in like a departures board, the status in the centre
saves to the live API, and the three-piece flight map fills in behind it. Page 2 (Next or
View checklist) has Readiness and Before you take off (task left, status centre,
prerequisite right; a prerequisite opens its documents and sources), a quote card, a
scroll-driven flight into Airshow, and the handoff template with .txt/.md export. A blocked
task's checklist has **Resolve blocker** (`POST /tasks/{task_id}/resolve`), which shows the
API's email draft and marks the missing step as waiting on an office.
Statuses and prerequisites remain backend-authoritative. Applying a new profile requires
explicit confirmation when progress exists. Settings can pause the banner or reduce motion;
OS reduced-motion preferences are also respected, and browsers without CSS scroll timelines
show the plane standing still. Profile and progress stay in the Streamlit browser session;
a new session starts from the demo profile with no steps completed yet.

The first screen is a **demo sign-in**: email (real, shape-checked), a password (any text
works; never stored or sent) and the profile questions (school, arrival date, visa type, SSN
yes/no). "Sign in and start" builds the workflow from those answers through the API, so
Profile setup opens pre-filled. There are no accounts: the email stays in the browser session
and never reaches the API or the model. Settings shows the masked address and Sign out, which
clears the session.

On a first visit a spotlight tour dims the page and walks through page 1 one control at a
time (profile, Generate, the current step, View checklist, AI Help, Next, Settings), with Back,
Next, Skip and Escape. It only explains; it never changes anything. The tab remembers it was
seen; Settings → Replay tutorial shows it again.

When the current or next step has appointment guidance (school check-in, REAL ID), page 1
shows it word for word from `rules.json` with its "Not verified" label and official link. The
student can add weekly free times (Pacific time) under it; they stay in the browser session,
are never sent to the API or the model, and are cleared by Start fresh. With no structured
office hours on file, Flyover never claims a match: it says to check the office's calendar.
The notice can be dismissed; the same text stays in the task's checklist.

The **AI Help** logo in the header opens a dropdown chat (Airshow) right below it, on either
page, without leaving the page. It calls `POST /assistant` with the workflow's `as_of` and
progress, the task in view, and `page_context` (`journey` on page 1, `readiness` on page 2),
so an answer reflects "Resolve blocker" and "Mark done"; it never sends `student_id`. The
last 10 questions stay in the dropdown for the session; answers from before a progress change
are marked "Earlier answer". A timeout shows its own message and keeps the unsent question.
The Airshow section at the bottom of page 2 is separate: a handoff drafted from a local
template, not by AI, and labeled that way. Verification warnings and official sources remain
visible. Generated-art provenance and prompts are in
[`app/assets/flyover/README.md`](app/assets/flyover/README.md).

### Original dashboard API

```bash
uv run uvicorn student_workflow.api:app --reload --port 8000
```

Check <http://localhost:8000/health> (expect `{"status": "ok"}`),
<http://localhost:8000/workflow> and <http://localhost:8000/docs>.

## Run the dashboard

In a second terminal, with the API still running:

```bash
uv run streamlit run app/streamlit_app.py
```

Open <http://localhost:8501>. It should show the sample-data warning and six tasks.

### Day 3: task details and assistant

Open **Task details**, choose **Apply for California REAL ID**, and check a document.
The missing-document list updates immediately. Switch to another task and back:
your choices remain for this browser session. Checking every document does not
unlock a blocked task, mark it completed, or establish eligibility. Visit details
and source links retain their verification warnings and dates.

Open **Assistant** and enter a question. By default it shows a fixed, explicitly
labeled sample response: no LLM request is made. **Clear conversation** removes
chat history without clearing document selections. Neither is written to disk;
a new browser session starts fresh. Do not enter personal identifiers in chat.

With `ASSISTANT_MODE=live`, the tab calls the API's `POST /assistant`
([contract](docs/contract.md#post-assistant)) at `API_URL`, with the same `X-API-Key`
header and 10-second timeout as the workflow calls. It sends the current workflow's
`as_of` and progress (`completed_tasks`, `awaiting_reply`), so an answer reflects
"Resolve blocker" and "Mark done"; it never sends `student_id`. A timeout shows its own
message. The frontend never calls a model directly.

In **Profile**, prepare a California-only school/profile draft using **Search
schools**. Other states are unsupported; a missing-school choice remains
available. Search failures can be retried without clearing document selections.
**Generate workflow**, **Resolve blocker** and **Mark done** are visibly disabled
while BE's POST contracts/routes remain unavailable. Profile edits are not yet
applied to the displayed workflow. **View checklist** on a task card and its
prerequisite buttons navigate directly to Task details; **View readiness** opens
an inventory summary without changing task status.

### Day 4: email preview and deployment preparation

In **Task details**, select a blocked task and click **Resolve blocker**. The dashboard
calls the live API, which marks the office as written to and returns an email draft. Copy
the subject and body with the copy icon, replace placeholders in your own mail app, and
confirm the recipient. The draft is labeled unverified; nothing is sent. **Mark done**
completes a Ready or In Progress task (for example, the proof-of-residency task unblocks
the DMV task). **Generate workflow** (Profile tab) sends the chosen school, visa, arrival
date and SSN yes/no to the API and shows the workflow it returns. The API stores nothing,
so the dashboard keeps the profile and one `as_of` date for the session and sends them on
every request. Set `API_KEY` in the dashboard's environment to the same value as the API.
Changing the profile clears old drafts.
See [Day 4 status and Render settings](docs/day-4-frontend.md) for deployment
preparation and the missing live backend dependencies.

## Environment variables

| Name | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Enables model calls from the Assistant API and the manual OpenAI smoke test. Set it in the API service environment or local `.env`. |
| `OPENAI_MODEL` | empty | Model used by the Assistant API and the manual OpenAI smoke test. The smoke test uses `gpt-6-luna`. |
| `USE_MOCK` | `true` | Only changes `GET /workflow`: `true` serves the mock file, `false` runs the demo student through the live engine. `POST /workflow` and the task actions always use the live engine. |
| `API_KEY` | empty | Shared secret for the `X-API-Key` header, needed on every endpoint except `/health` (FastAPI's `/docs` pages stay open; they show no data). Empty turns the check off (local only); the deployed API must set it. Never commit it. |
| `RATE_LIMIT` | `60/minute` | One allowance shared by all endpoints except `/health`: requests with the right `API_KEY` share one, every other address has its own. Over it returns `429`. An invalid value stops the API at startup. |
| `MOCK_PATH` | `data/mock/workflow.mock.json` | Path to a different mock file. |
| `RULES_PATH` | `data/rules/rules.json` | Path to a different rules file for the resolver. |
| `SCHOOLS_PATH` | `data/schools/sevp_schools_ca.csv` | Path to ENG's sourced California F-1 school directory. |
| `API_URL` | `http://localhost:8000` | Where the dashboard and the check script find the API. |
| `CORS_ORIGINS` | `http://localhost:8501` | Comma-separated origins allowed to call the API from a browser. Never `*`. |
| `ASSISTANT_MODE` | `mock` | Fixed sample chat preview. `live` calls the API's `POST /assistant` at `API_URL`. |

## School search and rule scope

`GET /schools?q=<name-or-city>&limit=20` searches ENG's sourced California school CSV
(`data/schools/sevp_schools_ca.csv`, merged in #14) without making external requests. If the
file can't be read, the endpoint returns `503` instead of inventing schools. A school being
in the directory doesn't mean its own steps are verified (`school_verified`). See [the contract](docs/contract.md#school-search) for the
CSV columns and response fields. The default limit is 20, with a maximum of 100.

The resolver selects school rules using `student_profile.school_id`; `institution` is a
display name. **Proposed, pending ENG agreement:** the existing CRC rule and mock use `crc`
as an internal ID, not an official SEVP code. Everyone gets the shared federal and
California rules. For school steps, the choice is made per task: a task uses the school's own
rule when one exists, and otherwise the generic rule ENG supplies with `school_id: "_generic"`.
One school's rules are never used for another school. `school_verified` is computed by the
engine, and it stays false while any task uses generic steps.

Source verification travels with each rule even after its timing blocker disappears. A URL
and an old verification date alone cannot make a rule verified. The dashboard also requires
explicit source verification.

## Live workflow and task actions

`POST /workflow` takes `{"as_of": "2026-08-14", "student_profile": {...}}` and returns that
student's workflow, computed from `data/rules/rules.json`. `POST /tasks/{task_id}/complete`
("Mark done") and `POST /tasks/{task_id}/resolve` ("Resolve blocker") take the same body and
return the updated profile inside the answer. The server stores nothing, so the dashboard keeps
that profile and sends it next time. See [the contract](docs/contract.md#task-actions)
for the rules and error codes. Try them at <http://localhost:8000/docs>.

`POST /assistant` uses the current workflow date and progress to explain a task. See the
[Assistant API contract](docs/contract.md#post-assistant) for the request and fallback behavior.

## Manual OpenAI smoke test

Set `OPENAI_API_KEY` and `OPENAI_MODEL` in your environment or local `.env`.
Existing environment variables take precedence over `.env`.

The tested model is `gpt-6-luna`. The script uses the Responses API,
Structured Outputs, and `reasoning={"effort": "none"}`. Other models may
require changes to these settings.

Run manually from the repository root:

```bash
uv run --locked python scripts/smoke_test_openai.py
```

This makes a real, paid API request. It is not part of pytest or CI.
It sends one fixed synthetic request, uses `store=False`, a 30-second
timeout, zero automatic retries, and a 200-token output limit.

Success prints `PASS: API connection, schema validation, and classification.`

The test verifies API connectivity and one structured classification.
It does not verify application-wide AI integration or privacy enforcement.

## Run the tests

```bash
uv run pytest
uv run ruff check .
```

Before recording the demo, with the API running:

```bash
uv run python scripts/check_no_sample.py
```

It exits with an error while sample or unverified data is still showing.

End-to-end check of a running API (every endpoint, then the demo path). CI runs it against a
fresh server on every pull request:

```bash
uv run --env-file .env.smoke python scripts/smoke_test.py   # see docs/deploy.md
```

## Deploy

Both services run on Render's free plan from `render.yaml`. Setup, the values to enter, the
live URLs and troubleshooting are in [docs/deploy.md](docs/deploy.md). The order of checks for
recording day and before the repo goes public (warm-up, smoke test, pre-recording check, key
audit) is in [docs/release-checklist.md](docs/release-checklist.md).

## Project structure

```text
app/streamlit_app.py          Streamlit dashboard
src/student_workflow/         config.py, contract.py (Pydantic models), api.py (FastAPI),
                              rules.py (rules-file models), engine.py (dependency resolver)
                              schools.py (sourced school search)
data/mock/workflow.mock.json  sample workflow (is_mock: true)
data/rules/rules.json         tasks and rules (written by ENG, checked by tests)
data/schools/                 ENG's scoped California F-1 school directory
docs/                         contract.md, deploy.md, release-checklist.md, sources.md,
                              credits.md, ai-data-policy.md
scripts/check_no_sample.py    pre-recording check
scripts/smoke_test.py         end-to-end check of a running API (also run by CI)
scripts/warm_up.py            wakes both live services before recording or judging
scripts/audit_secrets.py      searches all git history for keys before the repo goes public
scripts/smoke_test_openai.py  manual, paid OpenAI check (not run by CI)
tests/                        pytest tests
.github/workflows/ci.yml      CI: ruff check, pytest, and the end-to-end smoke test
render.yaml                   Render Blueprint: the API and dashboard deploys
```

## How we work

- Tickets: `STU-D01-BE` means Day 1, backend. One branch per ticket, named
  `feature/<ticket-id>`.
- Never push to `main`. Open a small pull request, get one review, and merge the same day once
  CI is green.
- The API's request and response shapes are in [docs/contract.md](docs/contract.md). Change
  `contract.py`, the mock and `docs/contract.md` together in one pull request, and tell everyone.
- Done means: merged and reviewed, tests pass, runs from this README, demoable in 30 seconds.

## Adding dependencies

Only one person changes `pyproject.toml` at a time.

```bash
uv add <package>
uv add --dev <package>
```

Commit `pyproject.toml` and `uv.lock` together. If `uv.lock` conflicts after a merge, pull, run
`uv lock`, and commit the result.

## Troubleshooting

- **Dashboard says "Could not reach the API"**: start the API first, and check `API_URL` in `.env`.
- **An endpoint returns 401**: the API has `API_KEY` set and the request did not send the same
  value in the `X-API-Key` header.
- **An endpoint returns 429**: the rate limit was reached; wait a minute, or raise `RATE_LIMIT`
  locally.
- **`ModuleNotFoundError: student_workflow`**: run commands with `uv run` from the project root.
