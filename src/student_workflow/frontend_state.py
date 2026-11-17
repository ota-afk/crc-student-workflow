"""Session context and task navigation; never changes backend task status."""

import json

import streamlit as st


def open_task(task_id: str) -> None:
    st.session_state['detail_task'] = task_id
    st.session_state['dashboard_tabs'] = 'Task details'


def sync_profile_context(profile: dict) -> None:
    context = json.dumps({key: profile.get(key) for key in (
        'student_id', 'institution', 'school_id', 'state', 'visa_type',
        'arrival_date', 'has_ssn',
    )}, sort_keys=True)
    old = st.session_state.get('profile_context')
    if old is not None and old != context:
        for key in list(st.session_state):
            if key.startswith('document:') or key in {
                'documents_on_hand', 'assistant_history', 'api_email_draft',
            }:
                del st.session_state[key]
        st.info('Profile context changed. Reconfirm your documents for this workflow. '
                'Old chat and email drafts have been cleared.')
    st.session_state['profile_context'] = context
