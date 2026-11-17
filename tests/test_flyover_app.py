"""Exercise the new visual frontend against controlled API responses."""

from copy import deepcopy
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest
from test_streamlit import FakeResponse, base_payload, values

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'


def app_with(monkeypatch, payload=None):
    payload = deepcopy(payload or base_payload())
    def get(url, **kw):
        if url.endswith('/schools'):
            return FakeResponse([{'school_id': 'crc', 'institution': 'Cosumnes River College',
                'city': 'Sacramento', 'state': 'CA', 'school_verified': False}])
        return FakeResponse(payload)
    monkeypatch.setattr(requests, 'get', get)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    return app


def test_profile_and_one_active_step_share_the_homepage(monkeypatch):
    app = app_with(monkeypatch)
    assert 'Profile setup' in values(app.subheader)
    assert 'Moving Forward (Workflow)' in values(app.subheader)
    assert len([b for b in app.button if b.key == 'flyover_checklist']) == 1
    assert app.selectbox(key='flyover_status').value == 'Ready'


def test_checklist_and_next_open_readiness(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_checklist').click().run()
    assert not app.exception
    assert app.session_state['flyover_page'] == 'readiness'
    assert 'Before you take off' in values(app.subheader)


def test_completed_step_advances_using_returned_backend_state(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] != 'Completed')
    task['status'] = 'Ready'
    updated = deepcopy(data)
    next(t for t in updated['workflow'] if t['id'] == task['id'])['status'] = 'Completed'
    updated['student_profile']['completed_tasks'].append(task['id'])
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(updated))
    app = app_with(monkeypatch, data)
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert app.session_state['flyover_data']['student_profile']['completed_tasks'] == updated['student_profile']['completed_tasks']
    assert app.session_state['flyover_active_id'] != task['id']
    assert any('completed' in text.lower() for text in values(app.success))
    assert '<div class="flyover-confetti"' in str([e.value for e in app.get('html')])
    app.run()
    assert '<div class="flyover-confetti"' not in str([e.value for e in app.get('html')])


def test_failed_status_update_keeps_current_workflow(monkeypatch):
    def fail(*a, **kw):
        raise requests.Timeout('private internal detail')
    monkeypatch.setattr(requests, 'post', fail)
    app = app_with(monkeypatch)
    before = deepcopy(app.session_state['flyover_data'])
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert app.session_state['flyover_data'] == before
    assert app.selectbox(key='flyover_status').value == 'Ready'
    assert '<div class="flyover-confetti"' not in str([e.value for e in app.get('html')])
    assert any('progress has been kept' in text for text in values(app.error))
    assert not any('private internal' in text for text in values(app.error))


def test_airshow_section_is_the_template_handoff_only(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_next').click().run()  # page 2: Airshow's handoff
    assert not app.exception
    assert app.session_state['flyover_page'] == 'readiness'
    assert 'Handoff for your visit' in values(app.subheader)
    assert 'Ask Airshow' not in values(app.subheader)  # the live chat lives in the dropdown
    # The handoff is still a page template, and says so.
    assert any('not by AI' in text for text in values(app.info))


def test_empty_workflow_never_implies_readiness(monkeypatch):
    data = base_payload()
    data['workflow'] = []
    app = app_with(monkeypatch, data)
    assert any('No workflow steps' in text for text in values(app.info))
    assert not any('complete' in text.lower() for text in values(app.success))


def test_profile_reset_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError('No request before reset confirmation')))
    app = app_with(monkeypatch)
    before = deepcopy(app.session_state['flyover_data'])
    next(button for button in app.button if button.label == 'Generate workflow').click().run()
    assert not app.exception
    assert app.session_state['flyover_data'] == before
    assert any('Confirm “Start fresh”' in text for text in values(app.warning))


