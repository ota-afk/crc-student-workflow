"""HTTP boundary for Flyover. Only validated backend responses become app state."""

from copy import deepcopy
from urllib.parse import quote

import requests
from pydantic import TypeAdapter

from .config import api_key
from .contract import StudentProfile, Workflow
from .schools import School


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
