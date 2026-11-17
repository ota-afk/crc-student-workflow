"""Flyover's public demo (STU-D07-demo-scenario), against the real API in process.

A fresh visitor clicks "Try the CRC demo" (no email, no password) and walks the August 14, 2026
scenario: tuition due today, resolve the DMV blocker, complete its prerequisite, DMV Ready. The
demo notice shows on every page, in Settings, and when the API is down. Only the model's intent
pick is faked, so nothing leaves the machine.
"""

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_flyover_app import go_to, open_checklist
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow import assistant
from student_workflow.ai_assistant import IntentResult
from student_workflow.flyover import _handoff_text

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'
DMV, RESIDENCY, FEE = 'task_dmv_id', 'task_proof_of_residency', 'task_crc_fee_payment'
NOTICE = 'Flyover demo · Updates coming soon.'
SCENARIO = '2026-08-14'


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(assistant, 'map_intent', lambda *a, **k: IntentResult(
        outcome='matched', task_id=DMV))
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def first_screen() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=30).run()


def demo() -> AppTest:
    app = first_screen()
    app.button(key='flyover_try_demo').click().run()
    assert not app.exception
    return app


def status_of(app: AppTest, task_id: str) -> str:
    return next(t['status'] for t in app.session_state['flyover_data']['workflow']
                if t['id'] == task_id)


def checklist(app: AppTest, task_id: str) -> AppTest:
    return open_checklist(app, task_id)


def notice_count(app: AppTest) -> int:
    return sum(NOTICE in v for v in values(app.get('html')))


def test_try_the_crc_demo_needs_no_email_or_password(live):
    app = demo()
    assert 'flyover_account' not in app.session_state
    profile = app.session_state['flyover_data']['student_profile']
    assert (profile['school_id'], profile['arrival_date'], profile['enrollment_date'],
            profile['enrollment_term']) == ('crc', '2026-08-11', '2026-08-13', 'fall_2026')
    assert profile['completed_tasks'] == [] and profile['awaiting_reply'] == []
    assert 'Profile setup' in values(app.subheader)


def test_the_demo_sends_its_scenario_date_explicitly(live):
    demo()
    path, body = live.posts()[-1]
    assert (path, body['as_of']) == ('/workflow', SCENARIO)


def test_demo_tuition_is_due_today_on_august_14(live):
    app = checklist(demo(), FEE)
    assert any(v.startswith('Due today, Fri, Aug 14, 2026 · Double-checked by our team')
               and '[Source ↗]' in v for v in values(app.success))
    assert not any('Past due' in v for v in values(app.warning))


def test_resolving_dmv_keeps_it_blocked_until_its_prerequisite_is_completed(live):
    app = checklist(demo(), DMV)
    assert status_of(app, DMV) == 'Blocked'
    app.button(key='flyover_resolve:' + DMV).click().run()
    assert (status_of(app, DMV), status_of(app, RESIDENCY)) == ('Blocked', 'In Progress')
    app = app.selectbox(key='flyover_checklist_pick').select(RESIDENCY).run()
    app.button(key='flyover_detail_complete').click().run()
    assert not app.exception
    assert (status_of(app, RESIDENCY), status_of(app, DMV)) == ('Completed', 'Ready')


def test_actions_chat_and_profile_changes_all_keep_the_scenario_date(live):
    app = checklist(demo(), DMV)
    app.button(key='flyover_resolve:' + DMV).click().run()
    app.text_area(key='flyover_question').input('What next?')
    next(b for b in app.button if b.label == 'Send').click().run()
    go_to(app, 'workflow')
    app.checkbox(key='flyover_new_profile').check()
    next(b for b in app.button if b.label == 'Generate workflow').click().run()
    assert not app.exception
    sent = {path: body.get('as_of') for path, body in live.posts()}
    assert set(sent) >= {'/workflow', f'/tasks/{DMV}/resolve', '/assistant'}
    assert set(sent.values()) == {SCENARIO}
    assert app.session_state['flyover_data']['as_of'] == SCENARIO


