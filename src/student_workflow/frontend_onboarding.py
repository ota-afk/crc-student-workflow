"""CA school/profile preparation; application awaits the agreed POST contract."""

from datetime import date

import requests
import streamlit as st

from .frontend import search_school_directory


def clear_school_selection() -> None:
    for key in ('school_results', 'school_search_error', 'onboarding_school', 'onboarding_draft'):
        st.session_state.pop(key, None)


def _search(api_url: str) -> None:
    query = st.session_state.get('school_query', '')
    st.session_state.pop('school_results', None)
    st.session_state.pop('onboarding_school', None)
    st.session_state.pop('onboarding_draft', None)
    try:
        with st.spinner('Searching California schools…'):
            schools = search_school_directory(api_url, query)
        st.session_state['school_results'] = [s.model_dump() for s in schools]
        st.session_state.pop('school_search_error', None)
    except (requests.RequestException, ValueError):
        st.session_state['school_search_error'] = True


def render_onboarding(profile: dict, api_url: str) -> None:
    st.subheader('Prepare your profile')
    st.caption('California only. Choose a state, then search for your school. '
               'Do not enter your name, student ID or document numbers.')
    state = st.selectbox('State', ['California', 'Other state (not supported)'],
                         key='onboarding_state', on_change=clear_school_selection)
    if state != 'California':
        st.info('California only is supported at this time. School selection has been cleared. '
                'Your current workflow has not changed.')
        return
    st.text_input('School name or city', key='school_query', max_chars=100,
                  on_change=clear_school_selection)
    st.button('Search schools', key='search_schools', on_click=_search, args=(api_url,))
    if st.session_state.get('school_search_error'):
        st.error('Could not search schools. Try again. Your current workflow and documents '
                 'have not changed.')
        st.button('Retry school search', key='retry_schools', on_click=_search, args=(api_url,))
    results = st.session_state.get('school_results', [])
    if 'school_results' in st.session_state and not results:
        st.info('No schools found. Try another name or city, or choose My school is not listed.')
    by_id = {school['school_id']: school for school in results}
    labels = {None: 'Choose a school', '__not_listed': 'My school is not listed', **{
        key: f'{school["institution"]} — {school["city"]}' for key, school in by_id.items()
    }}
    options = list(labels)
    if st.session_state.get('onboarding_school') not in options:
        st.session_state.pop('onboarding_school', None)
    selected = st.selectbox('Choose a school', options, key='onboarding_school',
                            format_func=lambda key: labels[key])
    school = by_id.get(selected)
    if school:
        st.caption('Selected school: ' + school['institution'])
    visa = st.text_input('Visa type', value=profile.get('visa_type', 'F-1'),
                         key='onboarding_visa', max_chars=20)
    arrival = st.date_input('Arrival date', value=date.fromisoformat(profile['arrival_date']),
                            key='onboarding_arrival')
    has_ssn = st.radio('Do you have an SSN?', ['No', 'Yes'], horizontal=True,
                       index=1 if profile.get('has_ssn') else 0, key='onboarding_has_ssn',
                       help='Only yes/no. Never enter the number.')
    if selected is not None and arrival is not None and visa.strip():
        st.session_state['onboarding_draft'] = {
            'state': 'CA', 'school_id': school['school_id'] if school else None,
            'institution': school['institution'] if school else 'School not listed',
            'visa_type': visa.strip(), 'arrival_date': arrival.isoformat(),
            'has_ssn': has_ssn == 'Yes',
        }
        if not school or school['school_verified'] is not True:
            st.warning('Not verified for your school. Confirm school-specific requirements '
                       'with your DSO.')
        if school is None:
            st.info('Not being listed does not mean your school is ineligible. Generic '
                    'guidance will need confirmation with your DSO.')
    else:
        st.session_state.pop('onboarding_draft', None)
        if arrival is None:
            st.info('Choose an arrival date before preparing your profile.')
        elif not visa.strip():
            st.info('Enter your visa type before preparing your profile.')
    st.button('Generate workflow', key='generate_workflow', disabled=True)
    st.info('Profile changes are not applied yet: workflow generation is awaiting backend '
            'integration. The current workflow and checked documents remain unchanged.')
