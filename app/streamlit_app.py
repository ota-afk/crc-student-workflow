"""Student dashboard with task details and a mock-first assistant preview."""

import html
import os
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv

from student_workflow.contract import Workflow
from student_workflow.frontend import safe_url, source_verified
from student_workflow.frontend_api import api_get
from student_workflow.frontend_email import render_email_preview
from student_workflow.frontend_onboarding import render_onboarding
from student_workflow.frontend_state import open_task, sync_profile_context
from student_workflow.frontend_views import render_assistant, render_task_details

load_dotenv()
API_URL = os.getenv('API_URL', 'http://localhost:8000').rstrip('/')

st.set_page_config(page_title='International Student Navigator', layout='wide')
st.title('International Student Navigator')

# Each badge sets both its background and its text color, so it stays readable in
# light and dark themes. Status is always a word plus a symbol, never color alone.
st.markdown(
    """
    <style>
    .badge { display: inline-block; padding: 0.2rem 0.6rem; font-size: 0.8rem;
             font-weight: 600; border-radius: 9999px; }
    .badge-completed { background: #d1fae5; color: #065f46; }
    .badge-ready { background: #dbeafe; color: #1e40af; }
    .badge-inprogress { background: #fef3c7; color: #92400e; }
    .badge-blocked { background: #fee2e2; color: #991b1b; }
    .badge-unverified { background: #ffedd5; color: #9a3412;
                        border: 1px solid #fdba74; }
    .badge-neutral { background: #e5e7eb; color: #374151; }
    .pill { font-size: 0.75rem; font-weight: 500; padding: 0.15rem 0.5rem;
            border-radius: 4px; background: #f3f4f6; color: #374151; }
    </style>
    """,
    unsafe_allow_html=True,
)

NOT_VERIFIED = 'Not verified. Confirm with the office.'
STATUS_STYLES = {
    'Completed': ('badge-completed', '✓'),
    'Ready': ('badge-ready', '▶'),
    'In Progress': ('badge-inprogress', '◐'),
    'Blocked': ('badge-blocked', '✕'),
}

# No caching on purpose: the dashboard must always show the live state.
# If you add caching later, clear it right after any action that changes a task.


def load_workflow() -> dict[str, Any]:
    # After "Generate workflow" or a task action, the dashboard holds the latest workflow
    # (the API is stateless) and shows it instead of the demo workflow.
    if held := st.session_state.get('workflow_data'):
        return held
    response = api_get(f'{API_URL}/workflow')
    response.raise_for_status()
    return Workflow.model_validate(response.json()).model_dump(mode='json', exclude_unset=True)


def esc(value: Any) -> str:
    """Escape any API value before it goes into HTML."""
    return html.escape('' if value is None else str(value))


def badge(text: str, css_class: str) -> str:
    return f'<span class="badge {css_class}">{esc(text)}</span>'


def unverified_badge(text: str = NOT_VERIFIED) -> str:
    return badge('⚠ ' + text, 'badge-unverified')


def status_badge(status: Any) -> str:
    # An unknown status gets a neutral badge, never a Ready-looking one.
    css_class, symbol = STATUS_STYLES.get(status, ('badge-neutral', '?'))
    return badge(f'{symbol} {status or "Unknown"}', css_class)


def safe_link(url: Any) -> str | None:
    """Return an http(s) URL, or None, so odd values never become links."""
    return safe_url(url)


def yes_no(value: Any) -> str:
    # Missing is not the same as No: never guess.
    if value is True:
        return 'Yes'
    if value is False:
        return 'No'
    return 'Not provided'


def detail_line(label: str, value: Any) -> None:
    if value:
        st.markdown(f'- **{label}:** {value}')
    else:
        st.markdown(f'- **{label}:** {unverified_badge()}', unsafe_allow_html=True)


try:
    with st.spinner('Loading your workflow…'):
        data = load_workflow()
except (requests.RequestException, ValueError):
    st.error('Could not load your workflow. The service may be unavailable or '
             'returned incomplete data. Try again in a moment.')
    st.info(
        'If this continues, contact the app team. Your selections in this '
        'session have been kept.'
    )
    st.button('Retry')  # Clicking any button reruns the script.
    st.stop()

