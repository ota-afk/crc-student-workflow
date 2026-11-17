"""Flyover: page 1 (profile + one-step workflow) and page 2 (readiness, take-off, Airshow)."""

import html
import json
import os
import re
import uuid
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from . import flyover_client as client
from .flyover_appointments import (
    DAYS,
    NO_HOURS_NOTE,
    TIMEZONE_LABEL,
    describe_windows,
    fact_verified,
    first_with_guidance,
    hours_summary,
    match_line,
    normalize_windows,
    notice_key,
)
from .flyover_art import ASSETS, banner, flight_map, flight_scene, logo, svg_asset
from .flyover_signin import masked, render_signin, sign_out, signed_in
from .flyover_state import (
    ENCOURAGEMENTS,
    active_task,
    due_note,
    map_piece_count,
    map_progress,
    task_queue,
)
from .flyover_tour import tour_script
from .frontend import safe_url, source_verified
from .frontend_state import sync_profile_context

PILLS = {'Completed': ('done', '✓'), 'In Progress': ('progress', '◐'),
         'Blocked': ('blocked', '✕'), 'Ready': ('ready', '▶')}
PROFESSIONALS = {
    'DMV clerk': ['Which documents do you accept as proof of California residency for a student?',
                  'Do my passport, I-20 and I-94 cover identity and lawful presence?',
                  'I don’t have an SSN. What do I bring instead?',
                  'Do I need an appointment, and what is the fee?'],
    'School DSO (international office)': [
        'Is my check-in complete, and is my SEVIS record Active?',
        'Can the school give me a letter that shows my local address?',
        'Which offices should I visit next, and in what order?',
        'Who do I contact if an office asks for something I don’t have?'],
    'Bank officer': ['Can I open an account without an SSN? What do you accept instead?',
                     'Which ID do you accept: passport, California ID, or both?',
                     'Are there student accounts without monthly fees?'],
    'Another office': ['Which requirements apply to my situation?',
                       'Which documents should I bring?',
                       'What are my next steps and deadlines?'],
}
VISIT_FACTS = [('Hours', 'hours'), ('Fees', 'fees'), ('Appointments', 'appointment_rules'),
               ('Phone', 'phone')]
OTHER_OFFICE = 'Another office'  # the preset that asks for its own office name
OFFICE_NAME_MAX = 80
# Airshow's voice: fixed lines chosen by code from what the API answered. The model never
# writes them, and they never replace or soften the cited answer that follows.
AIRSHOW_GREETING = ("Hi, I'm Airshow, your co-pilot for your first weeks. Ask me about the "
                    "step you're on, and I'll show you where the guidance comes from.")
AIRSHOW_INTROS = {
    'Blocked': "Holding short on this one: something has to happen first.",
    'Ready': "You're cleared for this one. Here's the flight plan.",
    'In Progress': "Holding pattern: you're waiting to hear back from an office.",
    'Completed': "Already landed. Nice work!",
    'referral': "That one's for your DSO. I stay out of immigration and work questions.",
    'other': "Let's try that another way.",
}
CHAT_LIMIT = 10  # questions kept in the dropdown's history for this session
PAGE_NAMES = {'journey': 'Your journey', 'readiness': 'Readiness and checklist'}


def esc(value) -> str:
    return html.escape('' if value is None else str(value))


def go(page: str, task_id: str | None = None) -> None:
    # 'assistant' (Skip to Airshow) lives on the readiness page.
    st.session_state['flyover_page'] = {'home': 'home', 'profile': 'profile'}.get(page, 'readiness')
    st.session_state['flyover_scroll'] = ('airshow' if page == 'assistant'
                                          else 'checklist' if task_id else 'top')
    if task_id:
        st.session_state['flyover_detail'] = task_id
        st.session_state['flyover_quote'] = st.session_state.get('flyover_quote', -1) + 1


def _replay_tour() -> None:
    # The tour points at page 1's controls, so go there and send it again.
    st.session_state['flyover_tour_replay'] = True
    st.session_state['flyover_page'] = 'home'


@st.dialog('Flight settings')
def settings() -> None:
    st.caption('Make this space comfortable for you.')
    def keep_preference(widget: str, preference: str) -> None:
        st.session_state[preference] = st.session_state[widget]
    st.toggle('Reduce motion', key='flyover_motion_widget',
              value=st.session_state.get('flyover_reduce_motion', False),
              on_change=keep_preference, args=('flyover_motion_widget', 'flyover_reduce_motion'),
              help='Turn off fades, banner crossfades, departure-board flips, the flight and map transitions.')
    st.toggle('Pause travel banner', key='flyover_pause_widget',
              value=st.session_state.get('flyover_pause_banner', False),
              on_change=keep_preference, args=('flyover_pause_widget', 'flyover_pause_banner'))
    st.caption('Your profile and checklist stay in this browser session. Nothing is uploaded.')
    # The callback sets the flags (it runs however the dialog is redrawn); the rerun then
    # redraws the whole page, closing the dialog, so the tour can find page 1's controls.
    if st.button('Replay tutorial', key='flyover_tour_replay_btn', icon=':material/school:',
                 on_click=_replay_tour):
        st.rerun()
    if account := st.session_state.get('flyover_account'):
        st.caption('Signed in as ' + masked(account['email']))
        if st.button('Your profile', key='flyover_settings_profile', icon=':material/badge:',
                     on_click=go, args=('profile',)):
            st.rerun()
        if st.button('Sign out', key='flyover_sign_out', on_click=sign_out):
            st.rerun()
    if st.button('Done', key='flyover_settings_done', type='primary'):
        st.rerun()


def _header():
    """The sticky header. Returns the AI Help dropdown, filled once the workflow has loaded."""
    with st.container(key='flyover_header'):
        brand, ai, gear = st.columns([8, 1, 1], vertical_alignment='center')
        with brand:
            st.image(logo(), width=185)
        with ai:
            # A dropdown anchored under the logo (not a page jump, not a modal). Its label is the
            # accessible name; CSS shows the AI Help logo in its place.
            panel = st.popover('AI Help', key='flyover_ai',
                               help='Ask Airshow about the step you are on')
        with gear:
            if st.button('Settings', icon=':material/settings:', key='flyover_settings',
                         help='Settings and motion preferences'):
                settings()
    return panel


def _chat_context(data: dict, page: str) -> tuple[str, str | None]:
    """(page_context, task_id) for the dropdown: the page it is opened on and the task in view."""
    tasks = data['workflow']
    if page in ('home', 'profile'):
        current = active_task(tasks)
        return 'journey', current['id'] if current else None
    # Page 2: the task chosen in "Your checklist", else the current one.
    chosen = st.session_state.get('flyover_detail')
    if chosen in {task['id'] for task in tasks}:
        return 'readiness', chosen
    current = active_task(tasks)
    return 'readiness', current['id'] if current else None


def _context_key(data: dict, page_context: str, task_id: str | None) -> str:
    # Changes when the task, page, date or progress changes, so older answers can be labelled.
    return json.dumps([page_context, task_id, data['as_of'], data['student_profile']],
                      sort_keys=True)


def _send_chat(page_context: str, task_id: str | None) -> None:
    """Send callback: only record the question. The request runs during the redraw, so the
    question shows at once and a spinner can say Airshow is working (a callback can't draw)."""
    st.session_state.pop('flyover_chat_error', None)
    question = (st.session_state.get('flyover_question') or '').strip()
    if not question:
        return
    st.session_state['flyover_chat_pending'] = {'question': question,
                                                'page_context': page_context, 'task_id': task_id}
    st.session_state['flyover_question'] = ''  # put back below if the answer fails


