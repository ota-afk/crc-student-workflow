import json
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openai import OpenAIError

from student_workflow import ai_assistant, api, assistant
from student_workflow.config import rules_path
from student_workflow.contract import AssistantAnswer

DMV = 'task_dmv_id'
RESIDENCY = 'task_proof_of_residency'
client = TestClient(api.app)


@pytest.fixture
def workflow_request():
    demo = json.loads(api.mock_path().read_text(encoding='utf-8'))
    return {'as_of': demo['as_of'], 'student_profile': demo['student_profile']}


@pytest.fixture
def provider(monkeypatch):
    fake = SimpleNamespace(task=DMV, clients=[], calls=[], before_parse=lambda _kind: None)

    class ModelClient:
        def __init__(self, **kwargs):
            fake.clients.append(kwargs)
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

        def close(self):
            pass

        def parse(self, **kwargs):
            fake.calls.append(kwargs)
            kind = kwargs['text_format'].__name__
            fake.before_parse(kind)
            data = {'task_id': fake.task}
            if kind == 'CitationChoice':
                blockers = json.loads(kwargs['input'])['blockers']
                data = {'rule_ids': [item['rule_id'] for item in reversed(blockers)]}
            return SimpleNamespace(output_parsed=kwargs['text_format'](**data))

    monkeypatch.setenv('OPENAI_API_KEY', 'test-provider-key')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    monkeypatch.setattr(ai_assistant, 'OpenAI', ModelClient)
    return fake


def assistant_body(workflow, task_id=DMV, question='Why is this task blocked?'):
    profile = dict(workflow['student_profile'])
    profile.pop('student_id')
    profile.pop('school_verified', None)
    return {'as_of': workflow['as_of'], 'student_profile': profile,
            'task_id': task_id, 'question': question}


def ask(body):
    response = client.post('/assistant', json=body)
    assert response.status_code == 200, response.text
    return AssistantAnswer.model_validate(response.json())


def test_answer_tracks_resolve_and_mark_done(workflow_request, provider):
    before = ask(assistant_body(workflow_request))
    assert before.task_id == DMV
    assert before.answer.startswith('Task status: Blocked.')
    assert before.steps[0].startswith('Finish ')
    assert before.sources[0].rule_id == 'rule_california_real_id_residency'
    assert before.verified == (before.sources[0].verification_status == 'verified')
    assert before.is_mock is False
    assert provider.calls[0]['input'] == 'Why is this task blocked?'
    assert f'The dashboard has selected {DMV}.' in provider.calls[0]['instructions']
    assert workflow_request['as_of'] not in provider.calls[0]['instructions']
    assert provider.calls[0]['store'] is False

    resolved = client.post(f'/tasks/{DMV}/resolve', json=workflow_request)
    assert resolved.status_code == 200, resolved.text
    workflow = resolved.json()['workflow']
    provider.task = RESIDENCY
    assert ask(assistant_body(workflow, RESIDENCY)).answer == 'Task status: In Progress.'

    done_request = {key: workflow[key] for key in ('as_of', 'student_profile')}
    done = client.post(f'/tasks/{RESIDENCY}/complete', json=done_request)
    assert done.status_code == 200, done.text
    assert ask(assistant_body(done.json(), RESIDENCY)).answer == 'Task status: Completed.'
    provider.task = DMV
    assert ask(assistant_body(done.json())).answer == 'Task status: Ready.'


def test_question_guardrails_run_before_openai(workflow_request, provider):
    referral = ask(assistant_body(workflow_request, None, 'Can I work off campus?'))
    assert 'DSO' in referral.contact
    assert not referral.steps and not referral.sources and referral.task_id is None
    privacy = ask(assistant_body(workflow_request, question='My name is Jane and I need help.'))
    assert privacy.answer == ai_assistant.REPHRASE_MESSAGE
    assert provider.clients == []

    provider.task = 'task_confirm_sevis_active'
    matched_referral = ask(assistant_body(workflow_request))
    assert matched_referral.contact == referral.contact
    assert len(provider.calls) == 1


def test_invalid_selection_profile_and_auth_are_rejected(workflow_request, provider, monkeypatch):
    payload = assistant_body(workflow_request)
    monkeypatch.setenv('API_KEY', 'test-dashboard-key')
    assert client.post('/assistant', json=payload).status_code == 401
    headers = {'X-API-Key': 'test-dashboard-key'}
    assert client.post('/assistant', json={**payload, 'task_id': 'missing'},
                       headers=headers).status_code == 404
    assert client.post('/assistant', json={**payload, 'question': '   '},
                       headers=headers).status_code == 422
    assert client.post('/assistant', json={**payload, 'as_of': None},
                       headers=headers).status_code == 422
    payload['student_profile']['student_id'] = 'demo_001'
    assert client.post('/assistant', json=payload, headers=headers).status_code == 422
    assert provider.clients == []


def _is_selected_step_answer(answer):
    return (answer.task_id == DMV and answer.answer.startswith('Task status: Blocked.')
            and answer.answer.endswith(assistant.SELECTED_STEP_NOTE) and answer.sources)


