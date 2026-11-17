"""Scheduled reminder emails (STU-D07-BE-reminders). Resend is faked: no network, no email."""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
import requests
from fastapi.testclient import TestClient

from student_workflow import api, notifications

client = TestClient(api.app)
NOW = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
ALLOWED = 'demo.inbox@example.com'


class Reply:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}')

    def json(self):
        return self._payload


@pytest.fixture
def resend(monkeypatch):
    """Configured reminders, a fixed clock, and a fake Resend that records each call."""
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RESEND_API_KEY', 're_test_only')
    monkeypatch.setenv('REMINDER_RECIPIENTS', f'{ALLOWED.upper()}, other@example.com')
    monkeypatch.setattr(notifications, 'now', lambda: NOW)
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Reply(payload={'id': '49a3999c-0ce1-4ea6-ab68-afcd6dc2e794'})

    monkeypatch.setattr(notifications.requests, 'post', post)
    return calls


def body(**changes):
    demo = json.loads(api.mock_path().read_text(encoding='utf-8'))
    profile = {k: v for k, v in demo['student_profile'].items()
               if k not in ('student_id', 'school_verified')}
    request = {'recipient': ALLOWED, 'consent': True, 'operation_id': 'op-1',
               'task_id': 'task_dmv_id', 'send_at': '2026-11-18T09:00:00-08:00',
               'as_of': demo['as_of'], 'student_profile': profile}
    return {**request, **changes}


def schedule(**changes):
    return client.post('/notifications/reminders', json=body(**changes))


def test_a_reminder_is_scheduled_with_resend(resend):
    reply = schedule()
    assert reply.status_code == 200, reply.text
    assert reply.json()['status'] == 'scheduled'
    assert reply.json()['reminder_id'] == '49a3999c-0ce1-4ea6-ab68-afcd6dc2e794'
    (url, sent), = resend
    assert url == 'https://api.resend.com/emails'
    assert sent['headers'] == {'Authorization': 'Bearer re_test_only', 'Idempotency-Key': 'op-1'}
    assert sent['json']['to'] == [ALLOWED]
    assert sent['json']['scheduled_at'] == '2026-11-18T17:00:00Z'  # Pacific 09:00 in UTC
    assert sent['json']['subject'] == 'Flyover reminder: Apply for a California REAL ID card'


def test_the_email_holds_the_task_and_no_profile_details(resend):
    schedule()
    text = resend[0][1]['json']['text']
    assert 'Status on 2026-08-14: Blocked.' in text
    assert "doesn't book an appointment" in text
    for private in ('Cosumnes', 'F-1', '2026-08-11', 'SSN'):
        assert private not in text


def test_without_a_key_reminders_are_off(resend, monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY')
    assert schedule().status_code == 503
    assert resend == []


def test_an_address_off_the_allow_list_is_refused(resend):
    assert schedule(recipient='stranger@example.com').status_code == 403
    assert resend == []


def test_consent_is_required(resend):
    assert schedule(consent=False).status_code == 422
    assert resend == []


@pytest.mark.parametrize('send_at', ['2026-11-17T09:00:00-08:00',      # already past
                                     '2027-01-01T09:00:00-08:00',      # beyond 30 days
                                     '2026-11-18T09:00:00'])           # no timezone
def test_send_times_outside_the_window_are_refused(resend, send_at):
    assert schedule(send_at=send_at).status_code == 422
    assert resend == []


def test_unknown_and_completed_tasks_are_refused(resend):
    assert schedule(task_id='task_nope').status_code == 404
    completed = body()['student_profile']['completed_tasks'][0]
    assert schedule(task_id=completed).status_code == 409
    assert resend == []


def test_a_provider_failure_is_a_safe_502(resend, monkeypatch):
    monkeypatch.setattr(notifications.requests, 'post',
                        lambda *a, **k: Reply(500, {'message': 'secret detail'}))
    reply = schedule()
    assert reply.status_code == 502
    assert 'secret detail' not in reply.text


def test_the_recipient_is_never_logged(resend, monkeypatch, caplog):
    monkeypatch.setattr(notifications.requests, 'post', lambda *a, **k: Reply(500))
    with caplog.at_level(logging.DEBUG):
        schedule()
    assert ALLOWED not in caplog.text and 're_test_only' not in caplog.text


def test_cancel_calls_resend_and_confirms(resend):
    reply = client.post('/notifications/reminders/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794/cancel')
    assert reply.status_code == 200 and reply.json()['status'] == 'cancelled'
    assert resend[0][0].endswith('/emails/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794/cancel')


def test_cancel_refuses_an_id_that_is_not_an_email_id(resend):
    assert client.post('/notifications/reminders/..%2F..%2Fdomains/cancel').status_code in (404, 422)
    assert client.post('/notifications/reminders/not!an!id/cancel').status_code == 422
    assert resend == []


def test_an_unconfirmed_cancel_says_the_reminder_may_still_arrive(resend, monkeypatch):
    monkeypatch.setattr(notifications.requests, 'post', lambda *a, **k: Reply(500))
    reply = client.post('/notifications/reminders/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794/cancel')
    assert reply.status_code == 502 and 'may still arrive' in reply.text


def test_reminders_need_the_api_key_like_every_route(resend, monkeypatch):
    monkeypatch.setenv('API_KEY', 'dashboard-key')
    assert schedule().status_code == 401
    assert resend == []


def test_send_time_limits_are_one_minute_to_thirty_days():
    with pytest.raises(ValueError):
        notifications.check_send_time(datetime.now(UTC) + timedelta(seconds=30))
    assert notifications.check_send_time(datetime.now(UTC) + timedelta(days=29))


@pytest.mark.parametrize(('event', 'expected'), [('delivered', 'delivered'), ('failed', 'failed'),
                                                 ('something_new', 'unknown')])
def test_status_reports_resends_last_event(resend, monkeypatch, event, expected):
    seen = []
    monkeypatch.setattr(notifications.requests, 'get', lambda url, **kw: seen.append(url) or Reply(
        payload={'object': 'email', 'last_event': event}))
    reply = client.get('/notifications/reminders/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794')
    assert reply.status_code == 200
    assert reply.json()['provider_status'] == expected
    assert seen == ['https://api.resend.com/emails/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794']


def test_status_failure_is_a_safe_502(resend, monkeypatch):
    monkeypatch.setattr(notifications.requests, 'get', lambda *a, **k: Reply(500))
    reply = client.get('/notifications/reminders/49a3999c-0ce1-4ea6-ab68-afcd6dc2e794')
    assert reply.status_code == 502


def test_status_refuses_an_id_that_is_not_an_email_id(resend):
    assert client.get('/notifications/reminders/not!an!id').status_code == 422
