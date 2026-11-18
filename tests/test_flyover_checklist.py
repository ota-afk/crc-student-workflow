"""Flyover's "Before you go" preview and Checklist tab (guide pages 3–4).

Pure checks of flyover_checklist.py, then the real page against the real API in process
(test_live_api's Bridge). Only synthetic profiles; no network, no model, no email.
"""

from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from test_flyover_app import open_checklist, signed_in_app
from test_live_api import KEY, Bridge
from test_streamlit import values

from student_workflow.api import app as api_app
from student_workflow.flyover import (
    _office_link,
    _source_rows,
    source_label,
)
from student_workflow.flyover_checklist import (
    document_groups,
    fact_sources,
    phone_link,
    task_actions,
)
from student_workflow.flyover_scenario import DEMO_PROFILE

APP = Path(__file__).resolve().parents[1] / 'app/flyover_app.py'
DMV, RESIDENCY, CHECKIN, FEE = ('task_dmv_id', 'task_proof_of_residency', 'task_school_checkin',
                                'task_crc_fee_payment')


@pytest.fixture
def live(monkeypatch):
    for name, value in {'USE_MOCK': 'false', 'RATE_LIMIT': '1000/minute', 'API_KEY': KEY,
                        'API_URL': 'http://localhost:8000'}.items():
        monkeypatch.setenv(name, value)
    bridge = Bridge()
    monkeypatch.setattr(requests, 'get', bridge.get)
    monkeypatch.setattr(requests, 'post', bridge.post)
    return bridge


def workflow(live, **changes) -> dict[str, dict]:
    """The demo student's tasks from the real API, by ID (changes = another profile)."""
    profile = {**DEMO_PROFILE, **changes}
    reply = TestClient(api_app).post('/workflow', headers={'X-API-Key': KEY},
                                     json={'student_profile': profile, 'as_of': '2026-08-14'})
    return {task['id']: task for task in reply.json()['workflow']}


def _task(task_id, documents=(), prerequisites=(), title=None):
    return {'id': task_id, 'title': title or task_id, 'status': 'Ready',
            'prerequisites': list(prerequisites),
            'before_you_go': {'required_documents': list(documents)}}


# ---- Pure helpers ----

def test_groups_start_with_the_task_then_each_prerequisite():
    a = _task('a', ['Passport', 'Lease', 'Passport'], ['b', 'c'], title='REAL ID')
    b, c = _task('b', ['Lease', 'Bill'], title='Residency'), _task('c', title='Check-in')
    groups = document_groups(a, {'a': a, 'b': b, 'c': c})
    assert [g['task']['id'] for g in groups] == ['a', 'b', 'c']
    assert groups[0]['documents'] == ['Passport', 'Lease']  # deduplicated within the task
    # A shared document stays under both tasks, and says which other task needs it.
    assert groups[0]['shared'] == {'Lease': ['Residency']}
    assert groups[1]['shared'] == {'Lease': ['REAL ID']}
    assert groups[2]['documents'] == []


def test_a_fact_is_sourced_only_by_a_citation_matching_field_and_text():
    task = {'before_you_go': {'hours': 'Mon 9–5', 'citations': [
        {'field': 'hours', 'text': 'Mon 9–5', 'rule_id': 'r1', 'verification_status': 'verified'},
        {'field': 'hours', 'text': 'old words', 'rule_id': 'r2',
         'verification_status': 'verified'},
        {'field': 'fees', 'text': 'Mon 9–5', 'rule_id': 'r3', 'verification_status': 'verified'}]},
        'sources': [{'rule_id': 'r1', 'url': 'https://example.gov/hours',
                     'last_verified': '2026-11-12', 'verification_status': 'verified'}]}
    assert [s['rule_id'] for s in fact_sources(task, 'hours')] == ['r1']
    assert fact_sources(task, 'phone') is None


def test_a_cited_rule_missing_from_sources_keeps_its_state_without_a_url():
    task = {'before_you_go': {'fees': '$40', 'citations': [
        {'field': 'fees', 'text': '$40', 'rule_id': 'r9',
         'verification_status': 'needs_verification'}]}, 'sources': []}
    assert fact_sources(task, 'fees') == [{'rule_id': 'r9', 'url': None, 'last_verified': None,
                                           'verification_status': 'needs_verification'}]


@pytest.mark.parametrize(('text', 'link'), [('(916) 691-7411', 'tel:+19166917411'),
                                            ('916.691.7411', 'tel:+19166917411'),
                                            ('DMV 1-800-777-0133, TTY 1-800-368-4327', None),
                                            (None, None)])
def test_only_a_single_phone_number_becomes_a_call_link(text, link):
    assert phone_link(text) == link


def test_an_unsafe_official_url_is_never_an_action():
    task = {'before_you_go': {'official_url': 'javascript:alert(1)'}, 'sources': []}
    assert task_actions(task) == []


def test_unsafe_or_missing_office_urls_render_as_plain_text():
    for url in ('javascript:alert(1)', None):
        html = _office_link({'name': 'Office <A>', 'source_url': url})
        assert html == '<span class="fly-office-src">View Office &lt;A&gt; hours source</span>'


