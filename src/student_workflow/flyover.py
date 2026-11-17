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
    HOURS_NOT_CONFIRMED,
    NO_HOURS_NOTE,
    TIMEZONE_LABEL,
    describe_windows,
    first_with_guidance,
    hours_summary,
    match_line,
    normalize_windows,
    notice_key,
    upcoming_closures,
    visit_hours,
)
from .flyover_art import ASSETS, banner, flight_map, flight_scene, logo, svg_asset
from .flyover_checklist import document_groups, fact_sources, task_actions
from .flyover_scenario import (
    DEMO_PROFILE,
    SCENARIO_AS_OF,
    export_line,
    long_date,
    notice_html,
)
from .flyover_signin import (
    ENROLLMENT_PRIORITIES,
    ENROLLMENT_TERMS,
    entered,
    masked,
    render_signin,
    sign_out,
)
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

# ---- Navigation (guide Part 1). Every page id maps to exactly one label; nothing is inferred.
DESTINATIONS = {
    'workflow': 'Workflow and readiness',
    'checklist': 'Checklist',
    'alerts': 'Alerts',
    'profile': 'Profile',
    'handoff': 'Office handoff',
    'updates': 'Updates and credits',
}
TABS = ('workflow', 'checklist', 'alerts')  # the sibling tabs under the header
# Older page names (saved sessions, Replay tutorial) -> the destination they now mean.
PAGE_ALIASES = {'home': 'workflow', 'readiness': 'workflow', 'assistant': 'handoff'}
# What POST /assistant hears as page_context (a display hint; see the contract).
PAGE_CONTEXT = {'workflow': 'journey', 'handoff': 'airshow'}  # every other page: 'readiness'
# Session-level state, never a widget key: the one task every page shows (flyover_detail).
TASK_KEY = 'flyover_detail'
STATUS_CHOICES = ['Ready', 'In Progress', 'Completed']
CREDITS_URL = 'https://github.com/ota-afk/crc-student-workflow/blob/main/docs/credits.md'


def esc(value) -> str:
    return html.escape('' if value is None else str(value))


def destination(page: str | None) -> str:
    """The destination id for any page name; unknown names land on Workflow and readiness."""
    page = PAGE_ALIASES.get(page, page)
    return page if page in DESTINATIONS else 'workflow'


def go(page: str, task_id: str | None = None) -> None:
    """Navigate. With task_id, that task becomes the selected task on every page."""
    st.session_state['flyover_page'] = destination(page)
    st.session_state['flyover_scroll'] = 'top'
    if task_id:
        _select_task(task_id)
        st.session_state['flyover_quote'] = st.session_state.get('flyover_quote', -1) + 1


def _select_task(task_id: str) -> None:
    """Choose a task without leaving the page. Saves nothing and plays no animation."""
    st.session_state[TASK_KEY] = task_id
    st.session_state.pop('flyover_next_offer', None)  # the choice has been made
    st.session_state.pop('flyover_reopen_block', None)


def _pick(widget: str) -> None:
    """Callback for a task selector: copy the widget's choice into the shared task ID."""
    if chosen := st.session_state.get(widget):
        _select_task(chosen)


def _goto(widget: str) -> None:
    """Callback for the header's Go to and the sibling tabs (they write the same page)."""
    if chosen := st.session_state.get(widget):
        go(chosen)
    # None: the active tab was pressed again. Stay; the next run shows it selected again.


def selected_task_id(tasks: list[dict]) -> str | None:
    """The student's chosen task; until they choose, the suggested one (active_task)."""
    if (chosen := st.session_state.get(TASK_KEY)) in {task['id'] for task in tasks}:
        return chosen
    if not tasks:
        return None
    suggestion = (active_task(tasks) or tasks[0])['id']
    st.session_state[TASK_KEY] = suggestion
    return suggestion


def _task_label(task: dict) -> str:
    return f'{task["title"]} · {task["status"]}'


def _task_picker(tasks: list[dict], widget: str, label: str) -> str:
    """A selector over the whole workflow (unfinished first, then completed), keyed by ID.

    Its widget key is its own; the choice lives in TASK_KEY, so every page agrees.
    """
    task_id = selected_task_id(tasks)
    by_id = {task['id']: task for task in tasks}
    order = [task['id'] for task in task_queue(tasks)]
    order += [task['id'] for task in tasks if task['id'] not in order]
    st.session_state[widget] = task_id
    st.selectbox(label, order, key=widget, format_func=lambda key: _task_label(by_id[key]),
                 on_change=_pick, args=(widget,))
    return task_id


def _replay_tour() -> None:
    # The tour points at page 1's controls, so go there and send it again.
    st.session_state['flyover_tour_replay'] = True
    st.session_state['flyover_page'] = 'home'


@st.dialog('Flight settings')
def settings() -> None:
    st.html(notice_html())  # the dialog covers the page, so it carries the notice too
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
    account = st.session_state.get('flyover_account')
    st.caption('Signed in as ' + masked(account['email']) if account
               else 'Demo visitor · no account, nothing saved after you leave')
    if st.button('Your profile', key='flyover_settings_profile', icon=':material/badge:',
                 on_click=go, args=('profile',)):
        st.rerun()
    if st.button('Sign out' if account else 'Leave the demo', key='flyover_sign_out',
                 on_click=sign_out):
        st.rerun()
    if st.button('Done', key='flyover_settings_done', type='primary'):
        st.rerun()


