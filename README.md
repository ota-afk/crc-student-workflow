# CRC Hacks Student Workflow Platform

A dashboard that shows an international student at Cosumnes River College which arrival tasks
are done, ready, in progress or blocked, and what to do next. A FastAPI backend serves the
workflow and a Streamlit dashboard displays it.

Right now the API serves **sample data only** (`data/mock/workflow.mock.json`). Nothing in it is
verified.

## First-time setup

Install [Git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/). uv installs
Python 3.12 for you.

```bash
git clone https://github.com/ota-afk/crc-student-workflow.git
cd crc-student-workflow
uv sync --locked
cp .env.example .env
```

On Windows PowerShell use `Copy-Item .env.example .env`. Then put your own OpenAI key in `.env`.
Never commit `.env`.

## Run the API

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

`ASSISTANT_MODE=live` opts into the **proposed** `POST /api/assistant/ask` integration.
That endpoint does not exist on current main. Keep mock mode until BE/AI agree on
and implement [the frontend adapter contract](docs/day-3-frontend.md).
Failures display a retry message and leave the checklist usable. Live requests
may invoke a paid model through the backend; the frontend never calls an LLM directly.

### Day 4: email preview and deployment preparation

In **Task details**, select a blocked task and click **Preview sample email draft**.
Copy the subject and body with the copy icon, replace placeholders in your own mail
app, and confirm the recipient. This is a labeled template preview; it does not
send email or resolve a blocker. Changing task/profile context clears stale drafts.
See [Day 4 status and Render settings](docs/day-4-frontend.md) for deployment
preparation and the missing live backend dependencies.

## Environment variables

| Name | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Required for the manual OpenAI smoke test. Set it in the environment or local `.env`; never commit the key. |
| `OPENAI_MODEL` | empty | Required for the manual OpenAI smoke test. Tested with `gpt-6-luna`. |
| `USE_MOCK` | `true` | `true` serves the mock file. `false` returns 501 until the live engine exists. |
| `MOCK_PATH` | `data/mock/workflow.mock.json` | Path to a different mock file. |
| `RULES_PATH` | `data/rules/rules.json` | Path to a different rules file for the resolver. |
| `SCHOOLS_PATH` | `data/schools/sevp_schools_ca.csv` | Path to ENG's sourced California F-1 school directory. |
| `API_URL` | `http://localhost:8000` | Where the dashboard and the check script find the API. |
| `CORS_ORIGINS` | `http://localhost:8501` | Comma-separated origins allowed to call the API from a browser. Never `*`. |
| `ASSISTANT_MODE` | `mock` | Fixed sample chat preview; `live` uses the proposed assistant endpoint once implemented. |

## School search and rule scope

`GET /schools?q=<name-or-city>&limit=20` searches the school CSV without making external
requests. ENG still needs to supply the sourced CSV; until then the endpoint returns `503`
instead of inventing schools. See [the contract](docs/contract.md#school-search-day-2) for the
CSV columns and response fields. The default limit is 20, with a maximum of 100.

The resolver selects school rules using `student_profile.school_id`; `institution` is a
display name. **Proposed, pending ENG agreement:** the existing CRC rule and mock use `crc`
as an internal ID, not an official SEVP code. Everyone gets the shared federal and
California rules. For school steps, the choice is made per task: a task uses the school's own
rule when one exists, and otherwise the generic rule ENG supplies with `school_id: "_generic"`.
One school's rules are never used for another school. `school_verified` is computed by the
engine, and it stays false while any task uses generic steps.

Source verification travels with each rule even after its timing blocker disappears. A URL
and an old verification date alone cannot make a rule verified (the dashboard follows once
FE's change lands). The API still serves only
the mock workflow; wiring the live resolver into workflow endpoints remains Day 3 work.

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

## Project structure

```text
app/streamlit_app.py          Streamlit dashboard
src/student_workflow/         config.py, contract.py (Pydantic models), api.py (FastAPI),
                              rules.py (rules-file models), engine.py (dependency resolver)
                              schools.py (sourced school search)
data/mock/workflow.mock.json  sample workflow (is_mock: true)
data/rules/rules.json         tasks and rules (written by ENG, checked by tests)
data/schools/                 ENG's California F-1 school CSV (not supplied yet)
docs/                         contract.md, sources.md, credits.md, ai-data-policy.md
scripts/check_no_sample.py    pre-recording check
scripts/smoke_test_openai.py  manual, paid OpenAI check (not run by CI)
tests/                        pytest tests
.github/workflows/ci.yml      CI: ruff check and pytest
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
- **`/workflow` returns 501**: `USE_MOCK` is `false` and the live engine is not built yet.
- **`ModuleNotFoundError: student_workflow`**: run commands with `uv run` from the project root.
