"""Task detail and assistant views for the existing Streamlit dashboard."""

import html
import os

import requests
import streamlit as st

from .frontend import ask_assistant, safe_url, source_verified
from .frontend_state import open_task


@st.dialog('Readiness', on_dismiss='rerun')
def show_readiness(task: dict) -> None:
    st.write(task['title'])
    if task['status'] == 'Blocked':
        st.warning('Status: Blocked. Documents checked do not remove prerequisites or timing blockers.')
    else:
        st.caption('Current task status: ' + task['status'])
    documents = list(dict.fromkeys((task.get('before_you_go') or {}).get('required_documents') or []))
    selected = st.session_state.get('documents_on_hand', {}).get(task['id'], {})
    missing = [document for document in documents if not selected.get(document)]
    if not documents:
        st.info('Document requirements are unknown. Confirm with the office.')
    elif missing:
        st.info('Missing listed documents: ' + ', '.join(missing))
    else:
        st.info('Listed documents checked. This does not confirm eligibility or change task status.')
    if task.get('missing_prerequisites'):
        st.warning('Some prerequisite tasks still need to be completed.')
    st.caption('This is your document inventory, not a backend readiness decision. '
               'Task updates are not connected yet.')
    if st.button('Close readiness', key='close_readiness'):
        st.rerun()


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption('No sources on file. Confirm with the office.')
    for source in sources:
        url = safe_url(source.get('url'))
        label = html.escape(str(source.get('rule_id') or 'Official source'))
        link = (f'<a href="{html.escape(url, quote=True)}" target="_blank" '
                f'rel="noopener noreferrer">{label}</a>' if url else label)
        verified_on = html.escape(str(source.get('last_verified') or 'Not recorded'))
        status = 'Verified' if source_verified(source) else 'Not verified'
        st.markdown(
            f'{link} — Source date: {verified_on} — {status}',
            unsafe_allow_html=True,
        )


def render_task_details(tasks: list[dict], is_mock: bool) -> str | None:
    st.subheader('Task details')
    if not tasks:
        st.info('No tasks available. Try again when your workflow is available.')
        return None
    by_id = {task['id']: task for task in tasks}
    if st.session_state.get('detail_task') not in by_id:
        st.session_state['detail_task'] = next(iter(by_id))
    task_id = st.selectbox('Choose a task', list(by_id), key='detail_task',
                           format_func=lambda key: by_id[key]['title'])
    task = by_id[task_id]
    st.markdown(f'### {task["title"]}')
    st.caption(f'{task["status"]} · {task["priority"]}')
    st.markdown('#### Next steps')
    action = task.get('next_action') or {}
    if action.get('text'):
        st.info(action['text'])
    else:
        st.caption('No next step supplied. Review the official sources or ask the office.')
    for prerequisite in task.get('missing_prerequisites') or []:
        title = by_id.get(prerequisite, {}).get('title', prerequisite)
        if prerequisite in by_id:
            st.button('Finish first: ' + title, key=f'prerequisite:{task_id}:{prerequisite}',
                      on_click=open_task, args=(prerequisite,))
        else:
            st.write('Finish first: ' + title)
    for blocker in task.get('blockers') or []:
        note = (' — Not verified. Confirm with the office.'
                if blocker.get('verification_status') != 'verified' else '')
        st.warning(blocker['explanation'] + note)
        if blocker.get('unlocks_on'):
            st.caption(f'Listed unlock date: {blocker["unlocks_on"]}{note}')
        elif blocker.get('type') == 'timing':
            st.caption('Unlock date: Not verified. Confirm with the office.')

    st.markdown('#### Document checklist')
    st.caption('Check what you have. No uploads or document numbers. '
               'Selections stay in this browser session and do not complete tasks.')
    guide = task.get('before_you_go') or {}
    documents = list(dict.fromkeys(guide.get('required_documents') or []))
    # Separate durable session state from widget state: Streamlit deletes hidden
    # widgets when switching tasks. Key by document text so reordered lists are safe.
    selected = st.session_state.setdefault('documents_on_hand', {})
    task_selected = selected.setdefault(task_id, {})
    missing = []
    for document in documents:
        key = f'document:{task_id}:{document}'
        if key not in st.session_state:
            st.session_state[key] = task_selected.get(document, False)
        checked = st.checkbox(f'I have: {document}', key=key)
        task_selected[document] = checked
        if not checked:
            missing.append(document)
    if not documents:
        st.info('Document requirements are not available. Confirm with the office.')
    elif missing:
        st.info(f'{len(missing)} documents still missing: ' + ', '.join(missing))
    else:
        st.info('Documents checked. This does not change task status or confirm eligibility.')
    # Do not infer overall readiness from a partial, potentially unverified list.
    if task.get('status') == 'Blocked':
        st.warning('This task is still blocked. Review its prerequisites and timing above.')
    if is_mock:
        st.caption('Sample checklist. Confirm the actual requirements before your visit.')

    if st.button('View readiness', key='show_readiness'):
        show_readiness(task)
    st.caption('Task updates are not connected yet. Your checks do not resolve or complete tasks.')
    st.button('Resolve blocker', key='resolve_task', disabled=True)
    st.button('Mark done', key='complete_task', disabled=True)

    st.markdown('#### Before your visit')
    for label, key in [('Hours', 'hours'), ('Fees', 'fees'),
                       ('Appointment rules', 'appointment_rules'), ('Phone', 'phone')]:
        st.write(f'{label}: {guide.get(key) or "Not verified. Confirm with the office."}')
    if link := safe_url(guide.get('official_url')):
        st.link_button('Open official visit information', link)
    for warning in guide.get('warnings') or []:
        st.warning(warning)
    st.markdown('#### Sources and dates')
    render_sources(task.get('sources') or [])
    return task_id