def _header(page: str):
    """The sticky header. Returns the AI Help dropdown, filled once the workflow has loaded.

    Order: logo, Go to, AI Help, Settings. On a phone, Go to drops to its own row so the
    logo, AI Help and Settings stay on the first one (style.css).
    """
    with st.container(key='flyover_header'):
        brand, nav, ai, gear = st.columns([5.2, 3, 1, 1], vertical_alignment='center')
        with brand:
            st.image(logo(), width=185)
        with nav:
            st.session_state['flyover_goto'] = page  # always shows where the student is
            st.selectbox('Go to', list(DESTINATIONS), key='flyover_goto',
                         format_func=DESTINATIONS.get, on_change=_goto, args=('flyover_goto',))
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


def _tabs(page: str) -> None:
    """Workflow and readiness, Checklist and Alerts as sibling tabs; same page as Go to."""
    st.session_state['flyover_tab'] = page if page in TABS else None
    with st.container(key='flyover_tabs'):
        st.segmented_control('Sections', TABS, key='flyover_tab', format_func=DESTINATIONS.get,
                             on_change=_goto, args=('flyover_tab',),
                             label_visibility='collapsed')


def _chat_context(data: dict, page: str) -> tuple[str, str | None]:
    """(page_context, task_id) for the dropdown: the page it is opened on and the chosen task."""
    return PAGE_CONTEXT.get(page, 'readiness'), selected_task_id(data['workflow'])


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
               f'{DESTINATIONS[page]} · as of {long_date(data["as_of"])}')
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
                term = st.selectbox(
                    'Enrollment term', list(ENROLLMENT_TERMS),
                    index=list(ENROLLMENT_TERMS).index(profile.get('enrollment_term')),
                    format_func=ENROLLMENT_TERMS.get, key='flyover_term',
                    help='Choose the semester these classes belong to.')
                priority = st.selectbox(
                    'Enrollment priority', list(ENROLLMENT_PRIORITIES),
                    index=list(ENROLLMENT_PRIORITIES).index(profile.get('enrollment_priority')),
                    format_func=ENROLLMENT_PRIORITIES.get, key='flyover_priority',
                    help='Use the priority listed in eServices. Your group determines the '
                         'published date range; eServices gives your exact appointment.')
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
                            'enrollment_date': enrolled.isoformat() if enrolled else None,
                            'enrollment_term': term, 'enrollment_priority': priority}
                        try:
                            # The spinner is the feedback; the page itself no longer dims.
                            with st.spinner('Building your workflow…'):
                                # The workflow's date (the scenario), never the API's today.
                                result = client.generate_workflow(
                                    api_url, profile, changes, as_of=data['as_of'])
                        except (requests.RequestException, ValueError):
                            st.error('Could not generate your workflow. Your progress has been kept. Try again.')
                        else:
                            st.session_state['flyover_data'] = result
                            st.session_state['flyover_clear_reset_confirmation'] = True
                            for key in (TASK_KEY, 'flyover_handoff',
                                        'flyover_map_done', 'flyover_celebrate', 'flyover_status_error',
                                        'flyover_email', 'flyover_resolve_error', 'flyover_popup_history',
                                        'flyover_chat_error', 'flyover_preferences',
                                        'flyover_appt_dismissed', 'flyover_next_offer',
                                        'flyover_reopen_block', 'flyover_boarding'):
                                st.session_state.pop(key, None)
                            for key in list(st.session_state):
                                if key.startswith('flyover_doc:'):
                                    del st.session_state[key]
                            st.session_state['flyover_flash'] = 'Your new workflow is ready to explore.'
                            st.rerun()
            st.caption('No names, document numbers or uploads. Your profile stays in this session.')
            for task in data['workflow']:
                _registration_info(task)
            st.button('View your profile', key='flyover_open_profile', type='tertiary',
                      icon=':material/badge:', on_click=go, args=('profile',))


SAVE_FAILED = 'Could not update this step. Your progress has been kept. Try again.'


def _save_status(api_url: str, task_id: str, widget: str) -> None:
    """The shared status callback. `widget` is the control that changed (the gate, a row's
    Edit status or the Checklist tab); the save always targets `task_id`.

    Success and failure both leave the selected task and the page as they were.
    """
    data = st.session_state['flyover_data']
    task = next((item for item in data['workflow'] if item['id'] == task_id), None)
    if task is None:
        return
    desired = st.session_state.get(widget)
    if desired == task['status']:
        return
    try:
        result = client.change_status(api_url, data, task_id, desired)
    except (requests.RequestException, ValueError):
        st.session_state[widget] = task['status']  # the previous status stays visible
        st.session_state['flyover_status_error'] = SAVE_FAILED
        return
    st.session_state[widget] = _record_update(task, result, api_url)['status']


def _reopen(api_url: str, task_id: str) -> None:
    """Reopen task callback: undo a completion, unless a completed task still needs this one."""
    st.session_state.pop('flyover_reopen_block', None)
    data = st.session_state['flyover_data']
    task = next((item for item in data['workflow'] if item['id'] == task_id), None)
    if task is None:
        return
    try:
        result = client.reopen_task(api_url, data, task_id)
    except client.DependentCompleted as error:
        # Named and linked (in _status_feedback), so the student can reopen that one first.
        st.session_state['flyover_reopen_block'] = {
            'task_id': task_id, 'dependents': [item['id'] for item in error.dependents]}
        return
    except (requests.RequestException, ValueError):
        st.session_state['flyover_status_error'] = ('Could not reopen this step. Your progress '
                                                    'has been kept. Try again.')
        return
    _record_update(task, result, api_url)


