"""Enrollment-based deadlines (STU-D07-due-dates): the CRC Fall 2026 fee rule."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from student_workflow.config import rules_path
from student_workflow.contract import StudentProfile
from student_workflow.engine import resolve
from student_workflow.flyover_state import due_note
from student_workflow.rules import RulesFile, load_rules

FEE = 'task_crc_fee_payment'


def fee_due(enrolled=None, as_of=date(2026, 8, 14), completed=(), term='fall_2026'):
    profile = StudentProfile(student_id='t', institution='Cosumnes River College', visa_type='F-1',
                             arrival_date=date(2026, 8, 11), has_ssn=False, school_id='crc',
                             enrollment_date=enrolled, enrollment_term=term, completed_tasks=list(completed))
    return next(t for t in resolve(load_rules(), profile, as_of).workflow if t.id == FEE).due


def test_enrolled_by_the_cutoff_pays_by_august_7():
    due = fee_due(enrolled=date(2026, 7, 24))
    assert due.due_on == date(2026, 8, 7) and due.past_due is True  # as_of is August 14


def test_enrolled_after_the_cutoff_pays_the_next_day():
    due = fee_due(enrolled=date(2026, 8, 13))  # the team's agreed demo scenario
    assert due.due_on == date(2026, 8, 14) and due.past_due is False


def test_the_deadline_comes_from_the_verified_rule():
    due = fee_due(enrolled=date(2026, 8, 13))
    assert (due.rule_id, due.verification_status) == (
        'rule_crc_fall_2026_payment_deadline', 'verified')


def test_without_an_enrollment_date_the_due_date_is_never_guessed():
    due = fee_due()
    assert due.due_on is None and due.needs == 'enrollment_date' and due.past_due is None


def test_a_completed_task_has_no_deadline():
    assert fee_due(enrolled=date(2026, 8, 13), completed=[FEE]) is None


def test_tasks_without_a_deadline_rule_have_none():
    profile = StudentProfile(student_id='t', institution='Cosumnes River College', visa_type='F-1',
                             arrival_date=date(2026, 8, 11), has_ssn=False, school_id='crc')
    tasks = resolve(load_rules(), profile, date(2026, 8, 14)).workflow
    assert [t.id for t in tasks if t.due] == [FEE]


@pytest.mark.parametrize('change', [{'days_after': -1}, {'from': 'arrival_date'}, {'typo': 1}])
def test_a_malformed_deadline_is_rejected(change):
    raw = json.loads(rules_path().read_text(encoding='utf-8'))
    rule = next(r for r in raw['rules'] if r.get('deadline'))
    rule['deadline'].update(change)
    with pytest.raises(ValidationError):
        RulesFile.model_validate(raw)


def _task(due, status='Ready'):
    return {'status': status, 'due': due}


def _due(due_on, past=False, status='verified'):
    return {'due_on': due_on, 'needs': None, 'rule_id': 'r', 'verification_status': status,
            'past_due': past}


@pytest.mark.parametrize(('due', 'expected'), [
    (_due('2026-08-14'), ('success', 'Due today, Fri, Aug 14, 2026 · Double-checked by our team')),
    (_due('2026-08-15'), ('success', 'Due tomorrow, Sat, Aug 15, 2026 · Double-checked by our team')),
    (_due('2026-08-20', status='needs_verification'),
     ('info', 'Due Thu, Aug 20, 2026 (in 6 days) · Not verified')),
    (_due('2026-08-07', past=True),
     ('warning', 'Past due since Fri, Aug 7, 2026. Check the official page for what to do now.')),
    ({'due_on': None, 'needs': 'enrollment_date', 'rule_id': 'r',
      'verification_status': 'verified', 'past_due': None},
     ('info', 'Add your enrollment date in Profile setup to see when this is due.')),
])
def test_due_note_wording(due, expected):
    assert due_note(_task(due), '2026-08-14') == expected


def test_no_note_for_completed_tasks_or_tasks_without_a_deadline():
    assert due_note(_task(_due('2026-08-14'), status='Completed'), '2026-08-14') is None
    assert due_note(_task(None), '2026-08-14') is None


@pytest.mark.parametrize(('enrolled', 'expected'), [
    (date(2026, 11, 23), date(2027, 1, 8)),
    (date(2026, 12, 25), date(2027, 1, 8)),
    (date(2026, 12, 26), date(2026, 12, 27)),
    (date(2027, 1, 5), date(2027, 1, 6)),
])
def test_spring_2027_uses_its_own_payment_table(enrolled, expected):
    due = fee_due(enrolled=enrolled, term='spring_2027', as_of=date(2026, 11, 17))
    assert due.due_on == expected
    assert due.rule_id == 'rule_crc_spring_2027_payment_deadline'
    assert due.verification_status == 'needs_verification'


def test_an_older_profile_without_a_term_needs_a_choice_before_calculating():
    due = fee_due(enrolled=date(2026, 12, 1), term=None)
    assert due.due_on is None and due.needs == 'enrollment_term'
    assert due_note(_task(due.model_dump(mode='json')), '2026-08-14') == (
        'info', 'Choose your enrollment term in Profile setup to see when tuition is due.')


def test_only_the_selected_terms_payment_rule_is_cited():
    profile = StudentProfile(student_id='t', institution='Synthetic CRC', visa_type='F-1',
                             school_id='crc', arrival_date=date(2027, 1, 5), has_ssn=False,
                             enrollment_term='spring_2027', enrollment_date=date(2026, 12, 1))
    fee = next(task for task in resolve(load_rules(), profile, date(2027, 1, 5)).workflow
               if task.id == FEE)
    assert [source.rule_id for source in fee.sources] == [
        'rule_crc_spring_2027_payment_deadline']
