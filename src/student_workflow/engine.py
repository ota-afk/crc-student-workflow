"""Dependency resolver (STU-D02-BE): rules file + student profile + "as of" date -> Workflow.

Code decides every status here; the AI never does. The status rules are written down in
docs/contract.md, section "Dependency resolver". The API starts using this on Day 3.
"""

from datetime import date, timedelta

from .contract import Blocker, NextAction, Source, StudentProfile, Task, Workflow
from .rules import Rule, RulesFile, RuleTask, applicable_rules
from .schools import school_is_verified

SCHEMA_VERSION = "1.0"


def resolve(rules: RulesFile, profile: StudentProfile, as_of: date) -> Workflow:
    # as_of is always passed in, never "today", so the demo and the tests repeat exactly.
    scoped = _for_school(rules, profile.school_id)
    completed = set(profile.completed_tasks)
    _check_profile(scoped, completed)
    tasks = [
        _resolve_task(scoped, task, profile, completed, as_of) for task in scoped.tasks
    ]
    return Workflow(
        schema_version=SCHEMA_VERSION,
        is_mock=False,  # computed from the rules file, not the sample mock
        as_of=as_of,
        student_profile=profile.model_copy(
            update={"school_verified": school_is_verified(rules, profile.school_id)}
        ),
        workflow=tasks,
    )


def _for_school(rules: RulesFile, school_id: str | None) -> RulesFile:
    """Keep the tasks that apply to this school, each citing only the rules that apply.

    The choice is made per task (see rules.applicable_rules): a school's own rule replaces
    the generic one for that task, and its other tasks keep their generic steps.
    """
    tasks = []
    for task in rules.tasks:
        applicable = applicable_rules(rules, task, school_id)
        # Empty = only other schools' rules, so this task is not part of this workflow.
        if applicable:
            tasks.append(
                task.model_copy(update={"rule_ids": [r.rule_id for r in applicable]})
            )
    if not tasks:
        raise ValueError(
            "No tasks found for this school, and no generic rules are available"
        )
    shown = {task.id for task in tasks}
    for task in tasks:
        # Fail loudly rather than quietly dropping a step the student still has to do.
        hidden = [p for p in task.prerequisites if p not in shown]
        if hidden:
            raise ValueError(
                f"task {task.id} needs {', '.join(hidden)}, which does not apply to "
                f"school {school_id}"
            )
    used = {rule_id for task in tasks for rule_id in task.rule_ids}
    return RulesFile(tasks=tasks, rules=[r for r in rules.rules if r.rule_id in used])


def _check_profile(rules: RulesFile, completed: set[str]) -> None:
    known = {t.id for t in rules.tasks}
    unknown = sorted(completed - known)
    if unknown:
        raise ValueError(f"completed_tasks has unknown task ids: {', '.join(unknown)}")
    for task in rules.tasks:
        if task.id not in completed:
            continue
        # A task done before its prerequisites breaks the contract's consistency rule.
        skipped = [p for p in task.prerequisites if p not in completed]
        if skipped:
            raise ValueError(
                f"task {task.id} is completed but its prerequisites are not: {', '.join(skipped)}"
            )


def _resolve_task(
    rules: RulesFile,
    task: RuleTask,
    profile: StudentProfile,
    completed: set[str],
    as_of: date,
) -> Task:
    task_rules = [rules.rule(rule_id) for rule_id in task.rule_ids]
    sources = [
        Source(
            rule_id=r.rule_id,
            url=r.source_url,
            last_verified=r.last_verified,
            verification_status=r.verification_status,
        )
        for r in task_rules
    ]

    if task.id in completed:
        return _task(task, "Completed", sources=sources)

    # Kept in file order, so next_action always points at the same first prerequisite.
    missing = [p for p in task.prerequisites if p not in completed]
    blockers = [b for r in task_rules if (b := _timing_blocker(r, profile, as_of))]
    next_action = None
    if missing:
        first = rules.task(missing[0])
        next_action = NextAction(
            task_id=first.id, text=f'Finish "{first.title}" first.'
        )

    status = "Blocked" if missing or blockers else "Ready"
    return _task(
        task,
        status,
        sources=sources,
        missing=missing,
        blockers=blockers,
        next_action=next_action,
    )


def _timing_blocker(rule: Rule, profile: StudentProfile, as_of: date) -> Blocker | None:
    # None = this rule does not block today (no timing, or the unlock date has arrived).
    if rule.timing is None:
        return None
    start = getattr(profile, rule.timing.from_)  # today only 'arrival_date' is allowed
    unlocks_on = start + timedelta(days=rule.timing.days)
    if as_of >= unlocks_on:
        return None
    return Blocker(
        type="timing",
        rule_id=rule.rule_id,
        unlocks_on=unlocks_on,
        # Carried over unchanged: an unverified rule stays visibly unverified on screen.
        verification_status=rule.verification_status,
        explanation=rule.statement,
    )


def _task(
    task: RuleTask,
    status: str,
    *,
    sources: list[Source],
    missing: list[str] | None = None,
    blockers: list[Blocker] | None = None,
    next_action: NextAction | None = None,
) -> Task:
    return Task(
        id=task.id,
        title=task.title,
        status=status,
        priority=task.priority,
        prerequisites=task.prerequisites,
        missing_prerequisites=missing or [],
        next_action=next_action,
        blockers=blockers or [],
        before_you_go=None,  # the rules file has no visit details yet
        sources=sources,
    )