def _record_update(task: dict, result: dict, api_url: str | None = None) -> dict:
    """The one success path for every status control: keep the API's answer, then celebrate.

    Every status control and "Mark this step completed" land here, so they give the same
    feedback. Confetti only for a new move to Completed, as the API returned it, never for the
    click alone. The flags are consumed once by _status_feedback, and reduce motion keeps the
    message. The selected task never changes here: the next suggested task is only offered.
    """
    st.session_state['flyover_data'] = result
    st.session_state.pop('flyover_status_error', None)
    returned = next((item for item in result['workflow'] if item['id'] == task['id']), task)
    if returned['status'] == 'Completed' and task['status'] != 'Completed':
        st.session_state['flyover_celebrate'] = True
        upcoming = active_task(result['workflow'])
        # The boarding board is driven by this confirmed completion, never by the current
        # step merely changing (picking a task by hand is not finishing one). None = last task.
        st.session_state['flyover_boarding'] = {
            'done': task['title'], 'next': upcoming['title'] if upcoming else None,
            'next_id': upcoming['id'] if upcoming else None}
        if upcoming:
            st.session_state['flyover_next_offer'] = upcoming['id']
        st.session_state['flyover_flash'] = (
            f"{task['title']} completed. Next: {upcoming['title']}" if upcoming
            else 'All steps completed. Your route is assembled!')
        if api_url and not _cancel_task_reminders(api_url, task['id']):
            st.session_state['flyover_flash'] += (
                ' A reminder for this step could not be cancelled and may still arrive.')
    elif task['status'] == 'Completed' and returned['status'] != 'Completed':
        st.session_state['flyover_flash'] = (f"{task['title']} reopened. "
                                             f"Status: {returned['status']}.")
    else:
        st.session_state['flyover_flash'] = f"Status saved: {returned['status']}."
    return returned


def _status_control(data: dict, task: dict, api_url: str, widget: str, *,
                    resolve: bool = False, checklist_link: bool = False) -> None:
    """The status control every surface uses: the gate, each row's Edit status and the
    Checklist tab, each with its own widget key. It always shows the API's status.

    Ready and In Progress can be edited. Blocked explains what comes first (and offers the
    blocker action when resolve=True). Completed offers Reopen task.
    """
    status = task['status']
    editable = status in ('Ready', 'In Progress')
    st.session_state[widget] = status  # mirror the API, never a stale pick
    st.selectbox('Status', STATUS_CHOICES if editable else [status], key=widget,
                 disabled=not editable, on_change=_save_status, args=(api_url, task['id'], widget),
                 help='In Progress means waiting on an office. Completion is self-reported; '
                      'prerequisites are enforced by the API.')
    if editable:
        st.caption('Changes save automatically.')
    elif status == 'Blocked':
        by_id = {item['id']: item for item in data['workflow']}
        needs = [by_id[key]['title'] for key in task.get('prerequisites') or []
                 if key in by_id and by_id[key]['status'] != 'Completed']
        st.caption('Blocked until you finish: ' + ', '.join(needs) if needs
                   else 'Blocked: something has to happen first. The checklist says what.')
        if checklist_link:
            st.button('Open checklist', key=widget + ':open', type='tertiary',
                      icon=':material/checklist:', on_click=go, args=('checklist', task['id']))
        if resolve:
            _resolve_section(task, api_url, where=':' + widget)
    else:
        st.button('Reopen task', key=widget + ':reopen', icon=':material/undo:',
                  on_click=_reopen, args=(api_url, task['id']),
                  help='Moves this step back out of your completed list.')


def _status_feedback(data: dict, boarding: dict | None) -> None:
    """What the last save did: confetti and board once, then the message and any choices.

    Drawn where the student is looking: under the map on Workflow and readiness, at the top
    of other pages. A toast repeats the message for a control further down the page.
    """
    by_id = {task['id']: task for task in data['workflow']}
    if st.session_state.pop('flyover_celebrate', False):
        _confetti()
    if boarding:
        st.html(_boarding_board(boarding))
    if error := st.session_state.pop('flyover_status_error', None):
        st.error(error)
        st.toast(error, icon=':material/error:')
    if flash := st.session_state.pop('flyover_flash', None):
        st.success(flash)
        st.toast(flash, icon=':material/check_circle:')
    if block := st.session_state.pop('flyover_reopen_block', None):
        task = by_id.get(block['task_id'])
        needing = [by_id[key] for key in block['dependents'] if key in by_id]
        if task and needing:
            names = ', '.join(item['title'] for item in needing)
            st.warning(f'{task["title"]} can’t be reopened yet: {names} depends on it and is '
                       f'completed. Reopen {names} first.')
            for item in needing:
                st.button(f'Go to {item["title"]}', key='flyover_reopen_dep:' + item['id'],
                          on_click=_select_task, args=(item['id'],), icon=':material/east:')
    offer = st.session_state.get('flyover_next_offer')
    if offer in by_id and offer != st.session_state.get(TASK_KEY) \
            and by_id[offer]['status'] != 'Completed':
        st.button(f'Next suggested: {by_id[offer]["title"]}', key='flyover_take_next',
                  on_click=_select_task, args=(offer,), icon=':material/arrow_forward:')


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


def _office_link(office: dict) -> str:
    """'View <office> hours source': the office's own page from the rules file, underlined.

    A missing or unsafe URL gives plain text, so a bad link never becomes clickable.
    """
    label = esc(f'View {office["name"]} hours source')
    if link := safe_url(office.get('source_url')):
        return (f'<a class="fly-office-src" href="{esc(link)}" target="_blank" '
                f'rel="noopener noreferrer">{label}</a>')
    return f'<span class="fly-office-src">{label}</span>'