def test_next_navigation_and_motion_settings(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_next').click().run()
    assert not app.exception
    assert app.session_state['flyover_page'] == 'readiness'
    app.button(key='flyover_settings').click().run()
    assert not app.exception
    app.toggle(key='flyover_motion_widget').set_value(True).run()
    # AppTest reruns the whole app for fragment widgets; reopen the dialog.
    app.button(key='flyover_settings').click().run()
    app.button(key='flyover_settings_done').click().run()
    assert app.session_state['flyover_reduce_motion'] is True
    app.button(key='flyover_back').click().run()
    assert app.session_state['flyover_reduce_motion'] is True


def test_profile_reset_confirmation_is_consumed_after_success(monkeypatch):
    fresh = base_payload()
    fresh['student_profile']['completed_tasks'] = []
    fresh['student_profile']['awaiting_reply'] = []
    for task in fresh['workflow']:
        if task['status'] == 'Completed':
            task['status'] = 'Ready'
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(fresh))
    app = app_with(monkeypatch)
    # Form values reach the server together with the submit action.
    app.checkbox(key='flyover_new_profile').check()
    next(button for button in app.button if button.label == 'Generate workflow').click().run()
    assert not app.exception
    assert app.session_state['flyover_data']['student_profile']['completed_tasks'] == []
    assert app.checkbox(key='flyover_new_profile').value is False


def test_final_completion_finishes_map_and_has_no_next_task(monkeypatch):
    data = base_payload()
    for task in data['workflow'][:-1]:
        task['status'] = 'Completed'
    data['workflow'][-1]['status'] = 'Ready'
    updated = deepcopy(data)
    updated['workflow'][-1]['status'] = 'Completed'
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(updated))
    app = app_with(monkeypatch, data)
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert any('3 of 3 route pieces' in text for text in values(app.caption))
    assert any('Your checklist is complete' in text for text in values(app.success))
    assert not any(widget.key == 'flyover_status' for widget in app.selectbox)


def test_in_progress_saves_without_advancing_or_celebrating(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] != 'Completed')
    updated = deepcopy(data)
    next(t for t in updated['workflow'] if t['id'] == task['id'])['status'] = 'In Progress'
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(updated))
    app = app_with(monkeypatch, data)
    app.selectbox(key='flyover_status').select('In Progress').run()
    assert not app.exception
    assert app.session_state['flyover_active_id'] == task['id']
    assert app.selectbox(key='flyover_status').value == 'In Progress'
    assert '<div class="flyover-confetti"' not in str([e.value for e in app.get('html')])


def test_unconfirmed_completion_does_not_advance_or_celebrate(monkeypatch):
    data = base_payload()
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(data))
    app = app_with(monkeypatch, data)
    active = app.session_state['flyover_active_id']
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert app.session_state['flyover_active_id'] == active
    assert app.selectbox(key='flyover_status').value == 'Ready'
    assert '<div class="flyover-confetti"' not in str([e.value for e in app.get('html')])


def _live_like(payload):
    """The mock lacks prerequisites; give the DMV step one, as the live engine does."""
    data = deepcopy(payload)
    ids = [t['id'] for t in data['workflow']]
    blocked = next(t for t in data['workflow'] if t['status'] == 'Blocked')
    blocked['prerequisites'] = [i for i in ids if i != blocked['id']][:1]
    return data, blocked


def test_readiness_tables_put_task_status_and_prerequisite_in_rows(monkeypatch):
    data, blocked = _live_like(base_payload())
    app = app_with(monkeypatch, data)
    app.button(key='flyover_next').click().run()
    assert not app.exception
    assert 'Readiness' in values(app.subheader)
    assert 'Before you take off' in values(app.subheader)
    keys = [b.key for b in app.button if b.key and b.key.startswith('fly_pre:')]
    # Every task appears once, in exactly one of the two tables.
    assert sorted(k.split(':', 2)[2] for k in keys) == sorted(t['id'] for t in data['workflow'])
    prereq = next(t for t in data['workflow'] if t['id'] == blocked['prerequisites'][0])
    assert app.button(key=f'fly_pre:takeoff:{blocked["id"]}').label == prereq['title']


def test_prerequisite_opens_documents_and_sources_and_advances_quote(monkeypatch):
    data, blocked = _live_like(base_payload())
    app = app_with(monkeypatch, data)
    app.button(key='flyover_next').click().run()
    before = app.session_state['flyover_quote'] if 'flyover_quote' in app.session_state else -1  # noqa: SIM401
    app.button(key=f'fly_pre:takeoff:{blocked["id"]}').click().run()
    assert not app.exception
    assert app.session_state['flyover_quote'] == before + 1
    html_text = str([e.value for e in app.get('html')])
    assert 'Needs first' in html_text and 'Our sources' in html_text
    assert 'Not verified' in html_text


