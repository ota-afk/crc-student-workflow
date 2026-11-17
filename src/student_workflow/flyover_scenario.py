"""Flyover's historical demo scenario (STU-D07-demo-scenario): its one date and profile.

The public Flyover link is a walkthrough set on a fixed past date, so every visitor sees the
statuses and deadlines the team rehearsed, not ones that drift with the real calendar. Only
Flyover sends this date to the API; the API's own default (today in California) is unchanged
for every other caller. Real reminder emails still use the real clock (see flyover.py).
"""

from datetime import date

# The walkthrough's "today". Every Flyover workflow request carries it as as_of.
SCENARIO_AS_OF = date(2026, 8, 14)

# A synthetic CRC student, never a real person: arrived August 11, enrolled August 13 for Fall
# 2026, with no completed steps, so the tuition deadline (the day after enrollment) is due on
# the scenario date.
DEMO_PROFILE = {
    'student_id': 'flyover_demo',  # never a real student ID
    'institution': 'Cosumnes River College',
    'school_id': 'crc',
    'visa_type': 'F-1',
    'arrival_date': '2026-08-11',
    'enrollment_date': '2026-08-13',
    'enrollment_term': 'fall_2026',  # the term picks the tuition rule (Fall 2026 here)
    'has_ssn': False,
    'completed_tasks': [],
    'awaiting_reply': [],
    'school_verified': False,  # the API decides this; False is the safe starting value
}


def long_date(day: date | str) -> str:
    """'August 14, 2026': spelled out, so no reader mixes up day and month."""
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return f'{day:%B} {day.day}, {day.year}'


def notice_lines(as_of: date | str = SCENARIO_AS_OF) -> tuple[str, str]:
    """(headline, details) of the demo notice shown on every page and in Settings."""
    details = (f'This walkthrough is set on {long_date(as_of)}. Current office hours aren’t '
               'confirmed. Check the official office page before visiting.')
    return 'Flyover demo · Updates coming soon.', details


def notice_html(as_of: date | str = SCENARIO_AS_OF) -> str:
    """The notice as HTML. It is drawn before any API call, so it survives loading and errors.

    role="note": screen readers announce it as an aside once, not as a live alert on every
    redraw. The text is ours (no user input), so it needs no escaping.
    """
    headline, details = notice_lines(as_of)
    return (f'<div class="fly-demo-notice" role="note" aria-label="Demo notice">'
            f'<b>{headline}</b> {details}</div>')


def export_line(as_of: date | str) -> str:
    """The scenario line repeated in exported handoffs, which leave the page without the banner."""
    headline, details = notice_lines(as_of)
    return f'{headline} {details}'
