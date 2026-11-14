"""Day 3 interactions, exercised through the actual Streamlit app."""

import pytest
import requests
from test_streamlit import FakeResponse, base_payload, run_dashboard, task_by_id, values


def select_dmv(app):
    return app.selectbox(key='detail_task').select('task_dmv_id').run()


def test_document_checklist_tracks_missing_without_unlocking(monkeypatch):
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    assert len(app.checkbox) == 3
    app.checkbox[0].check().run()
    assert any('2 documents still missing' in value for value in values(app.info))
    for checkbox in app.checkbox:
        checkbox.check()
    app.run()
    assert any('Documents checked' in value for value in values(app.info))
    assert not any('Ready to go' in value for value in values(app.success))
    assert any('Blocked' in value for value in values(app.markdown))


def test_document_choices_survive_switching_tasks(monkeypatch):
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.checkbox[0].check().run()
    app.selectbox(key='detail_task').select('task_bank_account').run()
    assert len(app.checkbox) == 0
    select_dmv(app)
    assert app.checkbox[0].value is True
    assert app.checkbox[1].value is False


def test_missing_guidance_never_shows_ready(monkeypatch):
    app = run_dashboard(monkeypatch, base_payload())
    app.selectbox(key='detail_task').select('task_school_checkin').run()
    assert any('Document requirements are not available' in x for x in values(app.info))
    assert not any('Ready to go' in x for x in values(app.success))


def test_source_link_and_date_are_shown_together(monkeypatch):
    payload = base_payload()
    task_by_id(payload, 'task_dmv_id')['sources'] = [{
        'rule_id': 'dmv', 'url': 'https://www.dmv.ca.gov/',
        'last_verified': '2026-11-12', 'verification_status': 'needs_verification',
    }]
    app = select_dmv(run_dashboard(monkeypatch, payload))
    assert any('https://www.dmv.ca.gov/' in x and '2026-11-12' in x
               for x in values(app.markdown))
    assert not any(x.startswith('Last verified:') for x in values(app.caption))


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://', 'https://bad host/'])
def test_invalid_source_urls_are_not_clickable(monkeypatch, url):
    payload = base_payload()
    task_by_id(payload, 'task_dmv_id')['sources'] = [{
        'rule_id': 'dmv', 'url': url, 'last_verified': '2026-11-12',
    }]
    app = select_dmv(run_dashboard(monkeypatch, payload))
    assert not any(f'href="{url}"' in x for x in values(app.markdown))


def test_sample_chat_is_labeled_and_does_not_change_workflow(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'mock')
    app = run_dashboard(monkeypatch, base_payload())
    app.chat_input[0].set_value('How do I apply for a California State ID?').run()
    assert not app.exception
    assert any('Sample response' in x for x in values(app.warning))
    assert len(app.chat_message) == 2
    assert any('Blocked' in x for x in values(app.markdown))


def test_chat_history_is_session_only(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'mock')
    app = run_dashboard(monkeypatch, base_payload())
    app.chat_input[0].set_value('State ID').run()
    app.run()
    assert len(app.chat_message) == 2
    other = run_dashboard(monkeypatch, base_payload())
    assert len(other.chat_message) == 0


def test_live_chat_sends_minimal_context_and_renders_answer(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'live')
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    captured = []

    def post(url, *, json, timeout):
        captured.append((url, json, timeout))
        return FakeResponse({
            'answer': 'Contact your DSO about this requirement.',
            'steps': ['Review the official source.'], 'verified': False,
            'sources': [{'rule_id': 'dmv', 'url': 'https://www.dmv.ca.gov/',
                         'last_verified': '2026-11-12',
                         'verification_status': 'needs_verification'}],
            'contact': 'International student office', 'task_id': 'task_dmv_id',
            'is_mock': False,
        })

    monkeypatch.setattr(requests, 'post', post)
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.chat_input[0].set_value('What is my next step?').run()
    assert not app.exception
    assert captured == [('http://localhost:8000/api/assistant/ask', {
        'question': 'What is my next step?', 'task_id': 'task_dmv_id',
        'student_profile': {'institution': 'Cosumnes River College',
                            'visa_type': 'F-1', 'arrival_date': '2026-08-11',
                            'has_ssn': False},
    }, 30)]
    assert any('Contact your DSO' in x for x in values(app.markdown))
    assert any('Not verified' in x for x in values(app.warning))
    app.run()
    assert len(captured) == 1  # Rerenders must not repeat paid requests.


@pytest.mark.parametrize('failure', ['timeout', 'http', 'invalid'])
def test_chat_failure_preserves_checklist_and_can_retry(monkeypatch, failure):
    monkeypatch.setenv('ASSISTANT_MODE', 'live')

    def post(*args, **kwargs):
        if failure == 'timeout':
            raise requests.Timeout('secret internal details')
        if failure == 'http':
            raise requests.HTTPError('secret internal details')
        return FakeResponse({'answer': 123, 'verified': True})

    monkeypatch.setattr(requests, 'post', post)
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.checkbox[0].check().run()
    app.chat_input[0].set_value('What next?').run()
    assert not app.exception
    assert any('Could not get an answer' in x for x in values(app.error))
    assert not any('secret internal details' in x for x in values(app.error))
    assert len(app.chat_message) == 1
    assert app.checkbox[0].value
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse({
        'answer': 'Ask the office.', 'steps': [], 'sources': [], 'verified': False,
        'contact': 'DSO', 'task_id': None, 'is_mock': False,
    }))
    app.chat_input[0].set_value('Try again').run()
    assert len(app.chat_message) == 3


def test_clear_chat_removes_history_without_clearing_documents(monkeypatch):
    monkeypatch.setenv('ASSISTANT_MODE', 'mock')
    app = select_dmv(run_dashboard(monkeypatch, base_payload()))
    app.checkbox[0].check().run()
    app.chat_input[0].set_value('State ID').run()
    app.button(key='clear_chat').click().run()
    assert len(app.chat_message) == 0
    assert app.checkbox[0].value
