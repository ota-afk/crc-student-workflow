"""Frontend-only helpers and the proposed assistant client; no workflow mutations."""

import json
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .frontend_api import api_get
from .schools import School


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


class AnswerSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rule_id: str
    url: str | None
    last_verified: date | None
    verification_status: Literal['verified', 'needs_verification', 're-checking']


class AssistantAnswer(BaseModel):
    """Proposed FE adapter contract, pending BE/AI agreement."""

    model_config = ConfigDict(extra='forbid')
    answer: str = Field(min_length=1)
    steps: list[str]
    sources: list[AnswerSource]
    verified: bool = Field(strict=True)
    contact: str | None
    task_id: str | None
    is_mock: bool = Field(strict=True)


def ask_assistant(question: str, task_id: str | None, profile: dict,
                  api_url: str, mode: str, *, endpoint: str | None = None) -> AssistantAnswer:
    if not question.strip() or len(question) > 500:
        raise ValueError('Question must contain 1 to 500 characters.')
    if mode == 'mock':
        path = Path(__file__).resolve().parents[2] / 'data/mock/assistant.mock.json'
        return AssistantAnswer.model_validate(json.loads(path.read_text(encoding='utf-8')))
    if mode != 'live':
        raise ValueError('Unknown assistant mode.')
    if not safe_url(endpoint):
        raise ValueError('Live assistant endpoint is not configured.')
    # Only the basic profile context; never send IDs, document choices or history.
    context = {key: profile[key] for key in (
        'institution', 'visa_type', 'arrival_date', 'has_ssn', 'school_id'
    ) if key in profile}
    response = requests.post(
        endpoint,
        json={'question': question.strip(), 'task_id': task_id,
              'student_profile': context}, timeout=30,
    )
    response.raise_for_status()
    return AssistantAnswer.model_validate(response.json())
