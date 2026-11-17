"""HTTP boundary for Flyover. Only validated backend responses become app state."""

from copy import deepcopy
from urllib.parse import quote

import requests
from pydantic import TypeAdapter

from .config import api_key
from .contract import AssistantAnswer, ResolveResult, StudentProfile, Workflow
from .schools import School

# The profile fields POST /assistant accepts (AssistantProfile); it rejects any other key, and
# student_id and school_verified must never reach it.
ASSISTANT_PROFILE_FIELDS = ('institution', 'visa_type', 'arrival_date', 'has_ssn', 'school_id',
                            'completed_tasks', 'awaiting_reply')


def _headers() -> dict[str, str]:
    return {'X-API-Key': key} if (key := api_key()) else {}


def _validated(response) -> dict:
    response.raise_for_status()
    return Workflow.model_validate(response.json()).model_dump(mode='json')


def fetch_workflow(api_url: str) -> dict:
    return _validated(requests.get(f'{api_url.rstrip("/")}/workflow',
                                   headers=_headers(), timeout=10))


def fetch_schools(api_url: str) -> list[dict]:
    response = requests.get(f'{api_url.rstrip("/")}/schools',
                            params={'q': '', 'limit': 100}, headers=_headers(), timeout=10)
    response.raise_for_status()
    return [school.model_dump() for school in
            TypeAdapter(list[School]).validate_python(response.json())]


def generate_workflow(api_url: str, current_profile: dict, changes: dict) -> dict:
    profile = {**deepcopy(current_profile), **changes, 'completed_tasks': [],
               'awaiting_reply': [], 'school_verified': False}
    profile = StudentProfile.model_validate(profile).model_dump(mode='json')
    return _validated(requests.post(f'{api_url.rstrip("/")}/workflow',
                                    json={'student_profile': profile},
                                    headers=_headers(), timeout=15))


def change_status(api_url: str, data: dict, task_id: str, status: str) -> dict:
    task = next((task for task in data['workflow'] if task['id'] == task_id), None)
    if task is None:
        raise ValueError('This task is not in the workflow.')
    if task['status'] == 'Blocked':
        raise ValueError('A blocked task must satisfy its prerequisites first.')
    if task['status'] == 'Completed':
        raise ValueError('This task is already completed.')
    if status not in {'Ready', 'In Progress', 'Completed'}:
        raise ValueError('Unsupported task status.')
    profile = deepcopy(data['student_profile'])
    body = {'student_profile': profile, 'as_of': data['as_of']}
    if status == 'Completed':
        path = f'/tasks/{quote(task_id, safe="")}/complete'
    else:
        path = '/workflow'
        awaiting = [key for key in profile.get('awaiting_reply', []) if key != task_id]
        if status == 'In Progress':
            awaiting.append(task_id)
        profile['awaiting_reply'] = awaiting
    return _validated(requests.post(f'{api_url.rstrip("/")}{path}', json=body,
                                    headers=_headers(), timeout=15))


def resolve_blocker(api_url: str, data: dict, task_id: str) -> tuple[dict, dict | None]:
    """POST /tasks/{id}/resolve: the updated workflow and the API's email draft (or None)."""
    body = {'student_profile': deepcopy(data['student_profile']), 'as_of': data['as_of']}
    response = requests.post(f'{api_url.rstrip("/")}/tasks/{quote(task_id, safe="")}/resolve',
                             json=body, headers=_headers(), timeout=15)
    response.raise_for_status()
    # A ValidationError is a ValueError, so callers that catch ValueError catch this too.
    result = ResolveResult.model_validate(response.json())
    draft = result.email_draft.model_dump() if result.email_draft else None
    return result.workflow.model_dump(mode='json'), draft


def ask_airshow(api_url: str, data: dict, question: str, task_id: str | None,
                page_context: str | None = None) -> dict:
    """POST /assistant: an answer built from this workflow's own date and progress."""
    profile = data['student_profile']
    body = {'question': question.strip(), 'task_id': task_id, 'as_of': data['as_of'],
            'student_profile': {key: profile[key] for key in ASSISTANT_PROFILE_FIELDS
                                if key in profile}}
    if page_context is not None:
        # Where the question was asked ("journey" or "readiness"); a display hint, see the
        # contract. Omitted rather than sent as null, so an older API never sees the key.
        body['page_context'] = page_context
    # 10 seconds, like the other dashboard: the API keeps its model calls inside that budget.
    response = requests.post(f'{api_url.rstrip("/")}/assistant', json=body,
                             headers=_headers(), timeout=10)
    response.raise_for_status()
    return AssistantAnswer.model_validate(response.json()).model_dump(mode='json')
