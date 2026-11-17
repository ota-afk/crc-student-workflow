"""Exercise the new visual frontend against controlled API responses."""

from copy import deepcopy
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_streamlit import FakeResponse, base_payload, values

from student_workflow import flyover_client

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'


def signed_in_app(app_path) -> AppTest:
    """Flyover past the demo sign-in (tested on its own in test_flyover_signin.py)."""
    app = AppTest.from_file(str(app_path), default_timeout=30)
    app.session_state['flyover_account'] = {'email': 'student@example.com'}
    return app.run()


def go_to(app: AppTest, page: str) -> AppTest:
    """Navigate with the header's Go to selector, as a student would."""
    return app.selectbox(key='flyover_goto').select(page).run()


def open_checklist(app: AppTest, task_id: str) -> AppTest:
    """The Checklist tab with task_id chosen in its own task selector."""
    go_to(app, 'checklist')
    return app.selectbox(key='flyover_checklist_pick').select(task_id).run()


def app_with(monkeypatch, payload=None):
    payload = deepcopy(payload or base_payload())
    def get(url, **kw):
        if url.endswith('/schools'):
            return FakeResponse([{'school_id': 'crc', 'institution': 'Cosumnes River College',
                'city': 'Sacramento', 'state': 'CA', 'school_verified': False}])
        return FakeResponse(payload)
    monkeypatch.setattr(requests, 'get', get)
    # These tests drive the page with a controlled payload, so the first load shows it as
    # given. The real fresh start (a POST with empty progress) is tested in test_flyover.py
    # and against the real API in test_flyover_live_api.py.
    monkeypatch.setattr(flyover_client, 'start_demo',
                        lambda api_url, profile, as_of: flyover_client.fetch_workflow(api_url))
    app = signed_in_app(APP)
    assert not app.exception
    return app


def test_profile_and_one_active_step_share_the_homepage(monkeypatch):
    app = app_with(monkeypatch)
    assert 'Profile setup' in values(app.subheader)
    assert 'Moving Forward (Workflow)' in values(app.subheader)
    assert len([b for b in app.button if b.key == 'flyover_checklist']) == 1
    assert app.selectbox(key='flyover_status').value == 'Ready'


def test_view_checklist_opens_the_checklist_tab_with_the_same_task(monkeypatch):
    app = app_with(monkeypatch)
    assert 'Before you take off' in values(app.subheader)  # same page as the workflow
    chosen = app.session_state['flyover_detail']
    app.button(key='flyover_checklist').click().run()
    assert not app.exception
    assert app.session_state['flyover_page'] == 'checklist'
    assert app.selectbox(key='flyover_checklist_pick').value == chosen
    assert app.button_group(key='flyover_tab').value == 'checklist'
    assert app.selectbox(key='flyover_goto').value == 'checklist'


def test_completion_keeps_the_task_and_offers_the_next_one(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] != 'Completed')
    task['status'] = 'Ready'
    updated = deepcopy(data)
    next(t for t in updated['workflow'] if t['id'] == task['id'])['status'] = 'Completed'
    updated['student_profile']['completed_tasks'].append(task['id'])
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(updated))
    app = app_with(monkeypatch, data)
    app.session_state['flyover_detail'] = task['id']
    app.run()
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert app.session_state['flyover_data']['student_profile']['completed_tasks'] == updated['student_profile']['completed_tasks']
    # The selected task stays; the next suggested one is offered, not switched to.
    assert app.session_state['flyover_detail'] == task['id']
    assert app.session_state['flyover_page'] == 'workflow'
    assert app.button(key='flyover_take_next')
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
    app = go_to(app_with(monkeypatch), 'handoff')  # its own destination now
    assert not app.exception
    assert app.session_state['flyover_page'] == 'handoff'
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
    app = go_to(app_with(monkeypatch), 'handoff')
    assert not app.exception
    assert app.session_state['flyover_page'] == 'handoff'
    app.button(key='flyover_settings').click().run()
    assert not app.exception
    app.toggle(key='flyover_motion_widget').set_value(True).run()
    # AppTest reruns the whole app for fragment widgets; reopen the dialog.
    app.button(key='flyover_settings').click().run()
    app.button(key='flyover_settings_done').click().run()
    assert app.session_state['flyover_reduce_motion'] is True
    go_to(app, 'workflow')
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
    assert 'flyover_take_next' not in [b.key for b in app.button]  # nothing left to offer
    # The finished task stays selected, read-only, with Reopen task.
    assert app.selectbox(key='flyover_status').disabled
    assert app.selectbox(key='flyover_status').value == 'Completed'
    assert app.button(key='flyover_status:reopen')


