"""Flyover's "Email me a reminder", against the real API in process with Resend faked."""

from pathlib import Path

import pytest
import requests
from test_flyover_app import open_checklist, signed_in_app
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow import notifications

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'
DMV, RESIDENCY = 'task_dmv_id', 'task_proof_of_residency'


@pytest.fixture
def live(monkeypatch):
    """Real API and dashboard; Resend replaced at its boundary (no network, no email)."""
    for name, value in {'USE_MOCK': 'false', 'RATE_LIMIT': '1000/minute', 'API_KEY': KEY,
                        'API_URL': 'http://localhost:8000', 'RESEND_API_KEY': 're_test_only',
                        'REMINDER_RECIPIENTS': 'student@example.com'}.items():
        monkeypatch.setenv(name, value)
    sent = {'scheduled': [], 'cancelled': []}
    monkeypatch.setattr(notifications, 'schedule', lambda *args: sent['scheduled'].append(args)
                        or f'00000000-0000-0000-0000-00000000000{len(sent["scheduled"])}')
    monkeypatch.setattr(notifications, 'cancel', lambda key, email_id:
                        sent['cancelled'].append(email_id))
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    bridge.sent = sent
    return bridge


def checklist(task_id):
    return open_checklist(signed_in_app(APP), task_id)


def remind(app, task_id, consent=True):
    if consent:
        app.checkbox(key=f'fly_rem_ok:{task_id}').check()
    next(b for b in app.button if b.label == 'Schedule reminder').click().run()
    assert not app.exception
    return app


def test_a_reminder_is_scheduled_for_the_signed_in_email(live):
    app = remind(checklist(DMV), DMV)
    body, = [b for p, b in live.posts() if p == '/notifications/reminders']
    assert body['recipient'] == 'student@example.com' and body['task_id'] == DMV
    # Pacific and timezone-aware (-08:00 in winter, -07:00 in summer).
    assert body['consent'] is True and body['send_at'][-6:] in ('-08:00', '-07:00')
    assert len(live.sent['scheduled']) == 1
    assert any(v.startswith('Reminder set for') for v in values(app.success))
    assert any(v.startswith('Reminder: ') for v in values(app.markdown))


def test_no_reminder_without_consent(live):
    app = remind(checklist(DMV), DMV, consent=False)
    assert any('Tick the box' in v for v in values(app.error))
    assert not [p for p, _ in live.posts() if p == '/notifications/reminders']


def test_an_address_off_the_allow_list_gets_a_friendly_message(live, monkeypatch):
    monkeypatch.setenv('REMINDER_RECIPIENTS', 'someone.else@example.com')
    app = remind(checklist(DMV), DMV)
    assert any("can't receive demo reminders" in v for v in values(app.error))
    assert live.sent['scheduled'] == []


def test_cancel_removes_the_reminder(live):
    app = remind(checklist(DMV), DMV)
    reminder_id = app.session_state['flyover_reminders'][0]['reminder_id']
    app.button(key=f'fly_rem_cancel:{reminder_id}').click().run()
    assert live.sent['cancelled'] == [reminder_id]
    assert app.session_state['flyover_reminders'] == []
    assert 'Reminder cancelled.' in values(app.info)


def test_completing_a_task_cancels_its_reminders(live):
    app = remind(checklist(RESIDENCY), RESIDENCY)
    reminder_id = app.session_state['flyover_reminders'][0]['reminder_id']
    app.button(key='flyover_detail_complete').click().run()
    assert live.sent['cancelled'] == [reminder_id]
    assert app.session_state['flyover_reminders'] == []


def test_a_completed_task_offers_no_reminder(live):
    app = checklist(RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    open_checklist(app, RESIDENCY)
    assert '#### Email me a reminder' not in values(app.markdown)


@pytest.mark.parametrize(('event', 'kind', 'words'), [
    ('scheduled', 'info', 'Waiting to be sent'),
    ('delivered', 'success', 'Check Spam and Promotions'),
    ('failed', 'error', "only the Resend account's own email address"),
])
def test_check_status_explains_the_result_in_plain_words(live, monkeypatch, event, kind, words):
    monkeypatch.setattr(notifications, 'status', lambda key, email_id: event)
    app = remind(checklist(DMV), DMV)
    reminder_id = app.session_state['flyover_reminders'][0]['reminder_id']
    app.button(key=f'fly_rem_status:{reminder_id}').click().run()
    assert any(words in v for v in values(getattr(app, kind)))