# One "as of" date per session, sent on every request so the whole session agrees on today.
if data.get('as_of'):
    st.session_state.setdefault('session_as_of', data['as_of'])

if data.get('is_mock'):
    st.warning('Sample data. Not verified. Do not rely on it.')

# Confirmation messages saved before a st.rerun() are shown once after it.
if 'flash_message' in st.session_state:
    st.success(st.session_state.pop('flash_message'))

profile = data.get('student_profile') or {}
sync_profile_context(profile)
st.session_state['workflow_profile'] = profile  # sent back with each task action
if profile.get('school_verified') is not True:
    st.warning('Not verified for your school. Confirm school-specific requirements with your DSO.')
tasks = data.get('workflow') or []
titles = {t['id']: t.get('title', t['id']) for t in tasks if t.get('id')}


def title_of(task_id: str) -> str:
    return titles.get(task_id, task_id)


def source_is_verified(source: dict[str, Any]) -> bool:
    """A source counts as evidence only with both an official URL and a date."""
    return source_verified(source)


def has_unverified_blocker(task: dict[str, Any]) -> bool:
    # Anything other than an explicit 'verified' counts as unverified.
    return any(
        blocker.get('verification_status') != 'verified'
        for blocker in task.get('blockers') or []
    )


def has_unverified_source(task: dict[str, Any]) -> bool:
    sources = task.get('sources') or []
    # An empty list proves nothing, so it counts as unverified too.
    return not sources or any(not source_is_verified(s) for s in sources)


def source_gap_label(task: dict[str, Any]) -> str:
    if not task.get('sources'):
        return 'No source on file'
    return 'Source link or date missing'


def has_unverified(task: dict[str, Any]) -> bool:
    return has_unverified_blocker(task) or has_unverified_source(task)


def last_verified_date(task: dict[str, Any]) -> str | None:
    """Oldest verified date, or None unless every source has a URL and a date."""
    sources = task.get('sources') or []
    if sources and all(source_is_verified(s) for s in sources):
        return str(min(s['last_verified'] for s in sources))
    return None


def verification_note(task: dict[str, Any]) -> str:
    """A date only when nothing about the task is unverified."""
    verified_on = last_verified_date(task)
    if has_unverified(task) or not verified_on:
        return NOT_VERIFIED
    return f'Last verified: {verified_on}'


profile_tab, workflow_tab, readiness_tab, detail_tab, assistant_tab = st.tabs(
    ['Profile', 'Workflow', 'Readiness', 'Task details', 'Assistant'],
    key='dashboard_tabs', on_change='rerun',
)

with profile_tab:
    render_onboarding(profile, API_URL)
    st.divider()
    st.subheader('Student profile')
    left, right = st.columns(2)
    left.metric('Institution', profile.get('institution') or 'Not provided')
    right.metric('Visa type', profile.get('visa_type') or 'Not provided')
    left.metric('Arrival date', str(profile.get('arrival_date') or 'Not provided'))
    right.metric('Has an SSN', yes_no(profile.get('has_ssn')))

    st.markdown('##### Completed tasks')
    completed = profile.get('completed_tasks') or []
    if completed:
        for task_id in completed:
            st.markdown(f'- ✓ {title_of(task_id)}')
    else:
        st.caption('No tasks marked as completed yet.')

with workflow_tab:
    st.subheader('Your workflow')
    if not tasks:
        st.info('No tasks to show yet.')
    for task in tasks:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.markdown(f'#### {task.get("title", "Untitled task")}')
            priority = esc(task.get('priority', 'Priority not set'))
            left.markdown(
                f'<span class="pill">{priority}</span>', unsafe_allow_html=True
            )
            status_html = status_badge(task.get('status'))
            right.markdown(
                f'<div style="text-align: right;">{status_html}</div>',
                unsafe_allow_html=True,
            )

            if has_unverified(task):
                st.markdown(unverified_badge(), unsafe_allow_html=True)
            else:
                st.caption(verification_note(task))

            action = task.get('next_action') or {}
            if action.get('text'):
                st.info(f'Next action: {action["text"]}')

            prerequisites = [title_of(p) for p in task.get('prerequisites') or []]
            if prerequisites:
                st.caption('Prerequisites: ' + ', '.join(prerequisites))
            st.button('View checklist', key='view_checklist:' + task['id'],
                      on_click=open_task, args=(task['id'],))


