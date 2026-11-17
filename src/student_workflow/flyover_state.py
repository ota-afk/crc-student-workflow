"""Small presentation rules; readiness and task status belong to the backend."""

from math import ceil


def active_task(tasks: list[dict]) -> dict | None:
    return next((task for task in tasks if task['status'] != 'Completed'), None)


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