def _ask_pending(data: dict, api_url: str) -> None:
    """Answer the recorded question, under a spinner, before the input box is drawn."""
    pending = st.session_state.pop('flyover_chat_pending', None)
    if pending is None:
        return
    st.markdown('**You:** ' + esc(pending['question']))
    try:
        with st.spinner('Airshow is checking your flight plan…'):
            answer = client.ask_airshow(api_url, data, pending['question'], pending['task_id'],
                                        pending['page_context'])
    except (requests.RequestException, ValueError) as error:
        st.session_state['flyover_chat_error'] = (
            'timeout' if isinstance(error, requests.Timeout) else 'failed')
        # The box isn't drawn yet this run, so the unsent question can go back into it.
        st.session_state['flyover_question'] = pending['question']
        return
    history = st.session_state.setdefault('flyover_popup_history', [])
    history.append({'question': pending['question'], **answer,
                    'context': _context_key(data, pending['page_context'], pending['task_id'])})
    del history[:-CHAT_LIMIT]  # bounded: a long session never grows without limit
    st.session_state['flyover_chat_answered'] = True  # the next lines draw it; no repeat


def airshow_intro(entry: dict) -> str:
    """Airshow's opening line for an answer, picked from what the API said (no model)."""
    if entry.get('contact'):
        return AIRSHOW_INTROS['referral']
    status = re.search(r'Task status: (Blocked|Ready|In Progress|Completed)\.', entry['answer'])
    return AIRSHOW_INTROS[status.group(1)] if status else AIRSHOW_INTROS['other']


def _chat_entry(entry: dict, current: str, *, show_question: bool = True) -> None:
    if show_question:
        st.markdown('**You:** ' + esc(entry['question']))
    if entry['context'] != current:
        st.caption('Earlier answer, before your latest progress or a different step.')
    st.markdown(f'**Airshow:** {airshow_intro(entry)}')
    if not entry['verified'] or not all(source_verified(s) for s in entry['sources']):
        st.warning('Not verified. Confirm with the office.')
    st.markdown(entry['answer'])  # the API's cited answer, unchanged
    for number, step in enumerate(entry['steps'], 1):
        st.write(f'{number}. {step}')
    if entry['contact']:
        st.write('Who to contact: ' + entry['contact'])
    if entry['sources']:
        st.html(f'<div class="fly-sheet">{_source_rows(entry["sources"])}</div>')


def _clear_chat() -> None:
    # Only the chat: the handoff below has its own state and is never touched here.
    st.session_state.pop('flyover_popup_history', None)
    st.session_state.pop('flyover_chat_error', None)


def _chat(data: dict, api_url: str, page: str) -> None:
    """The AI Help dropdown: a live chat on POST /assistant, separate from the handoff."""
    page_context, task_id = _chat_context(data, page)
    titles = {task['id']: task['title'] for task in data['workflow']}
    current = _context_key(data, page_context, task_id)
    st.html(f'<img class="fly-chat-badge" src="{svg_asset("ai-help.svg")}" alt="">')
    st.caption(f'Asking about: {titles.get(task_id, "your workflow")} · '
               f'{PAGE_NAMES[page_context]}')
    st.caption('Answers come from your workflow and our sources. Do not include your name, '
               'SSN or document numbers.')
    with st.container(key='fly_chat_log'):
        history = st.session_state.get('flyover_popup_history', [])
        if not history and 'flyover_chat_pending' not in st.session_state:
            st.markdown(f'**Airshow:** {AIRSHOW_GREETING}')
        for entry in history:
            _chat_entry(entry, current)
        # A just-sent question: shown at once, answered under the spinner, then drawn here.
        _ask_pending(data, api_url)
        if st.session_state.pop('flyover_chat_answered', False):
            _chat_entry(st.session_state['flyover_popup_history'][-1], current,
                        show_question=False)
    if (error := st.session_state.get('flyover_chat_error')) == 'timeout':
        st.error('Airshow took too long to answer. The service may be starting up: wait a '
                 'minute and send again. Your progress has been kept.')
    elif error:
        st.error('Airshow could not answer right now. Send again, or use your checklist and its '
                 'sources. Your progress has been kept.')
    with st.form('flyover_chat_form', border=False):
        # Several lines, so a longer question is easy to read back before sending.
        st.text_area('Your question', max_chars=500, key='flyover_question', height=110,
                     placeholder='For example: why is my California ID blocked?')
        st.form_submit_button('Send', type='primary', on_click=_send_chat,
                              args=(page_context, task_id))
    st.button('Clear conversation', key='flyover_chat_clear', on_click=_clear_chat,
              type='tertiary')


def _profile(data: dict, api_url: str) -> None:
    profile = data['student_profile']
    if st.session_state.pop('flyover_clear_reset_confirmation', False):
        st.session_state['flyover_new_profile'] = False
    with st.container(key='flyover_hero'):
        st.html(banner())
        left, _ = st.columns([.95, 1.25], gap='large')
        with left, st.container(key='flyover_profile'):
            st.html('<span class="fly-chip">Start here</span>')
            st.subheader('Profile setup')
            st.caption('Your next chapter starts with a little preparation.')
            if 'flyover_schools' not in st.session_state:
                try:
                    st.session_state['flyover_schools'] = client.fetch_schools(api_url)
                except (requests.RequestException, ValueError):
                    st.error('School search is unavailable. Your current workflow is unchanged.')
                    if st.button('Retry school directory', key='flyover_retry_schools'):
                        st.rerun()
                    return
            schools = {school['school_id']: school for school in st.session_state['flyover_schools']}
            school_ids = list(schools) + [None]
            selected = profile.get('school_id')
            default = school_ids.index(selected) if selected in school_ids else len(school_ids) - 1
            with st.form('flyover_profile_form', border=False):
                st.caption('California · F-1 student guidance')
                school_id = st.selectbox('School', school_ids, index=default,
                    format_func=lambda key: schools[key]['institution'] if key else 'My school is not listed',
                    key='flyover_school')
                first, second = st.columns([1.15, 1])
                with first:
                    arrival = st.date_input('Arrival date',
                        value=date.fromisoformat(profile['arrival_date']), key='flyover_arrival')
                with second:
                    visa = st.selectbox('Visa type', ['F-1'], key='flyover_visa')
                ssn = st.radio('Do you have an SSN?', ['No', 'Yes'], horizontal=True,
                    index=int(profile['has_ssn']), key='flyover_ssn', help='Yes or no only. Never enter the number.')
                enrolled = st.date_input(
                    'Enrollment date (optional)', key='flyover_enrollment',
                    value=date.fromisoformat(profile['enrollment_date'])
                    if profile.get('enrollment_date') else None,
                    help='The day you enrolled in classes. Only used to work out your tuition deadline.')
                has_progress = bool(profile.get('completed_tasks') or profile.get('awaiting_reply'))
                reset = st.checkbox('Start fresh and clear current progress', key='flyover_new_profile')
                submitted = st.form_submit_button('Generate workflow', type='primary', width='stretch')
                if submitted:
                    if has_progress and not reset:
                        st.warning('Confirm “Start fresh” to apply a new profile. Your current progress has been kept.')
                    elif arrival is None:
                        st.warning('Choose your arrival date first.')
                    else:
                        changes = {'school_id': school_id, 'institution': schools[school_id]['institution']
                            if school_id else 'School not listed', 'visa_type': visa,
                            'arrival_date': arrival.isoformat(), 'has_ssn': ssn == 'Yes',
                            'enrollment_date': enrolled.isoformat() if enrolled else None}
                        try:
                            # The spinner is the feedback; the page itself no longer dims.
                            with st.spinner('Building your workflow…'):
                                result = client.generate_workflow(api_url, profile, changes)
                        except (requests.RequestException, ValueError):
                            st.error('Could not generate your workflow. Your progress has been kept. Try again.')
                        else:
                            st.session_state['flyover_data'] = result
                            st.session_state['flyover_clear_reset_confirmation'] = True
                            for key in ('flyover_active_id', 'flyover_status', 'flyover_detail', 'flyover_handoff',
                                        'flyover_map_done', 'flyover_celebrate', 'flyover_status_error',
                                        'flyover_email', 'flyover_resolve_error', 'flyover_popup_history',
                                        'flyover_chat_error', 'flyover_preferences',
                                        'flyover_appt_dismissed'):
                                st.session_state.pop(key, None)
                            for key in list(st.session_state):
                                if key.startswith('flyover_doc:'):
                                    del st.session_state[key]
                            st.session_state['flyover_flash'] = 'Your new workflow is ready to explore.'
                            st.rerun()
            st.caption('No names, document numbers or uploads. Your profile stays in this session.')
            st.button('View your profile', key='flyover_open_profile', type='tertiary',
                      icon=':material/badge:', on_click=go, args=('profile',))


