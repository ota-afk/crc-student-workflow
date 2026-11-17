"""Appointment guidance and the student's free times for Flyover (plan feature 1, guidance only).

What this does and deliberately does not do:
- Guidance comes only from the sourced `before_you_go.appointment_rules` text of a task, word
  for word, with its own verification state. Having that text is not proof an appointment is
  required, so nothing here ever says "appointment required".
- Free times are optional weekly windows the student types in, kept in this browser session
  only. They are never sent to the API or the model.
- Matching free times against an office needs structured, sourced office hours that are
  confirmed for the workflow's date (visit_hours). Anything less (no hours, hours for another
  period or with no dates, unverified hours, another service's hours, a listed closure) is
  "Hours for this date aren't confirmed" plus the office's own page, never a suggested time.
  Never invent hours, slots, bookings or verification dates.
"""

import hashlib
from datetime import date, time, timedelta

DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
TIMEZONE_LABEL = 'Pacific time (America/Los_Angeles)'
NO_HOURS_NOTE = ("We don't have this office's hours on file, so we can't match your free "
                 "times. Check the office's calendar before you go.")


def appointment_guidance(task: dict) -> dict | None:
    """The task's sourced appointment text and its verification, or None if it has none."""
    guide = task.get('before_you_go') or {}
    text = (guide.get('appointment_rules') or '').strip()
    if not text:
        return None  # no appointment guidance on file: no notice, never a guess

    def verified(field: str) -> bool:
        return fact_verified(guide, field)

    hours = (guide.get('hours') or '').strip() or None
    revision = hashlib.sha256(f'{text}\n{hours}'.encode()).hexdigest()[:12]
    return {'task_id': task['id'], 'title': task['title'], 'text': text,
            'verified': verified('appointment_rules'), 'hours': hours,
            'hours_verified': verified('hours') if hours else False,
            'url': guide.get('official_url'), 'revision': revision}


def fact_verified(guide: dict, field: str) -> bool:
    """True only if a visit-detail fact has citations and every one of them is verified."""
    cited = [c for c in guide.get('citations') or [] if c.get('field') == field]
    # No citation for the fact = unverified; every citation for it must be verified.
    return bool(cited) and all(c.get('verification_status') == 'verified' for c in cited)


def first_with_guidance(queue: list[dict], look_ahead: int = 2) -> dict | None:
    """Guidance for the current or next task in the queue (the plan: current or next)."""
    for task in queue[:look_ahead]:
        if guidance := appointment_guidance(task):
            return guidance
    return None


def normalize_windows(windows: list[dict]) -> list[dict]:
    """Validated weekly windows, overlapping or touching ones merged, sorted by day and time.

    Each window is {'day': one of DAYS, 'start': time, 'end': time}. Fails loudly on an
    unknown day or a start that is not before its end (overnight windows aren't supported).
    """
    by_day: dict[str, list[tuple[time, time]]] = {}
    for window in windows:
        day, start, end = window['day'], window['start'], window['end']
        if day not in DAYS:
            raise ValueError(f'unknown day: {day!r}')
        if not start < end:
            raise ValueError('a free time must start before it ends (no overnight windows)')
        by_day.setdefault(day, []).append((start, end))
    merged = []
    for day in DAYS:
        spans = sorted(by_day.get(day, []))
        current: list[time] | None = None
        for start, end in spans:
            if current and start <= current[1]:
                current[1] = max(current[1], end)
            else:
                if current:
                    merged.append({'day': day, 'start': current[0], 'end': current[1]})
                current = [start, end]
        if current:
            merged.append({'day': day, 'start': current[0], 'end': current[1]})
    return merged


def describe_windows(windows: list[dict]) -> str:
    """'Monday 9:00 AM–12:00 PM, Wednesday 2:00 PM–4:30 PM' for the notice."""
    return ', '.join(f'{w["day"]} {clock(w["start"])}–{clock(w["end"])}' for w in windows)


def notice_key(guidance: dict, windows: list[dict]) -> str:
    """Dismissal key: changes with the task, its guidance text, or the student's free times,
    so a dismissed notice comes back only when something it says has changed."""
    availability = hashlib.sha256(describe_windows(windows).encode()).hexdigest()[:8]
    return f'{guidance["task_id"]}:{guidance["revision"]}:{availability}'


# ---- Office hours from the rules file (STU-D07-FE-hours-matching) ----

def _t(value) -> time:
    # The API sends times as 'HH:MM:SS'; tests may pass time objects.
    return value if isinstance(value, time) else time.fromisoformat(value)


def in_person_hours(office: dict) -> list[dict] | None:
    """The office's in-person opening hours, or None when the source publishes none."""
    hours = office.get('weekly_hours')
    if hours is None:
        return None
    return [{'day': h['day'], 'open': _t(h['open']), 'close': _t(h['close'])}
            for h in hours if h['mode'] == 'in_person']


