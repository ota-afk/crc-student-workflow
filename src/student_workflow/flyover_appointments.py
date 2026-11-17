"""Appointment guidance and the student's free times for Flyover (plan feature 1, guidance only).

What this does and deliberately does not do:
- Guidance comes only from the sourced `before_you_go.appointment_rules` text of a task, word
  for word, with its own verification state. Having that text is not proof an appointment is
  required, so nothing here ever says "appointment required".
- Free times are optional weekly windows the student types in, kept in this browser session
  only. They are never sent to the API or the model.
- Matching free times against an office needs structured, sourced office hours. The rules
  have none (hours are prose or a link), so the answer is always "check the office's
  calendar" until ENG supplies structured hours. Never invent hours, slots or bookings.
"""

import hashlib
from datetime import time

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


def match_line(office: dict, windows: list[dict]) -> str:
    """One honest sentence comparing free times with this office's published hours."""
    name = office['name']
    if in_person_hours(office) is None:
        return f'{name} publishes no hours: check with the office before you go.'
    if office.get('in_effect') is False:
        return (f"{name}'s published hours are for {office['period_note'].rstrip('.')}, "
                "not your workflow's date: check the office's current hours.")
    caveat = '' if office.get('in_effect') else ' These hours may differ from your workflow\'s date.'
    found = overlaps(windows, office)
    if found:
        return (f'Your free times overlap {name}\'s published hours: {describe_windows(found)}. '
                f'Confirm before you go; this is not a booking.{caveat}')
    return f'No overlap with {name}\'s published hours ({hours_summary(office)}).{caveat}'