def _save_status(api_url: str, task_id: str) -> None:
    """Widget callback: commit once, then render only the backend's returned state."""
    data = st.session_state['flyover_data']
    task = next((item for item in data['workflow'] if item['id'] == task_id), None)
    if task is None:
        return
    desired = st.session_state['flyover_status']
    if desired == task['status']:
        return
    try:
        result = client.change_status(api_url, data, task_id, desired)
    except (requests.RequestException, ValueError):
        st.session_state['flyover_status'] = task['status']
        st.session_state['flyover_status_error'] = 'Could not update this step. Your progress has been kept. Try again.'
        return
    returned = _record_update(task, result, api_url)
    st.session_state['flyover_status'] = returned['status']


def _record_update(task: dict, result: dict, api_url: str | None = None) -> dict:
    """The one success path for every status control: keep the API's answer, then celebrate.

    Both the status selector and "Mark this step completed" land here, so they give the same
    feedback. Confetti only for a new move to Completed, as the API returned it, never for the
    click alone. The flag is consumed once by _workflow, and reduce motion keeps the message.
    """
    st.session_state['flyover_data'] = result
    returned = next((item for item in result['workflow'] if item['id'] == task['id']), task)
    if returned['status'] == 'Completed' and task['status'] != 'Completed':
        st.session_state['flyover_celebrate'] = True
        upcoming = active_task(result['workflow'])
        # The boarding board is driven by this confirmed completion, never by the current
        # step merely changing (picking a task by hand is not finishing one). None = last task.
        st.session_state['flyover_boarding'] = {
            'done': task['title'], 'next': upcoming['title'] if upcoming else None,
            'next_id': upcoming['id'] if upcoming else None}
        st.session_state['flyover_flash'] = (
            f"{task['title']} completed. Next: {upcoming['title']}" if upcoming
            else 'All steps completed. Your route is assembled!')
        if api_url and not _cancel_task_reminders(api_url, task['id']):
            st.session_state['flyover_flash'] += (
                ' A reminder for this step could not be cancelled and may still arrive.')
    else:
        st.session_state['flyover_flash'] = 'Status saved.'
    return returned


def _confetti() -> None:
    if st.session_state.get('flyover_reduce_motion'):
        return
    colors = ['#629677', '#777DA7', '#E6CCBE', '#E6B951', '#FFFFFF']
    particles = ''.join(
        f'<i style="--x:{(i * 37) % 100}%;--delay:{(i % 7) * .06}s;'
        f'--drift:{(i % 9 - 4) * 24}px;--color:{colors[i % len(colors)]};'
        f'--spin:{180 + i * 29}deg"></i>' for i in range(48))
    st.html(f'<div class="flyover-confetti" aria-hidden="true">{particles}</div>')


def _flaps(text: str) -> str:
    """Each letter in its own span, numbered for the left-to-right flip delay (--i)."""
    index = 0
    words = []
    for word in text.split(' '):
        letters = []
        for char in word:
            letters.append(f'<span class="flap" style="--i:{index}">{esc(char)}</span>')
            index += 1
        words.append('<span class="word">' + ''.join(letters) + '</span>')
        index += 1
    return ' '.join(words)


def _boarding_board(event: dict) -> str:
    """The departures board shown once, right after the API confirms a task is Completed.

    Screen readers hear one sentence (role=status); the flipping letters are hidden from them.
    With reduce motion the letters simply appear (style.css and reduce-motion.css).
    """
    done, upcoming = event['done'], event['next']
    rows = [('Departed', '✓ ' + done),
            ('Now boarding', upcoming) if upcoming else ('Arrived', 'All steps completed')]
    spoken = f'{done} completed. ' + (f'Now boarding: {upcoming}.' if upcoming
                                      else 'All steps completed.')
    body = ''.join(f'<div class="fly-board-row"><span class="fly-board-label">{esc(label)}</span>'
                   f'<span class="fly-board-value">{_flaps(value)}</span></div>'
                   for label, value in rows)
    return (f'<div class="fly-board" role="status" aria-label="{esc(spoken)}">'
            f'<div aria-hidden="true">{body}</div></div>')


def _board(title: str, changing: bool) -> str:
    """Departure-board title: every letter flips in, left to right, after a completion.

    While the boarding board is announcing the change, the title stays quiet for screen
    readers (aria-live off), so the new step is announced once, not twice.
    """
    state = ' is-changing' if changing else ''
    live = 'off' if changing else 'polite'
    words = _flaps(title)
    return (f'<div class="gate-title{state}" role="text" aria-live="{live}" aria-label="{esc(title)}">'
            + words + '</div>')


def _windows() -> list[dict]:
    """The student's weekly free times: this browser session only, never sent anywhere."""
    return st.session_state.setdefault('flyover_preferences', {}).setdefault('availability', [])


def _add_window() -> None:
    """Form callback: validate and merge the new free time, or say what is wrong."""
    st.session_state.pop('flyover_avail_error', None)
    new = {'day': st.session_state['fly_avail_day'], 'start': st.session_state['fly_avail_start'],
           'end': st.session_state['fly_avail_end']}
    try:
        merged = normalize_windows([*_windows(), new])
    except ValueError as error:
        st.session_state['flyover_avail_error'] = str(error).capitalize() + '.'
        return
    st.session_state['flyover_preferences']['availability'] = merged


def _remove_window(index: int) -> None:
    windows = _windows()
    if 0 <= index < len(windows):
        del windows[index]


def _dismiss_notice(key: str) -> None:
    st.session_state.setdefault('flyover_appt_dismissed', []).append(key)


def _availability_editor() -> None:
    st.caption(f'{TIMEZONE_LABEL}. Kept in this browser session only and never sent anywhere. '
               'This plans your visit; it does not book an appointment.')
    with st.form('fly_avail_form', border=False):
        day, start, end = st.columns([1.4, 1, 1])
        with day:
            st.selectbox('Day', DAYS, key='fly_avail_day')
        with start:
            st.time_input('From', value=time(9, 0), step=900, key='fly_avail_start')
        with end:
            st.time_input('To', value=time(12, 0), step=900, key='fly_avail_end')
        st.form_submit_button('Add free time', on_click=_add_window)
    if error := st.session_state.pop('flyover_avail_error', None):
        st.error(error)
    for index, window in enumerate(_windows()):
        label, remove = st.columns([4, 1], vertical_alignment='center')
        with label:
            st.write(describe_windows([window]))
        with remove:
            st.button('Remove', key=f'fly_avail_rm:{index}', on_click=_remove_window,
                      args=(index,), type='tertiary')


def _appointment_notice(tasks: list[dict]) -> None:
    """In-app notice when the current or next step has sourced appointment guidance."""
    guidance = first_with_guidance(task_queue(tasks))
    if guidance is None:
        return
    windows = _windows()
    key = notice_key(guidance, windows)
    if key in st.session_state.get('flyover_appt_dismissed', []):
        return  # dismissed; the same text stays in the task's checklist under Visit details
    with st.container(key='fly_appt_notice'):
        st.markdown(f'**Appointment information for your next step:** {guidance["title"]}')
        st.markdown(guidance['text'])  # ENG's sourced wording, unchanged
        if not guidance['verified']:
            st.caption('⚠ Not verified. Confirm with the office.')
        if link := safe_url(guidance['url']):
            st.link_button('Official visit information', link)
        if windows:
            st.caption(f'Your free times: {describe_windows(windows)}.')
            task = next((t for t in tasks if t['id'] == guidance['task_id']), {})
            # One line per office on file (rules.json offices), else the honest no-hours note.
            for line in [match_line(o, windows) for o in task.get('offices') or []] or [
                    NO_HOURS_NOTE]:
                st.caption(line)
        with st.expander('Your free times (optional)'):
            _availability_editor()
        st.button('Dismiss', key='fly_appt_dismiss', on_click=_dismiss_notice, args=(key,),
                  type='tertiary')


