"""Check grounding, safe fallbacks and email draft behavior without a live model."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from httpx import Request
from openai import APITimeoutError, OpenAIError

from student_workflow.ai_day3 import CitationChoice, explain_task, generate_email
from student_workflow.contract import Blocker, NextAction, Source, StudentProfile, Task
from student_workflow.engine import resolve
from student_workflow.rules import load_rules


@pytest.fixture
def blocked_task():
    return Task(
        id='task_dmv_id',
        title='Apply for California REAL ID',
        status='Blocked',
        priority='Optional',
        missing_prerequisites=['task_proof_of_residency'],
        next_action=NextAction(
            task_id='task_proof_of_residency',
            text='Gather proof of residency.',
        ),
        blockers=[
            Blocker(
                type='timing', rule_id='timing', verification_status='verified',
                explanation='Wait until the dashboard date.',
            ),
            Blocker(
                type='document', rule_id='residency', verification_status='needs_verification',
                explanation='Gather residency evidence.',
            ),
            Blocker(
                type='document', rule_id='uncited', verification_status='needs_verification',
                explanation='Uncited detail.',
            ),
        ],
        sources=[
            Source(
                rule_id='timing', url='https://example.org/timing', verification_status='verified',
            ),
            Source(
                rule_id='residency', url='https://example.org/residency',
                verification_status='verified',
            ),
            Source(rule_id='other_task', url='https://example.org/other-task'),
        ],
    )


def test_valid_model_choice_only_reorders_grounded_citations(blocked_task):
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=CitationChoice(rule_ids=['residency']),
    )

    result = explain_task(blocked_task, high_risk=False, client=client, model='fake')

    assert result.outcome == 'explained'
    assert result.next_action == 'Gather proof of residency.'
    assert [item.source.rule_id for item in result.citations] == ['residency', 'timing']
    assert [item.verified for item in result.citations] == [False, True]
    assert 'lack a source' in result.message
    assert 'not verified' in result.message
    call = client.responses.parse.call_args.kwargs
    assert call['store'] is False
    assert json.loads(call['input']) == {
        'title': blocked_task.title,
        'blockers': [{'rule_id': 'timing', 'type': 'timing'},
                     {'rule_id': 'residency', 'type': 'document'}],
    }


@pytest.mark.parametrize('rule_ids', [
    ['residency', 'invented'], ['other_task'], ['uncited'], ['residency', 'residency'], [], None,
])
def test_invalid_or_missing_citations_preserve_the_engine_order(blocked_task, rule_ids):
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=CitationChoice(rule_ids=rule_ids) if rule_ids is not None else None,
    )

    result = explain_task(blocked_task, high_risk=False, client=client, model='fake')

    assert [item.source.rule_id for item in result.citations] == ['timing', 'residency']


@pytest.mark.parametrize('error', [
    OpenAIError('Service unavailable'),
    APITimeoutError(request=Request('POST', 'https://example.org/responses')),
])
def test_api_failure_preserves_the_engine_explanation(blocked_task, error):
    client = Mock()
    client.responses.parse.side_effect = error

    result = explain_task(blocked_task, high_risk=False, client=client, model='fake')

    assert result == explain_task(blocked_task, high_risk=False)


@pytest.mark.parametrize('risk, outcome', [(True, 'dso_referral'), (None, 'unavailable')])
def test_high_or_unknown_risk_stays_local(blocked_task, risk, outcome):
    client = Mock()

    result = explain_task(blocked_task, high_risk=risk, client=client, model='fake')

    assert result.outcome == outcome
    assert result.citations == []
    client.responses.parse.assert_not_called()


def test_email_draft_uses_placeholders_and_checklist_context(blocked_task):
    draft = generate_email(blocked_task)

    assert draft is not None
    assert draft.subject == 'Request for guidance: Apply for California REAL ID'
    assert 'Gather proof of residency.' in draft.body
    for placeholder in ('[Office or DSO]', '[Your Name]', '[Student ID]'):
        assert placeholder in draft.body
    assert 'Wait until' not in draft.body
    assert blocked_task.status == 'Blocked'


@pytest.mark.parametrize('update', [
    {'status': 'Ready'}, {'next_action': None}, {'missing_prerequisites': []},
])
def test_no_draft_without_an_actionable_prerequisite(blocked_task, update):
    assert generate_email(blocked_task.model_copy(update=update)) is None


def test_resolved_dmv_task_cites_its_actual_next_action():
    profile = StudentProfile(
        student_id='synthetic_demo',
        institution='Cosumnes River College',
        visa_type='F-1',
        arrival_date=date(2026, 8, 11),
        has_ssn=False,
        school_id='crc',
    )
    workflow = resolve(load_rules(), profile, date(2026, 8, 14))
    tasks = {task.id: task for task in workflow.workflow}
    task = tasks['task_dmv_id']
    prerequisite = tasks['task_proof_of_residency']
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=CitationChoice(rule_ids=['rule_california_real_id_residency']),
    )

    result = explain_task(
        task, prerequisite=prerequisite, high_risk=False, client=client, model='fake',
    )

    assert result.citations[0].source.rule_id == 'rule_california_real_id_residency'
    assert result.citations[0].blocker.explanation == task.next_action.text
    client.responses.parse.assert_called_once()
    assert 'synthetic_demo' not in client.responses.parse.call_args.kwargs['input']
    assert explain_task(task, prerequisite=task, high_risk=False).citations == []
    draft = generate_email(task, prerequisite=prerequisite)
    assert draft is not None
    assert prerequisite.title in draft.body
    assert generate_email(task, prerequisite=task) is None
