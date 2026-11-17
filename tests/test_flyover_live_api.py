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
    app.text_input(key='flyover_question').input(question)
    next(b for b in app.button if b.label == 'Ask Airshow').click().run()
    assert not app.exception
    return ' '.join(values(app.markdown))


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
    assert 'flyover_answer' not in app.session_state
