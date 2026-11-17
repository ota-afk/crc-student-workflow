"""Flyover against the real API (in process): resolve, mark done, then ask Airshow.

requests.get/post go to the FastAPI app through test_live_api's Bridge, so these tests check
Flyover and the contract together with ENG's real rules. Only the model's intent pick is
faked, so nothing leaves the machine and no OpenAI key is needed.
"""

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest
from test_flyover_app import signed_in_app
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow import assistant
from student_workflow.ai_assistant import IntentResult

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'
DMV = 'task_dmv_id'
RESIDENCY = 'task_proof_of_residency'


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv('USE_MOCK', 'false')
    monkeypatch.setenv('RATE_LIMIT', '1000/minute')
    monkeypatch.setenv('API_KEY', KEY)
    monkeypatch.setenv('API_URL', 'http://localhost:8000')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    # The one faked piece: the model always picks the DMV task.
    monkeypatch.setattr(assistant, 'map_intent', lambda *a, **k: IntentResult(
        outcome='matched', task_id=DMV))
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def status_of(app: AppTest, task_id: str) -> str:
    return next(t['status'] for t in app.session_state['flyover_data']['workflow']
                if t['id'] == task_id)


def open_checklist(app: AppTest, task_id: str) -> AppTest:
    app.button(key='flyover_next').click().run()  # page 2: readiness and the checklist
    return app.selectbox(key='flyover_detail').select(task_id).run()


def ask(app: AppTest, question: str) -> str:
    """Ask in the AI Help dropdown and return the newest answer's text."""
    app.text_area(key='flyover_question').input(question)
    next(b for b in app.button if b.label == 'Send').click().run()
    assert not app.exception
    history = app.session_state.get('flyover_popup_history', [])
    return history[-1]['answer'] if history else ''


def test_resolve_shows_the_api_draft_and_moves_the_prerequisite(live):
    app = open_checklist(signed_in_app(APP), DMV)
    assert status_of(app, DMV) == 'Blocked'
    app.button(key='flyover_resolve:' + DMV).click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) == 'In Progress'
    assert status_of(app, DMV) == 'Blocked'  # only marking residency done unblocks it
    assert app.code[0].value.startswith('Subject: ')
    assert any('Nothing has been sent' in v for v in values(app.warning))
    path, body = live.posts()[-1]
    assert path == f'/tasks/{DMV}/resolve'
    assert body['as_of'] == '2026-08-14'


def test_airshow_answer_follows_resolve_and_mark_done(live):
    app = open_checklist(signed_in_app(APP), DMV)
    assert 'Task status: Blocked.' in ask(app, 'Why is my ID blocked?')
    app.button(key='flyover_resolve:' + DMV).click().run()
    app.selectbox(key='flyover_detail').select(RESIDENCY).run()
    app.button(key='flyover_detail_complete').click().run()  # back to page 1
    assert status_of(app, DMV) == 'Ready'
    app = open_checklist(app, DMV)
    # The same kind of question now gets the new status, not the old one.
    assert 'Task status: Ready.' in ask(app, 'Can I apply for my ID now?')
    asked = [(body, headers) for method, path, body, headers in live.calls
             if path == '/assistant']
    (first, _), (second, headers) = asked
    assert first['student_profile']['completed_tasks'] == []  # a new visitor starts fresh
    assert RESIDENCY in second['student_profile']['completed_tasks']
    assert second['as_of'] == '2026-08-14'
    assert 'student_id' not in second['student_profile']
    assert headers == {'X-API-Key': KEY}


def test_airshow_timeout_shows_a_helpful_message(live, monkeypatch):
    app = open_checklist(signed_in_app(APP), DMV)
    real_post = requests.post

    def slow(url, **kwargs):
        if url.endswith('/assistant'):
            raise requests.Timeout('internal timeout details')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', slow)
    ask(app, 'What next?')
    assert any('took too long' in v for v in values(app.error))
    assert not any('internal timeout details' in v for v in values(app.error))
    assert 'flyover_popup_history' not in app.session_state
    # The unsent question stays in the box so it can be sent again.
    assert app.text_area(key='flyover_question').value == 'What next?'


def confetti_shown(app: AppTest) -> bool:
    return '<div class="flyover-confetti"' in str([e.value for e in app.get('html')])


def test_checklist_completion_celebrates_once_like_the_status_selector(live):
    app = open_checklist(signed_in_app(APP), RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) == 'Completed'  # the API's answer, not the click
    assert app.session_state['flyover_page'] == 'home'
    assert confetti_shown(app)
    assert any('completed. Next:' in v for v in values(app.success))
    app.run()
    assert not confetti_shown(app)  # consumed once