def test_in_progress_saves_without_advancing_or_celebrating(monkeypatch):
    data = base_payload()
    task = next(t for t in data['workflow'] if t['status'] != 'Completed')
    updated = deepcopy(data)
    next(t for t in updated['workflow'] if t['id'] == task['id'])['status'] = 'In Progress'
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(updated))
    app = app_with(monkeypatch, data)
    app.session_state['flyover_detail'] = task['id']
    app.run()
    app.selectbox(key='flyover_status').select('In Progress').run()
    assert not app.exception
    assert app.session_state['flyover_detail'] == task['id']
    assert app.selectbox(key='flyover_status').value == 'In Progress'
    assert '<div class="flyover-confetti"' not in str([e.value for e in app.get('html')])


def test_unconfirmed_completion_does_not_advance_or_celebrate(monkeypatch):
    data = base_payload()
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: FakeResponse(data))
    app = app_with(monkeypatch, data)
    active = app.session_state['flyover_detail']
    app.selectbox(key='flyover_status').select('Completed').run()
    assert not app.exception
    assert app.session_state['flyover_detail'] == active
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
    assert not app.exception
    assert 'Readiness' in values(app.subheader)
    assert 'Before you take off' in values(app.subheader)
    keys = [b.key for b in app.button if b.key and b.key.startswith('fly_pre:')]
    # Every task appears once, in exactly one of the two tables.
    assert sorted(k.split(':', 2)[2] for k in keys) == sorted(t['id'] for t in data['workflow'])
    groups = {k.split(':', 2)[2]: k.split(':')[1] for k in keys}
    for task in data['workflow']:
        # Completed tasks are history; every other status (In Progress too) is still ahead.
        assert groups[task['id']] == ('done' if task['status'] == 'Completed' else 'takeoff')
    prereq = next(t for t in data['workflow'] if t['id'] == blocked['prerequisites'][0])
    assert app.button(key=f'fly_pre:takeoff:{blocked["id"]}').label == prereq['title']


def test_prerequisite_opens_documents_and_sources_and_advances_quote(monkeypatch):
    data, blocked = _live_like(base_payload())
    app = app_with(monkeypatch, data)
    before = app.session_state['flyover_quote'] if 'flyover_quote' in app.session_state else -1  # noqa: SIM401
    app.button(key=f'fly_pre:takeoff:{blocked["id"]}').click().run()
    assert not app.exception
    assert app.session_state['flyover_quote'] == before + 1
    html_text = str([e.value for e in app.get('html')])
    assert 'Needs first' in html_text and 'Our sources' in html_text
    assert 'Not verified' in html_text


def test_airshow_handoff_is_labeled_template_and_clears_on_change(monkeypatch):
    app = go_to(app_with(monkeypatch), 'handoff')
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
    for args, page in [(('checklist', 'task_x'), 'checklist'), (('readiness',), 'workflow'),
                       (('assistant',), 'handoff'), (('home',), 'workflow'),
                       (('updates',), 'updates'), (('nowhere',), 'workflow')]:
        flyover.go(*args)
        assert (state['flyover_page'], state['flyover_scroll']) == (page, 'top')
    assert state['flyover_detail'] == 'task_x'  # carried, not a widget key
    monkeypatch.undo()


def test_scroll_request_is_used_once(monkeypatch):
    app = app_with(monkeypatch)
    app.button(key='flyover_checklist').click().run()
    assert not app.exception
    assert 'flyover_scroll' not in app.session_state  # consumed, so later reruns stay put


def test_reduce_motion_renders_the_flight_without_scrubbing(monkeypatch):
    app = app_with(monkeypatch)
    app.session_state['flyover_reduce_motion'] = True
    go_to(app, 'handoff')
    html_text = str([e.value for e in app.get('html')])
    assert 'fly-runway is-static' in html_text
    assert 'animation:none' in html_text


def _airshow_with_goal(monkeypatch):
    app = go_to(app_with(monkeypatch), 'handoff')
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


def test_redraws_do_not_dim_the_page():
    css = (Path(__file__).resolve().parents[1] / 'app/assets/flyover/style.css').read_text()
    assert '.stApp [data-stale="true"] { opacity:1!important; transition:none!important; }' in css


