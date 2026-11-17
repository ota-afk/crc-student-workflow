"""Every request the dashboard makes to the workflow API goes through here.

Why one place: the live API refuses any request without the X-API-Key header, and it is
stateless, so each call carries the whole profile. Streamlit runs on the server, so the key
never reaches a visitor's browser.
"""

import os
from typing import Any

import requests
from pydantic import ValidationError

from .contract import ResolveResult, Workflow

TIMEOUT = 10
# The fields of StudentProfile; the strict API rejects anything else (for example "state").
PROFILE_FIELDS = ('student_id', 'institution', 'visa_type', 'arrival_date', 'has_ssn',
                  'completed_tasks', 'awaiting_reply', 'school_id', 'school_verified')

# Short messages only: the API's own detail text and any exception text stay out of the page.
_STATUS_MESSAGES = {
    401: 'The dashboard could not sign in to the service. Contact the app team.',
    404: 'That task was not found. Reload the page and try again.',
    409: 'That task cannot be updated in its current state. Your workflow has not changed.',
    422: 'The service could not accept this profile. Check your details and try again.',
    429: 'Too many requests. Wait a minute and try again.',
}
_DEFAULT_MESSAGE = ('The service is unavailable or returned incomplete data. Try again in a '
                    'moment. Your workflow has not changed.')


class ApiError(Exception):
    """An action failed; str(error) is safe to show the student."""


def api_headers() -> dict[str, str]:
    """The X-API-Key header from the dashboard's API_KEY setting (none when it is empty)."""
    key = os.getenv('API_KEY', '').strip()
    return {'X-API-Key': key} if key else {}


def api_get(url: str, **kwargs: Any) -> requests.Response:
    return requests.get(url, headers=api_headers(), timeout=TIMEOUT, **kwargs)


def api_post(url: str, body: dict[str, Any]) -> requests.Response:
    return requests.post(url, json=body, headers=api_headers(), timeout=TIMEOUT)


def build_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields the API accepts, so a stored profile is always a valid request."""
    return {key: profile[key] for key in PROFILE_FIELDS if key in profile}


def _post(api_url: str, path: str, profile: dict[str, Any], as_of: str | None) -> Any:
    body = {'student_profile': build_profile(profile)}
    if as_of:
        body['as_of'] = as_of
    try:
        response = api_post(f'{api_url.rstrip("/")}{path}', body)
        status = getattr(response, 'status_code', 200)
        if status in _STATUS_MESSAGES:
            raise ApiError(_STATUS_MESSAGES[status])
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        raise ApiError(_DEFAULT_MESSAGE) from error


def _workflow(data: Any) -> dict[str, Any]:
    try:
        return Workflow.model_validate(data).model_dump(mode='json', exclude_unset=True)
    except (ValidationError, ValueError) as error:
        raise ApiError(_DEFAULT_MESSAGE) from error


def post_workflow(api_url: str, profile: dict[str, Any], as_of: str | None) -> dict[str, Any]:
    """POST /workflow: the workflow for this profile (the profile comes back inside it)."""
    return _workflow(_post(api_url, '/workflow', profile, as_of))


def complete_task(api_url: str, task_id: str, profile: dict[str, Any],
                  as_of: str | None) -> dict[str, Any]:
    """POST /tasks/{id}/complete: the updated workflow."""
    return _workflow(_post(api_url, f'/tasks/{task_id}/complete', profile, as_of))


def resolve_task(api_url: str, task_id: str, profile: dict[str, Any],
                 as_of: str | None) -> tuple[dict[str, Any], dict[str, str] | None]:
    """POST /tasks/{id}/resolve: the updated workflow and the email draft (or None)."""
    data = _post(api_url, f'/tasks/{task_id}/resolve', profile, as_of)
    try:
        result = ResolveResult.model_validate(data)
    except (ValidationError, ValueError) as error:
        raise ApiError(_DEFAULT_MESSAGE) from error
    workflow = result.workflow.model_dump(mode='json', exclude_unset=True)
    draft = result.email_draft.model_dump() if result.email_draft else None
    return workflow, draft