def test_august_dmv_checklist_links_the_office_without_a_november_time(live):
    app = checklist(demo(), DMV)
    shown = values(app.markdown)
    assert "**Hours for this date aren't confirmed** (August 14, 2026)." in shown
    assert any('href="https://www.dmv.ca.gov/portal/field-office/sacramento-south/"' in value
               and 'fly-source-tag' in value for value in shown)
    captions = values(app.caption)
    assert any(c.startswith('The published hours have no date range, so they may not apply '
                            'on August 14, 2026.') for c in captions)


def test_august_dmv_notice_and_checklist_suggest_no_time_for_free_times(live):
    app = demo()
    # A synthetic student two steps from DMV, so DMV's appointment notice is on page 1.
    others = [t['id'] for t in app.session_state['flyover_data']['workflow']
              if t['id'] not in (DMV, RESIDENCY, 'task_bank_account')]
    profile = {**app.session_state['flyover_data']['student_profile'], 'completed_tasks': others}
    reply = live.client.post('/workflow', json={'student_profile': profile, 'as_of': SCENARIO},
                             headers={'X-API-Key': KEY})
    app.session_state['flyover_data'] = reply.json()
    app.run()
    from datetime import time
    app.selectbox(key='fly_avail_day').select('Monday')
    app.time_input(key='fly_avail_start').set_value(time(10, 0))
    app.time_input(key='fly_avail_end').set_value(time(11, 0))
    next(b for b in app.button if b.label == 'Add free time').click().run()
    notice = values(app.caption)
    assert any(c.startswith("California DMV, Sacramento South: Hours for this date aren't "
                            'confirmed.') for c in notice)
    assert not any('overlap' in c for c in notice)
    app = checklist(app, DMV)
    assert not any('overlap' in c or '10:00 AM' in c for c in values(app.caption))


def test_the_demo_notice_is_on_every_page_and_in_settings(live):
    app = first_screen()
    assert notice_count(app) == 1  # the entry screen
    app.button(key='flyover_try_demo').click().run()
    assert app.session_state['flyover_data']['is_mock'] is False  # never decided by is_mock
    assert notice_count(app) == 1  # Workflow and readiness
    go_to(app, 'checklist')
    assert notice_count(app) == 1  # Checklist
    app.button(key='flyover_settings').click().run()
    assert notice_count(app) == 2  # the page and the Settings dialog
    app.button(key='flyover_settings_profile').click().run()
    assert app.session_state['flyover_page'] == 'profile' and notice_count(app) >= 1
    assert 'Walkthrough date' in ' '.join(values(app.get('html')))


def _api_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError('API unavailable (test)')
    monkeypatch.setattr(requests, 'get', refuse)
    monkeypatch.setattr(requests, 'post', refuse)


def test_the_demo_notice_survives_an_unavailable_api(live, monkeypatch):
    _api_down(monkeypatch)
    app = first_screen()
    app.button(key='flyover_try_demo').click().run()
    assert 'Could not start the demo. Try again in a moment.' in values(app.error)
    assert notice_count(app) == 1


def test_the_demo_notice_survives_a_failed_workflow_reload(live, monkeypatch):
    _api_down(monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state['flyover_demo'] = True  # entered, but no workflow kept
    app.run()
    assert any('Could not load your workflow' in v for v in values(app.error))
    assert notice_count(app) == 1


def test_exported_handoffs_carry_the_scenario_date(live):
    app = go_to(demo(), 'handoff')
    app.text_area(key='flyover_goal').input('Get my California ID.').run()
    app.button(key='flyover_prepare_handoff').click().run()
    doc = app.session_state['flyover_handoff']
    for markdown in (False, True):
        assert 'This walkthrough is set on August 14, 2026.' in _handoff_text(doc, markdown)


def test_a_demo_visitor_is_offered_no_email_reminder(live):
    app = checklist(demo(), DMV)
    assert '#### Email me a reminder' not in values(app.markdown)
