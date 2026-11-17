"""Flyover's first screen: try the CRC demo in one click, or start with your own details.

There are no accounts. "Try the CRC demo" needs no email and no password: it builds the
synthetic demo student's workflow on the scenario date (flyover_scenario.py). "Use your own
details" asks the profile questions and an email, which is used only for reminders the
student asks for; it stays in this browser session, never reaching the workflow API or the
model. There is no password field: a public demo has no reason to collect one. Both paths
build the first workflow through the API on the scenario date, so the public walkthrough
always tells the same, explicitly dated story.
"""

import re
from datetime import date

import requests
import streamlit as st

from . import flyover_client as client
from .flyover_art import banner, logo
from .flyover_scenario import DEMO_PROFILE, SCENARIO_AS_OF, long_date

# One @, something before it, a dot after it, no spaces: catches typos, not a full RFC check.
EMAIL_SHAPE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
EMAIL_MAX = 254  # the longest an email address can be
# Never a real student ID: the workflow only needs some identifier for this session.
SESSION_STUDENT_ID = 'flyover_session'
ENROLLMENT_TERMS = {None: 'Choose a term', 'fall_2026': 'Fall 2026',
                    'spring_2027': 'Spring 2027'}
ENROLLMENT_PRIORITIES = {
    None: "I don't know yet", '0': 'Priority 0', '0.5': 'Priority .5',
    '0.75': 'Priority .75', '1': 'Priority 1', '1.1': 'Priority 1.1',
    '1.2': 'Priority 1.2', '1.3': 'Priority 1.3', '1.4': 'Priority 1.4',
    '2': 'Priority 2', '3': 'Priority 3',
    'open_by_appointment': 'Open enrollment by appointment', 'open': 'Open enrollment',
}


def valid_email(email: str) -> bool:
    return len(email) <= EMAIL_MAX and bool(EMAIL_SHAPE.match(email))


def masked(email: str) -> str:
    """'r***@gmail.com': enough to recognise your own address on screen or in a recording."""
    name, _, domain = email.partition('@')
    return f'{name[:1]}***@{domain}'


def signed_in() -> bool:
    """True when the visitor gave an email (the own-details path); the demo has none."""
    return bool(st.session_state.get('flyover_account'))


def entered() -> bool:
    """True once the visitor is past the first screen, by either path."""
    return signed_in() or bool(st.session_state.get('flyover_demo'))


def sign_out() -> None:
    """Forget everything from this session (profile, progress, chat, free times, email)."""
    st.session_state.clear()


def render_signin(api_url: str) -> None:
    """The first screen. On success it stores the first workflow, then reruns."""
    with st.container(key='flyover_signin_hero'):
        st.html(banner())
        left, _ = st.columns([1, 1.15], gap='large')
        with left, st.container(key='flyover_signin'):
            st.image(logo(), width=200)
            st.subheader('Welcome aboard')
            st.caption('See how Flyover plans an international student’s first weeks at '
                       'Cosumnes River College. No account or password needed.')
            # The primary action comes before the school list, so it still works if the
            # school directory is down.
            if st.button('Try the CRC demo', key='flyover_try_demo', type='primary',
                         icon=':material/flight_takeoff:', width='stretch'):
                _start_demo(api_url)
            st.caption(f'A sample F-1 student who arrived {long_date(DEMO_PROFILE["arrival_date"])} '
                       f'and enrolled {long_date(DEMO_PROFILE["enrollment_date"])}, with no steps '
                       'done yet. Nothing to type.')
            with st.expander('Or use your own details'):
                _own_details_form(api_url)


def _start_demo(api_url: str) -> None:
    """Build the synthetic CRC student's workflow on the scenario date."""
    try:
        with st.spinner('Building the demo workflow…'):
            workflow = client.start_demo(api_url, DEMO_PROFILE, SCENARIO_AS_OF.isoformat())
    except (requests.RequestException, ValueError):
        st.error('Could not start the demo. Try again in a moment.')
        return
    st.session_state['flyover_demo'] = True
    st.session_state['flyover_data'] = workflow
    st.session_state['flyover_flash'] = 'Welcome aboard! The demo workflow is ready.'
    st.rerun()


