"""Office hours in the rules file (STU-D07-BE-office-hours): data, scoping and validation."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from student_workflow.config import rules_path
from student_workflow.contract import StudentProfile
from student_workflow.engine import resolve
from student_workflow.rules import RulesFile, load_rules

DEMO_DATE = date(2026, 8, 14)


def _profile(school_id='crc', institution='Cosumnes River College'):
    return StudentProfile(student_id='t', institution=institution, visa_type='F-1',
                          arrival_date=date(2026, 8, 11), has_ssn=False, school_id=school_id)


def _offices(workflow, task_id):
    return {o.office_id: o for o in next(t for t in workflow.workflow if t.id == task_id).offices}


def _raw():
    return json.loads(rules_path().read_text(encoding='utf-8'))


def test_every_researched_office_is_sourced_and_awaits_a_second_check():
    offices = load_rules().offices
    assert len(offices) == 5
    for office in offices:
        assert office.verification_status == 'needs_verification'
        assert office.second_checker is None
        assert office.source_url.startswith('https://') and office.evidence
        assert 'AI' in office.checked_by  # the first check was AI research, disclosed


def test_crc_check_in_gets_admissions_records_hours_for_the_demo_date():
    offices = _offices(resolve(load_rules(), _profile(), DEMO_DATE), 'task_school_checkin')
    records = offices['crc_admissions_records']
    assert records.in_effect is True  # Fall 2026 hours cover August 14
    assert [(h.day, f'{h.open:%H:%M}', f'{h.close:%H:%M}') for h in records.weekly_hours][-1] == (
        'Friday', '08:00', '16:30')


def test_an_office_without_published_hours_says_so():
    iso = _offices(resolve(load_rules(), _profile(), DEMO_DATE),
                   'task_school_checkin')['crc_international_students']
    assert iso.weekly_hours is None and iso.in_effect is None


def test_undated_hours_are_neither_in_nor_out_of_effect():
    dmv = _offices(resolve(load_rules(), _profile(), DEMO_DATE), 'task_dmv_id')
    assert set(dmv) == {'dmv_sacramento_south', 'dmv_sacramento'}
    assert all(o.in_effect is None for o in dmv.values())


def test_dated_hours_are_out_of_effect_after_their_range():
    records = _offices(resolve(load_rules(), _profile(), date(2027, 1, 15)),
                       'task_school_checkin')['crc_admissions_records']
    assert records.in_effect is False


def test_students_at_other_schools_never_get_crc_offices():
    workflow = resolve(load_rules(), _profile(school_id=None, institution='Other College'),
                       DEMO_DATE)
    assert all(not task.offices for task in workflow.workflow)


def test_a_task_naming_an_unknown_office_is_rejected():
    raw = _raw()
    raw['tasks'][0]['offices'] = ['no_such_office']
    with pytest.raises(ValidationError, match='unknown office'):
        RulesFile.model_validate(raw)


def test_hours_must_open_before_they_close():
    raw = _raw()
    raw['offices'][1]['weekly_hours'][0]['close'] = '07:00'
    with pytest.raises(ValidationError, match='not before close'):
        RulesFile.model_validate(raw)


def test_verified_hours_need_a_second_checker():
    raw = _raw()
    raw['offices'][1]['verification_status'] = 'verified'
    with pytest.raises(ValidationError, match='second checker'):
        RulesFile.model_validate(raw)


def test_an_unknown_office_key_is_rejected():
    raw = _raw()
    raw['offices'][0]['hourz'] = 'typo'
    with pytest.raises(ValidationError):
        RulesFile.model_validate(raw)


def test_the_api_returns_offices_on_tasks(monkeypatch):
    from fastapi.testclient import TestClient

    from student_workflow.api import app
    monkeypatch.setenv('USE_MOCK', 'false')
    tasks = TestClient(app).get('/workflow').json()['workflow']
    fee = next(t for t in tasks if t['id'] == 'task_crc_fee_payment')
    assert [o['office_id'] for o in fee['offices']] == ['crc_business_services']
