"""The API (STU-D03-BE): the live dependency resolver behind POST /workflow and the task actions.

Nothing is stored here. Every request carries the student's profile, and every answer carries
the updated profile back (docs/contract.md, "Task actions"). Code decides every status.
"""

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from limits import parse as parse_limit
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import api_key, cors_origins, mock_path, rate_limit, use_mock
from .contract import ResolveResult, StudentProfile, Task, Workflow, WorkflowRequest
from .engine import RulesError, resolve
from .rules import RulesFile, load_rules
from .schools import School, search_schools

logger = logging.getLogger(__name__)

# The students are in California, and a hosted server's clock is often on UTC: near midnight
# UTC is already "tomorrow", which would move unlock dates a day early.
CALIFORNIA = ZoneInfo('America/Los_Angeles')


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail at startup on a bad RATE_LIMIT (e.g. '60 per mins'). Otherwise every request would
    # return a bare 500 while /health still says ok, and the deploy would look healthy.
    try:
        parse_limit(rate_limit())
    except ValueError as error:
        raise RuntimeError(
            f"RATE_LIMIT {rate_limit()!r} is not valid; use a value like '60/minute'"
        ) from error
    if not api_key():
        # Fine on a laptop; on the deployed API this would leave every endpoint open.
        logger.warning('API_KEY is not set: the X-API-Key check is off')
    yield


app = FastAPI(title='CRC Student Workflow API', lifespan=lifespan)


def _key_is_valid(sent: str | None) -> bool:
    # compare_digest takes the same time for any wrong key, so timing gives no hints.
    return sent is not None and secrets.compare_digest(sent.encode(), api_key().encode())


def rate_limit_bucket(request: Request) -> str:
    """Which allowance a request counts against.

    Requests with the right key (the dashboard's server) share one allowance. Everyone else is
    counted by address, so requests without the key can never use up the dashboard's allowance.
    We don't trust forwarded-address headers: Render's docs don't say what they contain.
    """
    if api_key() and _key_is_valid(request.headers.get('X-API-Key')):
        return 'dashboard'
    return get_remote_address(request)


# rate_limit is passed as a function, so RATE_LIMIT is read on every request.
limiter = Limiter(key_func=rate_limit_bucket, default_limits=[rate_limit])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Streamlit calls the API from its server, so CORS does not affect it today.
# It only matters if a browser calls the API directly. Use specific origins, never '*'.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)

# auto_error=False: a missing header reaches require_api_key as None, so we answer 401 ourselves.
_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


def require_api_key(sent: str | None = Security(_key_header)) -> None:
    if not api_key():
        return  # no key configured: local development and tests (see lifespan's warning)
    if not _key_is_valid(sent):
        raise HTTPException(status_code=401, detail='Missing or invalid API key')


# Added to every route except /health, which hosts and warm-up pings call without the key.
# Not an APIRouter: FastAPI 0.162 hides included routes from slowapi, so they'd skip the limit.
NEEDS_KEY = [Depends(require_api_key)]


@app.get('/health')
@limiter.exempt  # a host's health check or a warm-up ping must never be rate limited
def health():
    return {'status': 'ok'}


