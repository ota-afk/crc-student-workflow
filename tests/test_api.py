from fastapi.testclient import TestClient

from student_workflow.api import app

client = TestClient(app)


def test_health():
    assert client.get('/health').json() == {'status': 'ok'}


def test_workflow_serves_mock(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'true')
    response = client.get('/workflow')
    assert response.status_code == 200
    assert response.json()['schema_version'] == '1.0'


def test_live_engine_not_ready(monkeypatch):
    # Day 3: replace this test when the live engine exists
    monkeypatch.setenv('USE_MOCK', 'false')
    assert client.get('/workflow').status_code == 501
