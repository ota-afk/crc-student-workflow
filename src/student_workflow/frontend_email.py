"""Shows the email draft the API returns from "Resolve blocker"; nothing is ever sent."""

import streamlit as st


def render_email_preview(task: dict | None) -> None:
    if task is None:
        return
    st.markdown('#### Email draft')
    stored = st.session_state.get('api_email_draft')
    draft = stored if stored and stored.get('task_id') == task['id'] else None
    if draft is None:
        if task['status'] == 'Blocked':
            st.info('Choose Resolve blocker to get an email draft for this task.')
        else:
            st.caption('No email draft for this task.')
        return
    st.warning('Draft email. Not verified. Review all wording and replace placeholders in '
               'your own mail app before sending. No email is sent from this page and '
               'task status is not changed by copying it.')
    st.caption('Recipient: [Office or DSO email address]. Confirm the correct contact with '
               'your school or the relevant office.')
    st.caption('Copy the draft using the copy icon at the top right of the text below. If '
               'copying is unavailable, select the text and use your device’s Copy command.')
    st.code('Subject: ' + draft['subject'] + '\n\n' + draft['body'], language=None,
            wrap_lines=True)
    if st.button('Clear email draft', key='clear_email'):
        st.session_state.pop('api_email_draft', None)
        st.rerun()