def _workflow(data: dict, api_url: str) -> None:
    tasks = data['workflow']
    done = sum(task['status'] == 'Completed' for task in tasks)
    pieces = map_piece_count(done, len(tasks))
    progress = map_progress(done, len(tasks))
    previous_done = st.session_state.get('flyover_map_done', done)
    st.session_state['flyover_map_done'] = done
    with st.container(key='flyover_workflow'):
        st.html(flight_map(progress, animate=done > previous_done and not st.session_state.get('flyover_reduce_motion'),
                           previous=map_progress(previous_done, len(tasks))))
        if st.session_state.pop('flyover_celebrate', False):
            _confetti()
        # Shown once per confirmed completion (set in _record_update), then consumed.
        boarding = st.session_state.pop('flyover_boarding', None)
        if boarding:
            st.html(_boarding_board(boarding))
        if error := st.session_state.pop('flyover_status_error', None):
            st.error(error)
        st.subheader('Moving Forward (Workflow)')
        st.caption(f'{done} of {len(tasks)} steps completed · {pieces} of 3 route pieces assembled')
        if flash := st.session_state.pop('flyover_flash', None):
            st.success(flash)
        current = active_task(tasks)
        if current is None:
            if tasks:
                st.success('Your checklist is complete. Confirm requirements with the relevant offices before your visit.')
            else:
                st.info('No workflow steps are available. Generate a profile or try again.')
        else:
            task_id = current['id']
            # Flip the title only when a completion just moved us to this step, never when the
            # current step merely changed (a new profile, or Required-first reordering).
            changing = bool(boarding) and boarding.get('next_id') == task_id
            if st.session_state.get('flyover_active_id') != task_id:
                st.session_state['flyover_active_id'] = task_id
                st.session_state['flyover_status'] = current['status']
            # Progress, not the rules file's position: tasks are shown Required-first (task_queue).
            number = done + 1
            with st.container(key='flyover_gate'):
                title_col, status_col, action_col = st.columns([2.6, 1.3, 1.1], gap='large',
                                                               vertical_alignment='center')
                with title_col:
                    st.html(f'<div class="gate-step">Step {number:02d} of {len(tasks):02d} · Now boarding</div>'
                            + _board(current['title'], changing)
                            + f'<span class="gate-priority">{esc(current["priority"])}</span>')
                with status_col:
                    options = [current['status']] if current['status'] == 'Blocked' else ['Ready', 'In Progress', 'Completed']
                    st.selectbox('Status', options, key='flyover_status',
                        on_change=_save_status, args=(api_url, task_id),
                        disabled=current['status'] == 'Blocked',
                        help='In Progress means waiting on an office. Completion is self-reported; prerequisites are enforced by the API.')
                    st.caption('Changes save automatically.')
                with action_col:
                    st.button('View checklist', key='flyover_checklist', on_click=go, type='tertiary',
                              args=('readiness', task_id), icon=':material/checklist:')
            with st.container(key='fly_gate_notes'):
                if note := due_note(current, data['as_of']):
                    getattr(st, note[0])(note[1])
                if current.get('next_action'):
                    st.info(current['next_action']['text'])
                for blocker in current.get('blockers') or []:
                    st.warning(blocker['explanation'])
                if not current.get('sources') or not all(source_verified(s) for s in current['sources']):
                    st.caption('Not verified. Confirm with the office. Completing a step does not confirm eligibility.')
                if current['status'] == 'Blocked':
                    _resolve_section(current, api_url)
                    other_ready = [t for t in tasks if t['status'] in ('Ready', 'In Progress')]
                    if other_ready:
                        st.caption('You can prepare another available task while this step is blocked:')
                        for task in other_ready:
                            st.button(task['title'], key='flyover_other:' + task['id'],
                                      on_click=go, args=('readiness', task['id']))
        _appointment_notice(tasks)
        _, next_col = st.columns([4, 1])
        with next_col:
            st.button('Next', key='flyover_next', type='primary', icon=':material/arrow_forward:',
                      icon_position='right', width='stretch', on_click=go, args=('readiness',))


def _office_hours(task: dict) -> None:
    """The task's offices with their published hours, and how they meet the free times."""
    offices = task.get('offices') or []
    if not offices:
        return
    windows = _windows()
    st.markdown('#### Office hours')
    for office in offices:
        badge = '' if office['verification_status'] == 'verified' else ' :orange-badge[Not verified]'
        st.markdown(f'**{office["name"]}**{badge}')
        if office.get('address'):
            st.caption(office['address'])
        summary = hours_summary(office)
        st.write(summary if summary == 'No hours published' else summary + ' (Pacific time)')
        st.caption(office['period_note'])
        if windows:
            st.caption(match_line(office, windows))


def _checklist(data: dict, task: dict, api_url: str) -> None:
    st.markdown('### ' + task['title'])
    st.html(f'<div class="fly-card-meta">{_pill(task["status"])}'
            f'<span class="gate-priority">{esc(task["priority"])}</span></div>')
    if note := due_note(task, data['as_of']):
        getattr(st, note[0])(note[1])
    st.html('<p class="fly-note"><b>Not verified</b> means our team hasn\'t double-checked that '
            'detail with the official source yet. Use it to plan, and confirm with the office.</p>')
    for blocker in task.get('blockers') or []:
        st.warning(blocker['explanation'])
        if blocker.get('unlocks_on'):
            st.caption('Listed unlock date: ' + blocker['unlocks_on'])
    guide = task.get('before_you_go') or {}
    documents = list(dict.fromkeys(guide.get('required_documents') or []))
    selected = st.session_state.setdefault('documents_on_hand', {}).setdefault(task['id'], {})
    for document in documents:
        key = f'flyover_doc:{task["id"]}:{document}'
        if key not in st.session_state:
            st.session_state[key] = selected.get(document, False)
        selected[document] = st.checkbox(document, key=key)
    if documents:
        st.caption('Checked documents are your inventory, not a readiness or eligibility decision.')
    else:
        st.html('<p class="fly-note">No document list on file yet. Ask the office what to bring.</p>')
    details, sources = st.columns([1, 1], gap='large')
    with details:
        st.markdown('#### Before you visit')
        missing = []
        for label, field in VISIT_FACTS:
            if not (value := guide.get(field)):
                missing.append(label)
                continue
            # The fact as sourced (it may contain a link), with a badge when it's unverified.
            badge = '' if fact_verified(guide, field) else ' :orange-badge[Not verified]'
            st.markdown(f'**{label}:** {value}{badge}')
        _office_hours(task)
        if missing:
            # One line for everything not on file, instead of the same warning four times.
            st.html(f'<p class="fly-note">Not on file yet: {esc(", ".join(missing))}. '
                    'Confirm with the office.</p>')
        if link := safe_url(guide.get('official_url')):
            st.link_button('Official visit information', link)
    with sources:
        st.markdown('#### Where this information comes from')
        st.html(f'<div class="fly-sheet">{_source_rows(task.get("sources") or [])}</div>')
    for warning in guide.get('warnings') or []:
        st.warning(warning)
    _resolve_section(task, api_url)
    _reminder_section(data, task, api_url)
    if task['status'] in ('Ready', 'In Progress') and st.button(
            'Mark this step completed', key='flyover_detail_complete', type='primary'):
        try:
            result = client.change_status(api_url, data, task['id'], 'Completed')
        except (requests.RequestException, ValueError):
            st.error('Could not update this step. Your progress has been kept. Try again.')
        else:
            # Same feedback as the status selector: message, and confetti back on page 1.
            _record_update(task, result, api_url)
            go('home')
            st.rerun()


