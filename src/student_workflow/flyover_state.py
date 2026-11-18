"""Small presentation rules; readiness and task status belong to the backend."""

from datetime import date
from math import ceil

# Lower comes first. An unknown or missing priority/status sorts after the known ones.
PRIORITY_ORDER = {'Required': 0, 'Recommended': 1, 'Optional': 2}
STATUS_ORDER = {'Ready': 0, 'In Progress': 1, 'Blocked': 2}


def task_queue(tasks: list[dict]) -> list[dict]:
    """Unfinished tasks in the order to show them: a display order, not a deadline.

    Required before Recommended before Optional; a prerequisite always comes before the
    tasks that need it and takes the highest priority among them (an Optional step that a
    Required task waits on is shown first). At equal priority: Ready, then In Progress,
    then Blocked, then the rules file's order. Statuses are shown as the API returned them.
    """
    pending = [task for task in tasks if task['status'] != 'Completed']
    ids = {task['id'] for task in pending}
    index = {task['id']: i for i, task in enumerate(tasks)}
    effective = {task['id']: PRIORITY_ORDER.get(task.get('priority'), 3) for task in pending}
    # Pass each task's priority down to its unfinished prerequisites, until nothing changes
    # (a chain a -> b -> c needs more than one pass; at most one per task).
    for _ in range(len(pending)):
        changed = False
        for task in pending:
            for prerequisite in task.get('prerequisites') or []:
                if prerequisite in ids and effective[task['id']] < effective[prerequisite]:
                    effective[prerequisite] = effective[task['id']]
                    changed = True
        if not changed:
            break

    def rank(task: dict) -> tuple:
        return (effective[task['id']], STATUS_ORDER.get(task['status'], 3), index[task['id']])

    ordered, placed, remaining = [], set(), sorted(pending, key=rank)
    while remaining:
        # The best-ranked task whose unfinished prerequisites are all placed already.
        ready = [t for t in remaining
                 if all(p in placed or p not in ids for p in t.get('prerequisites') or [])]
        chosen = ready[0] if ready else remaining[0]  # a cycle in the data: don't loop forever
        ordered.append(chosen)
        placed.add(chosen['id'])
        remaining.remove(chosen)
    return ordered


def active_task(tasks: list[dict]) -> dict | None:
    """The task to focus on now: the first in task_queue, or None when all are done."""
    queue = task_queue(tasks)
    return queue[0] if queue else None


def map_piece_count(completed: int, total: int) -> int:
    if not total or not completed:
        return 0
    if completed >= total:
        return 3
    return 2 if completed >= max(2, ceil(total / 2)) else 1


ENCOURAGEMENTS = (
    'Every small step is part of a bigger journey.',
    'You don’t need the whole route figured out to take the next step.',
    'A little preparation makes room for a little more confidence.',
    'New places. New possibilities. One step at a time.',
)


def map_progress(completed: int, total: int) -> float:
    """Three puzzle pieces, with visible progress between the 1/half/final milestones."""
    if total <= 0 or completed <= 0:
        return 0.0
    if completed >= total:
        return 3.0
    halfway = max(2, ceil(total / 2))
    if completed <= 1:
        return 1.0
    if completed <= halfway:
        return 1 + (completed - 1) / (halfway - 1)
    return 2 + (completed - halfway) / (total - halfway)


def due_note(task: dict, as_of: str) -> tuple[str, str] | None:
    """(kind, text) for a task's deadline, or None. kind is a Streamlit message type.

    The date comes from the API (a rule's deadline and the profile); nothing is guessed here.
    """
    due = task.get('due')
    if not due or task.get('status') == 'Completed':
        return None
    if due.get('needs') == 'enrollment_term':
        return 'info', 'Choose your enrollment term in Profile setup to see when tuition is due.'
    if due.get('needs') == 'enrollment_date':
        return 'info', 'Add your enrollment date in Profile setup to see when this is due.'
    due_on, today = date.fromisoformat(due['due_on']), date.fromisoformat(as_of)
    when = f'{due_on:%a, %b} {due_on.day}, {due_on.year}'
    if due.get('past_due'):
        return 'warning', f'Past due since {when}. Check the official page for what to do now.'
    days = (due_on - today).days
    # Today is the workflow's as_of (the demo's date on the public site), so it is spelled out.
    label = (f'Due today, {when}' if days == 0 else f'Due tomorrow, {when}' if days == 1
             else f'Due {when} (in {days} days)')
    if due['verification_status'] == 'verified':
        return 'success', label + ' · Double-checked by our team'
    return 'info', label
