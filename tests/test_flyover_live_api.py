"""Flyover against the real API (in process): resolve, mark done, then ask Airshow.

requests.get/post go to the FastAPI app through test_live_api's Bridge, so these tests check
Flyover and the contract together with ENG's real rules. Only the model's intent pick is
faked, so nothing leaves the machine and no OpenAI key is needed.
"""

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow import assistant
from student_workflow.ai_assistant import IntentResult

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'
DMV = 'task_dmv_id'
RESIDENCY = 'task_proof_of_residency'


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    # The one faked piece: the model always picks the DMV task.
    monkeypatch.setattr(assistant, 'map_intent', lambda *a, **k: IntentResult(
        outcome='matched', task_id=DMV))
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def status_of(app: AppTest, task_id: str) -> str:
    return next(t['status'] for t in app.session_state['flyover_data']['workflow']
                if t['id'] == task_id)


def open_checklist(app: AppTest, task_id: str) -> AppTest:
    app.button(key='flyover_next').click().run()  # page 2: readiness and the checklist
    return app.selectbox(key='flyover_detail').select(task_id).run()


def ask(app: AppTest, question: str) -> str:
    """Ask in the AI Help dropdown and return the newest answer's text."""
    app.text_input(key='flyover_question').input(question)
    next(b for b in app.button if b.label == 'Send').click().run()
    assert not app.exception
    history = app.session_state.get('flyover_popup_history', [])
    return history[-1]['answer'] if history else ''


def test_resolve_shows_the_api_draft_and_moves_the_prerequisite(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    assert status_of(app, DMV) == 'Blocked'
    app.button(key='flyover_resolve:' + DMV).click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) == 'In Progress'
    assert status_of(app, DMV) == 'Blocked'  # only marking residency done unblocks it
    assert app.code[0].value.startswith('Subject: ')
    assert any('Nothing has been sent' in v for v in values(app.warning))
    path, body = live.posts()[-1]
    assert path == f'/tasks/{DMV}/resolve'
    assert body['as_of'] == '2026-08-14'


def test_airshow_answer_follows_resolve_and_mark_done(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    assert 'Task status: Blocked.' in ask(app, 'Why is my ID blocked?')
    app.button(key='flyover_resolve:' + DMV).click().run()
    app.selectbox(key='flyover_detail').select(RESIDENCY).run()
    app.button(key='flyover_detail_complete').click().run()  # back to page 1
    assert status_of(app, DMV) == 'Ready'
    app = open_checklist(app, DMV)
    # The same kind of question now gets the new status, not the old one.
    assert 'Task status: Ready.' in ask(app, 'Can I apply for my ID now?')
    asked = [(body, headers) for method, path, body, headers in live.calls
             if path == '/assistant']
    (first, _), (second, headers) = asked
    assert first['student_profile']['completed_tasks'] == ['task_i94_retrieval', 'task_sevis_fee']
    assert RESIDENCY in second['student_profile']['completed_tasks']
    assert second['as_of'] == '2026-08-14'
    assert 'student_id' not in second['student_profile']
    assert headers == {'X-API-Key': KEY}


def test_airshow_timeout_shows_a_helpful_message(live, monkeypatch):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    real_post = requests.post

    def slow(url, **kwargs):
        if url.endswith('/assistant'):
            raise requests.Timeout('internal timeout details')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', slow)
    ask(app, 'What next?')
    assert any('took too long' in v for v in values(app.error))
    assert not any('internal timeout details' in v for v in values(app.error))
    assert 'flyover_popup_history' not in app.session_state
    # The unsent question stays in the box so it can be sent again.
    assert app.text_input(key='flyover_question').value == 'What next?'


def confetti_shown(app: AppTest) -> bool:
    return '<div class="flyover-confetti"' in str([e.value for e in app.get('html')])


def test_checklist_completion_celebrates_once_like_the_status_selector(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) == 'Completed'  # the API's answer, not the click
    assert app.session_state['flyover_page'] == 'home'
    assert confetti_shown(app)
    assert any('completed. Next:' in v for v in values(app.success))
    app.run()
    assert not confetti_shown(app)  # consumed once


def test_failed_checklist_completion_does_not_celebrate(live, monkeypatch):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), RESIDENCY)
    real_post = requests.post

    def refuse(url, **kwargs):
        if url.endswith('/complete'):
            raise requests.Timeout('private detail')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', refuse)
    app.button(key='flyover_detail_complete').click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) != 'Completed'
    assert not confetti_shown(app)
    assert any('progress has been kept' in v for v in values(app.error))


def test_reduce_motion_completion_shows_the_message_without_confetti(live):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.session_state['flyover_reduce_motion'] = True
    app = open_checklist(app, RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    assert not confetti_shown(app)
    assert any('completed. Next:' in v for v in values(app.success))


def chat_bodies(bridge: Bridge) -> list[dict]:
    return [body for path, body in bridge.posts() if path == '/assistant']


def test_dropdown_is_named_ai_help_and_asking_does_not_navigate(live):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    # AppTest has no Popover class; the label (the accessible name) is on the block's proto.
    assert [p.proto.popover.label for p in app.get('popover')] == ['AI Help']
    ask(app, 'What next?')
    # No jump to page 2 or Airshow (the app only sets flyover_page when you navigate).
    assert app.session_state.get('flyover_page', 'home') == 'home'
    assert 'flyover_scroll' not in app.session_state


def test_dropdown_sends_journey_and_the_current_step_on_page_one(live):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    ask(app, 'What next?')
    body, = chat_bodies(live)
    assert body['page_context'] == 'journey'
    assert body['task_id'] == app.session_state['flyover_active_id']


def test_dropdown_sends_readiness_and_the_chosen_task_on_page_two(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    answer = ask(app, 'Why is my ID blocked?')
    body, = chat_bodies(live)
    assert (body['page_context'], body['task_id']) == ('readiness', DMV)
    assert answer.startswith('What this step needs before you go. Task status: Blocked.')


def test_clearing_the_chat_keeps_the_handoff(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    ask(app, 'What next?')
    app.button(key='flyover_chat_clear').click().run()
    assert 'flyover_popup_history' not in app.session_state
    assert app.session_state['flyover_handoff']['title'] == 'Handoff for your DMV clerk'


def test_generating_a_handoff_sends_nothing_to_the_assistant(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    assert chat_bodies(live) == []


def test_answer_is_marked_earlier_after_progress_changes(live):
    app = open_checklist(AppTest.from_file(str(APP), default_timeout=30).run(), DMV)
    ask(app, 'Why is my ID blocked?')
    assert not any('Earlier answer' in v for v in values(app.caption))
    app.button(key='flyover_resolve:' + DMV).click().run()
    assert any('Earlier answer' in v for v in values(app.caption))


def test_chat_history_is_bounded(live, monkeypatch):
    from student_workflow import flyover
    monkeypatch.setattr(flyover, 'CHAT_LIMIT', 2)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    for number in range(3):
        ask(app, f'Question {number}?')
    assert [e['question'] for e in app.session_state['flyover_popup_history']] == [
        'Question 1?', 'Question 2?']