def _own_details_form(api_url: str) -> None:
    if 'flyover_schools' not in st.session_state:
        try:
            st.session_state['flyover_schools'] = client.fetch_schools(api_url)
        except (requests.RequestException, ValueError):
            st.error('The school list is unavailable right now. Try again in a minute, or try '
                     'the CRC demo above.')
            st.button('Retry', key='flyover_signin_retry')
            return
    schools = {s['school_id']: s for s in st.session_state['flyover_schools']}
    options = list(schools) + [None]
    default = options.index('crc') if 'crc' in options else len(options) - 1
    st.caption(f'Your plan is still worked out as of {long_date(SCENARIO_AS_OF)}, the demo’s '
               'date, so it matches the rest of this walkthrough.')
    with st.form('flyover_signin_form', border=False):
        email = st.text_input('Email', key='flyover_signin_email', max_chars=EMAIL_MAX,
                              placeholder='you@example.com',
                              help='Used only for reminders you ask for. Kept in this '
                                   'browser session; never sent to the AI.')
        st.markdown('##### About your arrival')
        school_id = st.selectbox(
            'School', options, index=default, key='flyover_signin_school',
            format_func=lambda key: schools[key]['institution'] if key
            else 'My school is not listed')
        first, second = st.columns([1.15, 1])
        with first:
            # The demo's arrival date by default: the walkthrough is set in August 2026.
            arrival = st.date_input('Arrival date',
                                    value=date.fromisoformat(DEMO_PROFILE['arrival_date']),
                                    key='flyover_signin_arrival')
        with second:
            visa = st.selectbox('Visa type', ['F-1'], key='flyover_signin_visa')
        ssn = st.radio('Do you have an SSN?', ['No', 'Yes'], horizontal=True,
                       key='flyover_signin_ssn',
                       help='Yes or no only. Never enter the number.')
        term = st.selectbox(
            'Enrollment term', list(ENROLLMENT_TERMS),
            format_func=ENROLLMENT_TERMS.get, key='flyover_signin_term',
            help='Choose the semester these classes belong to.')
        priority = st.selectbox(
            'Enrollment priority', list(ENROLLMENT_PRIORITIES),
            format_func=ENROLLMENT_PRIORITIES.get, key='flyover_signin_priority',
            help='Use the priority listed in eServices. We show your group’s date range; '
                 'check eServices for your exact appointment.')
        enrolled = st.date_input(
            'Enrollment date (optional)', value=None, key='flyover_signin_enrollment',
            help='The day you enrolled in classes. Only used to work out your tuition '
                 'deadline.')
        submitted = st.form_submit_button('Start with my details', width='stretch')
    st.caption('No names, document numbers, passwords or uploads.')
    if submitted:
        _sign_in(api_url, email.strip(), school_id, schools, arrival, visa, ssn, enrolled,
                 term, priority)


def _sign_in(api_url: str, email: str, school_id, schools: dict, arrival, visa: str,
             ssn: str, enrolled=None, term=None, priority=None) -> None:
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
               'enrollment_date': enrolled.isoformat() if enrolled else None,
               'enrollment_term': term, 'enrollment_priority': priority}
    try:
        with st.spinner('Building your workflow…'):
            # The scenario date, never the API's "today": the reproduction this fixes showed
            # an August profile computed on November 17 and marked "Past due".
            workflow = client.generate_workflow(api_url, {}, changes,
                                                as_of=SCENARIO_AS_OF.isoformat())
    except (requests.RequestException, ValueError):
        st.error('Could not build your workflow. Try again in a moment.')
        return
    st.session_state['flyover_account'] = {'email': email}
    st.session_state['flyover_data'] = workflow
    st.session_state['flyover_flash'] = 'Welcome aboard! Your workflow is ready.'
    st.rerun()
