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
    """'Monday 09:00–12:00, Wednesday 14:00–16:30' for the notice."""
    return ', '.join(f'{w["day"]} {w["start"]:%H:%M}–{w["end"]:%H:%M}' for w in windows)


def notice_key(guidance: dict, windows: list[dict]) -> str:
    """Dismissal key: changes with the task, its guidance text, or the student's free times,
    so a dismissed notice comes back only when something it says has changed."""
    availability = hashlib.sha256(describe_windows(windows).encode()).hexdigest()[:8]
    return f'{guidance["task_id"]}:{guidance["revision"]}:{availability}'
