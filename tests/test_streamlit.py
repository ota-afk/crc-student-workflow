"""Regression tests for the Streamlit dashboard, using Streamlit's AppTest harness.

Each test feeds the app a contract-valid /workflow response and checks what the
student would see. No API server is needed: requests.get is replaced.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import requests
from streamlit.testing.v1 import AppTest

from student_workflow.config import mock_path
from student_workflow.contract import Workflow

APP_PATH = Path(__file__).resolve().parents[1] / 'app' / 'streamlit_app.py'

NOT_VERIFIED = 'Not verified. Confirm with the office.'
MISSING_GUIDE = 'Before-you-go details not verified'
ALL_CLEAR = 'Nothing is blocked.'
NO_TASKS = 'No tasks available to assess readiness.'
SOURCE_GAP = 'Source link or date missing'


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def base_payload() -> dict[str, Any]:
    return json.loads(mock_path().read_text(encoding='utf-8'))


def task_by_id(payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    return next(t for t in payload['workflow'] if t['id'] == task_id)


def make_dmv_otherwise_verified(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove the other 'Not verified' signals so only the sources decide."""
    dmv = task_by_id(payload, 'task_dmv_id')
    dmv['blockers'][0]['verification_status'] = 'verified'
    dmv['before_you_go']['phone'] = '555-0100 (sample)'
    return dmv


def run_dashboard(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> AppTest:
    Workflow.model_validate(payload)  # only contract-valid data reaches the app
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: FakeResponse(payload))
    app = AppTest.from_file(str(APP_PATH), default_timeout=30)
    app.run()
    assert not app.exception
    return app


def values(elements: Any) -> list[str]:
    return [str(element.value) for element in elements]


def test_dashboard_renders_mock_with_sample_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = run_dashboard(monkeypatch, base_payload())
    assert 'Sample data. Not verified. Do not rely on it.' in values(app.warning)


@pytest.mark.parametrize(
    ('url', 'verified_on'),
    [
        (None, '2026-11-12'),
        ('https://www.dmv.ca.gov/', None),
        (None, None),
    ],
)
def test_incomplete_source_is_not_shown_as_verified(
    monkeypatch: pytest.MonkeyPatch, url: str | None, verified_on: str | None
) -> None:
    payload = base_payload()
    dmv = make_dmv_otherwise_verified(payload)
    dmv['sources'] = [
        {'rule_id': 'rule_dmv_timing_sample', 'url': url, 'last_verified': verified_on}
    ]

    app = run_dashboard(monkeypatch, payload)

    captions = values(app.caption)
    assert not any(c.startswith('Last verified:') for c in captions)
    assert NOT_VERIFIED in captions
    # This badge is only drawn inside the Readiness tab.
    assert any(SOURCE_GAP in m for m in values(app.markdown))


def test_complete_source_shows_last_verified_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    dmv = make_dmv_otherwise_verified(payload)
    dmv['sources'] = [
        {
            'rule_id': 'rule_dmv_timing_sample',
            'url': 'https://www.dmv.ca.gov/',
            'last_verified': '2026-11-12',
        }
    ]

    app = run_dashboard(monkeypatch, payload)

    assert 'Last verified: 2026-11-12' in values(app.caption)
    assert not any(SOURCE_GAP in m for m in values(app.markdown))


def test_task_without_before_you_go_stays_visible_as_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    task_by_id(payload, 'task_dmv_id')['before_you_go'] = None

    app = run_dashboard(monkeypatch, payload)

    markdown = values(app.markdown)
    expected_missing = sum(
        1
        for t in payload['workflow']
        if t.get('status') != 'Completed' and not t.get('before_you_go')
    )
    assert sum(MISSING_GUIDE in m for m in markdown) == expected_missing
    assert not any('Documents to bring' in m for m in markdown)


def test_default_mock_shows_guide_for_dmv_and_gaps_for_other_open_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    app = run_dashboard(monkeypatch, payload)

    markdown = values(app.markdown)
    assert any('Documents to bring' in m for m in markdown)
    expected_missing = sum(
        1
        for t in payload['workflow']
        if t.get('status') != 'Completed' and not t.get('before_you_go')
    )
    assert sum(MISSING_GUIDE in m for m in markdown) == expected_missing


def test_empty_workflow_is_not_reported_as_all_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    payload['workflow'] = []

    app = run_dashboard(monkeypatch, payload)

    assert NO_TASKS in values(app.info)
    assert ALL_CLEAR not in values(app.success)
    assert 'Before you go' not in values(app.subheader)


def test_all_clear_is_still_shown_when_tasks_exist_and_none_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    for task in payload['workflow']:
        if task['status'] == 'Blocked':
            task['status'] = 'Ready'
            task['missing_prerequisites'] = []
            task['blockers'] = []

    app = run_dashboard(monkeypatch, payload)

    assert ALL_CLEAR in values(app.success)


def test_unverified_blocker_prevents_verified_date_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    dmv = task_by_id(payload, 'task_dmv_id')
    # Blocker stays unverified (needs_verification), but source is complete.
    dmv['sources'] = [
        {
            'rule_id': 'rule_dmv_timing_sample',
            'url': 'https://www.dmv.ca.gov/',
            'last_verified': '2026-11-12',
        }
    ]

    app = run_dashboard(monkeypatch, payload)

    captions = values(app.caption)
    assert not any(c.startswith('Last verified:') for c in captions)
    assert NOT_VERIFIED in captions


def test_last_verified_date_shows_oldest_source_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    dmv = make_dmv_otherwise_verified(payload)
    dmv['sources'] = [
        {
            'rule_id': 'rule_dmv_timing_sample_1',
            'url': 'https://www.dmv.ca.gov/1',
            'last_verified': '2026-01-05',
        },
        {
            'rule_id': 'rule_dmv_timing_sample_2',
            'url': 'https://www.dmv.ca.gov/2',
            'last_verified': '2026-11-12',
        },
    ]

    app = run_dashboard(monkeypatch, payload)

    captions = values(app.caption)
    assert 'Last verified: 2026-01-05' in captions
    assert 'Last verified: 2026-11-12' not in captions


def test_unsourced_tasks_show_not_verified_state_in_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = base_payload()
    task_by_id(payload, 'task_school_checkin')['sources'] = []
    task_by_id(payload, 'task_bank_account')['sources'] = []

    app = run_dashboard(monkeypatch, payload)

    markdown = values(app.markdown)
    captions = values(app.caption)
    assert any(NOT_VERIFIED in m for m in markdown)
    assert NOT_VERIFIED in captions