SOURCE_UNAVAILABLE = 'Source unavailable. Confirm with the office.'
UNREVIEWED = 'Confirm this detail with the office.'
MORE_INFO = 'more info included here'


def _more_info(rows_html: str) -> str:
    """The evidence disclosure: opens in place (native <details>, keyboard and touch friendly)."""
    return (f'<div class="fly-sheet"><details class="fly-more"><summary>{MORE_INFO}</summary>'
            f'<div class="fly-sheet">{rows_html}</div></details></div>')


def _office_evidence(office: dict) -> str:
    """The office record's own evidence: the source's words, when it was read, and its state."""
    verified = office.get('verification_status') == 'verified'
    state = ('<span class="fly-tag ok">Verified</span>' if verified
             else '<span class="fly-tag">Not verified</span>')
    when = (f'Retrieved {esc(long_date(office["retrieved_on"]))}' if office.get('retrieved_on')
            else '') + ('' if verified else f' · {UNREVIEWED}')
    return (f'<div class="fly-src"><div>{_office_link(office)}<small>{when}</small>'
            f'<small>“{esc(office.get("evidence") or "")}”</small></div>{state}</div>')


def _appointment_notice(tasks: list[dict], as_of: str) -> None:
    """In-app notice when the current or next step has sourced appointment guidance."""
    guidance = first_with_guidance(task_queue(tasks))
    if guidance is None:
        return
    windows = _windows()
    key = notice_key(guidance, windows)
    if key in st.session_state.get('flyover_appt_dismissed', []):
        return  # dismissed; the same text stays in the task's checklist under Visit details
    task = next((t for t in tasks if t['id'] == guidance['task_id']), {})
    with st.container(key='fly_appt_notice'):
        st.markdown(f'**Appointment information for your next step:** {guidance["title"]}')
        st.markdown(guidance['text'])  # ENG's sourced wording, unchanged
        st.html(_more_info(_source_rows(fact_sources(task, 'appointment_rules') or [])))
        # The same action links as the checklist, named for where they go.
        _task_action_links(task)
        if windows:
            st.caption(f'Your free times: {describe_windows(windows)}.')
            # One line per office on file (rules.json offices), else the honest no-hours note.
            # A time is only suggested from hours confirmed for the workflow's date; otherwise
            # the line says so and the office's own page follows it.
            for office in task.get('offices') or []:
                st.caption(match_line(office, windows, as_of))
                if not visit_hours(office, as_of)['confirmed']:
                    st.html(f'<div class="fly-sheet">{_office_link(office)}</div>')
            if not task.get('offices'):
                st.caption(NO_HOURS_NOTE)
        with st.expander('Your free times (optional)'):
            _availability_editor()
        st.button('Dismiss', key='fly_appt_dismiss', on_click=_dismiss_notice, args=(key,),
                  type='tertiary')


def _step_label(task: dict, tasks: list[dict]) -> str:
    """'Step 03 of 08 · Now boarding': numbered by progress (completed, then the queue)."""
    if task['status'] == 'Completed':
        return 'Completed · Reopen it from the status control'
    queue = task_queue(tasks)
    done = sum(item['status'] == 'Completed' for item in tasks)
    position = next((i for i, item in enumerate(queue) if item['id'] == task['id']), 0)
    where = 'Now boarding' if position == 0 else 'Later in your route'
    return f'Step {done + position + 1:02d} of {len(tasks):02d} · {where}'


def _workflow(data: dict, api_url: str, boarding: dict | None = None) -> None:
    tasks = data['workflow']
    done = sum(task['status'] == 'Completed' for task in tasks)
    pieces = map_piece_count(done, len(tasks))
    progress = map_progress(done, len(tasks))
    previous_done = st.session_state.get('flyover_map_done', done)
    st.session_state['flyover_map_done'] = done
    with st.container(key='flyover_workflow'):
        st.html(flight_map(progress, animate=done > previous_done and not st.session_state.get('flyover_reduce_motion'),
                           previous=map_progress(previous_done, len(tasks))))
        # The API's answer is already in `data`; the feedback below only describes it.
        _status_feedback(data, boarding)
        st.subheader('Moving Forward (Workflow)')
        st.caption(f'{done} of {len(tasks)} steps completed · {pieces} of 3 route pieces assembled')
        if not tasks:
            st.info('No workflow steps are available. Generate a profile or try again.')
            return
        if active_task(tasks) is None:
            st.success('Your checklist is complete. Confirm requirements with the relevant offices before your visit.')
        with st.container(key='flyover_choose_box'):
            task_id = _task_picker(tasks, 'flyover_choose', 'Choose a task')
        task = next(item for item in tasks if item['id'] == task_id)
        # Flip the title only when a completion just moved us to this step, never when the
        # student merely picked another task.
        changing = bool(boarding) and boarding.get('next_id') == task_id
        with st.container(key='flyover_gate'):
            title_col, status_col, action_col = st.columns([2.6, 1.3, 1.1], gap='large',
                                                           vertical_alignment='center')
            with title_col:
                st.html(f'<div class="gate-step">{esc(_step_label(task, tasks))}</div>'
                        + _board(task['title'], changing)
                        + f'<span class="gate-priority">{esc(task["priority"])}</span>')
            with status_col:
                _status_control(data, task, api_url, 'flyover_status')
            with action_col:
                st.button('View checklist', key='flyover_checklist', on_click=go, type='tertiary',
                          args=('checklist', task_id), icon=':material/checklist:')
        with st.container(key='fly_gate_notes'):
            if note := due_note(task, data['as_of']):
                getattr(st, note[0])(note[1])
            if task.get('next_action'):
                st.info(task['next_action']['text'])
            for blocker in task.get('blockers') or []:
                st.warning(blocker['explanation'])
            if not task.get('sources') or not all(source_verified(s) for s in task['sources']):
                st.caption('Not verified. Confirm with the office. Completing a step does not confirm eligibility.')
            if task['status'] == 'Blocked':
                _resolve_section(task, api_url)
                other_ready = [t for t in tasks if t['status'] in ('Ready', 'In Progress')]
                if other_ready:
                    st.caption('You can prepare another available task while this step is blocked:')
                    for other in other_ready:
                        st.button(other['title'], key='flyover_other:' + other['id'],
                                  on_click=_select_task, args=(other['id'],))
        _appointment_notice(tasks, data['as_of'])


