"""FE 4 workflow failure behaviors in the actual app (email drafts: test_live_api.py)."""

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_streamlit import APP_PATH, FakeResponse, base_payload, values


@pytest.mark.parametrize('failure', ['timeout', 'http', 'invalid'])
def test_workflow_failure_hides_internal_details_and_retry_recovers(monkeypatch, failure):
    def get(*args, **kwargs):
        if failure == 'timeout':
            raise requests.Timeout('private backend details')
        if failure == 'http':
            raise requests.HTTPError('private backend details')
        return FakeResponse({'workflow': [{'id': 'broken'}]})

    monkeypatch.setattr(requests, 'get', get)
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert any('Could not load your workflow' in x for x in values(app.error))
    assert not any('private backend details' in x for x in values(app.error))
    assert len(app.tabs) == 0
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse(base_payload()))
    app.button[0].click().run()
    assert not app.exception
    assert len(app.tabs) == 5