def test_generate_shows_a_building_spinner(monkeypatch):
    import contextlib

    import streamlit
    spinning, seen = [], []

    @contextlib.contextmanager
    def spinner(text, **kwargs):
        spinning.append(text)
        yield
        spinning.pop()

    monkeypatch.setattr(streamlit, 'spinner', spinner)
    payload = base_payload()
    payload['student_profile']['completed_tasks'] = []
    payload['student_profile']['awaiting_reply'] = []
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: seen.append(list(spinning))
                        or FakeResponse(payload))
    app = app_with(monkeypatch, payload)
    next(b for b in app.button if b.label == 'Generate workflow').click().run()
    assert not app.exception
    assert ['Building your workflow…'] in seen


# ---- Guide Part 1: navigation, task selection and status edits, against the real API ----

I94 = 'task_i94_retrieval'
DMV = 'task_dmv_id'
RESIDENCY = 'task_proof_of_residency'
DMV_TITLE = 'Apply for a California REAL ID card'


@pytest.fixture
def live(monkeypatch):
    """requests.get/post go to the FastAPI app in process (test_live_api's Bridge)."""
    from test_live_api import KEY, Bridge
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def status_of(app: AppTest, task_id: str) -> str:
    return next(t['status'] for t in app.session_state['flyover_data']['workflow']
                if t['id'] == task_id)


def rows(app: AppTest, group: str) -> list[str]:
    """Task IDs in a readiness table: 'takeoff' (still ahead) or 'done' (completed)."""
    return [b.key.split(':', 2)[2] for b in app.button
            if b.key and b.key.startswith(f'fly_pre:{group}:')]


def counter(app: AppTest) -> str:
    import re
    page = ' '.join(str(e.value) for e in app.get('html'))
    return re.search(r'<b>(\d+ of \d+ steps complete · \d+ still ahead)</b>', page).group(1)


def choose(app: AppTest, task_id: str) -> AppTest:
    return app.selectbox(key='flyover_choose').select(task_id).run()


def test_one_student_journey(live, monkeypatch):
    app = signed_in_app(APP)
    assert counter(app) == '0 of 8 steps complete · 8 still ahead'
    posts = len(live.posts())

    # Browse the blocked REAL ID task: it is explained, and nothing is saved or animated.
    choose(app, DMV)
    assert not app.exception
    assert app.session_state['flyover_detail'] == DMV
    gate = app.selectbox(key='flyover_status')
    assert (gate.value, gate.disabled) == ('Blocked', True)
    assert ('Blocked until you finish: Gather residency evidence for California REAL ID'
            in values(app.caption))
    assert DMV in rows(app, 'takeoff')
    assert len(live.posts()) == posts
    assert 'class="fly-board"' not in str([e.value for e in app.get('html')])

    # Switch to I-94 and set it to In Progress from its own row: it stays in the list.
    choose(app, I94)
    app.selectbox(key=f'fly_status:takeoff:{I94}').select('In Progress').run()
    assert not app.exception
    assert status_of(app, I94) == 'In Progress'
    assert I94 in rows(app, 'takeoff')
    assert counter(app) == '0 of 8 steps complete · 8 still ahead'
    assert app.session_state['flyover_detail'] == I94
    assert app.session_state['flyover_page'] == 'workflow'

    # Complete it from the gate: history, counter, and the same task stays selected.
    app.selectbox(key='flyover_status').select('Completed').run()
    assert status_of(app, I94) == 'Completed'
    assert I94 in rows(app, 'done') and I94 not in rows(app, 'takeoff')
    assert counter(app) == '1 of 8 steps complete · 7 still ahead'
    assert app.session_state['flyover_detail'] == I94
    assert app.button(key='flyover_take_next')  # offered, not taken

    # Reopen it: the API decides the status, at the workflow's own date.
    app.button(key='flyover_status:reopen').click().run()
    assert not app.exception
    assert status_of(app, I94) == 'Ready'
    assert I94 in rows(app, 'takeoff') and I94 not in rows(app, 'done')
    assert counter(app) == '0 of 8 steps complete · 8 still ahead'
    assert any(v.startswith('Retrieve your I-94 record reopened') for v in values(app.success))
    path, body = live.posts()[-1]
    assert path == '/workflow' and body['as_of'] == '2026-08-14'
    assert I94 not in body['student_profile']['completed_tasks']

    # A failed save keeps the previous status on screen.
    def refuse(*args, **kwargs):
        raise requests.Timeout('private detail')
    monkeypatch.setattr(requests, 'post', refuse)
    app.selectbox(key='flyover_status').select('In Progress').run()
    assert not app.exception
    assert status_of(app, I94) == 'Ready'
    assert app.selectbox(key='flyover_status').value == 'Ready'
    assert app.selectbox(key=f'fly_status:takeoff:{I94}').value == 'Ready'
    assert any('progress has been kept' in v for v in values(app.error))
    assert not any('private detail' in v for v in values(app.error))
    assert app.session_state['flyover_detail'] == I94