def test_failed_checklist_completion_does_not_celebrate(live, monkeypatch):
    app = open_checklist(signed_in_app(APP), RESIDENCY)
    real_post = requests.post

    def refuse(url, **kwargs):
        if url.endswith('/complete'):
            raise requests.Timeout('private detail')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', refuse)
    app.button(key='flyover_detail_complete').click().run()
    assert not app.exception
    assert status_of(app, RESIDENCY) != 'Completed'
    assert not confetti_shown(app)
    assert any('progress has been kept' in v for v in values(app.error))


def test_reduce_motion_completion_shows_the_message_without_confetti(live):
    app = signed_in_app(APP)
    app.session_state['flyover_reduce_motion'] = True
    app = open_checklist(app, RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    assert not confetti_shown(app)
    assert any('completed. Next:' in v for v in values(app.success))


def chat_bodies(bridge: Bridge) -> list[dict]:
    return [body for path, body in bridge.posts() if path == '/assistant']


def test_dropdown_is_named_ai_help_and_asking_does_not_navigate(live):
    app = signed_in_app(APP)
    # AppTest has no Popover class; the label (the accessible name) is on the block's proto.
    assert [p.proto.popover.label for p in app.get('popover')] == ['AI Help']
    ask(app, 'What next?')
    # No jump to page 2 or Airshow (the app only sets flyover_page when you navigate).
    assert app.session_state.get('flyover_page', 'home') == 'home'
    assert 'flyover_scroll' not in app.session_state


def test_dropdown_sends_journey_and_the_current_step_on_page_one(live):
    app = signed_in_app(APP)
    ask(app, 'What next?')
    body, = chat_bodies(live)
    assert body['page_context'] == 'journey'
    assert body['task_id'] == app.session_state['flyover_active_id']


def test_dropdown_sends_readiness_and_the_chosen_task_on_page_two(live):
    app = open_checklist(signed_in_app(APP), DMV)
    answer = ask(app, 'Why is my ID blocked?')
    body, = chat_bodies(live)
    assert (body['page_context'], body['task_id']) == ('readiness', DMV)
    assert answer.startswith('What this step needs before you go. Task status: Blocked.')


def test_clearing_the_chat_keeps_the_handoff(live):
    app = open_checklist(signed_in_app(APP), DMV)
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    ask(app, 'What next?')
    app.button(key='flyover_chat_clear').click().run()
    assert 'flyover_popup_history' not in app.session_state
    assert app.session_state['flyover_handoff']['title'] == 'Handoff for your DMV clerk'


def test_generating_a_handoff_sends_nothing_to_the_assistant(live):
    app = open_checklist(signed_in_app(APP), DMV)
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    assert chat_bodies(live) == []


def test_answer_is_marked_earlier_after_progress_changes(live):
    app = open_checklist(signed_in_app(APP), DMV)
    ask(app, 'Why is my ID blocked?')
    assert not any('Earlier answer' in v for v in values(app.caption))
    app.button(key='flyover_resolve:' + DMV).click().run()
    assert any('Earlier answer' in v for v in values(app.caption))


def test_chat_history_is_bounded(live, monkeypatch):
    from student_workflow import flyover
    monkeypatch.setattr(flyover, 'CHAT_LIMIT', 2)
    app = signed_in_app(APP)
    for number in range(3):
        ask(app, f'Question {number}?')
    assert [e['question'] for e in app.session_state['flyover_popup_history']] == [
        'Question 1?', 'Question 2?']


def test_question_shows_once_and_is_not_repeated_on_rerun(live):
    app = signed_in_app(APP)
    ask(app, 'What next?')
    asked = [v for v in values(app.markdown) if v == '**You:** What next?']
    assert len(asked) == 1
    app.run()
    assert len([v for v in values(app.markdown) if v == '**You:** What next?']) == 1
    assert len(app.session_state['flyover_popup_history']) == 1
    assert len(chat_bodies(live)) == 1  # no second paid request


def test_answer_is_fetched_under_the_thinking_spinner(live, monkeypatch):
    import contextlib

    import streamlit

    from student_workflow import flyover_client
    spinning, seen = [], []

    @contextlib.contextmanager
    def spinner(text, **kwargs):
        spinning.append(text)
        yield
        spinning.pop()

    real = flyover_client.ask_airshow
    monkeypatch.setattr(streamlit, 'spinner', spinner)
    monkeypatch.setattr(flyover_client, 'ask_airshow',
                        lambda *a, **k: seen.append(list(spinning)) or real(*a, **k))
    app = signed_in_app(APP)
    ask(app, 'What next?')
    assert seen == [['Airshow is checking your flight plan…']]


def test_a_new_visitor_starts_with_no_completed_tasks(live):
    app = signed_in_app(APP)
    data = app.session_state['flyover_data']
    assert data['student_profile']['completed_tasks'] == []
    assert not [t for t in data['workflow'] if t['status'] == 'Completed']
    assert data['as_of'] == '2026-08-14'  # the demo's date, not today
    assert any(v.startswith('0 of 8 steps completed') for v in values(app.caption))
    # Statuses still come from the API: the REAL ID task is blocked by residency.
    assert status_of(app, DMV) == 'Blocked'


def card_titles(app: AppTest) -> list[str]:
    """Titles in the Now and Up next cards, in page order."""
    import html
    import re
    page = ' '.join(str(e.value) for e in app.get('html'))
    # The card HTML-escapes titles (an apostrophe becomes &#x27;), so undo that to compare.
    return [html.unescape(t) for t in re.findall(r'class="fly-card-title">([^<]*)<', page)]


def test_take_off_shows_one_now_card_then_up_next_required_first(live):
    from student_workflow.flyover_state import task_queue
    app = signed_in_app(APP)
    app.button(key='flyover_next').click().run()
    queue = task_queue(app.session_state['flyover_data']['workflow'])
    assert queue[0]['priority'] == 'Required'  # ENG's rules have Required tasks
    assert card_titles(app) == [queue[0]['title'], queue[1]['title']]


def test_page_one_and_the_now_card_focus_the_same_step(live):
    from student_workflow.flyover_state import task_queue
    app = signed_in_app(APP)
    first = task_queue(app.session_state['flyover_data']['workflow'])[0]
    assert app.session_state['flyover_active_id'] == first['id']
    app.button(key='flyover_next').click().run()
    app.button(key='fly_focus_open').click().run()
    assert app.session_state['flyover_detail'] == first['id']


def test_residency_is_queued_before_the_real_id_task_that_needs_it(live):
    from student_workflow.flyover_state import task_queue
    app = signed_in_app(APP)
    order = [t['id'] for t in task_queue(app.session_state['flyover_data']['workflow'])]
    assert order.index(RESIDENCY) < order.index(DMV)


def page_html(app: AppTest) -> str:
    return ' '.join(str(e.value) for e in app.get('html'))


def test_completion_shows_the_boarding_board_once(live):
    from student_workflow.flyover_state import active_task
    app = open_checklist(signed_in_app(APP), RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    upcoming = active_task(app.session_state['flyover_data']['workflow'])
    html = page_html(app)
    assert 'class="fly-board" role="status"' in html
    assert ('aria-label="Gather residency evidence for California REAL ID completed. '
            f'Now boarding: {upcoming["title"]}.') in html.replace('&#x27;', "'")
    assert 'gate-title is-changing' in html  # the title flips with it
    app.run()
    assert 'class="fly-board"' not in page_html(app)  # consumed once
    assert 'gate-title is-changing' not in page_html(app)


def test_no_board_or_flip_without_a_confirmed_completion(live, monkeypatch):
    app = signed_in_app(APP)
    assert 'class="fly-board"' not in page_html(app)
    assert 'gate-title is-changing' not in page_html(app)  # first load is not a completion
    app = open_checklist(app, RESIDENCY)
    real_post = requests.post

    def refuse(url, **kwargs):
        if url.endswith('/complete'):
            raise requests.Timeout('private detail')
        return real_post(url, **kwargs)

    monkeypatch.setattr(requests, 'post', refuse)
    app.button(key='flyover_detail_complete').click().run()
    assert 'class="fly-board"' not in page_html(app)


def test_step_number_counts_progress_not_file_position(live):
    app = signed_in_app(APP)
    assert 'Step 01 of 08 · Now boarding' in page_html(app)
    app = open_checklist(app, RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    assert 'Step 02 of 08 · Now boarding' in page_html(app)


def test_last_task_board_says_arrived():
    from student_workflow.flyover import _boarding_board
    html = _boarding_board({'done': 'Open a bank account', 'next': None, 'next_id': None})
    assert 'aria-label="Open a bank account completed. All steps completed."' in html
    assert '>Arrived<' in html and 'Now boarding' not in html
    assert '<div aria-hidden="true">' in html  # the flipping letters aren't read out


def add_free_time(app: AppTest, day: str, start: tuple, end: tuple) -> AppTest:
    from datetime import time
    app.selectbox(key='fly_avail_day').select(day)
    app.time_input(key='fly_avail_start').set_value(time(*start))
    app.time_input(key='fly_avail_end').set_value(time(*end))
    next(b for b in app.button if b.label == 'Add free time').click().run()
    return app


def notice_shown(app: AppTest) -> bool:
    return any(v.startswith('**Appointment information for your next step:**')
               for v in values(app.markdown))


def test_appointment_notice_shows_sourced_text_for_the_next_step(live):
    app = signed_in_app(APP)
    # School check-in is first (Required) and has CRC's appointment guidance.
    assert notice_shown(app)
    assert any('schedule an in-person or phone appointment' in v for v in values(app.markdown))
    assert any('Not verified' in v for v in values(app.caption))
    assert not any('required' in v.lower() and 'appointment' in v.lower()
                   for v in values(app.markdown))  # never claims an appointment is required


def test_free_times_are_matched_against_published_office_hours(live):
    app = add_free_time(signed_in_app(APP), 'Monday', (7, 0), (9, 30))
    captions = values(app.caption)
    assert 'Your free times: Monday 7:00 AM–9:30 AM.' in captions
    # Admissions & Records opens at 08:00 on Mondays (Fall 2026 hours, in effect on the demo date).
    assert any(c.startswith("Your free times overlap CRC Admissions and Records Office's "
                            'published hours: Monday 8:00 AM–9:30 AM.') for c in captions)
    # The International Students Office publishes none, and the notice says so.
    assert ('CRC International Students Office publishes no hours: check with the office '
            'before you go.') in captions


def test_a_backwards_free_time_is_refused(live):
    app = add_free_time(signed_in_app(APP),
                        'Monday', (14, 0), (9, 0))
    assert any('start before it ends' in v for v in values(app.error))
    assert app.session_state['flyover_preferences']['availability'] == []


def test_dismissed_notice_stays_dismissed_on_rerun(live):
    app = signed_in_app(APP)
    app.button(key='fly_appt_dismiss').click().run()
    assert not notice_shown(app)
    app.run()
    assert not notice_shown(app)


def test_free_times_are_never_sent_to_the_api(live):
    app = add_free_time(signed_in_app(APP),
                        'Wednesday', (13, 0), (15, 0))
    ask(app, 'What next?')
    app = open_checklist(app, DMV)
    app.button(key='flyover_resolve:' + DMV).click().run()
    sent = str([body for _, body in live.posts()])
    assert 'Wednesday' not in sent and 'availability' not in sent


def test_generating_a_new_profile_clears_free_times(live):
    app = add_free_time(signed_in_app(APP),
                        'Monday', (9, 0), (12, 0))
    assert app.session_state['flyover_preferences']['availability']
    next(b for b in app.button if b.label == 'Generate workflow').click().run()
    assert not app.exception
    assert 'flyover_preferences' not in app.session_state or not app.session_state[
        'flyover_preferences'].get('availability')


def test_a_task_with_no_visit_details_says_so_once(live):
    app = open_checklist(signed_in_app(APP),
                         'task_crc_fee_payment')
    notes = [v for v in values(app.get('html')) if 'Not on file yet' in str(v)]
    assert len(notes) == 1 and 'Hours, Fees, Appointments, Phone' in str(notes[0])
    assert not any(v.startswith('Hours: Not verified') for v in values(app.markdown))


def test_sourced_visit_details_show_with_a_not_verified_badge(live):
    app = open_checklist(signed_in_app(APP), DMV)
    hours = [v for v in values(app.markdown) if v.startswith('**Hours:**')]
    assert len(hours) == 1 and hours[0].endswith(':orange-badge[Not verified]')
    assert 'DMV office finder' in hours[0]  # ENG's sourced wording, link included


def test_airshow_greets_an_empty_chat(live):
    from student_workflow.flyover import AIRSHOW_GREETING
    app = signed_in_app(APP)
    assert f'**Airshow:** {AIRSHOW_GREETING}' in values(app.markdown)
    ask(app, 'What next?')
    assert f'**Airshow:** {AIRSHOW_GREETING}' not in values(app.markdown)


def test_airshow_opens_with_its_line_and_keeps_the_cited_answer(live):
    from student_workflow.flyover import AIRSHOW_INTROS
    app = open_checklist(signed_in_app(APP), DMV)
    answer = ask(app, 'Why is my ID blocked?')
    shown = values(app.markdown)
    assert f'**Airshow:** {AIRSHOW_INTROS["Blocked"]}' in shown
    assert answer in shown  # the API's answer, word for word, after the persona line


@pytest.mark.parametrize(('entry', 'kind'), [
    ({'answer': 'Task status: Ready.', 'contact': None}, 'Ready'),
    ({'answer': 'What this step needs before you go. Task status: In Progress.',
      'contact': None}, 'In Progress'),
    ({'answer': 'Please ask your DSO.', 'contact': 'DSO'}, 'referral'),
    ({'answer': "I couldn't match that to a task.", 'contact': None}, 'other'),
])
def test_airshow_picks_its_line_from_the_api_answer(entry, kind):
    from student_workflow.flyover import AIRSHOW_INTROS, airshow_intro
    assert airshow_intro(entry) == AIRSHOW_INTROS[kind]


def open_profile(app: AppTest) -> AppTest:
    return app.button(key='flyover_open_profile').click().run()


def test_profile_dashboard_shows_this_sessions_answers(live):
    app = open_profile(signed_in_app(APP))
    assert app.session_state['flyover_page'] == 'profile'
    assert 'Your profile' in values(app.subheader)
    assert 'Signed in as s***@example.com' in values(app.caption)
    html = ' '.join(values(app.get('html')))
    assert '<dt>School</dt><dd>Cosumnes River College</dd>' in html
    assert 'August 11, 2026 · 3 days ago' in html  # demo arrival vs the workflow's date


def test_profile_progress_counts_follow_the_api(live):
    app = open_checklist(signed_in_app(APP), RESIDENCY)
    app.button(key='flyover_detail_complete').click().run()
    app = open_profile(app)
    metrics = {m.label: m.value for m in app.metric}
    assert metrics['Completed'] == '1'
    assert sum(int(v) for v in metrics.values()) == 8


def test_email_joins_the_handoff_only_when_switched_on(live):
    app = open_checklist(signed_in_app(APP), DMV)
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    assert 'student@example.com' not in str(app.session_state['flyover_handoff'])
    app.button(key='flyover_back').click().run()
    app = open_profile(app)
    app.toggle(key='flyover_handoff_email_widget').set_value(True).run()
    app = open_checklist(app.button(key='flyover_profile_back').click().run(), DMV)
    assert 'flyover_handoff' not in app.session_state  # the old handoff no longer matches
    app.text_area(key='flyover_goal').input('Get my California ID').run()
    app.button(key='flyover_prepare_handoff').click().run()
    who = dict(app.session_state['flyover_handoff']['sections'])['Who I am'][0]
    assert who.endswith('Contact: student@example.com')
    assert 'student@example.com' not in str(live.calls)  # still never sent to the API


def test_checklist_lists_the_tasks_offices_with_their_hours(live):
    app = open_checklist(signed_in_app(APP), DMV)
    shown = values(app.markdown)
    assert '#### Office hours' in shown
    assert '**California DMV, Sacramento South** :orange-badge[Not verified]' in shown
    assert ('Mon–Tue 8:00 AM–5:00 PM · Wed 9:00 AM–5:00 PM · Thu–Fri 8:00 AM–5:00 PM '
            '(Pacific time)') in shown


def test_sources_have_readable_names_not_rule_ids(live):
    app = open_checklist(signed_in_app(APP), 'task_school_checkin')
    html = ' '.join(values(app.get('html')))
    assert 'Cosumnes River College · International students office' in html
    assert 'Not double-checked by our team yet' in html
    assert 'rule_crc_arrival_reporting<' not in html and 'Source date' not in html


def test_the_checklist_explains_not_verified_once(live):
    app = open_checklist(signed_in_app(APP), DMV)
    notes = [v for v in values(app.get('html')) if 'means our team hasn' in str(v)]
    assert len(notes) == 1


def test_an_office_without_hours_says_so_without_a_time_zone(live):
    app = open_checklist(signed_in_app(APP), 'task_school_checkin')
    assert 'No hours published' in values(app.markdown)
    assert 'No hours published (Pacific time)' not in values(app.markdown)


@pytest.mark.parametrize(('url', 'label'), [
    ('https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/',
     'California DMV · What is REAL ID'),
    ('https://www.ssa.gov/locator', 'Social Security · Locator'),
    (('https://www.dmv.ca.gov/portal/driver-education-and-safety/educational-materials/fast-facts/'
     'social-security-number-ffdl-8/'), 'California DMV · Social security number'),
    (None, 'Official source'),
])
def test_source_labels(url, label):
    from student_workflow.flyover import source_label
    assert source_label(url) == label