def test_source_rows_keep_verified_dates_and_say_when_to_confirm():
    html = _source_rows([
        {'rule_id': 'a', 'url': 'https://crc.losrios.edu/fees', 'last_verified': '2026-11-12',
         'verification_status': 'verified'},
        {'rule_id': 'b', 'url': 'javascript:alert(1)', 'last_verified': None,
         'verification_status': 'needs_verification'}])
    assert 'fly-source-tag' in html and 'https://crc.losrios.edu/fees' in html
    assert 'javascript:' not in html and 'verified' not in html.lower()
    assert _source_rows([]) == ''


# ---- Actions from the real API data ----

def test_actions_are_named_for_their_real_destinations(live):
    tasks = workflow(live)
    dmv = task_actions(tasks[DMV], source_label)
    assert (dmv[0]['label'], dmv[0]['url']) == ('Schedule a DMV visit',
                                                'https://www.dmv.ca.gov/portal/appointments/')
    assert dmv[1]['label'] == 'Open California DMV · REAL ID checklist'  # its official_url
    residency = task_actions(tasks[RESIDENCY], source_label)
    assert residency[0]['label'] == 'Open the REAL ID document checklist'
    assert 'preparation for the DMV visit' in residency[0]['note']
    checkin = task_actions(tasks[CHECKIN], source_label)
    assert (checkin[0]['label'], checkin[0]['url']) == ('Call to schedule: (916) 691-7411',
                                                        'tel:+19166917411')
    assert checkin[1]['url'].startswith('https://crc.losrios.edu/')
    fee = task_actions(tasks[FEE], source_label)
    assert fee[0]['label'] == 'Open CRC fee payment instructions'


def test_crc_actions_never_reach_another_schools_student(live):
    tasks = workflow(live, school_id=None, institution='School not listed')
    assert FEE not in tasks
    assert task_actions(tasks[CHECKIN], source_label) == []
    links = [a['url'] for task in tasks.values() for a in task_actions(task, source_label)]
    assert links and not any('losrios' in url or url.startswith('tel:') for url in links)


# ---- The page ----

def html(app: AppTest) -> str:
    return ' '.join(str(v) for v in values(app.get('html')))


def test_preview_groups_real_id_then_its_residency_prerequisite(live):
    app = signed_in_app(APP)  # Workflow and readiness: the task table opens the preview
    app.button(key=f'fly_pre:takeoff:{DMV}').click().run()
    page = html(app)
    selected = page.index('<span class="fly-group-kind">Selected step</span>')
    needs = page.index('<span class="fly-group-kind">Needs first</span>')
    assert selected < needs
    assert 'Apply for a California REAL ID card' in page[selected:needs]
    assert 'Gather residency evidence for California REAL ID' in page[needs:]
    assert 'Bring two different printed California address documents' in page[selected:needs]
    assert 'Schedule a DMV visit' in [b.label for b in app.get('link_button')]
    assert any('California DMV, Sacramento (Broadway)' in value and 'fly-source-tag' in value
               for value in values(app.markdown))
    # AppTest reruns the whole app for a dialog's button, so reopen the dialog first.
    app.session_state['flyover_prereq_open'] = DMV
    app.button(key='flyover_prereq_full').click().run()
    assert (app.session_state['flyover_page'], app.session_state['flyover_detail']) == (
        'checklist', DMV)


def test_a_checked_document_stays_with_its_task_across_switches(live):
    app = open_checklist(signed_in_app(APP), DMV)
    box = next(b for b in app.checkbox if b.key.startswith(f'flyover_doc:{DMV}:'))
    box.check().run()
    app = app.selectbox(key='flyover_checklist_pick').select(RESIDENCY).run()
    assert not any(b.key.startswith(f'flyover_doc:{DMV}:') for b in app.checkbox)
    app = app.selectbox(key='flyover_checklist_pick').select(DMV).run()
    assert app.checkbox(key=box.key).value is True
    assert app.session_state['documents_on_hand'][DMV]  # inventory, not progress
    assert RESIDENCY not in app.session_state['documents_on_hand'] or not any(
        app.session_state['documents_on_hand'][RESIDENCY].values())


def test_status_beside_the_title_saves_through_the_api_and_keeps_the_task(live):
    app = open_checklist(signed_in_app(APP), RESIDENCY)
    app.selectbox(key='flyover_checklist_status').select('In Progress').run()
    assert not app.exception
    task = next(t for t in app.session_state['flyover_data']['workflow'] if t['id'] == RESIDENCY)
    assert task['status'] == 'In Progress'
    assert app.session_state['flyover_page'] == 'checklist'
    assert app.session_state['flyover_detail'] == RESIDENCY
    assert ('/workflow', '2026-08-14') == (live.posts()[-1][0], live.posts()[-1][1]['as_of'])


def test_a_blocked_task_cannot_change_status_here(live):
    app = open_checklist(signed_in_app(APP), DMV)
    assert app.selectbox(key='flyover_checklist_status').disabled
