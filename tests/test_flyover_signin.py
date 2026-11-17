"""Flyover's first screen, "Use your own details" path, against the real API in process.

The "Try the CRC demo" path has its own file, test_flyover_demo.py.
"""

from datetime import date
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_flyover_app import open_checklist
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


def sign_in(app: AppTest, email='student@example.com', ssn='Yes',
            arrival=date(2026, 8, 11)) -> AppTest:
    app.text_input(key='flyover_signin_email').input(email)
    app.date_input(key='flyover_signin_arrival').set_value(arrival)
    app.radio(key='flyover_signin_ssn').set_value(ssn)
    next(b for b in app.button if b.label == 'Start with my details').click().run()
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


def test_the_first_screen_asks_for_no_password(live):
    app = first_screen()
    assert not [w for w in app.text_input if w.type == 'password']
    assert 'Password' not in [w.label for w in app.text_input]


def test_own_details_keep_the_email_in_the_session(live):
    app = sign_in(first_screen())
    assert app.session_state['flyover_account'] == {'email': 'student@example.com'}


def test_own_details_are_worked_out_on_the_scenario_date(live):
    # The reproduction: August inputs used November 17 as as_of and showed "Past due".
    app = first_screen()
    app.selectbox(key='flyover_signin_term').select('fall_2026')
    app.date_input(key='flyover_signin_enrollment').set_value(date(2026, 8, 13))
    app = sign_in(app)
    assert app.session_state['flyover_data']['as_of'] == '2026-08-14'
    assert live.posts()[-1][1]['as_of'] == '2026-08-14'  # sent explicitly, not the API default
    app = open_checklist(app, 'task_crc_fee_payment')
    assert 'Due today, Fri, Aug 14, 2026 · Double-checked by our team' in values(app.success)
    assert not any('Past due' in v for v in values(app.warning))


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


def test_an_enrollment_date_at_sign_in_shows_the_tuition_deadline(live):
    app = first_screen()
    app.selectbox(key='flyover_signin_term').select('fall_2026')
    app.date_input(key='flyover_signin_enrollment').set_value(date(2026, 7, 1))
    app = sign_in(app)
    assert app.session_state['flyover_data']['student_profile']['enrollment_date'] == '2026-07-01'
    app = open_checklist(app, 'task_crc_fee_payment')
    # Enrolled before the July 24 cutoff: due August 7, 2026 (the verified CRC rule).
    assert any(v.startswith('Past due since Fri, Aug 7, 2026.') for v in values(app.warning))


def test_without_an_enrollment_date_flyover_asks_for_it(live):
    app = open_checklist(sign_in(first_screen()), 'task_crc_fee_payment')
    assert 'Choose your enrollment term in Profile setup to see when tuition is due.' in values(app.info)


def test_spring_term_and_due_date_survive_sign_in_and_profile_edits(live):
    app = first_screen()
    app.selectbox(key='flyover_signin_term').select('spring_2027')
    app.selectbox(key='flyover_signin_priority').select('2')
    app.date_input(key='flyover_signin_enrollment').set_value(date(2026, 12, 1))
    app = sign_in(app)
    profile = app.session_state['flyover_data']['student_profile']
    assert profile['enrollment_term'] == 'spring_2027'
    assert profile['enrollment_priority'] == '2'
    assert app.selectbox(key='flyover_priority').value == '2'
    assert any('Dec 14, 2026 to Dec 16, 2026' in value for value in values(app.info))
    assert app.selectbox(key='flyover_term').value == 'spring_2027'
    app = open_checklist(app, 'task_crc_fee_payment')
    assert any('Jan 8, 2027' in value and 'Not verified' in value
               for value in values(app.info))


def test_fall_priority_uses_the_archive_and_preserves_actual_fee_date(live):
    app = first_screen()
    app.selectbox(key='flyover_signin_term').select('fall_2026')
    app.selectbox(key='flyover_signin_priority').select('1.4')
    app.date_input(key='flyover_signin_enrollment').set_value(date(2026, 8, 13))
    app = sign_in(app)
    assert any('Apr 20, 2026 to May 01, 2026' in value for value in values(app.info))
    assert any('archived May 17, 2026' in value for value in values(app.caption))
    app = open_checklist(app, 'task_crc_fee_payment')
    assert any(value.startswith('Due today') for value in values(app.success))
