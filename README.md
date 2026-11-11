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
git clone https://github.com/YOUR-USERNAME/crc-student-workflow.git
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

## Environment variables

| Name | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Your OpenAI key. Not used by the Day 1 code yet. |
| `OPENAI_MODEL` | empty | Model name for the AI layer. Not used by the Day 1 code yet. |
| `USE_MOCK` | `true` | `true` serves the mock file. `false` returns 501 until the live engine exists. |
| `MOCK_PATH` | `data/mock/workflow.mock.json` | Path to a different mock file. |
| `API_URL` | `http://localhost:8000` | Where the dashboard and the check script find the API. |
| `CORS_ORIGINS` | `http://localhost:8501` | Comma-separated origins allowed to call the API from a browser. Never `*`. |

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
src/student_workflow/         config.py, contract.py (Pydantic models), api.py (FastAPI)
data/mock/workflow.mock.json  sample workflow (is_mock: true)
data/rules/                   rules.json goes here (written by ENG)
docs/                         contract.md, sources.md, credits.md
scripts/check_no_sample.py    pre-recording check
tests/                        pytest tests
.github/workflows/ci.yml      CI: ruff check and pytest
```

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
