"""Appointment guidance and free times (plan feature 1, guidance only): pure logic."""

from datetime import time

import pytest

from student_workflow.flyover_appointments import (
    appointment_guidance,
    describe_windows,
    first_with_guidance,
    normalize_windows,
    notice_key,
)


def _task(task_id='t', text='Call the office to book.', status='needs_verification', hours=None):
    citations = [{'field': 'appointment_rules', 'rule_id': 'r', 'verification_status': status}]
    return {'id': task_id, 'title': f'Task {task_id}', 'before_you_go': {
        'appointment_rules': text, 'hours': hours, 'official_url': 'https://example.edu/',
        'citations': citations}}


def _w(day, start, end):
    return {'day': day, 'start': time(*start), 'end': time(*end)}


def test_no_appointment_text_means_no_guidance():
    assert appointment_guidance({'id': 'x', 'title': 'X', 'before_you_go': None}) is None
    assert appointment_guidance(_task(text='  ')) is None


def test_guidance_keeps_the_sourced_text_word_for_word():
    guidance = appointment_guidance(_task(text='Call CRC to schedule.'))
    assert guidance['text'] == 'Call CRC to schedule.'
    assert guidance['url'] == 'https://example.edu/'


def test_guidance_is_verified_only_when_its_citation_is():
    assert appointment_guidance(_task())['verified'] is False
    assert appointment_guidance(_task(status='verified'))['verified'] is True


def test_guidance_without_a_citation_counts_as_unverified():
    task = _task()
    task['before_you_go']['citations'] = []
    assert appointment_guidance(task)['verified'] is False


def test_only_the_current_or_next_task_gives_a_notice():
    plain = {'id': 'p', 'title': 'P', 'before_you_go': None}
    assert first_with_guidance([plain, _task('b')])['task_id'] == 'b'
    assert first_with_guidance([plain, plain, _task('c')]) is None


def test_overlapping_and_touching_windows_merge():
    merged = normalize_windows([_w('Monday', (9, 0), (11, 0)), _w('Monday', (10, 0), (12, 0)),
                                _w('Monday', (12, 0), (13, 0))])
    assert merged == [_w('Monday', (9, 0), (13, 0))]


def test_windows_are_sorted_by_day_then_time():
    merged = normalize_windows([_w('Friday', (9, 0), (10, 0)), _w('Monday', (14, 0), (15, 0)),
                                _w('Monday', (8, 0), (9, 0))])
    assert describe_windows(merged) == (
        'Monday 8:00 AM–9:00 AM, Monday 2:00 PM–3:00 PM, Friday 9:00 AM–10:00 AM')


@pytest.mark.parametrize('end', [(9, 0), (8, 0)])
def test_a_window_must_start_before_it_ends(end):
    with pytest.raises(ValueError):
        normalize_windows([_w('Monday', (9, 0), end)])


def test_an_unknown_day_is_rejected():
    with pytest.raises(ValueError):
        normalize_windows([_w('Funday', (9, 0), (10, 0))])


def test_the_dismissal_key_changes_with_free_times_and_text():
    guidance = appointment_guidance(_task())
    key = notice_key(guidance, [])
    assert notice_key(guidance, [_w('Monday', (9, 0), (10, 0))]) != key
    assert notice_key(appointment_guidance(_task(text='New text.')), []) != key
    assert notice_key(guidance, []) == key  # same inputs, same key: no repeat after dismissal


def _office(hours, in_effect=True, mode='in_person', name='Office', status='verified',
            office_id='office', closures=()):
    # Synthetic office data; the defaults are the one fully confirmed case.
    return {'office_id': office_id, 'name': name, 'in_effect': in_effect,
            'period_note': 'Fall 2026 hours.', 'verification_status': status,
            'closures': list(closures), 'weekly_hours': None if hours is None else [
                {'day': d, 'open': o, 'close': c, 'mode': mode} for d, o, c in hours]}


WEEK = [('Monday', '08:00:00', '17:00:00'), ('Tuesday', '08:00:00', '17:00:00'),
        ('Wednesday', '09:00:00', '17:00:00'), ('Friday', '08:00:00', '16:30:00')]