@app.get('/schools', response_model=list[School], dependencies=NEEDS_KEY)
def get_schools(
    q: str = Query(default='', max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        return search_schools(q, limit, load_rules())
    except (OSError, ValueError) as error:
        # The student sees a short 503; the server log keeps the real reason for us to fix.
        logger.exception('school search failed')
        raise HTTPException(
            status_code=503, detail='School search is temporarily unavailable'
        ) from error


@app.get('/workflow', response_model=Workflow, dependencies=NEEDS_KEY)
def get_workflow() -> Workflow:
    path = mock_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail='Mock file not found')
    demo = Workflow.model_validate_json(path.read_text(encoding='utf-8'))
    if use_mock():
        return demo
    # Live: the same demo student and "as of" date, computed by the engine from ENG's rules.
    # from_client=False: nobody sent this profile, so a rejected one is our bug (503), not a 422.
    return _workflow(demo.student_profile, demo.as_of, from_client=False)


@app.post('/workflow', response_model=Workflow, dependencies=NEEDS_KEY)
def post_workflow(request: WorkflowRequest) -> Workflow:
    return _workflow(request.student_profile, _as_of(request))


@app.post('/tasks/{task_id}/complete', response_model=Workflow, dependencies=NEEDS_KEY)
def complete_task(task_id: str, request: WorkflowRequest) -> Workflow:
    # One date for both steps, so the check and the answer can't fall on different days.
    as_of = _as_of(request)
    task = _find(_workflow(request.student_profile, as_of), task_id)
    if task.status not in ('Ready', 'In Progress'):
        # Completed already, or Blocked: a student can't finish a step they can't start yet.
        raise HTTPException(
            status_code=409,
            detail=f'Task {task_id} is {task.status}, so it cannot be marked done',
        )
    profile = request.student_profile
    updated = profile.model_copy(
        update={
            'completed_tasks': [*profile.completed_tasks, task_id],
            # Done means no longer waiting on the office.
            'awaiting_reply': [t for t in profile.awaiting_reply if t != task_id],
        }
    )
    return _workflow(updated, as_of)


@app.post('/tasks/{task_id}/resolve', response_model=ResolveResult, dependencies=NEEDS_KEY)
def resolve_blocker(task_id: str, request: WorkflowRequest) -> ResolveResult:
    as_of = _as_of(request)
    current = _workflow(request.student_profile, as_of)
    task = _find(current, task_id)
    if task.status != 'Blocked':
        raise HTTPException(
            status_code=409,
            detail=f'Task {task_id} is {task.status}; only a blocked task has a blocker',
        )
    # None = blocked only by a date: there is no office to write to, the student waits.
    if task.next_action is None:
        raise HTTPException(
            status_code=409,
            detail=f'Task {task_id} is waiting for a date, not for another task',
        )
    target = task.next_action.task_id  # the first missing prerequisite
    # In a chain (a -> b -> c), c's next action b can be Blocked too. Marking b as awaiting a
    # reply would show nothing (Blocked wins) and quietly turn b In Progress later.
    target_status = _find(current, target).status
    if target_status not in ('Ready', 'In Progress'):
        raise HTTPException(
            status_code=409,
            detail=f'Task {task_id} needs {target} first, and {target} is {target_status}',
        )
    profile = request.student_profile
    # Resolving twice changes nothing, instead of listing the same task twice.
    if target not in profile.awaiting_reply:
        profile = profile.model_copy(
            update={'awaiting_reply': [*profile.awaiting_reply, target]}
        )
    # The blocked task stays Blocked: only marking the prerequisite done makes it Ready.
    return ResolveResult(workflow=_workflow(profile, as_of))


def _as_of(request: WorkflowRequest) -> date:
    # None = the dashboard sent no date, so use today in California.
    return request.as_of or datetime.now(CALIFORNIA).date()


def _rules() -> RulesFile:
    try:
        return load_rules()
    except (OSError, ValueError) as error:
        # A broken rules file is our problem, not the student's: 503, and the reason in the log.
        logger.exception('rules file could not be loaded')
        raise HTTPException(
            status_code=503, detail='Workflow is temporarily unavailable'
        ) from error


def _workflow(
    profile: StudentProfile, as_of: date, *, from_client: bool = True
) -> Workflow:
    rules = _rules()  # read fresh: the workflow fetch is never cached (plan's ground rule)
    try:
        return resolve(rules, profile, as_of)
    except ValidationError as error:
        # The engine built an invalid Task or Workflow: a bug in our code. Checked before
        # ValueError, because pydantic's ValidationError is a kind of ValueError.
        logger.exception('engine built an invalid workflow')
        raise HTTPException(status_code=500, detail='Internal error') from error
    except RulesError as error:
        # The rules file can't serve this school: our data, so 503 and the reason in the log.
        logger.exception('rules file cannot build this workflow')
        raise HTTPException(
            status_code=503, detail='Workflow is temporarily unavailable'
        ) from error
    except ValueError as error:
        if not from_client:
            logger.exception('demo profile was rejected by the resolver')
            raise HTTPException(
                status_code=503, detail='Workflow is temporarily unavailable'
            ) from error
        # The resolver rejected the student's profile (e.g. an unknown task ID): say why.
        raise HTTPException(status_code=422, detail=str(error)) from error


def _find(workflow: Workflow, task_id: str) -> Task:
    # None = this task is not part of this student's workflow (or the ID is a typo).
    task = next((t for t in workflow.workflow if t.id == task_id), None)
    if task is None:
        raise HTTPException(
            status_code=404, detail=f'Task {task_id} is not in this workflow'
        )
    return task
