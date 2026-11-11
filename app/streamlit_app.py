import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv('API_URL', 'http://localhost:8000')

st.set_page_config(page_title='International Student Navigator', layout='wide')
st.title('International Student Navigator')

# No caching on purpose: the dashboard must always show the live state.
# If you add caching later, clear it right after any action that changes a task.


def load_workflow():
    response = requests.get(f'{API_URL}/workflow', timeout=10)
    response.raise_for_status()
    return response.json()


try:
    data = load_workflow()
except requests.RequestException as error:
    st.error(f'Could not reach the API at {API_URL}: {error}')
    st.stop()

if data.get('is_mock'):
    st.warning('Sample data. Not verified. Do not rely on it.')

profile_tab, workflow_tab, readiness_tab = st.tabs(['Profile', 'Workflow', 'Readiness'])

with profile_tab:
    st.json(data['student_profile'])

with workflow_tab:
    for task in data['workflow']:
        st.write(f"**{task['title']}**: {task['status']} ({task['priority']})")

with readiness_tab:
    blocked = [t for t in data['workflow'] if t['status'] == 'Blocked']
    if not blocked:
        st.success('Nothing is blocked.')
    for task in blocked:
        st.write(f"**{task['title']}** is waiting on: {', '.join(task['missing_prerequisites'])}")
        # Day 3 pattern (the endpoint name is an example): call the API, then rerun
        # so the screen redraws with fresh data and no second click is needed.
        #
        # if st.button('Resolve blocker', key='resolve_' + task['id']):
        #     requests.post(f"{API_URL}/tasks/{task['id']}/resolve", timeout=30).raise_for_status()
        #     st.rerun()
