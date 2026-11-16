"""Regression coverage for the BE and DATA review of STU-D03-FE."""

import pytest
import requests
from test_day3_frontend import select_dmv
from test_streamlit import FakeResponse, base_payload, run_dashboard, task_by_id, values

from student_workflow.frontend import source_verified


@pytest.mark.parametrize('status', ['missing', None, 'needs_verification', 're-checking'])
def test_source_requires_explicit_verified_status(status):
    source = {'url': 'https://www.dmv.ca.gov/', 'last_verified': '2026-11-12'}
    if status != 'missing':
        source['verification_status'] = status
    assert source_verified(source) is False


def test_explicitly_verified_source_still_requires_url_and_date():
    source = {'url': 'https://www.dmv.ca.gov/', 'last_verified': '2026-11-12',
              'verification_status': 'verified'}
    assert source_verified(source)
    assert not source_verified({**source, 'url': None})
    assert not source_verified({**source, 'last_verified': None})


def test_missing_source_status_cannot_show_verified_in_task_details(monkeypatch):
    payload = base_payload()
    task_by_id(payload, 'task_dmv_id')['sources'] = [{
        'rule_id': 'dmv', 'url': 'https://www.dmv.ca.gov/',
        'last_verified': '2026-11-12',
    }]
    app = select_dmv(run_dashboard(monkeypatch, payload))
    sources = [m for m in values(app.tabs[3].markdown) if 'Source date:' in m]
    assert len(sources) == 1 and sources[0].endswith('Not verified')


@pytest.mark.parametrize('status', ['needs_verification', 'verified'])
def test_task_details_labels_blocker_and_date_independently_of_source(monkeypatch, status):
    payload = base_payload()
    task = task_by_id(payload, 'task_dmv_id')
    task['blockers'][0]['verification_status'] = status
    task['sources'] = [{'rule_id': 'dmv', 'url': 'https://www.dmv.ca.gov/',
                        'last_verified': '2026-11-12', 'verification_status': 'verified'}]
    app = select_dmv(run_dashboard(monkeypatch, payload))
    detail = app.tabs[3]
    blocker = next(w for w in values(detail.warning) if 'Sample timing rule' in w)
    unlock = next(c for c in values(detail.caption) if 'Listed unlock date:' in c)
    assert ('Not verified' in blocker) is (status != 'verified')
    assert ('Not verified' in unlock) is (status != 'verified')


def test_live_assistant_without_agreed_endpoint_makes_no_request(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'live')
    monkeypatch.delenv('ASSISTANT_ENDPOINT', raising=False)
    calls = []
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: calls.append(a))
    app = run_dashboard(monkeypatch, base_payload())
    app.chat_input[0].set_value('What next?').run()
    assert calls == []
    assert not app.exception
    assert len(app.chat_message) == 1
    assert any('not configured' in v for v in values(app.info))


def test_assistant_shows_active_task_and_keeps_old_answer_context(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'mock')
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    assert 'Active task: Apply for California REAL ID' in values(app.tabs[4].caption)
    app.chat_input[0].set_value('What next?').run()
    app.selectbox(key='detail_task').select('task_bank_account').run()
    assert 'Active task: Open a U.S. bank account' in values(app.tabs[4].caption)
    assert 'Task context: Apply for California REAL ID' in values(app.chat_message[1].caption)


def test_workflow_and_prerequisite_buttons_navigate_to_selected_checklist(monkeypatch):
    app = run_dashboard(monkeypatch, base_payload())
    app.button(key='view_checklist:task_dmv_id').click().run()
    assert app.selectbox(key='detail_task').value == 'task_dmv_id'
    assert app.session_state['dashboard_tabs'] == 'Task details'
    app.checkbox[0].check().run()
    app.button(key='prerequisite:task_dmv_id:task_school_checkin').click().run()
    assert app.selectbox(key='detail_task').value == 'task_school_checkin'
    app.button(key='view_checklist:task_dmv_id').click().run()
    assert app.checkbox[0].value


def test_confirmed_school_change_resets_inventory_chat_and_drafts(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'mock')
    payload = base_payload()
    app = select_dmv(run_dashboard(monkeypatch, payload))
    app.checkbox[0].check().run()
    app.chat_input[0].set_value('What next?').run()
    app.button(key='preview_email').click().run()
    payload['student_profile']['school_id'] = 'different-school'
    payload['student_profile']['institution'] = 'Different School'
    app.run()
    assert not app.exception
    assert not app.checkbox[0].value
    assert len(app.code) == 0
    assert len(app.chat_message) == 0
    assert any('Profile context changed' in v for v in values(app.info))


def test_workflow_retry_preserves_selected_task_and_document_inventory(monkeypatch):
    payload = base_payload()
    app = select_dmv(run_dashboard(monkeypatch, payload))
    app.checkbox[0].check().run()

    def unavailable(*args, **kwargs):
        raise requests.Timeout('private details')

    monkeypatch.setattr(requests, 'get', unavailable)
    app.run()
    assert not app.exception
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse(payload))
    app.button[0].click().run()
    assert app.selectbox(key='detail_task').value == 'task_dmv_id'
    assert app.checkbox[0].value


def test_readiness_dialog_keeps_document_inventory_separate_from_status(monkeypatch):
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    for checkbox in app.checkbox:
        checkbox.check()
    app.run()
    app.button(key='show_readiness').click().run()
    assert not app.exception
    assert any('Blocked' in x for x in values(app.warning))
    assert any('does not confirm eligibility' in x for x in values(app.info))
    assert app.button(key='resolve_task').disabled
    assert app.button(key='complete_task').disabled