def hours_summary(office: dict) -> str:
    """'Mon–Thu 08:00–17:00 · Fri 08:00–16:30', grouping consecutive days with equal hours."""
    hours = in_person_hours(office)
    if not hours:
        return 'No hours published'
    by_day = {h['day']: (h['open'], h['close']) for h in hours}
    groups: list[list] = []
    for day in DAYS:
        if day not in by_day:
            continue
        span = by_day[day]
        last = groups[-1] if groups else None
        if last and last[2] == span and DAYS.index(day) == DAYS.index(last[1]) + 1:
            last[1] = day
        else:
            groups.append([day, day, span])
    return ' · '.join(
        f'{first[:3]}{"–" + last[:3] if last != first else ""} {clock(s)}–{clock(e)}'
        for first, last, (s, e) in groups)


def clock(moment: time) -> str:
    """'8:00 AM', '4:30 PM': the 12-hour clock most students in the US read at a glance."""
    return f'{moment.hour % 12 or 12}:{moment:%M} {"AM" if moment.hour < 12 else "PM"}'


def overlaps(windows: list[dict], office: dict) -> list[dict]:
    """The parts of the student's free times when the office is open in person, by day."""
    found = []
    for hours in in_person_hours(office) or []:
        for window in windows:
            if window['day'] != hours['day']:
                continue
            start, end = max(window['start'], hours['open']), min(window['end'], hours['close'])
            if start < end:
                found.append({'day': window['day'], 'start': start, 'end': end})
    return normalize_windows(found) if found else []


# ---- Are these hours usable for a visit on the workflow's date? (STU-D07-demo-scenario) ----

HOURS_NOT_CONFIRMED = "Hours for this date aren't confirmed"
# Offices whose published hours are for a different service than the visit their tasks need.
# The rules file has no "which service do these hours cover" field yet (flagged for ENG), so
# this stopgap lives here. ENG's own note on the International Students Office says to see the
# International Student Advisor in Admissions & Records; the A&R hours are the front desk's.
OTHER_SERVICE = {
    'crc_admissions_records': ('These are the Admissions & Records front desk’s hours, not '
                               'when an International Student Advisor is available.'),
}


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def visit_hours(office: dict, as_of) -> dict:
    """{'confirmed': bool, 'reason': str, 'detail': str} for a visit on as_of.

    Confirmed only when the office publishes in-person hours, they are for the visit's own
    service, the office is not listed as closed that day, the source's dates cover as_of
    (in_effect True; None = no dates, so not confirmed) and our team verified them.
    Phone or virtual hours never count as visit hours (in_person_hours drops them).
    """
    day = _day(as_of)
    when = f'{day:%B} {day.day}, {day.year}'
    if not in_person_hours(office):
        return {'confirmed': False, 'reason': 'no_hours',
                'detail': 'The office publishes no in-person hours we can use.'}
    if office['office_id'] in OTHER_SERVICE:
        return {'confirmed': False, 'reason': 'other_service',
                'detail': OTHER_SERVICE[office['office_id']]}
    closed = next((c for c in office.get('closures') or [] if _day(c['date']) == day), None)
    if closed:
        return {'confirmed': False, 'reason': 'closed',
                'detail': f'The office is listed as closed on {when}: {closed["note"]}'}
    if office.get('in_effect') is False:
        return {'confirmed': False, 'reason': 'other_period',
                'detail': f'The published hours are for another period, not {when}.'}
    if office.get('in_effect') is None:
        return {'confirmed': False, 'reason': 'undated',
                'detail': f'The published hours have no date range, so they may not apply on '
                          f'{when}.'}
    if office.get('verification_status') != 'verified':
        return {'confirmed': False, 'reason': 'unverified',
                'detail': "Our team hasn't double-checked these hours with the office yet."}
    return {'confirmed': True, 'reason': 'confirmed', 'detail': ''}


def upcoming_closures(office: dict, as_of, days: int = 14) -> list[str]:
    """'Thu, Nov 26: Thanksgiving' for each listed closure within `days` of as_of."""
    start = _day(as_of)
    return [f'{_day(c["date"]):%a, %b} {_day(c["date"]).day}: {c["note"]}'
            for c in office.get('closures') or []
            if start <= _day(c['date']) <= start + timedelta(days=days)]


def match_line(office: dict, windows: list[dict], as_of) -> str:
    """One honest sentence comparing free times with this office's hours on the workflow's date.

    An overlap is only worked out from hours confirmed for as_of (visit_hours); otherwise
    the line says the hours aren't confirmed, so no time is ever suggested from other hours.
    """
    name = office['name']
    check = visit_hours(office, as_of)
    if not check['confirmed']:
        return (f'{name}: {HOURS_NOT_CONFIRMED}. {check["detail"]} Check the official office '
                'page before you go.')
    found = overlaps(windows, office)
    if found:
        return (f'Your free times overlap {name}\'s published hours: {describe_windows(found)}. '
                'Confirm before you go; this is not a booking.')
    return f'No overlap with {name}\'s published hours ({hours_summary(office)}).'