PACIFIC = ZoneInfo('America/Los_Angeles')
TEST_SENDER_NOTE = ("While the team uses Resend's test sender, only the Resend account's own "
                    'email address can receive reminders.')
# What each email-service status means for the student, in plain words.
REMINDER_STATUS_TEXT = {
    'scheduled': ('info', 'Waiting to be sent at the time you picked.'),
    'queued': ('info', 'About to be sent.'),
    'sent': ('info', 'Sent. It should reach your inbox in a minute or two.'),
    'delivered': ('success', ("Delivered to your email provider. Can't see it? Check Spam and "
                             'Promotions.')),
    'opened': ('success', 'Delivered and opened.'),
    'clicked': ('success', 'Delivered and opened.'),
    'delivery_delayed': ('warning', ("Delayed: the email service is still trying (for up to "
                                    '14 hours).')),
    'canceled': ('info', 'Cancelled. It will not be sent.'),
    'bounced': ('error', 'Not delivered: your email provider rejected it. ' + TEST_SENDER_NOTE),
    'failed': ('error', 'Not delivered: the email service could not send it. ' + TEST_SENDER_NOTE),
    'suppressed': ('error', 'Not sent: this address is on the email service\'s blocked list.'),
    'complained': ('warning', 'Delivered, but marked as spam.'),
}


def _reminders() -> list[dict]:
    """Reminders scheduled in this session: Resend holds them, we keep their IDs to cancel."""
    return st.session_state.setdefault('flyover_reminders', [])


def _when(iso: str) -> str:
    return f'{datetime.fromisoformat(iso).astimezone(PACIFIC):%a %b %d, %I:%M %p} Pacific'


def _cancel_task_reminders(api_url: str, task_id: str) -> bool:
    """Cancel this task's pending reminders (on completion). False if any wasn't confirmed."""
    confirmed = True
    for reminder in [r for r in _reminders() if r['task_id'] == task_id]:
        try:
            client.cancel_reminder(api_url, reminder['reminder_id'])
        except client.ReminderError:
            confirmed = False  # kept in the list, so the student can try Cancel again
            continue
        _reminders().remove(reminder)
    return confirmed


def _cancel_one(api_url: str, reminder_id: str) -> None:
    """Cancel button callback."""
    reminder = next((r for r in _reminders() if r['reminder_id'] == reminder_id), None)
    if reminder is None:
        return
    try:
        client.cancel_reminder(api_url, reminder_id)
    except client.ReminderError as error:
        st.session_state['flyover_reminder_note'] = (reminder['task_id'], 'error', str(error))
        return
    _reminders().remove(reminder)
    st.session_state['flyover_reminder_note'] = (reminder['task_id'], 'info',
                                                 'Reminder cancelled.')


def _check_status(api_url: str, reminder_id: str) -> None:
    """Check status callback: ask the email service what happened to this reminder."""
    try:
        event = client.reminder_status(api_url, reminder_id)
    except client.ReminderError as error:
        result = ('error', str(error))
    else:
        result = REMINDER_STATUS_TEXT.get(event, ('info', 'Status unknown. Try again later.'))
    st.session_state.setdefault('flyover_reminder_status', {})[reminder_id] = result


def _reminder_section(data: dict, task: dict, api_url: str) -> None:
    """Email me a reminder: one scheduled email through the API (Resend), for this task."""
    email = (st.session_state.get('flyover_account') or {}).get('email')
    if task['status'] == 'Completed' or not email:
        return
    st.markdown('#### Email me a reminder')
    today = datetime.now(PACIFIC).date()
    with st.form(f'fly_reminder_form:{task["id"]}', border=False):
        day_col, time_col = st.columns(2)
        with day_col:
            day = st.date_input('Day', value=today + timedelta(days=1), min_value=today,
                                max_value=today + timedelta(days=30),
                                key=f'fly_rem_day:{task["id"]}')
        with time_col:
            at = st.time_input('Time (Pacific)', value=time(9, 0), step=900,
                               key=f'fly_rem_time:{task["id"]}')
        consent = st.checkbox(f'Email this reminder to {masked(email)}',
                              key=f'fly_rem_ok:{task["id"]}')
        submitted = st.form_submit_button('Schedule reminder')
    st.caption("A nudge to act on this step. It doesn't book anything, and the demo only emails "
               'addresses the team allowed.')
    if submitted:
        if not consent:
            st.error('Tick the box to agree to the email first.')
        elif day is None or at is None:
            st.error('Choose a day and a time.')
        else:
            send_at = datetime.combine(day, at, tzinfo=PACIFIC)
            try:
                with st.spinner('Scheduling your reminder…'):
                    result = client.schedule_reminder(api_url, data, email, task['id'], send_at,
                                                      str(uuid.uuid4()))
            except client.ReminderError as error:
                st.error(str(error))
            else:
                _reminders().append({'reminder_id': result['reminder_id'], 'task_id': task['id'],
                                     'send_at': result['send_at']})
                st.success(f'Reminder set for {_when(result["send_at"])}. It will arrive even '
                           'if you close this page.')
    note = st.session_state.pop('flyover_reminder_note', None)
    if note and note[0] == task['id']:
        (st.error if note[1] == 'error' else st.info)(note[2])
    for reminder in [r for r in _reminders() if r['task_id'] == task['id']]:
        line, button = st.columns([4, 1], vertical_alignment='center')
        with line:
            st.write(f'Reminder: {_when(reminder["send_at"])}')
        with button:
            st.button('Cancel', key=f'fly_rem_cancel:{reminder["reminder_id"]}', type='tertiary',
                      on_click=_cancel_one, args=(api_url, reminder['reminder_id']))
        st.button('Check status', key=f'fly_rem_status:{reminder["reminder_id"]}',
                  type='tertiary', on_click=_check_status, args=(api_url, reminder['reminder_id']))
        if shown := st.session_state.get('flyover_reminder_status', {}).get(
                reminder['reminder_id']):
            kind, text = shown
            getattr(st, kind)(text)


def _resolve(api_url: str, task_id: str) -> None:
    """Button callback: ask the API to resolve the blocker, then show only what it returns."""
    st.session_state.pop('flyover_resolve_error', None)
    try:
        result, draft = client.resolve_blocker(api_url, st.session_state['flyover_data'], task_id)
    except (requests.RequestException, ValueError):
        # Nothing changed on screen; the API's own reason text stays out of the page.
        st.session_state['flyover_resolve_error'] = task_id
        return
    st.session_state['flyover_data'] = result
    # None = the API had no draft for this blocker; the step still moved to "waiting on an office".
    st.session_state['flyover_email'] = {'task_id': task_id, 'draft': draft}


def _resolve_section(task: dict, api_url: str) -> None:
    """For a blocked task: the "Resolve blocker" button and, once used, the API's email draft."""
    if task['status'] == 'Blocked' and task.get('next_action'):
        st.button('Resolve blocker', key='flyover_resolve:' + task['id'], on_click=_resolve,
                  args=(api_url, task['id']), icon=':material/mail:',
                  help='Marks the missing step as waiting on an office and drafts an email to send.')
    if st.session_state.get('flyover_resolve_error') == task['id']:
        st.error('Could not resolve this blocker. Your progress has been kept. Try again.')
    email = st.session_state.get('flyover_email') or {}
    if email.get('task_id') != task['id']:
        return
    if draft := email.get('draft'):
        st.warning('Draft email. Not verified. Fill in the placeholders, review it, and send it '
                   'yourself. Nothing has been sent.')
        st.code(f'Subject: {draft["subject"]}\n\n{draft["body"]}', language=None, wrap_lines=True)
    else:
        st.info('The missing step is now waiting on an office. No email draft is available.')