def _office_hours(task: dict, as_of: str) -> None:
    """Compact office rows, shared by the "Before you go" preview and the Checklist tab.

    Hours only when confirmed for the workflow's date; otherwise the reason and, for offices
    that publish hours for another date, a dated reference. Each office gets its own
    "View <office> hours source" link and evidence, even when several serve one task.
    """
    offices = task.get('offices') or []
    if not offices:
        return
    windows = _windows()
    st.markdown('#### Office hours')
    for office in offices:
        with st.container():  # unkeyed: the preview and checklist may show the same task
            st.markdown(f'**{office["name"]}**')
            if office.get('address'):
                st.caption(office['address'])
            check = visit_hours(office, as_of)
            if check['confirmed']:
                st.write(hours_summary(office) + ' (Pacific time)')
                st.caption(office['period_note'])
                for closure in upcoming_closures(office, as_of):
                    st.caption('Listed closure · ' + closure)
                if windows:
                    st.caption(match_line(office, windows, as_of))
            elif check['reason'] == 'no_hours':
                st.markdown('**No hours published**')
                st.caption(check['detail'] + ' Check the official office page before visiting.')
            else:
                st.markdown(f'**{HOURS_NOT_CONFIRMED}** ({long_date(as_of)}).')
                st.caption(check['detail'] + ' Check the official office page before visiting.')
                # Kept as dated reference only: the source's own period words, its retrieval
                # date and verification state. No free-time match is worked out from these.
                with st.expander('Reference only: the hours this office published'):
                    st.caption(f'{office["period_note"]} Retrieved '
                               f'{long_date(office["retrieved_on"])} · '
                               f'{"Verified" if office["verification_status"] == "verified" else "Not verified"}.')
                    st.write(hours_summary(office) + ' (Pacific time)')
                    for closure in office.get('closures') or []:
                        st.caption(f'Listed closure · {long_date(closure["date"])}: '
                                   f'{closure["note"]}')
            st.html(f'<div class="fly-sheet">{_office_link(office)}'
                    f'{_more_info(_office_evidence(office))}</div>')


def _task_action_links(task: dict) -> None:
    """Links to where the student acts, each labelled by its real destination."""
    for action in task_actions(task, source_label):
        st.link_button(action['label'], action['url'], type='primary', width='stretch')
        if action['note']:
            st.caption(action['note'])


def _visit_fact(task: dict, label: str, field: str, value: str) -> None:
    """A visit fact as sourced, with its evidence one click away (never a repeated badge)."""
    st.markdown(f'**{label}:** {value}')  # ENG's sourced wording (it may contain a link)
    st.html(_more_info(_source_rows(fact_sources(task, field) or [])))


def _registration_info(task: dict) -> None:
    window = task.get('registration_window')
    if not window:
        return
    term = ENROLLMENT_TERMS[window['term']]
    if window.get('needs') == 'published_period':
        text = f'{term} priority-group dates are not available in this guide yet.'
    elif window.get('needs') == 'enrollment_priority':
        text = f'Choose your enrollment priority in Profile setup to see your {term} registration information.'
    else:
        start = date.fromisoformat(window['starts_on']).strftime('%b %d, %Y')
        end = window.get('ends_on')
        dates = (start + ' to ' + date.fromisoformat(end).strftime('%b %d, %Y')
                 if end and end != window['starts_on'] else start)
        label = ENROLLMENT_PRIORITIES[window['priority']]
        text = f'{label} · {term} registration ' + ('begins ' if end is None else 'period: ') + dates + '.'
    verification = ('Double-checked by our team' if window['verification_status'] == 'verified'
                    else 'Not verified')
    st.info(text + ' ' + verification + '. Check your exact appointment date and time in '
            '[eServices](https://ps.losrios.edu/). Enter the date you actually register '
            'separately to calculate your payment deadline.')
    if url := safe_url(window.get('source_url')):
        label = ('Los Rios Fall 2026 priority dates · archived May 17, 2026'
                 if 'web.archive.org' in url else 'Official CRC priority registration dates')
        st.caption(f'[{label}]({url})')


