"""Flyover's demo sign-in, against the real API in process (test_live_api's Bridge)."""

from datetime import date
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow.flyover_signin import masked, valid_email

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def first_screen() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=30).run()


def sign_in(app: AppTest, email='student@example.com', password='anything', ssn='Yes',
            arrival=date(2026, 8, 11)) -> AppTest:
    app.text_input(key='flyover_signin_email').input(email)
    app.text_input(key='flyover_signin_password').input(password)
    app.date_input(key='flyover_signin_arrival').set_value(arrival)
    app.radio(key='flyover_signin_ssn').set_value(ssn)
    next(b for b in app.button if b.label == 'Sign in and start').click().run()
    assert not app.exception
    return app


def test_the_first_screen_is_the_sign_in(live):
    app = first_screen()
    assert values(app.subheader) == ['Welcome aboard']
    assert ('GET', '/workflow') not in [(m, p) for m, p, _, _ in live.calls]


def test_a_malformed_email_is_refused(live):
    app = sign_in(first_screen(), email='not-an-email')
    assert any('real email address' in v for v in values(app.error))
    assert 'flyover_account' not in app.session_state


def test_any_password_works_and_is_never_kept(live):
    app = sign_in(first_screen(), password='hunter2')
    assert app.session_state['flyover_account'] == {'email': 'student@example.com'}
    assert 'flyover_signin_password' not in app.session_state
    assert 'hunter2' not in str(live.calls)


def test_sign_in_answers_carry_into_the_workflow(live):
    app = sign_in(first_screen(), ssn='Yes', arrival=date(2026, 8, 20))
    profile = app.session_state['flyover_data']['student_profile']
    assert (profile['school_id'], profile['arrival_date'], profile['has_ssn']) == (
        'crc', '2026-08-20', True)
    assert profile['completed_tasks'] == []
    assert 'Profile setup' in values(app.subheader)  # straight into page 1, pre-filled


def test_the_email_is_never_sent_to_the_api(live):
    sign_in(first_screen(), email='private.person@example.com')
    assert 'private.person' not in str(live.calls)


def test_sign_out_clears_the_session_and_returns_to_sign_in(live):
    app = sign_in(first_screen())
    app.button(key='flyover_settings').click().run()
    app.button(key='flyover_sign_out').click().run()
    assert values(app.subheader) == ['Welcome aboard']
    assert 'flyover_data' not in app.session_state and 'flyover_account' not in app.session_state


@pytest.mark.parametrize(('email', 'ok'), [('a@b.co', True), ('a@b', False), ('a b@c.d', False),
                                           ('@b.co', False), ('a@b.co' + 'x' * 260, False)])
def test_email_shape_check(email, ok):
    assert valid_email(email) is ok


def test_masked_email_hides_the_name_part():
    assert masked('ryan@example.com') == 'r***@example.com'