def _pill(status: str) -> str:
    css, symbol = PILLS.get(status, ('neutral', '?'))
    return f'<span class="fly-pill {css}">{symbol} {esc(status or "Unknown")}</span>'


def _open_prereqs(task_id: str) -> None:
    st.session_state['flyover_prereq_open'] = task_id
    st.session_state['flyover_quote'] = st.session_state.get('flyover_quote', -1) + 1


SITE_NAMES = {
    'crc.losrios.edu': 'Cosumnes River College', 'losrios.edu': 'Los Rios Colleges',
    'dmv.ca.gov': 'California DMV', 'ssa.gov': 'Social Security', 'i94.cbp.dhs.gov': 'U.S. CBP (I-94)',
    'cbp.gov': 'U.S. Customs and Border Protection', 'fmjfee.com': 'SEVIS I-901 fee site',
    'studyinthestates.dhs.gov': 'Study in the States (DHS)', 'ice.gov': 'U.S. ICE',
}


ACRONYMS = {'real id': 'REAL ID', 'id': 'ID', 'ssn': 'SSN', 'sevis': 'SEVIS', 'dmv': 'DMV',
            'crc': 'CRC', 'i94': 'I-94', 'i 94': 'I-94', 'f 1': 'F-1'}


def source_label(url: str | None) -> str:
    """'Cosumnes River College · International students office', instead of a rule ID."""
    if not (link := safe_url(url)):
        return 'Official source'
    host = urlsplit(link).hostname.removeprefix('www.')
    site = SITE_NAMES.get(host) or next(
        (name for domain, name in SITE_NAMES.items() if host.endswith('.' + domain)), host)
    page = [part for part in urlsplit(link).path.split('/') if part]
    words = page[-1].replace('-', ' ').replace('_', ' ').strip() if page else ''
    words = re.sub(r'(\s+[a-z]{2,5}\s?\d+)+$', '', words)  # drop form codes like "ffdl 8"
    # Keep the acronyms students know in capitals ("REAL ID", "SSN"), not "real id".
    words = re.sub(r'\b(real id|id|ssn|sevis|dmv|crc|i94|i 94|f 1)\b',
                   lambda m: ACRONYMS[m.group(1)], words)
    return f'{site} · {words[:1].upper()}{words[1:]}' if words else site


def _source_rows(sources: list[dict]) -> str:
    rows = []
    for source in sources:
        url = safe_url(source.get('url'))
        label = esc(source_label(source.get('url')))
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'
                if url else f'<span>{label}</span>')
        if source_verified(source):
            tag = '<span class="fly-tag ok">Verified</span>'
            when = f'Double-checked by our team on {esc(source.get("last_verified"))}'
        else:
            tag = '<span class="fly-tag">⚠ Not verified</span>'
            when = 'Not double-checked by our team yet'
        rows.append(f'<div class="fly-src"><div>{link}<small>{when}</small></div>{tag}</div>')
    return ''.join(rows) or '<p class="fly-muted">No sources on file. Confirm with the office.</p>'


@st.dialog('Before you go', width='medium')
def _prereq_dialog(task: dict, by_id: dict) -> None:
    st.html(f'<h3 class="fly-sheet-title">{esc(task["title"])}</h3>')
    prereqs = [by_id[key] for key in task.get('prerequisites') or [] if key in by_id]
    if prereqs:
        items = ''.join(f'<li><span>{esc(p["title"])}</span>{_pill(p["status"])}</li>' for p in prereqs)
        needs = f'<ul class="fly-needs">{items}</ul>'
    else:
        needs = '<p class="fly-muted">No other step has to come first.</p>'
    documents: list[str] = []
    for item in [task, *prereqs]:
        documents += (item.get('before_you_go') or {}).get('required_documents') or []
    documents = list(dict.fromkeys(documents))
    docs = (f'<ul class="fly-docs">{"".join(f"<li>{esc(d)}</li>" for d in documents)}</ul>' if documents
            else '<p class="fly-muted">No document list on file. Confirm with the office.</p>')
    sources = list({s.get('rule_id'): s for item in [task, *prereqs] for s in item.get('sources') or []}.values())
    st.html('<div class="fly-sheet">'
            f'<h4>Needs first</h4>{needs}<h4>Bring these</h4>{docs}'
            f'<h4>Our sources</h4>{_source_rows(sources)}</div>')
    st.caption('Not verified unless marked. Confirm requirements with the office before your visit.')
    if st.button('Open full checklist', key='flyover_prereq_full', type='primary'):
        st.session_state['flyover_detail'] = task['id']
        st.session_state['flyover_scroll'] = 'checklist'
        st.rerun()


def _tour() -> None:
    """Send the spotlight tour once per session (and again on Settings → Replay tutorial).

    The browser remembers a finished or skipped tour for the tab (sessionStorage), so a sent
    tour that was already seen doesn't show again. Nothing here calls the API.
    """
    replay = st.session_state.pop('flyover_tour_replay', False)
    if st.session_state.get('flyover_tour_sent') and not replay:
        return
    st.session_state['flyover_tour_sent'] = True
    with st.container(key='fly_tour'):
        st.iframe(tour_script(replay, bool(st.session_state.get('flyover_reduce_motion'))),
                  height=1)


def _scroll(target: str) -> None:
    """Streamlit keeps the scroll position between pages; move it where the click meant to go."""
    smooth = 'auto' if st.session_state.get('flyover_reduce_motion') else 'smooth'
    with st.container(key='fly_scroll'):
        st.iframe(f'''<script>
setTimeout(() => {{
  const doc = window.parent.document, main = doc.querySelector('[data-testid="stMain"]');
  if (!main) return;
  const target = {json.dumps(target)};
  let top = 0;
  if (target === 'airshow') {{
    const runway = doc.querySelector('.fly-runway'), box = runway && runway.getBoundingClientRect();
    const tall = box && box.height > main.clientHeight * 1.5;
    const stage = doc.querySelector('.fly-stage'), stageH = stage ? stage.offsetHeight : 0;
    // Land with the Airshow title near the top and the form just below it.
    const reveal = doc.querySelector('.fly-reveal');
    if (box && tall) top = main.scrollTop + box.top + box.height - main.clientHeight + 4 + stageH / 2 - 170;
    else if (reveal) top = main.scrollTop + reveal.getBoundingClientRect().top - 90;
  }} else if (target === 'checklist') {{
    const el = doc.querySelector('.st-key-fly_checklist');
    if (el) top = main.scrollTop + el.getBoundingClientRect().top - 90;
  }}
  main.scrollTo({{top: Math.max(0, top), behavior: target === 'top' ? 'auto' : '{smooth}'}});
}}, 250);
</script>''', height=1)


def _task_table(group: str, tasks: list[dict], by_id: dict, empty: str) -> None:
    with st.container(key=f'fly_table_{group}'):
        st.html('<div class="fly-thead"><span>Task</span><span>Status</span><span>Needs first</span></div>')
        if not tasks:
            st.html(f'<p class="fly-empty">{esc(empty)}</p>')
        for task in tasks:
            with st.container(key=f'fly_row_{group}_{task["id"]}'):
                left, mid, right = st.columns([1.7, 1, 1.25], vertical_alignment='center', gap='medium')
                with left:
                    st.html(f'<div class="fly-task">{esc(task["title"])}<small>{esc(task["priority"])}</small></div>')
                with mid:
                    st.html(f'<div class="fly-center">{_pill(task["status"])}</div>')
                with right:
                    names = [by_id[key]['title'] for key in task.get('prerequisites') or [] if key in by_id]
                    st.button(' · '.join(names) if names else 'No prerequisites',
                              key=f'fly_pre:{group}:{task["id"]}', type='tertiary',
                              help='Documents to bring and our sources', on_click=_open_prereqs,
                              args=(task['id'],))


