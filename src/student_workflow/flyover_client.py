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
                            'completed_tasks', 'awaiting_reply', 'enrollment_date')


def _headers() -> dict[str, str]:
    return {'X-API-Key': key} if (key := api_key()) else {}


def _validated(response) -> dict:
    response.raise_for_status()
    return Workflow.model_validate(response.json()).model_dump(mode='json')


def fetch_workflow(api_url: str) -> dict:
    return _validated(requests.get(f'{api_url.rstrip("/")}/workflow',
                                   headers=_headers(), timeout=10))


def fetch_fresh_workflow(api_url: str) -> dict:
    """The demo student with no progress yet, so a new visitor starts at step one.

    GET /workflow serves the shared demo, which is partway through (I-94 and SEVIS fee already
    done) because the classic dashboard, the smoke test and the pre-recording check use it.
    Flyover asks the API to rebuild that same profile and date with empty progress, so every
    status still comes from the backend, never from the page.
    """
    demo = fetch_workflow(api_url)
    profile = demo['student_profile']
    if not profile.get('completed_tasks') and not profile.get('awaiting_reply'):
        return demo  # already a fresh start: no second request
    fresh = {**deepcopy(profile), 'completed_tasks': [], 'awaiting_reply': []}
    return _validated(requests.post(f'{api_url.rstrip("/")}/workflow',
                                    json={'student_profile': fresh, 'as_of': demo['as_of']},
                                    headers=_headers(), timeout=15))


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
    # The API answers within about 8 seconds even with a retry; 15 leaves room for the network
    # and a just-woken server, so a slow first answer isn't cut off at the dashboard.
    response = requests.post(f'{api_url.rstrip("/")}/assistant', json=body,
                             headers=_headers(), timeout=15)
    response.raise_for_status()
    return AssistantAnswer.model_validate(response.json()).model_dump(mode='json')


# ---- Reminder emails (POST /notifications/reminders, STU-D07-FE-reminders) ----

REMINDER_MESSAGES = {
    403: "This address can't receive demo reminders. Ask the team to add it.",
    409: 'This step is already completed, so no reminder is needed.',
    503: 'Reminders are switched off right now.',
}


class ReminderError(Exception):
    """Scheduling or cancelling failed; str(error) is safe to show the student."""


def _reminder_error(response) -> ReminderError:
    status = getattr(response, 'status_code', 0)
    if status in REMINDER_MESSAGES:
        return ReminderError(REMINDER_MESSAGES[status])
    if status in (422, 502):
        # Our API's own wording ("Pick a time at least a minute from now.", "may still arrive").
        try:
            detail = response.json().get('detail')
        except ValueError:
            detail = None
        if isinstance(detail, str):
            return ReminderError(detail)
    return ReminderError('Could not reach the reminder service. Try again in a moment.')


def schedule_reminder(api_url: str, data: dict, recipient: str, task_id: str, send_at,
                      operation_id: str) -> dict:
    """Schedule one reminder email; send_at is a timezone-aware datetime."""
    profile = data['student_profile']
    body = {'recipient': recipient, 'consent': True, 'operation_id': operation_id,
            'task_id': task_id, 'send_at': send_at.isoformat(), 'as_of': data['as_of'],
            'student_profile': {key: profile[key] for key in ASSISTANT_PROFILE_FIELDS
                                if key in profile}}
    try:
        response = requests.post(f'{api_url.rstrip("/")}/notifications/reminders', json=body,
                                 headers=_headers(), timeout=15)
    except requests.RequestException as error:
        raise ReminderError('Could not reach the reminder service. Try again in a moment.') \
            from error
    if getattr(response, 'status_code', 200) >= 400:
        raise _reminder_error(response)
    return response.json()


def cancel_reminder(api_url: str, reminder_id: str) -> None:
    try:
        response = requests.post(
            f'{api_url.rstrip("/")}/notifications/reminders/{quote(reminder_id, safe="")}/cancel',
            headers=_headers(), timeout=15)
    except requests.RequestException as error:
        raise ReminderError('Cancellation not confirmed: the reminder may still arrive.') \
            from error
    if getattr(response, 'status_code', 200) >= 400:
        raise _reminder_error(response)


def reminder_status(api_url: str, reminder_id: str) -> str:
    """The email service's latest status for a reminder ('scheduled', 'delivered', ...)."""
    try:
        response = requests.get(
            f'{api_url.rstrip("/")}/notifications/reminders/{quote(reminder_id, safe="")}',
            headers=_headers(), timeout=15)
    except requests.RequestException as error:
        raise ReminderError('Could not check this reminder right now.') from error
    if getattr(response, 'status_code', 200) >= 400:
        raise _reminder_error(response)
    return response.json().get('provider_status', 'unknown')