def test_airshow_handoff_is_labeled_template_and_clears_on_change(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_next').click().run()  # page 2: Airshow's handoff
    assert app.button(key='flyover_prepare_handoff').disabled
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    assert not app.exception
    handoff = app.session_state['flyover_handoff']
    assert handoff['title'] == 'Handoff for your DMV clerk'
    assert any(h == 'Questions to ask' for h, _ in handoff['sections'])
    html_text = str([e.value for e in app.get('html')])
    assert 'Not verified' in html_text and 'not by AI' in html_text
    app.selectbox(key='flyover_pro').select('Bank officer').run()
    assert 'flyover_handoff' not in app.session_state


def test_navigation_requests_a_scroll_to_where_the_click_points(monkeypatch):
    from student_workflow import flyover
    state = {}
    monkeypatch.setattr(flyover.st, 'session_state', state)
    for args, target in [(('readiness', 'task_x'), 'checklist'), (('readiness',), 'top'),
                         (('assistant',), 'airshow'), (('home',), 'top')]:
        flyover.go(*args)
        assert state['flyover_scroll'] == target
    monkeypatch.undo()


def test_scroll_request_is_used_once(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_checklist').click().run()
    assert not app.exception
    assert 'flyover_scroll' not in app.session_state  # consumed, so later reruns stay put


def test_reduce_motion_renders_the_flight_without_scrubbing(monkeypatch):
    app = app_with(monkeypatch)
    app.session_state['flyover_reduce_motion'] = True
    app.button(key='flyover_next').click().run()
    html_text = str([e.value for e in app.get('html')])
    assert 'fly-runway is-static' in html_text
    assert 'animation:none' in html_text


def _airshow_with_goal(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_next').click().run()  # page 2: Airshow's handoff
    app.text_area(key='flyover_goal').input('Ask about my enrollment letter').run()
    return app


def test_only_another_office_shows_the_office_name_field(monkeypatch):
    app = _airshow_with_goal(monkeypatch)
    assert not [w for w in app.text_input if w.key == 'flyover_office']
    app.selectbox(key='flyover_pro').select('Another office').run()
    assert [w for w in app.text_input if w.key == 'flyover_office']


def test_another_office_needs_a_name_before_generating(monkeypatch):
    app = _airshow_with_goal(monkeypatch)
    app.selectbox(key='flyover_pro').select('Another office').run()
    assert app.button(key='flyover_prepare_handoff').disabled
    app.text_input(key='flyover_office').input('   ').run()
    assert app.button(key='flyover_prepare_handoff').disabled


def test_office_name_titles_the_handoff_and_keeps_the_generic_questions(monkeypatch):
    app = _airshow_with_goal(monkeypatch)
    app.selectbox(key='flyover_pro').select('Another office').run()
    app.text_input(key='flyover_office').input('  Student   services desk ').run()
    app.button(key='flyover_prepare_handoff').click().run()
    assert not app.exception
    handoff = app.session_state['flyover_handoff']
    assert handoff['title'] == 'Handoff for Student services desk'
    questions = dict(handoff['sections'])['Questions to ask']
    assert 'Which documents should I bring?' in questions


def test_switching_to_a_preset_clears_the_office_name_and_handoff(monkeypatch):
    app = _airshow_with_goal(monkeypatch)
    app.selectbox(key='flyover_pro').select('Another office').run()
    app.text_input(key='flyover_office').input('Housing office').run()
    app.button(key='flyover_prepare_handoff').click().run()
    app.selectbox(key='flyover_pro').select('Bank officer').run()
    assert 'flyover_handoff' not in app.session_state
    assert 'flyover_office' not in app.session_state


def test_typed_office_name_stays_literal_in_both_exports():
    from student_workflow.flyover import _handoff_text
    doc = {'title': 'Handoff for <b>*Desk*</b> #1', 'sections': [('What I’m here to do', ['F-1 (DSO)'])]}
    markdown = _handoff_text(doc, markdown=True)
    assert '# Handoff for \\<b\\>\\*Desk\\*\\</b\\> \\#1' in markdown
    assert 'F-1 (DSO)' in markdown  # ordinary punctuation is not escaped
    assert 'Handoff for <b>*Desk*</b> #1' in _handoff_text(doc, markdown=False)


def test_office_name_is_html_escaped_on_the_page(monkeypatch):
    app = _airshow_with_goal(monkeypatch)
    app.selectbox(key='flyover_pro').select('Another office').run()
    app.text_input(key='flyover_office').input('<script>x</script> office').run()
    app.button(key='flyover_prepare_handoff').click().run()
    html_text = str([e.value for e in app.get('html')])
    assert '<script>x</script>' not in html_text
    assert '&lt;script&gt;' in html_text