def _focus_card(task: dict, kind: str) -> None:
    """kind 'now': the step to do first, with its checklist button. 'next': a quieter preview."""
    with st.container(key=f'fly_{kind}_card'):
        label = 'Now' if kind == 'now' else 'Up next'
        st.html(f'<div class="fly-card-label">{label}</div>'
                f'<div class="fly-card-title">{esc(task["title"])}</div>'
                f'<div class="fly-card-meta"><span class="gate-priority">{esc(task["priority"])}'
                f'</span>{_pill(task["status"])}</div>')
        if task['status'] == 'In Progress':
            # In Progress means waiting on an office, never that the task is done.
            st.caption('Waiting on an office.')
        if note := due_note(task, st.session_state['flyover_data']['as_of']):
            st.caption(note[1])
        if kind == 'now':
            if task.get('next_action'):
                st.caption(task['next_action']['text'])
            st.button('Open checklist', key='fly_focus_open', type='primary',
                      icon=':material/checklist:', on_click=go, args=('readiness', task['id']))


def _quote_card() -> None:
    index = st.session_state.get('flyover_quote', 0) % len(ENCOURAGEMENTS)
    dots = ''.join(f'<i class="{"on" if k == index else ""}"></i>' for k in range(len(ENCOURAGEMENTS)))
    st.html(f'<aside class="fly-quote" aria-label="Encouragement" data-quote="{index}">'
            '<span class="mark" aria-hidden="true">“</span>'
            f'<blockquote>{esc(ENCOURAGEMENTS[index])}</blockquote>'
            '<footer><span>A new line each time you open a checklist</span>'
            f'<span class="dots" aria-hidden="true">{dots}</span></footer></aside>')


def _readiness(data: dict, api_url: str) -> None:
    tasks = data['workflow']
    by_id = {task['id']: task for task in tasks}
    back_col, skip_col = st.columns([1, 1], vertical_alignment='center')
    with back_col:
        st.button('Back to my journey', key='flyover_back', on_click=go, args=('home',),
                  icon=':material/west:', type='tertiary')
    with skip_col:
        st.button('Skip to Airshow', key='flyover_skip', on_click=go, args=('assistant',),
                  icon=':material/south:', icon_position='right', type='tertiary')
    done = sum(task['status'] == 'Completed' for task in tasks)
    with st.container(key='fly_readiness'):
        head, meter = st.columns([2, 1], vertical_alignment='bottom')
        with head:
            st.subheader('Readiness')
            st.caption('Where you stand. Tap a prerequisite for the documents to bring and where '
                       'the guidance comes from.')
        with meter:
            width = 100 * done / len(tasks) if tasks else 0
            st.html(f'<div class="fly-meter"><b>{done} of {len(tasks)} steps complete</b>'
                    f'<div class="bar"><span style="width:{width:.0f}%"></span></div></div>')
        main, aside = st.columns([2.4, 1], gap='large')
        with main:
            _task_table('ready', [t for t in tasks if t['status'] in ('Completed', 'In Progress')], by_id,
                        'Nothing finished yet. Your first completed step will land here.')
            st.caption('Completing a step does not confirm eligibility. Backend status and prerequisites decide.')
        with aside, st.container(key='fly_quote_col'):
            _quote_card()
    with st.container(key='fly_takeoff'):
        st.subheader('Before you take off')
        queue = task_queue(tasks)
        if queue:
            st.caption('One step at a time, most important first. A step another one needs '
                       'always comes before it.')
            _focus_card(queue[0], 'now')
            if len(queue) > 1:
                _focus_card(queue[1], 'next')
        else:
            st.html('<p class="fly-empty">Nothing left ahead. Confirm requirements with each '
                    'office before you visit.</p>')
        ahead = [t for t in tasks if t['status'] in ('Ready', 'Blocked')]
        with st.expander(f'View all tasks ahead ({len(ahead)})'):
            _task_table('takeoff', ahead, by_id,
                        'Nothing left ahead. Confirm requirements with each office before you visit.')
        if tasks:
            if st.session_state.get('flyover_detail') not in by_id:
                st.session_state['flyover_detail'] = (active_task(tasks) or tasks[0])['id']
            with st.container(key='fly_checklist'):
                chosen = st.selectbox('Your checklist', list(by_id), key='flyover_detail',
                                      format_func=lambda key: by_id[key]['title'])
                _checklist(data, by_id[chosen], api_url)
        else:
            st.info('No workflow steps are available yet.')
    if (opened := st.session_state.pop('flyover_prereq_open', None)) in by_id:
        _prereq_dialog(by_id[opened], by_id)


def _handoff_contact() -> str:
    """' Contact: <email>' when the student switched it on in their profile; '' otherwise."""
    account = st.session_state.get('flyover_account') or {}
    if st.session_state.get('flyover_handoff_email') and account.get('email'):
        return ' Contact: ' + account['email']
    return ''


def _keep_handoff_email() -> None:
    st.session_state['flyover_handoff_email'] = st.session_state['flyover_handoff_email_widget']