def _checklist(data: dict, task: dict, api_url: str) -> None:
    """The full checklist: status by the title, then documents, step actions, office hours."""
    title_col, status_col = st.columns([2.4, 1], vertical_alignment='bottom')
    with title_col:
        st.markdown('### ' + task['title'])
        st.html(f'<div class="fly-card-meta">{_pill(task["status"])}'
                f'<span class="gate-priority">{esc(task["priority"])}</span></div>')
    with status_col:
        # The shared status control (Edit status, Reopen); its key is the Checklist's own.
        _status_control(data, task, api_url, 'flyover_checklist_status')
    _registration_info(task)
    if note := due_note(task, data['as_of']):
        getattr(st, note[0])(note[1])
    for blocker in task.get('blockers') or []:
        st.warning(blocker['explanation'])
        if blocker.get('unlocks_on'):
            st.caption('Listed unlock date: ' + blocker['unlocks_on'])
    guide = task.get('before_you_go') or {}
    documents = list(dict.fromkeys(guide.get('required_documents') or []))
    # {document: on hand?} per task ID, so a check stays with the task it was made on.
    selected = st.session_state.setdefault('documents_on_hand', {}).setdefault(task['id'], {})
    st.markdown('#### Documents')
    for document in documents:
        key = f'flyover_doc:{task["id"]}:{document}'
        if key not in st.session_state:
            st.session_state[key] = selected.get(document, False)
        selected[document] = st.checkbox(document, key=key)
    if documents:
        st.caption('Checked documents are your inventory, not a readiness or eligibility decision.')
    else:
        st.html('<p class="fly-note">No document list on file yet. Ask the office what to bring.</p>')
    st.markdown('#### Next action')
    _task_action_links(task)
    _resolve_section(task, api_url)
    if task['status'] in ('Ready', 'In Progress') and st.button(
            'Mark this step completed', key='flyover_detail_complete', type='primary'):
        try:
            result = client.change_status(api_url, data, task['id'], 'Completed')
        except (requests.RequestException, ValueError):
            st.error('Could not update this step. Your progress has been kept. Try again.')
        else:
            # Same feedback as the status selector, drawn on this page by _status_feedback;
            # the chosen task and this tab stay put (no jump back to page 1).
            _record_update(task, result, api_url)
            st.rerun()
    _reminder_section(data, task, api_url)
    details, sources = st.columns([1, 1], gap='large')
    with details:
        st.markdown('#### Before you visit')
        missing = []
        for label, field in VISIT_FACTS:
            if not (value := guide.get(field)):
                missing.append(label)
                continue
            _visit_fact(task, label, field, value)
        _office_hours(task, data['as_of'])
        if missing:
            # One line for everything not on file, instead of the same warning four times.
            st.html(f'<p class="fly-note">Not on file yet: {esc(", ".join(missing))}. '
                    'Confirm with the office.</p>')
    with sources:
        st.markdown('#### Where this information comes from')
        st.html(_more_info(_source_rows(task.get('sources') or [])))
    for warning in guide.get('warnings') or []:
        st.warning(warning)


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
               'addresses the team allowed. Reminders use today’s real date and time, not the '
               'demo’s date.')
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


def _resolve_section(task: dict, api_url: str, where: str = '') -> None:
    """For a blocked task: the "Resolve blocker" button and, once used, the API's email draft.

    `where` keeps the button's key unique when a row's Edit status shows it on the same page.
    """
    if task['status'] == 'Blocked' and task.get('next_action'):
        st.button('Resolve blocker', key='flyover_resolve:' + task['id'] + where, on_click=_resolve,
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
    """Evidence rows: the source's title, its link (plain text if missing or unsafe) and date.

    A reviewed source keeps its real verified date; one awaiting review says to confirm with
    the office; no source at all says so. Same signature and HTML as before for every caller.
    """
    rows = []
    for source in sources:
        url = safe_url(source.get('url'))
        label = esc(source_label(source.get('url')))
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'
                if url else f'<span>{label}</span>')
        if source_verified(source):
            tag = '<span class="fly-tag ok">Verified</span>'
            when = ('Double-checked by our team on ' + esc(source['last_verified'])
                    if source.get('last_verified') else 'Double-checked by our team')
        else:
            tag = '<span class="fly-tag">Not verified</span>'
            when = UNREVIEWED
        rows.append(f'<div class="fly-src"><div>{link}<small>{when}</small></div>{tag}</div>')
    return ''.join(rows) or f'<p class="fly-muted">{SOURCE_UNAVAILABLE}</p>'


def _preview_group(group: dict, kind: str) -> str:
    """One task in the preview: its title and status, then its own documents."""
    task = group['task']
    items = ''.join(
        f'<li><span>{esc(doc)}'
        + (f'<small>Also needed for: {esc(", ".join(group["shared"][doc]))}</small>'
           if doc in group['shared'] else '') + '</span></li>'
        for doc in group['documents'])
    docs = (f'<ul class="fly-docs">{items}</ul>' if items
            else '<p class="fly-muted">No document list on file. Confirm with the office.</p>')
    return (f'<section class="fly-group"><div class="fly-group-head"><span class="fly-group-kind">'
            f'{esc(kind)}</span><span class="fly-group-title">{esc(task["title"])}</span>'
            f'{_pill(task["status"])}</div>{docs}</section>')


@st.dialog('Before you go', width='medium')
def _prereq_dialog(task: dict, by_id: dict) -> None:
    """Quick look at one task: it first, then each prerequisite with its own documents."""
    st.html(f'<h3 class="fly-sheet-title">{esc(task["title"])}</h3>')
    groups = document_groups(task, by_id)
    sections = [_preview_group(groups[0], 'Selected step'),
                *(_preview_group(group, 'Needs first') for group in groups[1:])]
    if len(groups) == 1:
        sections.append('<p class="fly-muted">No other step has to come first.</p>')
    sources = list({s.get('rule_id'): s for group in groups
                    for s in group['task'].get('sources') or []}.values())
    st.html(f'<div class="fly-sheet"><div class="fly-needs">{"".join(sections)}</div>'
            f'<h4>Our sources</h4>{_more_info(_source_rows(sources))}</div>')
    _task_action_links(task)
    _office_hours(task, st.session_state['flyover_data']['as_of'])
    if st.button('Open full checklist', key='flyover_prereq_full', type='primary',
                 width='stretch'):
        go('checklist', task['id'])
        st.rerun()


