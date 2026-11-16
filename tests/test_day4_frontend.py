"""FE 4 draft preview and workflow failure behaviors in the actual app."""

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_day3_frontend import select_dmv
from test_streamlit import APP_PATH, FakeResponse, base_payload, run_dashboard, values


def test_draft_requires_click_and_keeps_blocked_status_and_documents(monkeypatch):
    # Catches implicit generation, status mutation and loss of local inventory.
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    assert len(app.code) == 0
    app.checkbox[0].check().run()
    app.button(key='preview_email').click().run()
    assert not app.exception
    text = app.code[0].value
    assert 'Subject:' in text and 'Apply for California REAL ID' in text
    assert '[Your Name]' in text and '[Student ID]' in text
    assert '[Office or DSO]' in text
    assert 'Sample timing rule' in text
    assert 'Missing prerequisite: Complete CRC international student check-in' in text
    assert 'task_school_checkin' not in text
    assert any('Sample email draft' in x for x in values(app.warning))
    assert any('Blocked' in x for x in values(app.caption))
    assert app.checkbox[0].value
    app.run()
    assert app.code[0].value == text


def test_draft_clears_when_task_or_profile_changes(monkeypatch):
    payload = base_payload()
    app = select_dmv(run_dashboard(monkeypatch, payload))
    app.button(key='preview_email').click().run()
    app.selectbox(key='detail_task').select('task_bank_account').run()
    assert len(app.code) == 0
    select_dmv(app)
    assert len(app.code) == 0
    app.button(key='preview_email').click().run()
    payload['student_profile']['school_id'] = 'another-school'
    app.run()
    assert len(app.code) == 0


def test_reruns_do_not_rebuild_draft_and_clear_keeps_documents(monkeypatch):
    from pathlib import Path

    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.checkbox[0].check().run()
    app.button(key='preview_email').click().run()
    real_read = Path.read_text

    def no_regeneration(path, *args, **kwargs):
        if path.name == 'email.mock.json':
            pytest.fail('Draft was regenerated without a button click')
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', no_regeneration)
    app.run()
    assert len(app.code) == 1
    app.button(key='clear_email').click().run()
    assert len(app.code) == 0
    assert app.checkbox[0].value


def test_no_email_preview_for_unblocked_or_empty_workflow(monkeypatch):
    payload = base_payload()
    app = run_dashboard(monkeypatch, payload)
    assert not any(b.key == 'preview_email' for b in app.button)
    payload['workflow'] = []
    app.run()
    assert not app.exception
    assert not any(b.key == 'preview_email' for b in app.button)


@pytest.mark.parametrize('failure', ['missing', 'invalid'])
def test_draft_failure_preserves_checklist_and_retries(monkeypatch, failure):
    from pathlib import Path

    real_read = Path.read_text

    def broken_read(path, *args, **kwargs):
        if path.name == 'email.mock.json':
            if failure == 'missing':
                raise OSError('private file details')
            return '{"subject": 123}'
        return real_read(path, *args, **kwargs)

    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.checkbox[0].check().run()
    monkeypatch.setattr(Path, 'read_text', broken_read)
    app.button(key='preview_email').click().run()
    assert not app.exception
    assert any('Could not prepare the sample draft' in x for x in values(app.error))
    assert not any('private file details' in x for x in values(app.error))
    assert len(app.code) == 0
    assert app.checkbox[0].value
    monkeypatch.setattr(Path, 'read_text', real_read)
    app.button(key='preview_email').click().run()
    assert len(app.code) == 1


@pytest.mark.parametrize('failure', ['timeout', 'http', 'invalid'])
def test_workflow_failure_hides_internal_details_and_retry_recovers(monkeypatch, failure):
    def get(*args, **kwargs):
        if failure == 'timeout':
            raise requests.Timeout('private backend details')
        if failure == 'http':
            raise requests.HTTPError('private backend details')
        return FakeResponse({'workflow': [{'id': 'broken'}]})

    monkeypatch.setattr(requests, 'get', get)
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert any('Could not load your workflow' in x for x in values(app.error))
    assert not any('private backend details' in x for x in values(app.error))
    assert len(app.tabs) == 0
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse(base_payload()))
    app.button[0].click().run()
    assert not app.exception
    assert len(app.tabs) == 5