def test_reopening_a_prerequisite_names_the_completed_task_that_needs_it(live):
    app = signed_in_app(APP)
    for task_id in (RESIDENCY, DMV):  # residency unblocks REAL ID; complete both
        choose(app, task_id)
        app.selectbox(key='flyover_status').select('Completed').run()
        assert status_of(app, task_id) == 'Completed'
    choose(app, RESIDENCY)
    posts = len(live.posts())
    app.button(key='flyover_status:reopen').click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) == 'Completed'
    assert len(live.posts()) == posts  # refused before any request
    assert any(DMV_TITLE in v and 'Reopen' in v for v in values(app.warning))
    # Linked, so the student can reopen REAL ID first.
    app.button(key=f'flyover_reopen_dep:{DMV}').click().run()
    assert app.session_state['flyover_detail'] == DMV
    app.button(key='flyover_status:reopen').click().run()
    assert status_of(app, DMV) != 'Completed'


def test_tabs_and_go_to_share_one_page_and_one_task(live):
    app = choose(signed_in_app(APP), DMV)
    assert [o for o in app.selectbox(key='flyover_goto').options] == [
        'Workflow and readiness', 'Checklist', 'Alerts', 'Profile', 'Office handoff',
        'Updates and credits']
    app.button_group(key='flyover_tab').set_value('checklist').run()
    assert app.session_state['flyover_page'] == 'checklist'
    assert app.selectbox(key='flyover_goto').value == 'checklist'
    assert app.selectbox(key='flyover_checklist_pick').value == DMV
    go_to(app, 'alerts')
    assert app.button_group(key='flyover_tab').value == 'alerts'
    go_to(app, 'profile')
    assert app.button_group(key='flyover_tab').value is None  # not one of the tabs
    for page, heading in [('handoff', 'Handoff for your visit'),
                          ('updates', 'Updates and credits'), ('alerts', 'Alerts')]:
        go_to(app, page)
        assert not app.exception and heading in values(app.subheader)
    go_to(app, 'workflow')
    assert app.selectbox(key='flyover_choose').value == DMV  # kept across every page


def test_checklist_status_saves_against_its_task_and_stays_on_the_tab(live):
    app = open_checklist(signed_in_app(APP), I94)
    app.selectbox(key='flyover_checklist_status').select('In Progress').run()
    assert not app.exception
    assert status_of(app, I94) == 'In Progress'
    assert app.session_state['flyover_page'] == 'checklist'
    assert app.selectbox(key='flyover_checklist_pick').value == I94
    # The row and the Checklist control have different widget keys for the same task.
    go_to(app, 'workflow')
    assert app.selectbox(key=f'fly_status:takeoff:{I94}').value == 'In Progress'


def test_blocked_row_offers_its_checklist_and_the_blocker_action(live):
    app = signed_in_app(APP)
    app.button(key=f'fly_status:takeoff:{DMV}:open').click().run()
    assert app.session_state['flyover_page'] == 'checklist'
    assert app.selectbox(key='flyover_checklist_pick').value == DMV
    go_to(app, 'workflow')
    app.button(key=f'flyover_resolve:{DMV}:fly_status:takeoff:{DMV}').click().run()
    assert status_of(app, RESIDENCY) == 'In Progress'


def test_reopen_posts_the_profile_without_that_task(monkeypatch):
    from student_workflow import flyover_client as client
    data = base_payload()
    done = next(t for t in data['workflow'] if t['status'] == 'Completed')
    data['student_profile'].setdefault('awaiting_reply', []).append(done['id'])
    sent = {}

    def post(url, json, **kwargs):
        sent.update(url=url, body=json)
        return FakeResponse(base_payload())

    monkeypatch.setattr(requests, 'post', post)
    client.reopen_task('http://api', data, done['id'])
    assert sent['url'] == 'http://api/workflow'
    assert sent['body']['as_of'] == data['as_of']
    profile = sent['body']['student_profile']
    assert done['id'] not in profile['completed_tasks'] + profile['awaiting_reply']
    assert done['id'] in data['student_profile']['completed_tasks']  # the original is a copy
