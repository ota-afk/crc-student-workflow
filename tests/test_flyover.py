"""Flyover preserves backend authority while presenting sequential progress."""

from copy import deepcopy
from itertools import pairwise

import pytest
import requests
from test_streamlit import FakeResponse, base_payload

from student_workflow.flyover_client import (
    ask_airshow,
    change_status,
    fetch_workflow,
    generate_workflow,
    resolve_blocker,
)
from student_workflow.flyover_state import active_task, map_piece_count


def test_initial_request_sends_configured_api_key(monkeypatch):
    calls = []
    monkeypatch.setenv('API_KEY', 'test-only')
    monkeypatch.setattr(requests, 'get', lambda url, **kw: (
        calls.append((url, kw)) or FakeResponse(base_payload())))
    assert fetch_workflow('http://api/')['schema_version'] == '1.0'
    assert calls == [('http://api/workflow', {'headers': {'X-API-Key': 'test-only'}, 'timeout': 10})]


def test_completion_uses_backend_and_returns_its_new_workflow(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] == 'Ready')
    updated = deepcopy(data)
    next(t for t in updated['workflow'] if t['id'] == task['id'])['status'] = 'Completed'
    updated['student_profile']['completed_tasks'].append(task['id'])
    calls = []
    monkeypatch.setattr(requests, 'post', lambda url, **kw: (
        calls.append((url, kw)) or FakeResponse(updated)))
    result = change_status('http://api', data, task['id'], 'Completed')
    assert result['student_profile']['completed_tasks'] == updated['student_profile']['completed_tasks']
    assert calls[0][0] == f'http://api/tasks/{task["id"]}/complete'
    assert calls[0][1]['json']['student_profile'] == data['student_profile']


def test_blocked_task_cannot_be_completed_without_calling_server(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] == 'Blocked')
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: pytest.fail('must not call API'))
    with pytest.raises(ValueError, match='blocked'):
        change_status('http://api', data, task['id'], 'Completed')


def test_waiting_on_office_uses_a_copy_and_does_not_duplicate_progress(monkeypatch):
    data = base_payload()
    before = deepcopy(data)
    task = next(t for t in data['workflow'] if t['status'] == 'Ready')
    calls = []
    monkeypatch.setattr(requests, 'post', lambda url, **kw: (
        calls.append(kw['json']) or FakeResponse(data)))
    change_status('http://api', data, task['id'], 'In Progress')
    assert calls[0]['student_profile']['awaiting_reply'] == [task['id']]
    assert data == before


def test_failed_update_does_not_mutate_current_data(monkeypatch):
    data = base_payload()
    before = deepcopy(data)
    task = next(t for t in data['workflow'] if t['status'] == 'Ready')
    def fail(*a, **kw):
        raise requests.Timeout('private error')
    monkeypatch.setattr(requests, 'post', fail)
    with pytest.raises(requests.Timeout):
        change_status('http://api', data, task['id'], 'In Progress')
    assert data == before


def test_invalid_response_is_rejected(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse({'workflow': []}))
    with pytest.raises(ValueError):
        fetch_workflow('http://api')


def test_new_profile_drops_old_progress_and_lets_api_choose_today(monkeypatch):
    profile = base_payload()['student_profile']
    calls = []
    monkeypatch.setattr(requests, 'post', lambda url, **kw: (
        calls.append(kw['json']) or FakeResponse(base_payload())))
    generate_workflow('http://api', profile, {'school_id': 'crc', 'institution': 'CRC',
        'visa_type': 'F-1', 'arrival_date': '2026-11-17', 'has_ssn': True})
    assert 'as_of' not in calls[0]
    assert calls[0]['student_profile']['completed_tasks'] == []
    assert calls[0]['student_profile']['awaiting_reply'] == []
    assert calls[0]['student_profile']['has_ssn'] is True


@pytest.mark.parametrize(('done', 'total', 'pieces'), [
    (0, 0, 0), (0, 8, 0), (1, 8, 1), (3, 8, 1), (4, 8, 2), (7, 8, 2), (8, 8, 3),
    (0, 1, 0), (1, 1, 3),
])
def test_map_assembles_at_first_half_and_final_completion(done, total, pieces):
    assert map_piece_count(done, total) == pieces


def test_active_task_skips_completed_and_retains_blocked_steps():
    tasks = [{'id': 'a', 'status': 'Completed'}, {'id': 'b', 'status': 'Blocked'},
             {'id': 'c', 'status': 'Ready'}]
    assert active_task(tasks)['id'] == 'b'
    assert active_task([]) is None
    assert active_task([tasks[0]]) is None


def test_map_progress_increases_on_every_completion():
    from student_workflow.flyover_state import map_progress
    progress = [map_progress(done, 8) for done in range(9)]
    assert progress[0] == 0
    assert progress[1] == 1
    assert progress[4] == 2
    assert progress[8] == 3
    assert all(a < b for a, b in pairwise(progress))
    assert map_progress(0, 0) == 0
    assert map_progress(1, 1) == 3


def test_resolve_sends_profile_date_and_key_and_returns_the_draft(monkeypatch):
    data = base_payload()
    calls = []
    monkeypatch.setenv('API_KEY', 'test-only')
    monkeypatch.setattr(requests, 'post', lambda url, **kw: calls.append((url, kw)) or FakeResponse(
        {'workflow': base_payload(), 'email_draft': {'subject': 'Hello', 'body': 'Body'}}))
    workflow, draft = resolve_blocker('http://api/', data, 'task_dmv_id')
    (url, kw), = calls
    assert url == 'http://api/tasks/task_dmv_id/resolve'
    assert kw['json'] == {'student_profile': data['student_profile'], 'as_of': data['as_of']}
    assert kw['headers'] == {'X-API-Key': 'test-only'}
    assert draft == {'subject': 'Hello', 'body': 'Body'}
    assert workflow['workflow']


def test_airshow_sends_the_workflow_date_and_only_assistant_fields(monkeypatch):
    data = base_payload()
    calls = []
    monkeypatch.setattr(requests, 'post', lambda url, **kw: calls.append((url, kw)) or FakeResponse(
        {'answer': 'Task status: Blocked.', 'steps': [], 'sources': [], 'verified': False,
         'contact': None, 'task_id': 'task_dmv_id', 'is_mock': False}))
    answer = ask_airshow('http://api', data, '  Why is my ID blocked?  ', 'task_dmv_id')
    (url, kw), = calls
    assert url == 'http://api/assistant'
    assert kw['timeout'] == 10
    assert kw['json']['question'] == 'Why is my ID blocked?'
    assert kw['json']['as_of'] == data['as_of']
    # POST /assistant rejects these, and they must never leave the dashboard.
    assert 'student_id' not in kw['json']['student_profile']
    assert 'school_verified' not in kw['json']['student_profile']
    assert answer['answer'] == 'Task status: Blocked.'


def test_invalid_assistant_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse({'answer': 123}))
    with pytest.raises(ValueError):
        ask_airshow('http://api', base_payload(), 'What next?', None)


def test_airshow_sends_page_context_only_when_given(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, 'post', lambda url, **kw: calls.append(kw['json']) or FakeResponse(
        {'answer': 'ok', 'steps': [], 'sources': [], 'verified': False, 'contact': None,
         'task_id': None, 'is_mock': False}))
    ask_airshow('http://api', base_payload(), 'Hi?', None, 'journey')
    ask_airshow('http://api', base_payload(), 'Hi?', None)
    assert calls[0]['page_context'] == 'journey'
    assert 'page_context' not in calls[1]  # older APIs never see the key
