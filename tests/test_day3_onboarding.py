"""School picker uses the live directory contract without pretending POST exists."""

import pytest
import requests
from test_day3_frontend import select_dmv
from test_streamlit import FakeResponse, base_payload, run_dashboard, values

SCHOOLS = [{'school_id': 'crc', 'institution': 'Cosumnes River College',
            'city': 'Sacramento', 'state': 'CA', 'school_verified': False}]


def directory_app(monkeypatch, result=SCHOOLS):
    payload = base_payload()
    app = run_dashboard(monkeypatch, payload)
    calls = []

    def get(url, *, params=None, timeout):
        if url.endswith('/schools'):
            calls.append((params, timeout))
            if isinstance(result, Exception):
                raise result
            return FakeResponse(result)
        return FakeResponse(payload)

    monkeypatch.setattr(requests, 'get', get)
    return app, calls


def test_search_select_school_does_not_post_or_replace_current_workflow(monkeypatch):
    app, calls = directory_app(monkeypatch)
    posts = []
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: posts.append(a))
    select_dmv(app)
    app.checkbox[0].check().run()
    app.text_input(key='school_query').set_value('  Cosumnes  ').run()
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    assert not app.exception
    assert calls == [({'q': 'Cosumnes', 'limit': 20}, 10)]
    assert app.session_state['onboarding_draft']['school_id'] == 'crc'
    assert any('Not verified for your school' in x for x in values(app.warning))
    assert app.button(key='generate_workflow').disabled
    assert posts == []
    assert app.checkbox[0].value
    app.run()
    assert len(calls) == 1


def test_state_and_search_changes_clear_incompatible_school_selection(monkeypatch):
    app, calls = directory_app(monkeypatch)
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    app.text_input(key='school_query').set_value('another school').run()
    assert app.selectbox(key='onboarding_school').value is None
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    app.selectbox(key='onboarding_state').select('Other state (not supported)').run()
    assert any('California only' in v for v in values(app.info))
    assert 'onboarding_draft' not in app.session_state
    app.selectbox(key='onboarding_state').select('California').run()
    assert app.selectbox(key='onboarding_school').value is None
    assert len(calls) == 2


def test_school_no_results_offers_explicit_missing_school_path(monkeypatch):
    app, _ = directory_app(monkeypatch, [])
    app.button(key='search_schools').click().run()
    assert any('No schools found' in v for v in values(app.info))
    app.selectbox(key='onboarding_school').select('__not_listed').run()
    assert app.session_state['onboarding_draft']['school_id'] is None
    assert any('does not mean your school is ineligible' in v for v in values(app.info))


def test_selected_school_name_is_readable_outside_the_narrow_dropdown(monkeypatch):
    name = 'California Polytechnic State University, San Luis Obispo'
    app, _ = directory_app(monkeypatch, [{**SCHOOLS[0], 'institution': name}])
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    assert 'Selected school: ' + name in values(app.tabs[0].caption)


def test_cleared_arrival_date_does_not_crash_or_leave_a_stale_profile_draft(monkeypatch):
    app, _ = directory_app(monkeypatch)
    app.button(key='search_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    app.date_input(key='onboarding_arrival').set_value(None).run()
    assert not app.exception
    assert 'onboarding_draft' not in app.session_state
    assert any('Choose an arrival date' in v for v in values(app.info))


@pytest.mark.parametrize('result', [requests.Timeout('private details'),
                                 {'unexpected': 'not a school list'},
                                 [{**SCHOOLS[0], 'state': 'NY'}]])
def test_school_failures_retry_without_losing_documents(monkeypatch, result):
    app, calls = directory_app(monkeypatch, result)
    select_dmv(app)
    app.checkbox[0].check().run()
    app.button(key='search_schools').click().run()
    assert not app.exception
    assert any('Could not search schools' in v for v in values(app.error))
    assert not any('private details' in v for v in values(app.error))
    assert app.checkbox[0].value
    monkeypatch.setattr(requests, 'get', lambda url, **kw: FakeResponse(
        SCHOOLS if url.endswith('/schools') else base_payload()))
    app.button(key='retry_schools').click().run()
    app.selectbox(key='onboarding_school').select('crc').run()
    assert app.session_state['onboarding_draft']['school_id'] == 'crc'
    assert app.checkbox[0].value
    assert len(calls) == 1
