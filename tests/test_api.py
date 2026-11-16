"""Tests for the API endpoints (STU-D03-BE): live workflow, task actions, API key, rate limit.

Most tests use a small made-up rules file ("(sample)") through RULES_PATH, so they never
depend on ENG's real rules. The demo profile tests at the bottom use the real file.
Dates match the demo: arrived 2026-08-11, "as of" 2026-08-14 (3 days later).
"""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from student_workflow import api
from student_workflow.api import app
from student_workflow.contract import Workflow
from student_workflow.engine import RulesError

client = TestClient(app)

AS_OF = '2026-08-14'


def sample_rule(rule_id, **changes):
    base = {
        'rule_id': rule_id,
        'statement': f'Sample statement for {rule_id} (sample)',
        'layer': 'california',
        'high_risk': False,
        'verification_status': 'needs_verification',
    }
    return {**base, **changes}


def sample_task(task_id, prerequisites=None):
    return {
        'id': task_id,
        'title': f'Title of {task_id} (sample)',
        'priority': 'Required',
        'prerequisites': prerequisites or [],
        'rule_ids': [f'rule_{task_id}'],
    }


TEN_DAYS = {'from': 'arrival_date', 'days': 10}  # unlocks 2026-08-21, after AS_OF


@pytest.fixture
def sample_rules(monkeypatch, tmp_path):
    """dmv needs residency. wait: only a date. both: residency and a date. chain_c->b->a."""
    rules = {
        'tasks': [
            sample_task('residency'),
            sample_task('dmv', ['residency']),
            sample_task('wait'),
            sample_task('both', ['residency']),
            sample_task('chain_a'),
            sample_task('chain_b', ['chain_a']),
            sample_task('chain_c', ['chain_b']),
        ],
        'rules': [
            sample_rule('rule_residency'),
            sample_rule('rule_dmv'),
            sample_rule('rule_wait', timing=TEN_DAYS),
            sample_rule('rule_both', timing=TEN_DAYS),
            sample_rule('rule_chain_a'),
            sample_rule('rule_chain_b'),
            sample_rule('rule_chain_c'),
        ],
    }
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(rules), encoding='utf-8')
    monkeypatch.setenv('RULES_PATH', str(path))


def body(completed=None, awaiting=None, **changes):
    profile = {
        'student_id': 'demo_001',
        'institution': 'Sample College (sample)',
        'visa_type': 'F-1',
        'arrival_date': '2026-08-11',
        'has_ssn': False,
        'completed_tasks': completed or [],
        'awaiting_reply': awaiting or [],
    }
    return {'as_of': AS_OF, 'student_profile': profile, **changes}


def status_of(workflow, task_id):
    return next(t['status'] for t in workflow['workflow'] if t['id'] == task_id)


# Health and GET /workflow


def test_health():
    assert client.get('/health').json() == {'status': 'ok'}


def test_health_needs_no_api_key(monkeypatch):
    # Hosts and warm-up pings call /health without the key.
    monkeypatch.setenv('API_KEY', 'secret')
    assert client.get('/health').status_code == 200


def test_workflow_serves_mock(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'true')
    response = client.get('/workflow')
    assert response.status_code == 200
    assert response.json()['is_mock'] is True


