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
        'Monday 08:00–09:00, Monday 14:00–15:00, Friday 09:00–10:00')


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


def _office(hours, in_effect=True, mode='in_person', name='Office'):
    return {'name': name, 'in_effect': in_effect, 'period_note': 'Fall 2026 hours.',
            'weekly_hours': None if hours is None else [
                {'day': d, 'open': o, 'close': c, 'mode': mode} for d, o, c in hours]}


WEEK = [('Monday', '08:00:00', '17:00:00'), ('Tuesday', '08:00:00', '17:00:00'),
        ('Wednesday', '09:00:00', '17:00:00'), ('Friday', '08:00:00', '16:30:00')]


def test_hours_summary_groups_consecutive_equal_days():
    from student_workflow.flyover_appointments import hours_summary
    assert hours_summary(_office(WEEK)) == (
        'Mon–Tue 08:00–17:00 · Wed 09:00–17:00 · Fri 08:00–16:30')
    assert hours_summary(_office(None)) == 'No hours published'


def test_overlap_is_the_shared_part_of_the_same_day():
    from student_workflow.flyover_appointments import overlaps
    found = overlaps([_w('Wednesday', (7, 0), (10, 0)), _w('Thursday', (9, 0), (10, 0))],
                     _office(WEEK))
    assert found == [_w('Wednesday', (9, 0), (10, 0))]  # Thursday: office closed


def test_phone_hours_never_count_as_in_person():
    from student_workflow.flyover_appointments import overlaps
    assert overlaps([_w('Monday', (9, 0), (10, 0))], _office(WEEK, mode='phone')) == []


def test_match_lines_are_honest_about_each_case():
    from student_workflow.flyover_appointments import match_line
    monday = [_w('Monday', (9, 0), (10, 0))]
    assert match_line(_office(WEEK), monday).startswith("Your free times overlap Office's")
    assert 'not a booking' in match_line(_office(WEEK), monday)
    assert match_line(_office(WEEK), [_w('Sunday', (9, 0), (10, 0))]).startswith('No overlap')
    assert 'publishes no hours' in match_line(_office(None), monday)
    assert "not your workflow's date" in match_line(_office(WEEK, in_effect=False), monday)
    assert 'may differ' in match_line(_office(WEEK, in_effect=None), monday)
