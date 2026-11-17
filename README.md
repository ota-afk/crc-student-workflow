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

Flyover's sticky header has a labelled **Go to** selector with six destinations: Workflow
and readiness, Checklist, Alerts, Profile, Office handoff, and Updates and credits. The first
three are also sibling tabs under the header, and both controls set the same page. One
selected task follows you across every page: pick it in **Choose a task** (or "Your checklist")
and View checklist, Open full checklist and the profile shortcut all open the Checklist tab
with it. Workflow and readiness holds profile setup over the travel banner, the selected step
(its title flips in like a departures board after a completion, its status saves to the live
API, and the three-piece flight map fills in behind it), Readiness with completed history, and
Before you take off with every unfinished task (task left, status centre, prerequisite right,
then **Edit status**; a prerequisite opens its documents and sources). Each Edit status saves
against its own task; a completed task offers **Reopen task** (refused, with a link, while a
completed task still depends on it), and after a completion the next suggested task is offered,
not switched to. Office handoff has a scroll-driven flight into Airshow and the handoff
template with .txt/.md export. A blocked
task's checklist has **Resolve blocker** (`POST /tasks/{task_id}/resolve`), which shows the
API's email draft and marks the missing step as waiting on an office.

**Before you go** (a prerequisite in the task table) is a quick look: the selected task first,
then one section per prerequisite, each with its title, status and its own documents (a
document two tasks need stays under both, with "Also needed for"), the task's action link, its
office rows and **Open full checklist**. The **Checklist** tab puts the shared status control
beside the title, then documents (inventory only), the next action, reminders, visit details
and office hours; completing a step keeps you on that task. Evidence sits behind **more info
included here**, which opens in place: the source's name and link, the real verified date, or
"Confirm this detail with the office." / "Source unavailable. Confirm with the office." Each
office row has an underlined **View [office] hours source** link (plain text if the URL is
missing or unsafe). Action links are named for their real destination and come only from URLs
the API cites for that task (`flyover_checklist.py`), so CRC links stay CRC-only: Schedule a
DMV visit, Open the REAL ID document checklist, Call to schedule (CRC check-in, by phone), Open
CRC fee payment instructions.
Statuses and prerequisites remain backend-authoritative. Applying a new profile requires
explicit confirmation when progress exists. Settings can pause the banner or reduce motion;
OS reduced-motion preferences are also respected, and browsers without CSS scroll timelines
show the plane standing still. Profile and progress stay in the Streamlit browser session;
a new session starts from the demo profile with no steps completed yet.

The public Flyover link is a **historical walkthrough set on August 14, 2026**
(`flyover_scenario.py`, the one place its date and profile are defined). A notice saying so
("Flyover demo · Updates coming soon…") is drawn before any API call, so it shows on the first
screen, every page, in Settings and when the API is down; it never depends on `is_mock`.
The first screen's primary action, **Try the CRC demo**, needs no email or password: it builds
a synthetic CRC student (arrived August 11, enrolled August 13 for Fall 2026, nothing done
yet) through `POST /workflow` with `as_of` 2026-08-14. **Or use your own details** asks for an
email (shape-checked, for reminders only) and the profile questions; there is no password
field. Every Flyover request (profile changes, task actions, Airshow) sends the workflow's
`as_of`, and exported handoffs repeat the scenario line; the API's own default (today in
California) is unchanged for other callers. There are no accounts: the email stays in the
browser session, never reaches the model, and goes to the API only when you schedule a
reminder.

Choose an **enrollment term** (Fall 2026 or Spring 2027) and optionally enter the actual
**enrollment date** at sign-in or in Profile setup. Flyover uses that semester's CRC payment
table. For Spring 2027, students enrolled by December 25, 2026 pay by January 8, 2027;
students enrolled from December 26 pay the following day. Spring rules show **Not verified**
until their human checks are complete. A missing term or date prompts for that input.
[Official enrollment timeline](https://crc.losrios.edu/admissions/enroll-in-classes) and
[payment dates](https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines)
are recorded in `docs/sources.md`.

**Enrollment priority** narrows Fall 2026 or Spring 2027 registration to the published group
period. Use your assigned level from eServices. Priority 1 sublevels retain the whole published
range; eServices gives the personal appointment time. Fall data comes from the May 17, 2026
archive of the Los Rios page; Spring data comes from CRC's current page. Registration guidance
is labeled **Not verified** and is separate from the actual enrollment date used for fees.
[CRC priority dates](https://crc.losrios.edu/admissions/enroll-in-classes/priority-registration-and-enrollment-dates)

Each unfinished task's checklist has **Email me a reminder** (own-details path only): a day and
time (Pacific, up to 30 days ahead on the real calendar, not the demo's date) and a consent box. The API schedules it with Resend, so it arrives even if you

close the page; scheduled reminders are listed with Cancel, and completing the task cancels
them. The public demo only emails addresses on the server's allow-list (`docs/deploy.md`).
Signing out doesn't cancel reminders already scheduled. Settings shows the masked address and Sign out, which
clears the session.

**Your profile** (under Profile setup, or in Settings) is a dashboard for this session: the
sign-in answers, how long since arrival, progress by status from the API, the next step,
your free times, and an "Include my email in handoffs" switch (off by default) that adds a
Contact line to handoffs you export. Nothing on it is sent anywhere.

On a first visit a spotlight tour dims the page and walks through page 1 one control at a
time (profile, Generate, the current step, View checklist, AI Help, Next, Settings), with Back,
Next, Skip and Escape. It only explains; it never changes anything. The tab remembers it was
seen; Settings → Replay tutorial shows it again.

When the current or next step has appointment guidance (school check-in, REAL ID), page 1
shows it word for word from `rules.json` with its "Not verified" label and official link. The
student can add weekly free times (Pacific time) under it; they stay in the browser session,
are never sent to the API or the model, and are cleared by Start fresh. Free times are only
compared with an office's in-person hours when they are confirmed for the workflow's date
(`visit_hours`: published, for that service, not a listed closure, dated to cover `as_of`,
and verified). Otherwise the notice and the checklist say "Hours for this date aren't
confirmed", give the reason and link the office's own page; other published hours stay in a
dated "Reference only" expander and never produce a suggested time. With today's data every
office falls back (none is verified, the DMV schedules are undated, and Admissions & Records
front-desk hours are not advisor availability). Flyover never books anything.
The notice can be dismissed; the same text stays in the task's checklist.

The **AI Help** logo in the header opens a dropdown chat (Airshow) right below it, on either
page, without leaving it. It calls `POST /assistant` with the workflow's `as_of` and
progress, the selected task, and `page_context` (`journey` on Workflow and readiness,
`airshow` on Office handoff, `readiness` elsewhere),
so an answer reflects "Resolve blocker" and "Mark done"; it never sends `student_id`. The
last 10 questions stay in the dropdown for the session; answers from before a progress change
are marked "Earlier answer". A timeout shows its own message and keeps the unsent question.
The Office handoff page is separate: a handoff drafted from a local
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