def test_live_get_workflow_runs_the_demo_student_through_the_engine(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    mock = json.loads(api.mock_path().read_text(encoding='utf-8'))
    workflow = client.get('/workflow').json()
    assert workflow['is_mock'] is False
    assert workflow['as_of'] == mock['as_of']
    assert workflow['student_profile']['completed_tasks'] == (
        mock['student_profile']['completed_tasks']
    )
    assert status_of(workflow, 'task_dmv_id') == 'Blocked'


def test_live_get_workflow_is_503_when_the_demo_profile_no_longer_fits(
    sample_rules, monkeypatch
):
    # The mock's completed tasks are not in the sample rules. Nobody sent this profile, so
    # it is our problem (503), not a client error (422).
    monkeypatch.setenv('USE_MOCK', 'false')
    assert client.get('/workflow').status_code == 503


# POST /workflow


def test_post_workflow_returns_the_live_workflow(sample_rules):
    workflow = client.post('/workflow', json=body()).json()
    assert workflow['is_mock'] is False
    assert status_of(workflow, 'dmv') == 'Blocked'


def test_post_workflow_without_as_of_uses_todays_date_in_california(
    sample_rules, monkeypatch
):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            # 06:30 UTC on Aug 15 is still Aug 14 in California. Without tz it stays Aug 15.
            utc = datetime(2026, 8, 15, 6, 30, tzinfo=UTC)
            return utc.astimezone(tz) if tz else utc

    monkeypatch.setattr(api, 'datetime', FixedClock)
    request = body()
    del request['as_of']
    assert client.post('/workflow', json=request).json()['as_of'] == AS_OF


def test_unknown_request_key_is_rejected(sample_rules):
    assert client.post('/workflow', json=body(asof=AS_OF)).status_code == 422


def test_unknown_profile_key_is_rejected(sample_rules):
    request = body()
    request['student_profile']['completed_task'] = ['residency']
    assert client.post('/workflow', json=request).status_code == 422


def test_profile_the_resolver_rejects_is_422_with_its_reason(sample_rules):
    response = client.post('/workflow', json=body(['task_typo']))
    assert response.status_code == 422
    assert 'task_typo' in response.json()['detail']


def test_task_listed_twice_is_422(sample_rules):
    response = client.post('/workflow', json=body(['residency', 'residency']))
    assert response.status_code == 422
    assert 'more than once' in response.json()['detail']


def test_rules_that_cannot_serve_the_school_are_503_not_422(sample_rules, monkeypatch):
    def no_tasks(*_args):
        raise RulesError('No tasks found for this school (sample)')

    monkeypatch.setattr(api, 'resolve', no_tasks)
    assert client.post('/workflow', json=body()).status_code == 503


def test_engine_bug_is_500_without_internal_details(sample_rules, monkeypatch):
    def broken_engine(*_args):
        return Workflow.model_validate({})  # raises pydantic's ValidationError

    monkeypatch.setattr(api, 'resolve', broken_engine)
    response = client.post('/workflow', json=body())
    assert response.status_code == 500
    assert response.json()['detail'] == 'Internal error'


def test_broken_rules_file_is_503_without_details(monkeypatch, tmp_path):
    path = tmp_path / 'rules.json'
    path.write_text('{not json', encoding='utf-8')
    monkeypatch.setenv('RULES_PATH', str(path))
    response = client.post('/workflow', json=body())
    assert response.status_code == 503
    assert response.json()['detail'] == 'Workflow is temporarily unavailable'


# POST /tasks/{task_id}/complete


def test_complete_makes_the_dependent_task_ready(sample_rules):
    workflow = client.post('/tasks/residency/complete', json=body()).json()
    assert workflow['student_profile']['completed_tasks'] == ['residency']
    assert status_of(workflow, 'dmv') == 'Ready'


def test_complete_removes_the_task_from_awaiting_reply(sample_rules):
    request = body(awaiting=['residency'])
    workflow = client.post('/tasks/residency/complete', json=request).json()
    assert workflow['student_profile']['awaiting_reply'] == []


def test_complete_a_blocked_task_is_409(sample_rules):
    assert client.post('/tasks/dmv/complete', json=body()).status_code == 409


def test_complete_a_task_blocked_only_by_a_date_is_409(sample_rules):
    assert client.post('/tasks/wait/complete', json=body()).status_code == 409


def test_complete_a_completed_task_is_409(sample_rules):
    response = client.post('/tasks/residency/complete', json=body(['residency']))
    assert response.status_code == 409


@pytest.mark.parametrize('action', ['complete', 'resolve'])
def test_unknown_task_is_404(sample_rules, action):
    assert client.post(f'/tasks/task_typo/{action}', json=body()).status_code == 404


# POST /tasks/{task_id}/resolve


def test_resolve_moves_the_next_action_to_in_progress(sample_rules):
    result = client.post('/tasks/dmv/resolve', json=body()).json()
    assert result['workflow']['student_profile']['awaiting_reply'] == ['residency']
    assert status_of(result['workflow'], 'residency') == 'In Progress'


def test_resolve_keeps_the_blocked_task_blocked(sample_rules):
    result = client.post('/tasks/dmv/resolve', json=body()).json()
    assert status_of(result['workflow'], 'dmv') == 'Blocked'


def test_resolve_has_no_email_draft_yet(sample_rules):
    # None = AI's generate_email() is not built; the API never makes one up.
    result = client.post('/tasks/dmv/resolve', json=body()).json()
    assert result['email_draft'] is None


def test_resolve_twice_changes_nothing(sample_rules):
    result = client.post('/tasks/dmv/resolve', json=body(awaiting=['residency'])).json()
    assert result['workflow']['student_profile']['awaiting_reply'] == ['residency']


def test_resolve_a_ready_task_is_409(sample_rules):
    assert client.post('/tasks/residency/resolve', json=body()).status_code == 409


def test_resolve_a_completed_task_is_409(sample_rules):
    response = client.post('/tasks/residency/resolve', json=body(['residency']))
    assert response.status_code == 409


def test_resolve_a_task_blocked_only_by_a_date_is_409(sample_rules):
    response = client.post('/tasks/wait/resolve', json=body())
    assert response.status_code == 409
    assert 'waiting for a date' in response.json()['detail']


def test_resolve_a_task_blocked_by_a_prerequisite_and_a_date_is_allowed(sample_rules):
    result = client.post('/tasks/both/resolve', json=body()).json()
    assert status_of(result['workflow'], 'residency') == 'In Progress'
    assert status_of(result['workflow'], 'both') == 'Blocked'  # the date still holds


def test_resolve_is_409_when_the_next_action_is_blocked_itself(sample_rules):
    # chain_c needs chain_b, which needs chain_a: chain_b can't be "in progress" yet.
    response = client.post('/tasks/chain_c/resolve', json=body())
    assert response.status_code == 409
    assert 'chain_b is Blocked' in response.json()['detail']


# API key


def test_missing_api_key_is_401(sample_rules, monkeypatch):
    monkeypatch.setenv('API_KEY', 'secret')
    assert client.post('/workflow', json=body()).status_code == 401


def test_every_route_except_health_needs_the_api_key(monkeypatch):
    # Catches a new route added without dependencies=NEEDS_KEY.
    monkeypatch.setenv('API_KEY', 'secret')
    # hasattr(r, 'tags'): our own routes, not FastAPI's built-in /docs and /openapi.json.
    own_routes = [r for r in app.routes if r.path != '/health' and hasattr(r, 'tags')]
    for route in own_routes:
        (method,) = route.methods  # each of our routes has exactly one method
        path = route.path.replace('{task_id}', 'residency')
        response = client.request(method, path, json=body())
        assert response.status_code == 401, f'{method} {route.path}'


def test_wrong_api_key_is_401(sample_rules, monkeypatch):
    monkeypatch.setenv('API_KEY', 'secret')
    headers = {'X-API-Key': 'wrong'}
    assert client.post('/workflow', json=body(), headers=headers).status_code == 401


def test_right_api_key_is_accepted(sample_rules, monkeypatch):
    monkeypatch.setenv('API_KEY', 'secret')
    headers = {'X-API-Key': 'secret'}
    assert client.post('/workflow', json=body(), headers=headers).status_code == 200


# Rate limit


def test_rate_limit_returns_429(sample_rules, monkeypatch):
    monkeypatch.setenv('RATE_LIMIT', '2/minute')
    codes = [client.post('/workflow', json=body()).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_invalid_rate_limit_stops_the_api_at_startup(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT', '60 per mins')
    # Entering TestClient(app) runs the startup (lifespan) code, which should refuse to start.
    with pytest.raises(RuntimeError, match='RATE_LIMIT'), TestClient(app):
        pass


def test_health_is_not_rate_limited(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT', '1/minute')
    codes = [client.get('/health').status_code for _ in range(3)]
    assert codes == [200, 200, 200]


# The demo path on ENG's real rules file


def demo_body():
    mock = json.loads(api.mock_path().read_text(encoding='utf-8'))
    return {'as_of': mock['as_of'], 'student_profile': mock['student_profile']}


def test_demo_dmv_task_is_blocked_by_proof_of_residency():
    workflow = client.post('/workflow', json=demo_body()).json()
    dmv = next(t for t in workflow['workflow'] if t['id'] == 'task_dmv_id')
    assert dmv['status'] == 'Blocked'
    assert dmv['next_action']['task_id'] == 'task_proof_of_residency'


def test_demo_path_round_trip_blocked_then_ready():
    # The Day 3 demo, stateless: each step sends back the profile the last answer returned.
    as_of = demo_body()['as_of']
    resolved = client.post('/tasks/task_dmv_id/resolve', json=demo_body()).json()
    profile = resolved['workflow']['student_profile']
    assert status_of(resolved['workflow'], 'task_proof_of_residency') == 'In Progress'
    request = {'as_of': as_of, 'student_profile': profile}
    done = client.post('/tasks/task_proof_of_residency/complete', json=request).json()
    assert status_of(done, 'task_dmv_id') == 'Ready'
    assert done['student_profile']['awaiting_reply'] == []
