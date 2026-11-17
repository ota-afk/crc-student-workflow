"""Scheduled reminder emails through Resend (STU-D07-BE-reminders).

Resend holds the scheduled email, so it is delivered even after the student closes the tab
or the app restarts. Nothing is stored on our side: the dashboard keeps the reminder's ID for
this browser session, which is how it can cancel. That is the demo design the owner chose;
docs/contract.md says what it can't do (no listing or cancelling after the session ends).

Privacy: the email holds only the task's title, status, next step and official link, never
profile details. The recipient address is never logged and never reaches the model.
"""

import logging
from datetime import UTC, datetime, timedelta

import requests

from .contract import Task

logger = logging.getLogger(__name__)

RESEND_EMAILS = 'https://api.resend.com/emails'
MAX_AHEAD = timedelta(days=30)  # Resend schedules at most 30 days ahead
MIN_AHEAD = timedelta(minutes=1)  # "now" has already passed by the time it's scheduled
TIMEOUT = 10


class ProviderError(Exception):
    """The email service refused or didn't answer. The text is safe to show the student."""


def now() -> datetime:
    """The real clock (UTC). A separate function so tests can set the time."""
    return datetime.now(UTC)


def check_send_time(send_at: datetime) -> datetime:
    """The send time in UTC, or ValueError if it's in the past or beyond 30 days."""
    when = send_at.astimezone(UTC)
    current = now()
    if when < current + MIN_AHEAD:
        raise ValueError('Pick a time at least a minute from now.')
    if when > current + MAX_AHEAD:
        raise ValueError('Reminders can be at most 30 days ahead.')
    return when


def email_for(task: Task, as_of: str) -> tuple[str, str]:
    """(subject, text): a fixed template from the task alone, no profile details."""
    lines = [f'You asked Flyover to remind you about: {task.title}', '',
             f'Status on {as_of}: {task.status}.']
    if task.next_action:
        lines.append(f'Next: {task.next_action.text}')
    if task.due and task.due.due_on:
        lines.append(f'Due: {task.due.due_on:%A, %B} {task.due.due_on.day}, {task.due.due_on.year}')
    link = task.before_you_go.official_url if task.before_you_go else None
    link = link or next((s.url for s in task.sources if s.url), None)
    if link:
        lines.append(f'Official page: {link}')
    lines += ['', ("This reminder doesn't book an appointment. Some details in Flyover are not "
              'verified: confirm requirements and hours with the office before you go.'), '',
              'You got this email because you asked for it in the Flyover demo.']
    return f'Flyover reminder: {task.title}', '\n'.join(lines)


def schedule(api_key: str, sender: str, recipient: str, subject: str, text: str,
             send_at: datetime, idempotency_key: str) -> str:
    """Ask Resend to send the email at send_at (UTC). Returns Resend's email ID."""
    try:
        response = requests.post(
            RESEND_EMAILS, timeout=TIMEOUT,
            headers={'Authorization': f'Bearer {api_key}', 'Idempotency-Key': idempotency_key},
            json={'from': sender, 'to': [recipient], 'subject': subject, 'text': text,
                  'scheduled_at': send_at.isoformat().replace('+00:00', 'Z')})
        response.raise_for_status()
        email_id = response.json()['id']
    except (requests.RequestException, ValueError, KeyError) as error:
        # Log the kind of failure only: never the recipient, the key or the email text.
        logger.warning('reminder scheduling failed (%s)', type(error).__name__)
        raise ProviderError('The email service could not schedule this reminder.') from error
    return str(email_id)


def cancel(api_key: str, email_id: str) -> None:
    """Ask Resend to cancel a scheduled email. ProviderError if it isn't confirmed."""
    try:
        response = requests.post(f'{RESEND_EMAILS}/{email_id}/cancel', timeout=TIMEOUT,
                                 headers={'Authorization': f'Bearer {api_key}'})
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning('reminder cancel failed (%s)', type(error).__name__)
        raise ProviderError('Cancellation not confirmed: the reminder may still arrive.') from error


# Resend's last_event values (Email Events overview). Anything else is reported as 'unknown'.
PROVIDER_STATUSES = {'scheduled', 'queued', 'sent', 'delivered', 'delivery_delayed', 'bounced',
                     'failed', 'suppressed', 'canceled', 'opened', 'clicked', 'complained'}


def status(api_key: str, email_id: str) -> str:
    """Resend's latest event for a scheduled email (e.g. 'scheduled', 'delivered', 'failed')."""
    try:
        response = requests.get(f'{RESEND_EMAILS}/{email_id}', timeout=TIMEOUT,
                                headers={'Authorization': f'Bearer {api_key}'})
        response.raise_for_status()
        event = response.json().get('last_event')
    except (requests.RequestException, ValueError, AttributeError) as error:
        logger.warning('reminder status failed (%s)', type(error).__name__)
        raise ProviderError('Could not get the status from the email service.') from error
    return event if event in PROVIDER_STATUSES else 'unknown'
