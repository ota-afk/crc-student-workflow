"""Flyover: page 1 (profile + one-step workflow) and page 2 (readiness, take-off, Airshow)."""

import html
import json
import os
from datetime import date

import requests
import streamlit as st

from . import flyover_client as client
from .flyover_art import ASSETS, banner, flight_map, flight_scene, logo
from .flyover_state import ENCOURAGEMENTS, active_task, map_piece_count, map_progress
from .frontend import safe_url, source_verified
from .frontend_state import sync_profile_context
from .frontend_views import render_sources

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


def esc(value) -> str:
    return html.escape('' if value is None else str(value))


def go(page: str, task_id: str | None = None) -> None:
    st.session_state['flyover_page'] = 'home' if page == 'home' else 'readiness'
    st.session_state['flyover_scroll'] = ('airshow' if page == 'assistant'
                                          else 'checklist' if task_id else 'top')
    if task_id:
        st.session_state['flyover_detail'] = task_id
        st.session_state['flyover_quote'] = st.session_state.get('flyover_quote', -1) + 1


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
    if st.button('Done', key='flyover_settings_done', type='primary'):
        st.rerun()


def _header() -> None:
    with st.container(key='flyover_header'):
        brand, ai, gear = st.columns([8, 1, 1], vertical_alignment='center')
        with brand:
            st.image(logo(), width=185)
        with ai:
            st.button('AI', key='flyover_ai', help='Meet Airshow, your assistant',
                      on_click=go, args=('assistant',))
        with gear:
            if st.button('Settings', icon=':material/settings:', key='flyover_settings',
                         help='Settings and motion preferences'):
                settings()


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
                            'arrival_date': arrival.isoformat(), 'has_ssn': ssn == 'Yes'}
                        try:
                            result = client.generate_workflow(api_url, profile, changes)
                        except (requests.RequestException, ValueError):
                            st.error('Could not generate your workflow. Your progress has been kept. Try again.')
                        else:
                            st.session_state['flyover_data'] = result
                            st.session_state['flyover_clear_reset_confirmation'] = True
                            for key in ('flyover_active_id', 'flyover_status', 'flyover_detail', 'flyover_handoff',
                                        'flyover_map_done', 'flyover_celebrate', 'flyover_status_error',
                                        'flyover_email', 'flyover_resolve_error', 'flyover_answer'):
                                st.session_state.pop(key, None)
                            for key in list(st.session_state):
                                if key.startswith('flyover_doc:'):
                                    del st.session_state[key]
                            st.session_state['flyover_flash'] = 'Your new workflow is ready to explore.'
                            st.rerun()
            st.caption('No names, document numbers or uploads. Your profile stays in this session.')


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
    st.session_state['flyover_data'] = result
    returned = next((item for item in result['workflow'] if item['id'] == task_id), task)
    st.session_state['flyover_status'] = returned['status']
    if returned['status'] == 'Completed':
        st.session_state['flyover_celebrate'] = True
        upcoming = active_task(result['workflow'])
        st.session_state['flyover_flash'] = (
            f"{task['title']} completed. Next: {upcoming['title']}" if upcoming
            else 'All steps completed. Your route is assembled!')
    else:
        st.session_state['flyover_flash'] = 'Status saved.'


def _confetti() -> None:
    if st.session_state.get('flyover_reduce_motion'):
        return
    colors = ['#629677', '#777DA7', '#E6CCBE', '#E6B951', '#FFFFFF']
    particles = ''.join(
        f'<i style="--x:{(i * 37) % 100}%;--delay:{(i % 7) * .06}s;'
        f'--drift:{(i % 9 - 4) * 24}px;--color:{colors[i % len(colors)]};'
        f'--spin:{180 + i * 29}deg"></i>' for i in range(48))
    st.html(f'<div class="flyover-confetti" aria-hidden="true">{particles}</div>')