def _tour(page: str) -> None:
    """Send the spotlight tour once per session (and again on Settings → Replay tutorial).

    The browser remembers a finished or skipped tour for the tab (sessionStorage), so a sent
    tour that was already seen doesn't show again. Nothing here calls the API.
    render_app calls this after every view (and on sign-in) with the current destination;
    today's steps cover Workflow and readiness only (per-page steps: guide Part 2).
    """
    if page != 'workflow':
        return
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


def _task_table(group: str, tasks: list[dict], data: dict, api_url: str, empty: str) -> None:
    """Rows of Task | Status | Needs first | Edit status. Each Edit status targets its row's
    task ID and has its own widget key (fly_status:<group>:<id>), apart from the Checklist's."""
    by_id = {task['id']: task for task in data['workflow']}
    with st.container(key=f'fly_table_{group}'):
        st.html('<div class="fly-thead"><span>Task</span><span>Status</span>'
                '<span>Needs first</span><span>Edit</span></div>')
        if not tasks:
            st.html(f'<p class="fly-empty">{esc(empty)}</p>')
        for task in tasks:
            with st.container(key=f'fly_row_{group}_{task["id"]}'):
                left, mid, right, edit = st.columns([1.6, .95, 1.2, .95], vertical_alignment='center',
                                                    gap='small')
                with edit, st.popover('Edit status', key=f'fly_edit:{group}:{task["id"]}',
                                      icon=':material/edit:'):
                    st.markdown(f'**{task["title"]}**')
                    _status_control(data, task, api_url, f'fly_status:{group}:{task["id"]}',
                                    resolve=True, checklist_link=True)
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
                      icon=':material/checklist:', on_click=go, args=('checklist', task['id']))


def _quote_card() -> None:
    index = st.session_state.get('flyover_quote', 0) % len(ENCOURAGEMENTS)
    dots = ''.join(f'<i class="{"on" if k == index else ""}"></i>' for k in range(len(ENCOURAGEMENTS)))
    st.html(f'<aside class="fly-quote" aria-label="Encouragement" data-quote="{index}">'
            '<span class="mark" aria-hidden="true">“</span>'
            f'<blockquote>{esc(ENCOURAGEMENTS[index])}</blockquote>'
            '<footer><span>A new line each time you open a checklist</span>'
            f'<span class="dots" aria-hidden="true">{dots}</span></footer></aside>')


def _readiness(data: dict, api_url: str) -> None:
    """Progress, Before you take off (every unfinished task) and completed history."""
    tasks = data['workflow']
    by_id = {task['id']: task for task in tasks}
    done = sum(task['status'] == 'Completed' for task in tasks)
    queue = task_queue(tasks)  # every unfinished task: Ready, In Progress and Blocked
    with st.container(key='fly_readiness'):
        head, meter = st.columns([2, 1], vertical_alignment='bottom')
        with head:
            st.subheader('Readiness')
            st.caption('Where you stand. Tap a prerequisite for the documents to bring and where '
                       'the guidance comes from.')
        with meter:
            width = 100 * done / len(tasks) if tasks else 0
            st.html(f'<div class="fly-meter" role="status"><b>{done} of {len(tasks)} steps '
                    f'complete · {len(queue)} still ahead</b>'
                    f'<div class="bar"><span style="width:{width:.0f}%"></span></div></div>')
        main, aside = st.columns([2.4, 1], gap='large')
        with main:
            st.markdown('#### Completed')
            _task_table('done', [t for t in tasks if t['status'] == 'Completed'], data, api_url,
                        'Nothing finished yet. Your first completed step will land here.')
            st.caption('Completing a step does not confirm eligibility. Backend status and '
                       'prerequisites decide. Use Edit status to reopen a step.')
        with aside, st.container(key='fly_quote_col'):
            _quote_card()
    with st.container(key='fly_takeoff'):
        st.subheader('Before you take off')
        if queue:
            st.caption('One step at a time, most important first. A step another one needs '
                       'always comes before it.')
            _focus_card(queue[0], 'now')
            if len(queue) > 1:
                _focus_card(queue[1], 'next')
        _task_table('takeoff', queue, data, api_url,
                    'Nothing left ahead. Confirm requirements with each office before you visit.')
    if (opened := st.session_state.pop('flyover_prereq_open', None)) in by_id:
        _prereq_dialog(by_id[opened], by_id)


def _checklist_page(data: dict, api_url: str) -> None:
    """The Checklist tab: the selected task's status control, then its full checklist."""
    tasks = data['workflow']
    if not tasks:
        st.info('No workflow steps are available yet.')
        return
    by_id = {task['id']: task for task in tasks}
    with st.container(key='fly_checklist'):
        task_id = _task_picker(tasks, 'flyover_checklist_pick', 'Your checklist')
        # The status control sits beside the checklist title (inside _checklist).
        _checklist(data, by_id[task_id], api_url)
    if (opened := st.session_state.pop('flyover_prereq_open', None)) in by_id:
        _prereq_dialog(by_id[opened], by_id)


