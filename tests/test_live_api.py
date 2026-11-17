"""The dashboard against the real API (in process): key header, generate, resolve, complete.

requests.get/post are routed to the FastAPI app through TestClient, so these tests check the
dashboard and the contract together, with ENG's real rules and the demo profile.
"""

import pytest
import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from test_streamlit import APP_PATH, values

from student_workflow import api, assistant
from student_workflow.ai_assistant import IntentResult
from student_workflow.api import app as api_app

KEY = 'test-key-123'


class Reply:
    """An httpx reply that fails the way requests does."""

    def __init__(self, reply) -> None:
        self._reply = reply
        self.status_code = reply.status_code

    def json(self):
        return self._reply.json()

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} error')


class Bridge:
    """Stands in for the network: sends each request to the API and records what was sent."""

    def __init__(self) -> None:
        self.client = TestClient(api_app)
        self.calls: list[tuple[str, str, dict | None, dict]] = []

    @staticmethod
    def _path(url: str) -> str:
        return url.removeprefix('http://localhost:8000')

    def get(self, url, *, headers=None, params=None, timeout=None):
        self.calls.append(('GET', self._path(url), None, dict(headers or {})))
        return Reply(self.client.get(self._path(url), params=params, headers=headers))

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.calls.append(('POST', self._path(url), json, dict(headers or {})))
        return Reply(self.client.post(self._path(url), json=json, headers=headers))

    def posts(self) -> list[tuple[str, dict]]:
        return [(path, body) for method, path, body, _ in self.calls if method == 'POST']


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def start() -> AppTest:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    return app


def status_of(app: AppTest, task_id: str) -> str:
    return next(t for t in app.session_state['workflow_data']['workflow']
                if t['id'] == task_id)['status']


def pick(app: AppTest, task_id: str) -> AppTest:
    return app.selectbox(key='detail_task').select(task_id).run()


def test_key_is_sent_on_workflow_and_school_search(bridge):
    app = start()
    assert not any('Could not load' in v for v in values(app.error))
    app.text_input(key='school_query').set_value('Cosumnes').run()
    app.button(key='search_schools').click().run()
    assert not app.exception
    paths = [(m, p) for m, p, _, _ in bridge.calls]
    assert ('GET', '/workflow') in paths and ('GET', '/schools') in paths
    assert all(headers == {'X-API-Key': KEY} for *_, headers in bridge.calls)


def test_rejected_key_shows_friendly_load_error(bridge, monkeypatch):
    class Rejected:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError('Missing or invalid API key')

    monkeypatch.setattr(requests, 'get', lambda *a, **k: Rejected())
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert any('Could not load your workflow' in v for v in values(app.error))
    assert not any('API key' in v for v in values(app.error))


def test_server_refuses_requests_without_the_key(bridge, monkeypatch):
    # Proves the header is what lets the dashboard load: without it the real API says 401.
    monkeypatch.setattr(api, 'api_key', lambda: KEY)  # the server keeps its key
    monkeypatch.setenv('API_KEY', '')  # the dashboard has none, so it sends no header
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert any('Could not load your workflow' in v for v in values(app.error))


def test_generate_posts_profile_without_state_and_holds_result(bridge):
    app = start()
    app.text_input(key='school_query').set_value('Cosumnes').run()
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    app.text_input(key='onboarding_visa').set_value('J-1').run()
    app.radio(key='onboarding_has_ssn').set_value('Yes').run()
    app.button(key='generate_workflow').click().run()
    assert not app.exception
    (path, body), = bridge.posts()
    assert path == '/workflow'
    assert 'state' not in body['student_profile']
    assert body['student_profile']['student_id'] == 'demo_001'
    assert body['student_profile']['visa_type'] == 'J-1'
    assert body['student_profile']['has_ssn'] is True
    assert body['student_profile']['completed_tasks'] == []
    assert body['as_of'] == '2026-08-14'
    held = app.session_state['workflow_data']
    assert held['student_profile']['visa_type'] == 'J-1'
    assert held['is_mock'] is False
    # The next rerun shows the held workflow; it does not fetch the demo again.
    gets = [c for c in bridge.calls if c[0] == 'GET' and c[1] == '/workflow']
    app.run()
    assert [c for c in bridge.calls if c[0] == 'GET' and c[1] == '/workflow'] == gets


