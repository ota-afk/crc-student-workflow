"""Flyover's demo sign-in: the first screen, and where the profile questions are first asked.

It imitates a sign-in. There are no accounts: any password works and is never stored or sent.
The email is real and checked for shape, because the notification feature will send to it;
until that exists it stays in this browser session only, never reaching the API or the model.
The profile answers (school, arrival date, visa type, SSN yes/no) build the first workflow
through the API, exactly as Profile setup does, so they carry over into page 1.
"""

import re
from datetime import date

import requests
import streamlit as st

from . import flyover_client as client
from .flyover_art import banner, logo

# One @, something before it, a dot after it, no spaces: catches typos, not a full RFC check.
EMAIL_SHAPE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
EMAIL_MAX = 254  # the longest an email address can be
# Never a real student ID: the workflow only needs some identifier for this session.
SESSION_STUDENT_ID = 'flyover_session'


def valid_email(email: str) -> bool:
    return len(email) <= EMAIL_MAX and bool(EMAIL_SHAPE.match(email))


def masked(email: str) -> str:
    """'r***@gmail.com': enough to recognise your own address on screen or in a recording."""
    name, _, domain = email.partition('@')
    return f'{name[:1]}***@{domain}'


def signed_in() -> bool:
    return bool(st.session_state.get('flyover_account'))


def sign_out() -> None:
    """Forget everything from this session (profile, progress, chat, free times, email)."""
    st.session_state.clear()


def render_signin(api_url: str) -> None:
    """The sign-in screen. On success it stores the account and first workflow, then reruns."""
    with st.container(key='flyover_signin_hero'):
        st.html(banner())
        left, _ = st.columns([1, 1.15], gap='large')
        with left, st.container(key='flyover_signin'):
            st.image(logo(), width=200)
            st.subheader('Welcome aboard')
            st.caption('Sign in to plan your first weeks as an international student. '
                       'This is a demo: any password works.')
            if 'flyover_schools' not in st.session_state:
                try:
                    st.session_state['flyover_schools'] = client.fetch_schools(api_url)
                except (requests.RequestException, ValueError):
                    st.error('The school list is unavailable right now. Try again in a minute.')
                    st.button('Retry', key='flyover_signin_retry')
                    return
            schools = {s['school_id']: s for s in st.session_state['flyover_schools']}
            options = list(schools) + [None]
            default = options.index('crc') if 'crc' in options else len(options) - 1
            with st.form('flyover_signin_form', border=False):
                email = st.text_input('Email', key='flyover_signin_email', max_chars=EMAIL_MAX,
                                      placeholder='you@example.com',
                                      help='Used only for reminders you ask for. Kept in this '
                                           'browser session; never sent to the AI.')
                st.text_input('Password', type='password', key='flyover_signin_password',
                              help="Demo sign-in: any password works. Don't use a real "
                                   'password; it is never stored or sent anywhere.')
                st.markdown('##### About your arrival')
                school_id = st.selectbox(
                    'School', options, index=default, key='flyover_signin_school',
                    format_func=lambda key: schools[key]['institution'] if key
                    else 'My school is not listed')
                first, second = st.columns([1.15, 1])
                with first:
                    arrival = st.date_input('Arrival date', value=date.today(),
                                            key='flyover_signin_arrival')
                with second:
                    visa = st.selectbox('Visa type', ['F-1'], key='flyover_signin_visa')
                ssn = st.radio('Do you have an SSN?', ['No', 'Yes'], horizontal=True,
                               key='flyover_signin_ssn',
                               help='Yes or no only. Never enter the number.')
                enrolled = st.date_input(
                    'Enrollment date (optional)', value=None, key='flyover_signin_enrollment',
                    help='The day you enrolled in classes. Only used to work out your tuition '
                         'deadline.')
                submitted = st.form_submit_button('Sign in and start', type='primary',
                                                  width='stretch')
            st.caption('No names, document numbers or uploads.')
            if submitted:
                _sign_in(api_url, email.strip(), school_id, schools, arrival, visa, ssn,
                         enrolled)


def _sign_in(api_url: str, email: str, school_id, schools: dict, arrival, visa: str,
             ssn: str, enrolled=None) -> None:
    # The password is never kept: drop the widget's value whatever happens next.
    st.session_state.pop('flyover_signin_password', None)
    if not valid_email(email):
        st.error('Enter a real email address, like you@example.com.')
        return
    if arrival is None:
        st.error('Choose your arrival date.')
        return
    changes = {'student_id': SESSION_STUDENT_ID, 'school_id': school_id,
               'institution': schools[school_id]['institution'] if school_id
               else 'School not listed',
               'visa_type': visa, 'arrival_date': arrival.isoformat(), 'has_ssn': ssn == 'Yes',
               'enrollment_date': enrolled.isoformat() if enrolled else None}
    try:
        with st.spinner('Building your workflow…'):
            workflow = client.generate_workflow(api_url, {}, changes)
    except (requests.RequestException, ValueError):
        st.error('Could not build your workflow. Try again in a moment.')
        return
    st.session_state['flyover_account'] = {'email': email}
    st.session_state['flyover_data'] = workflow
    st.session_state['flyover_flash'] = 'Welcome aboard! Your workflow is ready.'
    st.rerun()
