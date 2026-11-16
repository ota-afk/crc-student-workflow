# STU-D03-FE review follow-up

Reviewed November 15, 2026. This records the response to BE's changes-requested
review and DATA's student-journey feedback on PR #16. It does not redefine the
team plan or claim the real-call checkpoint is complete.

## Comment disposition

| Feedback | Response |
| --- | --- |
| BE 1: shared-plan wording | Restored `docs/contract.md` byte-for-byte to main's agreement. Removed the conflicting Day 3 scope/plan claims. The earlier wording came from a separately supplied local five-day PDF, not BE agreement. |
| BE 2 / DATA 2: blocker verification | Every unverified blocker explanation and listed unlock date carries Not verified; missing timing dates remain unknown. Regression covers a verified source beside an unverified blocker. |
| BE 3 / DATA 2: absent source status | Removed the legacy default. Missing/null/unknown status cannot qualify as verified. Positive source fixtures now explicitly declare verified rather than depending on a default. |
| BE 4: assistant naming | Removed the hardcoded `/api/` route. Live calls require explicitly configured `ASSISTANT_ENDPOINT` after BE/AI agreement. With no endpoint, no assistant request is made. Answer/request schema is still proposed. |
| BE 5: tool working plan | Removed the Day 3 working plan and the remaining Day 4 tool plan from project docs. Human-facing integration/status docs remain. |
| BE smaller items | Moved the Day 3 credit into date order; added review/FE 4 attribution; UTF-8 fixture read is explicit. Considered moving UI modules: kept them separate from backend imports and verified API import does not load Streamlit. |
| DATA 1: State → School | CA-only state/school preparation uses real GET school search with validation, loading, no-results, retry and missing-school choice. State/query changes invalidate old school choices. Generation remains visibly disabled until POST exists. |
| DATA 3: readiness → action | Added a local readiness inventory dialog. Resolve/Mark done remain disabled with honest explanation; no invented state transition or backend readiness claim. Actual integration is blocked below. |
| DATA 4: navigation | Task cards open the selected checklist directly. Missing-prerequisite buttons navigate to that task; tab and selection state are retained. |
| DATA 5: profile changes | Confirmed school/profile-context changes clear old inventory, document widget values, chat and email drafts; users must reconfirm. Ordinary reruns/progress-only changes and unapplied drafts do not clear documents. |
| DATA 6: responsive checks | Browser validation covers 320/375/768/desktop with long school, document and source labels. Native mobile keyboard remains a physical-device check. |
| DATA 7: Assistant context | Active task title is visible and historical user/assistant messages retain their submission task context. |

## Executable evidence

Starting branch `feature/STU-D03-FE` at `a2f07db` already included FE 4 and the
merged ENG rules. Baseline: 110 tests passed. New tests reproduced the missing
source-status default, unmarked blocker/date, missing context/navigation/reset,
and missing school picker before implementation.

- `uv run --locked pytest -q`: 132 passed after implementation.
- `uv run --locked ruff check .`: all checks passed.
- `git diff --check`: passed.
- API import check: `import student_workflow.api` does not put `streamlit` in
  `sys.modules`. `frontend.py` remains a non-Streamlit helper/client module.
- Actual FastAPI TestClient: GET `/schools?q=Cosumnes` → 200 with one result;
  POST `/workflow` → 405; POST task complete/resolve → 404. These failures confirm
  the missing integration rather than a frontend route assumption.
- `git diff origin/main -- docs/contract.md`: empty after restoring the agreement.

AppTest covers school search success/no-results/invalid response/timeout/retry,
state/query invalidation, no repeated search on reruns, no profile POST while
unagreed, no loss of document inventory, direct/prerequisite navigation, workflow
retry, readiness with all documents checked while still blocked, confirmed-school
reset, source/blocker verification, current/historical Assistant context, readable long school names, and clearing an
arrival date without crashing or retaining a stale draft.
The older checklist/chat/email regression suites also pass.

## Browser protocol and limits

Local Streamlit plus the actual FastAPI school endpoint; headless installed
Chrome with touch/mobile emulation for phone widths. The workflow is a clearly
labeled synthetic fixture with extra-long document and source labels, not live
verified content. The school name exercised is California Polytechnic State
University, San Luis Obispo. No real model call or POST task action is made.

Tested flow: search/select school → switch to unsupported state and back → verify
old selection cleared → exercise all five tabs → open blocked State ID directly
from its card → check a document → inspect readiness modal (still Blocked) →
navigate prerequisite → return with document retained → submit mock chat under
the selected task. Browser automation waits for completed Streamlit reruns rather
than clicking stale widgets during updates.

The browser report/screenshots live outside the repository at the planning
workspace's `output/frontend-guides/day3-review-verification/`. Final per-width
results are recorded in the PR response. No horizontal page overflow or browser
page errors is the acceptance condition; screenshots are inspected for wrapping.
Phone chat also runs with a focused input at a reduced 480px height. This simulates
restricted vertical space; it is not evidence that a native iOS/Android keyboard
has opened. Teammates should repeat on actual hardware, plus deployed HTTPS and
dark theme. The full real-call journey remains blocked below.

Observed on the final working tree:

| Viewport | Flow/layout | Focused chat in reduced viewport | Browser page errors |
| --- | --- | --- | --- |
| 320×844 | PASS | Input visible at 320×480 | None |
| 375×844 | PASS | Input visible at 375×480 | None |
| 768×1000 | PASS | Not a phone keyboard check | None |
| 1440×1000 | PASS | Not a phone keyboard check | None |

Phone/profile/readiness/chat screenshots were visually inspected. The long school
name is repeated in a wrapping caption because the narrow dropdown truncates its
selected text. Selection of the long option was exercised by keyboard in the
browser test. The app is still fixture-backed outside the actual school search.

VERDICT: PASS for the local regression/browser scope above; live integration and
native-device keyboard acceptance remain pending.

## Required teammate handoffs

- BE: authoritative build-plan link and agreed `POST /workflow` request/model,
  response and validation errors, including CA/state handling, synthetic identity,
  injected date and optional fields. Current doc contains proposals, not routes.
- BE: complete/resolve request/response examples and implemented branch/PR.
  Resolve needs agreed awaiting-reply state and email result semantics; generating
  a draft must not claim a sent message or remove dependency/timing blockers.
- BE + DATA: readiness inputs/outputs for missing prerequisites, documents and
  unknown requirements. Confirm whether the inventory modal should call a new
  endpoint or consume a Workflow field; no path is invented here.
- AI + BE: no-prefix route(s) and agreed cited-explanation / `generate_email()`
  payloads, strict response shape, minimum workflow context, privacy filtering,
  high-risk referrals and timeout/failure behavior. Keep preview mode until agreed.
- DATA: reviewed documents, visit details, sources/dates and contacts for CRC,
  Sacramento State and generic fallback; confirm missing-school wording and try
  the native mobile keyboard flow.

The user confirmed no newer BE contract was available and requested these
blockers be documented. Consequently onboarding submission, successful task
updates, authoritative readiness, and the complete real-call acceptance flow
are intentionally not claimed as addressed.