def test_missing_key_falls_back_to_the_selected_step(workflow_request, provider, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    assert _is_selected_step_answer(ask(assistant_body(workflow_request)))
    assert provider.clients == []


def test_provider_failure_is_retried_once_then_falls_back(workflow_request, provider):
    def fail(_kind):
        raise OpenAIError('private provider error')

    provider.before_parse = fail
    answer = ask(assistant_body(workflow_request))
    assert _is_selected_step_answer(answer)
    assert len(provider.calls) == 2  # the first try and one retry
    assert 'private provider error' not in answer.answer


def test_a_retry_that_succeeds_gives_the_normal_answer(workflow_request, provider):
    tries = []

    def fail_once(_kind):
        tries.append(_kind)
        if len(tries) == 1:
            raise OpenAIError('cold start')

    provider.before_parse = fail_once
    answer = ask(assistant_body(workflow_request))
    assert answer.task_id == DMV
    assert assistant.SELECTED_STEP_NOTE not in answer.answer


def test_without_a_selected_step_the_failure_says_so(workflow_request, provider, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    answer = ask(assistant_body(workflow_request, task_id=None))
    assert answer.answer == ai_assistant.ERROR_MESSAGE
    assert not answer.verified and not answer.sources and not answer.is_mock


@pytest.mark.parametrize(('question', 'expected'), [
    ('Can I work off campus?', ai_assistant.DSO_MESSAGE),
    ('My name is Jane and I need help.', ai_assistant.REPHRASE_MESSAGE),
])
def test_fallback_still_runs_the_question_checks(workflow_request, provider, monkeypatch,
                                                 question, expected):
    # As if the model call timed out before map_intent's own checks could answer.
    monkeypatch.setattr(assistant, 'map_intent', lambda *a, **k: None)
    answer = ask(assistant_body(workflow_request, question=question))
    assert answer.answer == expected
    assert answer.task_id is None and not answer.sources


def test_fallback_is_framed_for_the_page(workflow_request, provider, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    answer = ask({**assistant_body(workflow_request), 'page_context': 'journey'})
    assert answer.answer.startswith(assistant.PAGE_LEADS['journey'] + ' Task status:')


def test_waiting_for_intent_is_bounded(workflow_request, provider, monkeypatch):
    entered, release, finished = Event(), Event(), Event()

    def block_intent(_kind):
        entered.set()
        release.wait(4)
        finished.set()

    provider.before_parse = block_intent
    monkeypatch.setattr(assistant, 'INTENT_TIMEOUT', 0.25)
    try:
        # Both tries time out, so the answer falls back to the selected step.
        assert _is_selected_step_answer(ask(assistant_body(workflow_request)))
        assert entered.is_set() and not finished.is_set()
    finally:
        release.set()
    assert finished.wait(1)
    assert provider.clients[0]['timeout'] == 0.25
    assert provider.clients[0]['max_retries'] == 0


def test_timing_and_citations_survive_ranking_timeout(workflow_request, provider, tmp_path,
                                                      monkeypatch):
    rules = json.loads(rules_path().read_text(encoding='utf-8'))
    timing_rule_id = 'rule_california_id_application'
    rule = next(item for item in rules['rules'] if item['rule_id'] == timing_rule_id)
    rule['timing'] = {'from': 'arrival_date', 'days': 10}
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(rules), encoding='utf-8')
    monkeypatch.setenv('RULES_PATH', str(path))

    body = assistant_body(workflow_request)
    ranked = ask(body)
    assert ranked.sources[1].rule_id == timing_rule_id
    assert provider.calls[-1]['text_format'].__name__ == 'CitationChoice'
    assert any('Unlock date: 2026-08-21.' in step for step in ranked.steps)

    entered, release, finished = Event(), Event(), Event()

    def block_ranking(kind):
        if kind == 'CitationChoice':
            entered.set()
            release.wait(4)
            finished.set()

    provider.before_parse = block_ranking
    monkeypatch.setattr(assistant, 'CITATION_TIMEOUT', 0.25)
    try:
        fallback = ask(body)
        assert entered.is_set() and not finished.is_set()
        assert fallback.answer == ranked.answer
        assert fallback.sources == list(reversed(ranked.sources))
        assert fallback.sources[0].rule_id == timing_rule_id
    finally:
        release.set()
    assert finished.wait(1)

    body['as_of'] = '2026-08-21'
    after_unlock = ask(body)
    assert all('Unlock date' not in step for step in after_unlock.steps)
    assert all(source.rule_id != timing_rule_id for source in after_unlock.sources)


PAGES = ['journey', 'readiness', 'airshow']


@pytest.mark.parametrize('page', PAGES)
def test_page_context_adds_its_lead_and_keeps_the_cited_answer(workflow_request, provider, page):
    plain = ask(assistant_body(workflow_request))
    framed = ask({**assistant_body(workflow_request), 'page_context': page})
    assert framed.answer == f'{assistant.PAGE_LEADS[page]} {plain.answer}'
    assert (framed.steps, framed.sources, framed.verified, framed.task_id) == (
        plain.steps, plain.sources, plain.verified, plain.task_id)


def test_null_page_context_leaves_the_answer_unchanged(workflow_request, provider):
    body = assistant_body(workflow_request)
    assert ask({**body, 'page_context': None}) == ask(body)


def test_unknown_page_context_is_rejected_before_any_model_call(workflow_request, provider):
    body = {**assistant_body(workflow_request), 'page_context': 'settings'}
    assert client.post('/assistant', json=body).status_code == 422
    assert provider.clients == []


def test_page_context_never_reaches_the_model(workflow_request, provider):
    ask({**assistant_body(workflow_request), 'page_context': 'readiness'})
    sent = json.dumps(provider.calls, default=str)  # every call's instructions, input, etc.
    assert 'readiness' not in sent and assistant.PAGE_LEADS['readiness'] not in sent


def test_referral_is_not_framed_on_any_page(workflow_request, provider):
    body = assistant_body(workflow_request, None, 'Can I work off campus?')
    referral = ask({**body, 'page_context': 'airshow'})
    assert 'DSO' in referral.contact
    assert not referral.answer.startswith(assistant.PAGE_LEADS['airshow'])


def test_every_page_in_the_contract_has_a_lead():
    from typing import get_args

    from student_workflow.contract import PageContext
    assert set(get_args(PageContext)) == set(assistant.PAGE_LEADS)