def test_resolve_then_mark_done_unblocks_dmv_with_same_as_of(bridge):
    app = start()
    pick(app, 'task_dmv_id')
    assert not app.button(key='resolve_task').disabled
    assert app.button(key='complete_task').disabled
    app.button(key='resolve_task').click().run()
    assert not app.exception
    assert status_of(app, 'task_proof_of_residency') == 'In Progress'
    # The email draft from the API is shown, not a sample template.
    code = app.code[0].value
    assert code.startswith('Subject: ')
    assert not any('Sample email draft' in v for v in values(app.warning))
    assert any('Draft email. Not verified' in v for v in values(app.warning))
    pick(app, 'task_proof_of_residency')
    assert not app.button(key='complete_task').disabled
    app.button(key='complete_task').click().run()
    assert not app.exception
    assert status_of(app, 'task_proof_of_residency') == 'Completed'
    assert status_of(app, 'task_dmv_id') == 'Ready'
    (resolve, first), (complete, second) = bridge.posts()
    assert resolve == '/tasks/task_dmv_id/resolve'
    assert complete == '/tasks/task_proof_of_residency/complete'
    assert first['as_of'] == second['as_of'] == '2026-08-14'
    # Stateless round trip: the second request carries the profile the first one returned.
    assert second['student_profile']['awaiting_reply'] == ['task_proof_of_residency']


def test_clear_email_draft_removes_only_the_draft(bridge):
    app = start()
    pick(app, 'task_dmv_id')
    app.button(key='resolve_task').click().run()
    assert len(app.code) == 1
    app.button(key='clear_email').click().run()
    assert len(app.code) == 0
    assert status_of(app, 'task_proof_of_residency') == 'In Progress'


def test_draft_is_shown_only_for_its_own_task(bridge):
    app = start()
    pick(app, 'task_dmv_id')
    app.button(key='resolve_task').click().run()
    pick(app, 'task_bank_account')
    assert len(app.code) == 0


def test_resolve_without_email_draft_says_so(bridge, monkeypatch):
    real_post = bridge.post

    def no_draft(url, **kwargs):
        response = real_post(url, **kwargs)
        data = response.json()
        if 'email_draft' in data:
            data['email_draft'] = None
        response.json = lambda: data
        return response

    monkeypatch.setattr(requests, 'post', no_draft)
    app = start()
    pick(app, 'task_dmv_id')
    app.button(key='resolve_task').click().run()
    assert not app.exception
    assert len(app.code) == 0
    assert status_of(app, 'task_proof_of_residency') == 'In Progress'


@pytest.mark.parametrize(('code', 'text'), [
    (409, 'cannot be updated in its current state'),
    (422, 'could not accept this profile'),
    (429, 'Too many requests'),
    (401, 'could not sign in'),
    (503, 'service is unavailable'),
])
def test_action_errors_are_friendly_and_keep_the_workflow(bridge, monkeypatch, code, text):
    class Failed:
        status_code = code

        def raise_for_status(self):
            raise requests.HTTPError('private backend details')

        def json(self):
            return {'detail': 'private backend details'}

    app = start()
    pick(app, 'task_dmv_id')
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Failed())
    app.button(key='resolve_task').click().run()
    assert not app.exception
    assert any(text in v for v in values(app.error))
    assert not any('private backend details' in v for v in values(app.error))
    assert 'workflow_data' not in app.session_state
    assert len(app.code) == 0
    # The error belongs to this task only.
    pick(app, 'task_bank_account')
    assert not any(text in v for v in values(app.error))


