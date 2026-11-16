# STU-D04-FE: draft preview, resilient states and Render preparation

## Implemented locally

Task details now offers a placeholder email template for the selected blocked
task. Click **Preview sample email draft**; it shows a subject, body, supplied
blocker context and prerequisite titles. It is explicitly sample/unverified,
with no invented recipient address. Use the native copy icon to copy subject and
body together, or select the text manually. Complete placeholders in your own
mail app. The app neither sends email nor changes task status.

The preview remains in transient Streamlit session memory. It clears when task,
profile, workflow date or relevant task data changes. **Clear email draft**
does not clear document selections or chat. Rerenders do not rebuild a draft.
Missing or invalid template data shows a friendly retry error and preserves the
checklist. There is no new email API contract or live email mode.

Workflow loading now shows a spinner and validates the shared `Workflow` model
before rendering. Request and validation failures show retry guidance without
backend exception details. Existing empty-workflow, missing-document and
assistant loading/failure states remain in place.

## Dependency status at the local starting commit `eb77801`

| Feature | Existing or missing | Owner / next condition |
| --- | --- | --- |
| Onboarding | Profile display only; form missing | FE, after profile/workflow contract agreement |
| School search | `GET /schools` exists; picker missing | FE carryover; coordinate school changes with BE |
| Personalized workflow | Resolver exists; GET is mock-only, live mode 501 | BE to implement reviewed profile-driven route |
| Task actions | Routes and awaiting-reply shape are proposals | BE/AI/FE to agree before wiring buttons |
| Readiness | Inventory and dependency views exist; visit data incomplete | BE/ENG to supply requirements and sourced details |
| Assistant | Mock preview plus proposed live adapter | BE/AI to implement agreed route and filtering |
| Email | New fixed preview and copy; planned `/api/assistant/email` absent | BE/AI to agree and implement a distinct email response |

These are findings from the starting commit. Before publishing, a successful
`git fetch origin` confirmed no new commits on main or the Day 3 frontend branch.
Day 3 remains open as PR #16, so the FE 4 PR targets `feature/STU-D03-FE` to keep
its diff focused. Retarget it to main after Day 3 merges. No real model requests
are part of the verification.

## Render deployment preparation

The owner selected Render and will provide the frontend service and backend URL.
Deployment remains pending those details. The owner approved commit/push and
teammate PR review on November 15, 2026.
Use a **Python web service** for Streamlit, with repository root as the root
directory. The frontend requires a separately running FastAPI service.

Proposed service settings to apply after review:

| Setting | Value |
| --- | --- |
| Build command | `uv sync --locked --no-dev` |
| Start command | `uv run --no-sync streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true --browser.gatherUsageStats false` |
| Health check | `/_stcore/health` (checks Streamlit, not backend connectivity) |
| `PYTHON_VERSION` | `3.12.15` (version used for local verification) |
| `API_URL` | Actual deployed FastAPI base URL, supplied by owner; never hosted `localhost` |
| `ASSISTANT_MODE` | `mock` until the reviewed backend assistant endpoint is live |

No OpenAI key is needed by this frontend preview. Keep backend secrets in the
backend service's secret settings. No disk or database is needed for FE state.
The email fixture must stay available at `data/mock/email.mock.json` in the
deployed repository checkout.

Render supports uv when `uv.lock` is at the service root; its web service must
listen on `0.0.0.0` and should use `$PORT`. References checked November 15, 2026:
[uv on Render](https://render.com/docs/uv-version),
[web service setup and port binding](https://render.com/docs/web-services).

After deployment, record the service URL and deployed commit, verify Streamlit
health and a real workflow fetch in a fresh session, then repeat phone layout,
clipboard, failed-request/retry and state-isolation checks over HTTPS. A green
Streamlit health check alone does not establish backend integration. Do not
claim FE 4 complete until deployment and those checks are recorded.

## Verification

Commands: `uv sync --locked`, `uv run --locked ruff check .`,
`uv run --locked pytest`. AppTest covers preview generation, placeholder content,
context invalidation, failures/retries, clearing without losing documents,
non-regeneration on reruns, and workflow validation/retry.

Browser evidence and deployment results are separate from AppTest. The preview
does not establish live email generation, live assistant or the seven-feature
end-to-end release checkpoint.

Observed November 15, 2026 on the uncommitted `feature/STU-D04-FE` working tree:

- `uv sync --locked`: resolved 68 packages; checked 65 packages.
- `uv run --locked ruff check .`: all checks passed.
- `uv run --locked pytest -q`: 105 passed. The original baseline was 96 passed;
  new behavior tests were observed failing before implementation.
- Local headless Chrome at 390×844 and 1440×1000: all five tabs without page
  overflow; wrapped draft without horizontal overflow; clipboard readback
  exactly matched subject/body; clearing removed the draft and retained the
  checked passport item; no browser page errors. Copy confirmation was visible.
- Phone and desktop screenshots were visually inspected. Evidence is in the
  planning workspace's `output/frontend-guides/fe4-verification` directory.
- Local development required restarting Streamlit after an imported helper's
  signature changed; browser checks above ran against the restarted process.

These checks used the local API's sample workflow, light theme and a narrow
desktop-browser viewport. Real phone hardware, dark theme, deployed HTTPS
clipboard and hosted connectivity remain unverified.

VERDICT: PASS for the local preview and regression checks above. Deployment and
live integration remain pending; this is not a full FE 4 completion claim.