def render_assistant(profile: dict, task_id: str | None, api_url: str, mode: str,
                     task_title: str | None = None) -> None:
    st.subheader('Process assistant')
    context = task_title or 'No task selected'
    st.caption('Active task: ' + context)
    st.caption('Ask about the task selected in Task details. Do not include your name, '
               'student ID, passport number, SSN or other personal details.')
    st.caption('For immigration status or work authorization, contact your school’s DSO.')
    if mode == 'mock':
        st.info('Chat preview: replies are fixed sample text. Live AI is not connected.')
    elif mode == 'live' and not os.getenv('ASSISTANT_ENDPOINT'):
        st.info('Live assistant is not configured. Its endpoint and answer format '
                'still need BE/AI agreement; use the sample preview for now.')
    history = st.session_state.setdefault('assistant_history', [])
    if st.button('Clear conversation', key='clear_chat'):
        history.clear()
    question = st.chat_input('Ask about your next step', max_chars=500)
    error = False
    if question and question.strip():
        history.append({'role': 'user', 'text': question, 'task_title': context})
        try:
            with st.spinner('Getting an answer…'):
                answer = ask_assistant(question, task_id, profile, api_url, mode,
                                       endpoint=os.getenv('ASSISTANT_ENDPOINT'))
            history.append({'role': 'assistant', 'answer': answer.model_dump(mode='json'),
                            'task_title': context})
        except (requests.RequestException, ValueError, OSError):
            error = True
        # Bound memory in a long-running browser session.
        del history[:-40]
    for message in history:
        with st.chat_message(message['role']):
            st.caption('Task context: ' + message.get('task_title', 'Not recorded'))
            if message['role'] == 'user':
                st.write(message['text'])
                continue
            answer = message['answer']
            if answer['is_mock']:
                st.warning('Sample response. Not verified. Do not rely on it.')
            elif not answer['verified'] or not answer['sources'] or not all(
                source_verified(source) for source in answer['sources']
            ):
                st.warning('Not verified. Confirm with the office.')
            st.markdown(answer['answer'])
            for index, step in enumerate(answer['steps'], 1):
                st.write(f'{index}. {step}')
            if answer['contact']:
                st.write('Who to contact: ' + answer['contact'])
            render_sources(answer['sources'])
    if error:
        st.error('Could not get an answer. Try your question again, or use the '
                 'task details and official sources. Your checklist is unchanged.')