def _board(title: str, changing: bool) -> str:
    """Departure-board title: every letter flips in, left to right, when the step changes."""
    index = 0
    words = []
    for word in title.split(' '):
        letters = []
        for char in word:
            letters.append(f'<span class="flap" style="--i:{index}">{esc(char)}</span>')
            index += 1
        words.append('<span class="word">' + ''.join(letters) + '</span>')
        index += 1
    state = ' is-changing' if changing else ''
    return (f'<div class="gate-title{state}" role="text" aria-live="polite" aria-label="{esc(title)}">'
            + ' '.join(words) + '</div>')


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
            changing = st.session_state.get('flyover_active_id') not in (None, task_id)
            if st.session_state.get('flyover_active_id') != task_id:
                st.session_state['flyover_active_id'] = task_id
                st.session_state['flyover_status'] = current['status']
            number = next(i + 1 for i, task in enumerate(tasks) if task['id'] == task_id)
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
        _, next_col = st.columns([4, 1])
        with next_col:
            st.button('Next', key='flyover_next', type='primary', icon=':material/arrow_forward:',
                      icon_position='right', width='stretch', on_click=go, args=('readiness',))


def _checklist(data: dict, task: dict, api_url: str) -> None:
    st.markdown('### ' + task['title'])
    st.caption(task['status'] + ' · ' + task['priority'])
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
    if not documents:
        st.info('Document requirements are not available. Confirm with the office.')
    st.caption('Checked documents are your inventory, not a readiness or eligibility decision.')
    details, sources = st.columns([1, 1], gap='large')
    with details:
        st.markdown('#### Visit details')
        for label, field in [('Hours', 'hours'), ('Fees', 'fees'), ('Appointments', 'appointment_rules'), ('Phone', 'phone')]:
            st.write(f'{label}: {guide.get(field) or "Not verified. Confirm with the office."}')
        if link := safe_url(guide.get('official_url')):
            st.link_button('Official visit information', link)
    with sources:
        st.markdown('#### Sources and verification')
        render_sources(task.get('sources') or [])
    for warning in guide.get('warnings') or []:
        st.warning(warning)
    _resolve_section(task, api_url)
    if task['status'] in ('Ready', 'In Progress') and st.button(
            'Mark this step completed', key='flyover_detail_complete', type='primary'):
        try:
            st.session_state['flyover_data'] = client.change_status(api_url, data, task['id'], 'Completed')
        except (requests.RequestException, ValueError):
            st.error('Could not update this step. Your progress has been kept. Try again.')
        else:
            go('home')
            st.rerun()


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