def test_hours_summary_groups_consecutive_equal_days():
    from student_workflow.flyover_appointments import hours_summary
    assert hours_summary(_office(WEEK)) == (
        'Mon–Tue 8:00 AM–5:00 PM · Wed 9:00 AM–5:00 PM · Fri 8:00 AM–4:30 PM')
    assert hours_summary(_office(None)) == 'No hours published'


def test_overlap_is_the_shared_part_of_the_same_day():
    from student_workflow.flyover_appointments import overlaps
    found = overlaps([_w('Wednesday', (7, 0), (10, 0)), _w('Thursday', (9, 0), (10, 0))],
                     _office(WEEK))
    assert found == [_w('Wednesday', (9, 0), (10, 0))]  # Thursday: office closed


def test_phone_hours_never_count_as_in_person():
    from student_workflow.flyover_appointments import overlaps
    assert overlaps([_w('Monday', (9, 0), (10, 0))], _office(WEEK, mode='phone')) == []


AUGUST_14 = '2026-08-14'  # the demo scenario's date
MONDAY = [_w('Monday', (9, 0), (10, 0))]


def test_confirmed_hours_give_an_overlap_that_is_not_a_booking():
    from student_workflow.flyover_appointments import match_line
    line = match_line(_office(WEEK), MONDAY, AUGUST_14)
    assert line.startswith("Your free times overlap Office's published hours: Monday")
    assert 'not a booking' in line


def test_confirmed_hours_without_overlap_say_so():
    from student_workflow.flyover_appointments import match_line
    line = match_line(_office(WEEK), [_w('Sunday', (9, 0), (10, 0))], AUGUST_14)
    assert line.startswith('No overlap')


@pytest.mark.parametrize(('office', 'reason'), [
    (_office(None), 'no_hours'),
    (_office(WEEK, in_effect=None), 'undated'),  # the DMV case: no dates on the schedule
    (_office(WEEK, in_effect=False), 'other_period'),
    (_office(WEEK, status='needs_verification'), 'unverified'),
    (_office(WEEK, office_id='crc_admissions_records'), 'other_service'),
    (_office(WEEK, closures=[{'date': AUGUST_14, 'note': 'Holiday'}]), 'closed'),
    (_office(WEEK, mode='phone'), 'no_hours'),  # phone hours are never visit hours
])
def test_hours_not_confirmed_for_the_date_never_suggest_a_time(office, reason):
    from student_workflow.flyover_appointments import match_line, visit_hours
    check = visit_hours(office, AUGUST_14)
    assert check == {'confirmed': False, 'reason': reason, 'detail': check['detail']}
    line = match_line(office, MONDAY, AUGUST_14)
    assert line.startswith("Office: Hours for this date aren't confirmed.")
    assert 'overlap' not in line and 'AM' not in line


def test_admissions_and_records_hours_are_not_advisor_availability():
    from student_workflow.flyover_appointments import visit_hours
    detail = visit_hours(_office(WEEK, office_id='crc_admissions_records'), AUGUST_14)['detail']
    assert 'not when an International Student Advisor is available' in detail


def test_a_listed_closure_on_the_date_is_named():
    from student_workflow.flyover_appointments import visit_hours
    office = _office(WEEK, closures=[{'date': '2026-11-26', 'note': 'Thanksgiving'}])
    assert visit_hours(office, '2026-11-26')['detail'] == (
        'The office is listed as closed on November 26, 2026: Thanksgiving')


def test_upcoming_closures_lists_only_the_next_two_weeks():
    from student_workflow.flyover_appointments import upcoming_closures
    office = _office(WEEK, closures=[{'date': '2026-08-20', 'note': 'Training day'},
                                     {'date': '2026-09-07', 'note': 'Labor Day'}])
    assert upcoming_closures(office, AUGUST_14) == ['Thu, Aug 20: Training day']


@pytest.mark.parametrize(('moment', 'shown'), [((0, 0), '12:00 AM'), ((8, 0), '8:00 AM'),
                                               ((12, 30), '12:30 PM'), ((16, 30), '4:30 PM')])
def test_times_use_the_12_hour_clock(moment, shown):
    from student_workflow.flyover_appointments import clock
    assert clock(time(*moment)) == shown