def test_network_failure_is_friendly(bridge, monkeypatch):
    app = start()
    pick(app, 'task_dmv_id')

    def down(*args, **kwargs):
        raise requests.ConnectionError('private backend details')

    monkeypatch.setattr(requests, 'post', down)
    app.button(key='resolve_task').click().run()
    assert any('service is unavailable' in v for v in values(app.error))
    assert not any('private backend details' in v for v in values(app.error))


def test_generated_profile_change_clears_old_draft(bridge):
    app = start()
    pick(app, 'task_dmv_id')
    app.button(key='resolve_task').click().run()
    assert 'api_email_draft' in app.session_state
    app.session_state['workflow_data'] = {
        **app.session_state['workflow_data'],
        'student_profile': {**app.session_state['workflow_data']['student_profile'],
                            'institution': 'Another College'}}
    app.run()
    assert 'api_email_draft' not in app.session_state


@pytest.fixture
def assistant_live(bridge, monkeypatch):
    """Live assistant mode, with the model's intent pick faked: it always picks the DMV task.

    Everything else is real: the dashboard request, the API route, the resolver and the
    rules-based explanation. No OpenAI key is set, so nothing leaves the machine.
    """
    monkeypatch.setenv('ASSISTANT_MODE', 'live')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(assistant, 'map_intent', lambda *a, **k: IntentResult(
        outcome='matched', task_id='task_dmv_id'))
    return bridge


def ask(app: AppTest, question: str) -> str:
    """Ask in the Assistant tab and return the newest answer's text."""
    app.chat_input[0].set_value(question).run()
    assert not app.exception
    return ' '.join(values(app.chat_message[-1].markdown))


def assistant_bodies(bridge: Bridge) -> list[dict]:
    return [body for path, body in bridge.posts() if path == '/assistant']


def test_assistant_answer_follows_resolve_and_mark_done(assistant_live):
    app = start()
    pick(app, 'task_dmv_id')
    assert 'Task status: Blocked.' in ask(app, 'Why is my ID blocked?')
    app.button(key='resolve_task').click().run()
    assert 'Task status: Blocked.' in ask(app, 'Why is my ID blocked?')
    pick(app, 'task_proof_of_residency')
    app.button(key='complete_task').click().run()
    # After "Mark done" the same question gets the new status, not the old one.
    assert 'Task status: Ready.' in ask(app, 'Can I apply for my ID now?')
    first, after_resolve, after_done = assistant_bodies(assistant_live)
    assert first['student_profile']['awaiting_reply'] == []
    assert after_resolve['student_profile']['awaiting_reply'] == ['task_proof_of_residency']
    assert 'task_proof_of_residency' in after_done['student_profile']['completed_tasks']


def test_assistant_sends_the_workflow_date_and_no_identifiers(assistant_live):
    app = start()
    pick(app, 'task_dmv_id')
    ask(app, 'What next?')
    body, = assistant_bodies(assistant_live)
    # The workflow's own date, so the answer can't fall on a different day than the screen.
    assert body['as_of'] == app.session_state['session_as_of'] == '2026-08-14'
    assert body['task_id'] == 'task_dmv_id'
    assert 'student_id' not in body['student_profile']
    assert 'school_verified' not in body['student_profile']
    headers = [h for m, p, _, h in assistant_live.calls if p == '/assistant']
    assert headers == [{'X-API-Key': KEY}]


def test_assistant_timeout_shows_a_helpful_message(assistant_live, monkeypatch):
    app = start()
    pick(app, 'task_dmv_id')
    real_post = requests.post

    def slow(url, **kwargs):
        if url.endswith('/assistant'):
            raise requests.Timeout('internal timeout details')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', slow)
    app.chat_input[0].set_value('What next?').run()
    assert not app.exception
    assert any('took too long' in v for v in values(app.error))
    assert not any('internal timeout details' in v for v in values(app.error))
    # Only the question is in the chat: no half answer, and asking again works.
    assert len(app.chat_message) == 1