def _source_rows(sources: list[dict]) -> str:
    rows = []
    for source in sources:
        url = safe_url(source.get('url'))
        label = esc(source.get('rule_id') or 'Official source')
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'
                if url else f'<span>{label}</span>')
        tag = ('<span class="fly-tag ok">Verified</span>' if source_verified(source)
               else '<span class="fly-tag">⚠ Not verified</span>')
        when = esc(source.get('last_verified') or 'not recorded')
        rows.append(f'<div class="fly-src"><div>{link}<small>Source date: {when}</small></div>{tag}</div>')
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
        st.caption('Steps still ahead. Line up what each one needs so one visit covers it.')
        _task_table('takeoff', [t for t in tasks if t['status'] in ('Ready', 'Blocked')], by_id,
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


def _handoff(data: dict, goal: str, professional: str) -> dict:
    profile = data['student_profile']
    tasks = data['workflow']

    def titles(status: str) -> str:
        return ', '.join(t['title'] for t in tasks if t['status'] == status) or 'none'

    task = next((t for t in tasks if t['id'] == st.session_state.get('flyover_detail')), None) or active_task(tasks)
    documents = list(dict.fromkeys(((task or {}).get('before_you_go') or {}).get('required_documents') or []))
    arrival = date.fromisoformat(profile['arrival_date'])
    return {'title': 'Handoff for your ' + professional.split(' (')[0], 'sections': [
        ('Who I am', [(f'{profile["visa_type"]} student at {profile["institution"]}. Arrived '
                       f'{arrival:%B} {arrival.day}, {arrival.year}. '
                       f'{"Has an" if profile["has_ssn"] else "No"} SSN. Name: [YOUR NAME]')]),
        ('What I’m here to do', [goal]),
        ('Where I am', [f'Done: {titles("Completed")}', f'In progress: {titles("In Progress")}',
                        f'Blocked: {titles("Blocked")}']),
        ('Questions to ask', PROFESSIONALS[professional]),
        ('Bring with me', documents or ['No document list on file. Confirm with the office.']),
    ]}


def _handoff_text(doc: dict, markdown: bool) -> str:
    lines = [('# ' if markdown else '') + doc['title'], '']
    for heading, items in doc['sections']:
        lines.append(('## ' if markdown else '') + heading)
        lines += [('- ' if markdown else '• ') + item for item in items] if len(items) > 1 else items
        lines.append('')
    lines.append('Drafted from a template. Not verified. Confirm every requirement with the office.')
    return '\n'.join(lines)


def _clear_handoff() -> None:
    st.session_state.pop('flyover_handoff', None)


def _ask(data: dict, api_url: str) -> None:
    """Ask Airshow: a live answer from POST /assistant, grounded in this workflow."""
    with st.container(key='fly_ask'):
        st.subheader('Ask Airshow')
        st.caption('Ask about the task in your checklist. Answers come from your workflow and our '
                   'sources. Do not include your name, SSN or document numbers.')
        with st.form('flyover_ask_form', border=False, clear_on_submit=True):
            question = st.text_input('Your question', max_chars=500, key='flyover_question',
                                     placeholder='For example: why is my California ID blocked?')
            asked = st.form_submit_button('Ask Airshow', type='primary')
        if asked and question.strip():
            try:
                with st.spinner('Airshow is checking your workflow…'):
                    answer = client.ask_airshow(api_url, data, question,
                                                st.session_state.get('flyover_detail'))
            except requests.Timeout:
                # Its own message: on the free host the API may still be waking up.
                st.error('Airshow took too long to answer. The service may be starting up: wait '
                         'a minute and ask again. Your progress has been kept.')
            except (requests.RequestException, ValueError):
                st.error('Airshow could not answer right now. Try again, or use your checklist '
                         'and its sources. Your progress has been kept.')
            else:
                st.session_state['flyover_answer'] = {'question': question.strip(), **answer}
        if answer := st.session_state.get('flyover_answer'):
            st.caption('You asked: ' + answer['question'])
            if not answer['verified'] or not all(source_verified(s) for s in answer['sources']):
                st.warning('Not verified. Confirm with the office.')
            st.markdown(answer['answer'])
            for number, step in enumerate(answer['steps'], 1):
                st.write(f'{number}. {step}')
            if answer['contact']:
                st.write('Who to contact: ' + answer['contact'])
            if answer['sources']:
                st.html(f'<div class="fly-sheet">{_source_rows(answer["sources"])}</div>')


def _assistant(data: dict, api_url: str) -> None:
    st.html(flight_scene(static=bool(st.session_state.get('flyover_reduce_motion'))))
    with st.container(key='fly_airshow'):
        context = json.dumps([st.session_state.get('flyover_detail'), data['student_profile']], sort_keys=True)
        if st.session_state.get('flyover_handoff_context') != context:
            st.session_state.pop('flyover_handoff', None)
            # An answer about another task or older progress would now be out of date.
            st.session_state.pop('flyover_answer', None)
            st.session_state['flyover_handoff_context'] = context
        _ask(data, api_url)
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
            with button_col:
                if st.button('Generate handoff', key='flyover_prepare_handoff', type='primary',
                             disabled=not goal.strip(), width='stretch'):
                    st.session_state['flyover_handoff'] = _handoff(data, goal.strip(), professional)
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
    _header()
    if 'flyover_data' not in st.session_state:
        try:
            st.session_state['flyover_data'] = client.fetch_workflow(api_url)
        except (requests.RequestException, ValueError):
            st.error('Could not load your workflow. Check that the API is running and try again.')
            st.button('Retry', key='flyover_retry')
            st.stop()
    data = st.session_state['flyover_data']
    sync_profile_context(data['student_profile'])
    page = st.session_state.get('flyover_page', 'home')
    if page == 'home':
        _profile(data, api_url)
        if data.get('is_mock'):
            st.warning('Sample data. Not verified. Do not rely on it.')
        elif data['student_profile'].get('school_verified') is not True:
            st.caption('School-specific guidance is not verified. Confirm requirements with your DSO.')
        _workflow(data, api_url)
    else:
        _readiness(data, api_url)
        _assistant(data, api_url)
    if target := st.session_state.pop('flyover_scroll', None):
        _scroll(target)
    st.html('<footer class="flyover-footer">Flyover · A little preparation. A world of possibility.</footer>')
