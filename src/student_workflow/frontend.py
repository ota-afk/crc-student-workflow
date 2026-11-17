"""Frontend-only helpers and the assistant client (POST /assistant); no workflow mutations."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from .contract import AnswerSource, AssistantAnswer  # noqa: F401 - keep the existing exports
from .frontend_api import api_get, api_post
from .schools import School

# AssistantProfile in contract.py: the workflow inputs, without any student identifier.
ASSISTANT_PROFILE_FIELDS = ('institution', 'visa_type', 'arrival_date', 'has_ssn', 'school_id',
                            'completed_tasks', 'awaiting_reply', 'enrollment_date',
                            'enrollment_term')


def safe_url(value: object) -> str | None:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme in {'https', 'http'} and parts.hostname
                and not parts.username and not parts.password):
            return value
    except ValueError:
        pass
    return None


def source_verified(source: dict) -> bool:
    return bool(
        safe_url(source.get('url')) and source.get('last_verified')
        and source.get('verification_status') == 'verified'
    )


def search_school_directory(api_url: str, query: str) -> list[School]:
    query = query.strip()
    if len(query) > 100:
        raise ValueError('School search must contain at most 100 characters.')
    response = api_get(f'{api_url.rstrip("/")}/schools', params={'q': query, 'limit': 20})
    response.raise_for_status()
    schools = TypeAdapter(list[School]).validate_python(response.json(), strict=True)
    ids = [school.school_id for school in schools]
    if len(set(ids)) != len(ids):
        raise ValueError('School search returned duplicate identifiers.')
    return schools


def assistant_profile(profile: dict) -> dict:
    """The profile fields POST /assistant accepts (docs/contract.md); it rejects any other key."""
    # Never student_id, school_verified, document choices or chat history. The progress lists
    # are sent so the server rebuilds the same workflow the student is looking at.
    return {key: profile[key] for key in ASSISTANT_PROFILE_FIELDS if key in profile}


def ask_assistant(question: str, task_id: str | None, profile: dict, api_url: str,
                  mode: str, as_of: str | None) -> AssistantAnswer:
    if not question.strip() or len(question) > 500:
        raise ValueError('Question must contain 1 to 500 characters.')
    if mode == 'mock':
        path = Path(__file__).resolve().parents[2] / 'data/mock/assistant.mock.json'
        return AssistantAnswer.model_validate(json.loads(path.read_text(encoding='utf-8')))
    if mode != 'live':
        raise ValueError('Unknown assistant mode.')
    if not as_of:
        # The answer must match the workflow on screen, and that workflow has a date.
        raise ValueError('The current workflow has no date.')
    # Same API, key header and 10-second timeout as the workflow calls (#30).
    response = api_post(f'{api_url.rstrip("/")}/assistant', {
        'question': question.strip(), 'task_id': task_id, 'as_of': as_of,
        'student_profile': assistant_profile(profile),
    })
    response.raise_for_status()
    return AssistantAnswer.model_validate(response.json())
