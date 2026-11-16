"""Explicit, session-only email template preview; no live API or email sending."""

import json
from pathlib import Path

import streamlit as st
from pydantic import BaseModel, ConfigDict, Field


class EmailTemplate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


def render_email_preview(task: dict | None, profile: dict, as_of: str,
                         task_titles: dict[str, str]) -> None:
    # Include all supplied context so changed requirements invalidate a draft too.
    context_key = json.dumps([task, profile, as_of, task_titles], sort_keys=True)
    if st.session_state.get('email_context') != context_key:
        st.session_state.pop('email_preview', None)
        st.session_state['email_context'] = context_key
    if task is None:
        return
    st.markdown('#### Email draft')
    if task['status'] != 'Blocked':
        st.caption('Choose a blocked task to preview a request for guidance.')
        return
    st.caption('Preview a placeholder template for the selected task. Live email '
               'generation is not connected. No email is sent and task status stays unchanged.')
    if st.button('Preview sample email draft', key='preview_email'):
        st.session_state.pop('email_preview', None)
        try:
            with st.spinner('Preparing sample draft…'):
                path = Path(__file__).resolve().parents[2] / 'data/mock/email.mock.json'
                template = EmailTemplate.model_validate_json(path.read_text(encoding='utf-8'))
                items = [b['explanation'] for b in task.get('blockers') or []]
                items += ['Missing prerequisite: ' + task_titles.get(key, 'Unlisted task')
                          for key in task.get('missing_prerequisites') or []]
                fields = {'task_title': task['title'],
                          'context': '\n'.join('- ' + item for item in items)
                          or '- No blocker details supplied. Please advise.'}
                st.session_state['email_preview'] = (
                    'Subject: ' + template.subject.format(**fields) + '\n\n'
                    + template.body.format(**fields)
                )
        except (OSError, ValueError, KeyError):
            st.error('Could not prepare the sample draft. Try previewing it again. '
                     'Your checklist is unchanged.')
    if draft := st.session_state.get('email_preview'):
        st.warning('Sample email draft. Not verified. Review all wording and '
                   'replace placeholders in your own mail app before sending.')
        st.caption('Recipient: [Office or DSO email address]. Confirm the correct '
                   'contact with your school or the relevant office.')
        st.caption('Copy email draft using the copy icon at the top right of the '
                   'text below. If copying is unavailable, select the text and '
                   'use your device’s Copy command.')
        st.code(draft, language=None, wrap_lines=True)
        if st.button('Clear email draft', key='clear_email'):
            st.session_state.pop('email_preview', None)
            st.rerun()
    else:
        st.info('No email draft yet. Preview a sample when you are ready.')