def _alerts(data: dict) -> None:
    """The Alerts tab. Guide Part 2 fills it with each task's notices, grouped by task."""
    with st.container(key='fly_alerts'):
        st.subheader('Alerts')
        st.caption('Task notices are being collected here. Until then, each task’s notices '
                   'are in its checklist.')
        task_id = selected_task_id(data['workflow'])
        if task_id:
            st.button('Open the selected task’s checklist', key='fly_alerts_open',
                      icon=':material/checklist:', on_click=go, args=('checklist', task_id))


def _updates() -> None:
    """Updates and credits. Guide Part 2 adds flyover_about.py (Planned updates, Credits)."""
    with st.container(key='fly_updates'):
        st.subheader('Updates and credits')
        st.caption('Planned updates and the full credits list are on their way to this page.')
        st.link_button('Read the project credits', CREDITS_URL, icon=':material/open_in_new:')


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
    st.button('Back to Workflow and readiness', key='flyover_profile_back', on_click=go,
              args=('workflow',),
              icon=':material/west:', type='tertiary')
    with st.container(key='fly_profile_page'):
        st.subheader('Your profile')
        account = st.session_state.get('flyover_account')
        st.caption('Signed in as ' + masked(account['email']) if account
                   else 'Demo visitor · a sample student, no account')
        arrival = date.fromisoformat(profile['arrival_date'])
        days = (date.fromisoformat(data['as_of']) - arrival).days
        since = f'{days} days ago' if days >= 0 else f'in {-days} days'
        # "3 days ago" is counted from the workflow's date, so that date is shown too.
        facts = [('Walkthrough date', long_date(data['as_of'])),
                 ('School', profile['institution']), ('Visa type', profile['visa_type']),
                 ('Arrival date', f'{arrival:%B} {arrival.day}, {arrival.year} · {since}'),
                 ('Has an SSN', 'Yes' if profile['has_ssn'] else 'No'),
                 ('Enrollment term', ENROLLMENT_TERMS.get(profile.get('enrollment_term'))),
                 ('Enrollment priority', ENROLLMENT_PRIORITIES.get(profile.get('enrollment_priority'))),
                 ('Enrollment date', date.fromisoformat(profile['enrollment_date']).strftime('%B %d, %Y')
                  if profile.get('enrollment_date') else 'Not given')]
        st.html('<dl class="fly-facts">' + ''.join(
            f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>' for label, value in facts) + '</dl>')
        st.button('Edit in Profile setup', key='flyover_profile_edit', on_click=go,
                  args=('workflow',), icon=':material/edit:')
    with st.container(key='fly_profile_progress'):
        st.subheader('Progress')
        columns = st.columns(4)
        for column, status in zip(columns, ('Completed', 'In Progress', 'Ready', 'Blocked'),
                                  strict=True):
            column.metric(status, sum(task['status'] == status for task in tasks))
        if upcoming := active_task(tasks):
            st.markdown(f'**Next step:** {upcoming["title"]}')
            st.button('Open its checklist', key='flyover_profile_next', type='primary',
                      on_click=go, args=('checklist', upcoming['id']))
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
    return {'title': title, 'scenario': export_line(data['as_of']), 'sections': [
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
    if doc.get('scenario'):
        lines += [clean(doc['scenario']), '']
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
                    f'<span class="fly-tag">⚠ Preview · Not verified</span></div>'
                    f'<p class="fly-doc-scenario">{esc(doc.get("scenario", ""))}</p>{body}'
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
    # The demo notice comes before any API call, so it shows on the first screen, every page,
    # and also when loading fails. It never depends on is_mock: the live engine computes this
    # historical demo with is_mock false.
    with st.container(key='fly_demo_notice'):
        st.html(notice_html())
    if not entered():
        # The first screen: "Try the CRC demo", or the visitor's own details.
        render_signin(api_url)
        _tour('signin')
        return
    # One page id, normalised once, drives the header, the tabs and the dispatch below.
    page = st.session_state['flyover_page'] = destination(st.session_state.get('flyover_page'))
    panel = _header(page)
    if 'flyover_data' not in st.session_state:
        try:
            # No workflow kept for this session (a reload, say): rebuild the demo student's
            # on the scenario date.
            st.session_state['flyover_data'] = client.start_demo(
                api_url, DEMO_PROFILE, SCENARIO_AS_OF.isoformat())
        except (requests.RequestException, ValueError):
            with panel:
                st.caption('Airshow can answer once your workflow has loaded.')
            st.error('Could not load your workflow. Check that the API is running and try again.')
            st.button('Retry', key='flyover_retry')
            st.stop()
    data = st.session_state['flyover_data']
    sync_profile_context(data['student_profile'])
    with panel:
        _chat(data, api_url, page)
    _tabs(page)
    # Shown once per confirmed completion (set in _record_update), then consumed.
    boarding = st.session_state.pop('flyover_boarding', None)
    if page == 'workflow':
        _profile(data, api_url)
        if data.get('is_mock'):
            st.warning('Sample data. Not verified. Do not rely on it.')
        elif data['student_profile'].get('school_verified') is not True:
            st.caption('School-specific guidance is not verified. Confirm requirements with your DSO.')
        _workflow(data, api_url, boarding)
        _readiness(data, api_url)
    else:
        _status_feedback(data, boarding)
        if page == 'checklist':
            _checklist_page(data, api_url)
        elif page == 'alerts':
            _alerts(data)
        elif page == 'profile':
            _profile_page(data)
        elif page == 'handoff':
            _assistant(data, api_url)
        elif page == 'updates':
            _updates()
    if target := st.session_state.pop('flyover_scroll', None):
        _scroll(target)
    _tour(page)
    st.html('<footer class="flyover-footer">Flyover · A little preparation. A world of possibility.</footer>')