def _profile_page(data: dict) -> None:
    """The profile dashboard: this session's answers, progress and handoff choices."""
    profile, tasks = data['student_profile'], data['workflow']
    st.button('Back to my journey', key='flyover_profile_back', on_click=go, args=('home',),
              icon=':material/west:', type='tertiary')
    with st.container(key='fly_profile_page'):
        st.subheader('Your profile')
        if account := st.session_state.get('flyover_account'):
            st.caption('Signed in as ' + masked(account['email']))
        arrival = date.fromisoformat(profile['arrival_date'])
        days = (date.fromisoformat(data['as_of']) - arrival).days
        since = f'{days} days ago' if days >= 0 else f'in {-days} days'
        facts = [('School', profile['institution']), ('Visa type', profile['visa_type']),
                 ('Arrival date', f'{arrival:%B} {arrival.day}, {arrival.year} · {since}'),
                 ('Has an SSN', 'Yes' if profile['has_ssn'] else 'No'),
                 ('Enrollment date', date.fromisoformat(profile['enrollment_date']).strftime('%B %d, %Y')
                  if profile.get('enrollment_date') else 'Not given')]
        st.html('<dl class="fly-facts">' + ''.join(
            f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>' for label, value in facts) + '</dl>')
        st.button('Edit in Profile setup', key='flyover_profile_edit', on_click=go,
                  args=('home',), icon=':material/edit:')
    with st.container(key='fly_profile_progress'):
        st.subheader('Progress')
        columns = st.columns(4)
        for column, status in zip(columns, ('Completed', 'In Progress', 'Ready', 'Blocked'),
                                  strict=True):
            column.metric(status, sum(task['status'] == status for task in tasks))
        if upcoming := active_task(tasks):
            st.markdown(f'**Next step:** {upcoming["title"]}')
            st.button('Open its checklist', key='flyover_profile_next', type='primary',
                      on_click=go, args=('readiness', upcoming['id']))
        else:
            st.success('Every step is completed.')
    with st.container(key='fly_profile_more'):
        st.subheader('Free times and handoffs')
        windows = _windows()
        st.write('Free times: ' + (describe_windows(windows) if windows else
                                   'none yet. Add them under the appointment notice on page 1.'))
        # Streamlit forgets a widget's value once it's off screen, so the choice is copied to
        # its own key (like Settings' toggles) and survives going back to the other pages.
        st.toggle('Include my email in handoffs', key='flyover_handoff_email_widget',
                  value=bool(st.session_state.get('flyover_handoff_email')),
                  on_change=_keep_handoff_email,
                  help='Adds a Contact line to handoffs you generate and export. Off by default; '
                       'nothing is sent anywhere.')
    st.caption('Everything here lives in this browser session. Sign out (in Settings) clears it.')


def _handoff(data: dict, goal: str, professional: str, office: str = '') -> dict:
    # office = the student's own label for "Another office"; '' for the preset professionals.
    profile = data['student_profile']
    tasks = data['workflow']

    def titles(status: str) -> str:
        return ', '.join(t['title'] for t in tasks if t['status'] == status) or 'none'

    task = next((t for t in tasks if t['id'] == st.session_state.get('flyover_detail')), None) or active_task(tasks)
    documents = list(dict.fromkeys(((task or {}).get('before_you_go') or {}).get('required_documents') or []))
    arrival = date.fromisoformat(profile['arrival_date'])
    title = ('Handoff for ' + office) if office else 'Handoff for your ' + professional.split(' (')[0]
    return {'title': title, 'sections': [
        ('Who I am', [(f'{profile["visa_type"]} student at {profile["institution"]}. Arrived '
                       f'{arrival:%B} {arrival.day}, {arrival.year}. '
                       f'{"Has an" if profile["has_ssn"] else "No"} SSN. Name: [YOUR NAME]'
                       + _handoff_contact())]),
        ('What I’m here to do', [goal]),
        ('Where I am', [f'Done: {titles("Completed")}', f'In progress: {titles("In Progress")}',
                        f'Blocked: {titles("Blocked")}']),
        ('Questions to ask', PROFESSIONALS[professional]),
        ('Bring with me', documents or ['No document list on file. Confirm with the office.']),
    ]}


def _md(text: str) -> str:
    """Typed text stays literal in a Markdown export: '*' or '#' is shown, not formatted."""
    # Only characters that format inline (emphasis, code, links, HTML, headings, tables);
    # ordinary '-', '(' or '.' stay readable, as in "F-1" or "(DSO)".
    return re.sub(r'([\\`*_\[\]<>#|])', r'\\\1', text)


def _handoff_text(doc: dict, markdown: bool) -> str:
    clean = _md if markdown else str
    lines = [('# ' if markdown else '') + clean(doc['title']), '']
    for heading, items in doc['sections']:
        lines.append(('## ' if markdown else '') + heading)
        items = [clean(item) for item in items]
        lines += [('- ' if markdown else '• ') + item for item in items] if len(items) > 1 else items
        lines.append('')
    lines.append('Drafted from a template. Not verified. Confirm every requirement with the office.')
    return '\n'.join(lines)


def _clear_handoff() -> None:
    st.session_state.pop('flyover_handoff', None)


def _assistant(data: dict, api_url: str) -> None:
    st.html(flight_scene(static=bool(st.session_state.get('flyover_reduce_motion'))))
    with st.container(key='fly_airshow'):
        # Includes the email switch, so turning it on or off clears an older handoff.
        context = json.dumps([st.session_state.get('flyover_detail'), data['student_profile'],
                              bool(st.session_state.get('flyover_handoff_email'))], sort_keys=True)
        if st.session_state.get('flyover_handoff_context') != context:
            st.session_state.pop('flyover_handoff', None)
            st.session_state['flyover_handoff_context'] = context
        st.subheader('Handoff for your visit')
        st.info('The handoff below is drafted from a template on this page, not by AI, and '
                'nothing is sent.')
        with st.container(key='fly_prompt'):
            goal = st.text_area('What you want to accomplish, given your situation', max_chars=1000,
                                placeholder='For example: get my California ID. I have my passport, '
                                            'I-20 and I-94 but no SSN.',
                                key='flyover_goal', on_change=_clear_handoff)
            pro_col, button_col = st.columns([2, 1], vertical_alignment='bottom')
            with pro_col:
                professional = st.selectbox('Professional you’ll visit', list(PROFESSIONALS),
                                            key='flyover_pro', on_change=_clear_handoff)
                office = ''
                if professional == OTHER_OFFICE:
                    # Its own field; the preset key above still picks the generic questions.
                    office = ' '.join(st.text_input(
                        'Office name', max_chars=OFFICE_NAME_MAX, key='flyover_office',
                        on_change=_clear_handoff, placeholder='For example: Student services desk',
                        help='The office, not a person. It stays on this page and in your export.',
                    ).split())
                    if not office:
                        st.caption('Enter the office name to generate this handoff.')
                else:
                    # A label typed for another office must not follow you to a preset.
                    st.session_state.pop('flyover_office', None)
            with button_col:
                if st.button('Generate handoff', key='flyover_prepare_handoff', type='primary',
                             disabled=not goal.strip() or (professional == OTHER_OFFICE and not office),
                             width='stretch'):
                    st.session_state['flyover_handoff'] = _handoff(data, goal.strip(), professional,
                                                                   office)
        if doc := st.session_state.get('flyover_handoff'):
            body = ''.join(f'<h4>{esc(h)}</h4>' + (f'<p>{esc(items[0])}</p>' if len(items) == 1 else
                           '<ul>' + ''.join(f'<li>{esc(i)}</li>' for i in items) + '</ul>')
                           for h, items in doc['sections'])
            st.html(f'<article class="fly-doc"><div class="fly-doc-top"><h3>{esc(doc["title"])}</h3>'
                    f'<span class="fly-tag">⚠ Preview · Not verified</span></div>{body}'
                    '<p class="fine">Drafted from a template on this page, not by AI. '
                    'Never add document numbers. Confirm every requirement with the office.</p></article>')
            fmt_col, button_col, _ = st.columns([1, 1, 2], vertical_alignment='bottom')
            with fmt_col:
                extension = st.selectbox('Export as', ['Text (.txt)', 'Markdown (.md)'], key='flyover_export')
            markdown = extension.startswith('Markdown')
            with button_col:
                st.download_button('Export handoff', _handoff_text(doc, markdown),
                                   file_name='flyover-handoff.' + ('md' if markdown else 'txt'),
                                   mime='text/markdown' if markdown else 'text/plain', key='flyover_download')
        else:
            st.caption('Your handoff document appears here once you generate it.')


def render_app() -> None:
    st.set_page_config(page_title='Flyover · Your next chapter', page_icon='✈', layout='wide',
                       initial_sidebar_state='collapsed')
    api_url = os.getenv('API_URL', 'http://localhost:8000').rstrip('/')
    st.html('<style>' + (ASSETS / 'style.css').read_text() + '</style>')
    if st.session_state.get('flyover_reduce_motion'):
        st.html('<style>' + (ASSETS / 'reduce-motion.css').read_text() + '</style>')
    elif st.session_state.get('flyover_pause_banner'):
        st.html('<style>.flyover-slide{animation-play-state:paused!important}</style>')
    # The launcher's logo comes from our own committed SVG; the rest of its look is in style.css.
    st.html('<style>.st-key-flyover_ai [data-testid="stPopoverButton"]{background-image:url('
            + svg_asset('ai-help-icon.svg') + ')!important}</style>')
    if not signed_in():
        # The demo sign-in is the first screen; it also asks the profile questions.
        render_signin(api_url)
        return
    panel = _header()
    if 'flyover_data' not in st.session_state:
        try:
            st.session_state['flyover_data'] = client.fetch_fresh_workflow(api_url)
        except (requests.RequestException, ValueError):
            with panel:
                st.caption('Airshow can answer once your workflow has loaded.')
            st.error('Could not load your workflow. Check that the API is running and try again.')
            st.button('Retry', key='flyover_retry')
            st.stop()
    data = st.session_state['flyover_data']
    sync_profile_context(data['student_profile'])
    page = st.session_state.get('flyover_page', 'home')
    with panel:
        _chat(data, api_url, page)
    if page == 'home':
        _profile(data, api_url)
        if data.get('is_mock'):
            st.warning('Sample data. Not verified. Do not rely on it.')
        elif data['student_profile'].get('school_verified') is not True:
            st.caption('School-specific guidance is not verified. Confirm requirements with your DSO.')
        _workflow(data, api_url)
    elif page == 'profile':
        _profile_page(data)
    else:
        _readiness(data, api_url)
        _assistant(data, api_url)
    if target := st.session_state.pop('flyover_scroll', None):
        _scroll(target)
    if page == 'home':
        _tour()
    st.html('<footer class="flyover-footer">Flyover · A little preparation. A world of possibility.</footer>')