def render_readiness() -> None:
    st.subheader('Readiness')
    if not tasks:
        # No tasks is not the same as nothing blocked: never show an all-clear.
        st.info('No tasks available to assess readiness.')
        return
    blocked = [t for t in tasks if t.get('status') == 'Blocked']
    if not blocked:
        st.success('Nothing is blocked.')
    for task in blocked:
        heading = f'{task.get("title", "Untitled task")} (blocked)'
        with st.expander(heading, expanded=True):
            missing = task.get('missing_prerequisites') or []
            if missing:
                st.markdown('**Finish these first:**')
                for task_id in missing:
                    st.markdown(f'- {title_of(task_id)}')

            for blocker in task.get('blockers') or []:
                reason = blocker.get('explanation', 'No explanation given')
                st.markdown(f'**Why:** {reason}')
                if blocker.get('unlocks_on'):
                    st.info(f'Unlocks on {blocker["unlocks_on"]}')
                if blocker.get('verification_status') != 'verified':
                    st.markdown(unverified_badge(), unsafe_allow_html=True)

            if has_unverified_source(task):
                st.markdown(
                    unverified_badge(source_gap_label(task)),
                    unsafe_allow_html=True,
                )
            st.caption(verification_note(task))

            # Day 3 pattern. The endpoint name and shape are still to be agreed
            # with BE, so do not build against this URL yet.
            #
            # if st.button('Resolve blocker', key='resolve_' + task['id']):
            #     ...call the API, then:
            #     st.session_state['flash_message'] = 'Blocker resolved.'
            #     st.rerun()

    st.divider()
    st.subheader('Before you go')
    # Show every task that still needs doing, plus any task that has guidance.
    # Missing guidance stays visible as "Not verified" instead of disappearing.
    guides = [
        t for t in tasks if t.get('before_you_go') or t.get('status') != 'Completed'
    ]
    if not guides:
        st.caption('Every task is completed.')
    for task in guides:
        guide = task.get('before_you_go')
        with st.container(border=True):
            st.markdown(f'#### {task.get("title", "Untitled task")}')
            if not guide:
                st.markdown(
                    unverified_badge('Before-you-go details not verified'),
                    unsafe_allow_html=True,
                )
                st.caption(
                    'Confirm hours, fees and required documents with the office '
                    'before you go.'
                )
                continue
            docs_col, details_col = st.columns(2)

            with docs_col:
                st.markdown('**Documents to bring**')
                documents = guide.get('required_documents') or []
                if documents:
                    for document in documents:
                        st.markdown(f'- {document}')
                else:
                    st.markdown(
                        unverified_badge('Document list not verified'),
                        unsafe_allow_html=True,
                    )
                for warning in guide.get('warnings') or []:
                    st.warning(warning)

            with details_col:
                st.markdown('**Visit details**')
                detail_line('Hours', guide.get('hours'))
                detail_line('Fees', guide.get('fees'))
                detail_line('Appointment rules', guide.get('appointment_rules'))
                detail_line('Phone', guide.get('phone'))
                link = safe_link(guide.get('official_url'))
                if link:
                    st.markdown(
                        '- **Official page:** '
                        f'<a href="{esc(link)}" target="_blank" '
                        f'rel="noopener noreferrer">{esc(link)}</a>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'- **Official page:** {unverified_badge("No verified link")}',
                        unsafe_allow_html=True,
                    )
                st.caption(verification_note(task))


with readiness_tab:
    render_readiness()

with detail_tab:
    selected_task = render_task_details(tasks, bool(data.get('is_mock')), API_URL)
    render_email_preview(next((t for t in tasks if t['id'] == selected_task), None))

with assistant_tab:
    render_assistant(profile, selected_task, API_URL, os.getenv('ASSISTANT_MODE', 'mock'),
                     titles.get(selected_task))
