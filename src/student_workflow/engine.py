"""Dependency resolver (STU-D02-BE): rules file + student profile + "as of" date -> Workflow.

Code decides every status here; the AI never does. The status rules are written down in
docs/contract.md, section "Dependency resolver". The API calls it on every workflow request
(STU-D03-BE), with the profile the dashboard sends.
"""

from collections import Counter
from datetime import date, timedelta

from .contract import (
    BeforeYouGo,
    Blocker,
    Citation,
    EnrollmentTerm,
    NextAction,
    Source,
    StudentProfile,
    Task,
    TaskDue,
    TaskOffice,
    Workflow,
)
from .rules import (
    LIST_FIELDS,
    SINGLE_FIELDS,
    VISIT_FIELDS,
    CitedText,
    Office,
    Rule,
    RuleBeforeYouGo,
    RulesFile,
    RuleTask,
    applicable_facts,
    applicable_rules,
)
from .schools import school_is_verified

SCHEMA_VERSION = "1.0"


class RulesError(ValueError):
    """The rules file can't build a workflow for this school: our data problem, not the student's.

    A subclass of ValueError, so code that only asks "is the input bad?" still catches it.
    """


def resolve(rules: RulesFile, profile: StudentProfile, as_of: date) -> Workflow:
    # as_of is always passed in, never "today", so the demo and the tests repeat exactly.
    scoped = _for_school(rules, profile.school_id, profile.enrollment_term)
    _reject_repeats(profile)  # before the sets below, which would hide a repeat
    completed = set(profile.completed_tasks)
    awaiting = set(profile.awaiting_reply)
    _check_profile(scoped, completed, awaiting)
    tasks = [
        _resolve_task(scoped, task, profile, completed, awaiting, as_of)
        for task in scoped.tasks
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


def _for_school(
    rules: RulesFile, school_id: str | None, enrollment_term: EnrollmentTerm | None = None,
) -> RulesFile:
    """Keep the tasks that apply to this school, each citing only the rules that apply.

    The choice is made per task (see rules.applicable_rules): a school's own rule replaces
    the generic one for that task, and its other tasks keep their generic steps.
    """
    tasks = []
    for task in rules.tasks:
        applicable = [
            rule for rule in applicable_rules(rules, task, school_id)
            if enrollment_term is None or rule.deadline is None
            or rule.deadline.term in (None, enrollment_term)
        ]
        # Empty = only other schools' rules, so this task is not part of this workflow.
        if applicable:
            update = {
                "rule_ids": [r.rule_id for r in applicable],
                # Only the visit details whose rule applies to this school (e.g. no other
                # school's phone number); None when nothing is left.
                "before_you_go": _visit_details(
                    applicable_facts(rules, task, school_id)
                ),
                # Only offices for every student or for this school (never another
                # school's offices, or DMV offices chosen for being near another campus).
                "offices": [o for o in task.offices
                            if rules.office(o).school_id in (None, school_id)],
            }
            tasks.append(task.model_copy(update=update))
    if not tasks:
        raise RulesError(
            "No tasks found for this school, and no generic rules are available"
        )
    shown = {task.id for task in tasks}
    for task in tasks:
        # Fail loudly rather than quietly dropping a step the student still has to do.
        hidden = [p for p in task.prerequisites if p not in shown]
        if hidden:
            raise RulesError(
                f"task {task.id} needs {', '.join(hidden)}, which does not apply to "
                f"school {school_id}"
            )
    # Keep every rule a task or one of its visit-details facts cites, so each source is found.
    used = {rule_id for task in tasks for rule_id in _cited_rule_ids(task)}
    named = {office_id for task in tasks for office_id in task.offices}
    return RulesFile(tasks=tasks, rules=[r for r in rules.rules if r.rule_id in used],
                     offices=[o for o in rules.offices if o.office_id in named])


def _visit_details(facts: list[tuple[str, CitedText]]) -> RuleBeforeYouGo | None:
    """Rebuild a task's visit details from the facts that were kept; None = none left."""
    if not facts:
        return None
    fields: dict[str, list[CitedText]] = {field: [] for field in VISIT_FIELDS}
    for field, fact in facts:
        fields[field].append(fact)
    return RuleBeforeYouGo(
        **{
            f: items if f in LIST_FIELDS else (items[0] if items else None)
            for f, items in fields.items()
        }
    )


def _cited_rule_ids(task: RuleTask) -> list[str]:
    """The task's own rules, then the rules its visit details cite, each once, in order."""
    cited = list(task.rule_ids)
    for _field, fact in task.before_you_go.facts() if task.before_you_go else []:
        if fact.rule_id not in cited:
            cited.append(fact.rule_id)
    return cited


def _reject_repeats(profile: StudentProfile) -> None:
    # A task listed twice means the client built the profile wrong; say so instead of hiding it.
    for field in ("completed_tasks", "awaiting_reply"):
        ids = getattr(profile, field)
        repeated = sorted(task_id for task_id, count in Counter(ids).items() if count > 1)
        if repeated:
            raise ValueError(f"{field} lists a task more than once: {', '.join(repeated)}")


def _check_profile(rules: RulesFile, completed: set[str], awaiting: set[str]) -> None:
    known = {t.id for t in rules.tasks}
    for field, ids in (("completed_tasks", completed), ("awaiting_reply", awaiting)):
        unknown = sorted(ids - known)
        if unknown:
            raise ValueError(f"{field} has unknown task ids: {', '.join(unknown)}")
    # A finished task is no longer waiting on anyone; both at once means the profile is broken.
    both = sorted(completed & awaiting)
    if both:
        raise ValueError(
            f"tasks both completed and awaiting a reply: {', '.join(both)}"
        )
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
    awaiting: set[str],
    as_of: date,
) -> Task:
    # Only the task's own rules control status. A rule cited as preparation guidance must
    # still appear in sources, but its timing must not introduce a new workflow blocker.
    task_rules = [rules.rule(rule_id) for rule_id in task.rule_ids]
    cited_rules = [rules.rule(rule_id) for rule_id in _cited_rule_ids(task)]
    sources = [
        Source(
            rule_id=r.rule_id,
            url=r.source_url,
            last_verified=r.last_verified,
            verification_status=r.verification_status,
        )
        for r in cited_rules
    ]

    visit = _before_you_go(rules, task)
    offices = [_office(rules.office(office_id), as_of) for office_id in task.offices]
    if task.id in completed:
        return _task(task, "Completed", sources=sources, visit=visit, offices=offices)
    due = _due(task_rules, profile, as_of)

    # Kept in file order, so next_action always points at the same first prerequisite.
    missing = [p for p in task.prerequisites if p not in completed]
    blockers = [b for r in task_rules if (b := _timing_blocker(r, profile, as_of))]
    next_action = None
    if missing:
        first = rules.task(missing[0])
        next_action = NextAction(
            task_id=first.id, text=f'Finish "{first.title}" first.'
        )

    # Blocked wins over In Progress: waiting on an office never skips a prerequisite or a date.
    if missing or blockers:
        status = "Blocked"
    elif task.id in awaiting:
        status = "In Progress"  # the student wrote to the office and waits for a reply
    else:
        status = "Ready"
    return _task(
        task,
        status,
        sources=sources,
        missing=missing,
        blockers=blockers,
        next_action=next_action,
        visit=visit,
        offices=offices,
        due=due,
    )


def _due(task_rules: list[Rule], profile: StudentProfile, as_of: date) -> TaskDue | None:
    """The selected semester's deadline, or the input needed before calculating it."""
    candidates = [rule for rule in task_rules if rule.deadline]
    if not candidates:
        return None
    rule = next(
        (rule for rule in candidates
         if rule.deadline.term is None or rule.deadline.term == profile.enrollment_term),
        None,
    )
    if rule is None:
        # A selected semester is required for term-specific fees, including older profiles.
        return TaskDue(needs="enrollment_term", rule_id=candidates[0].rule_id,
                       verification_status=candidates[0].verification_status)
    deadline, enrolled = rule.deadline, profile.enrollment_date
    if enrolled is None:
        # Never guess a due date: say which date the student still has to give.
        return TaskDue(needs="enrollment_date", rule_id=rule.rule_id,
                       verification_status=rule.verification_status)
    due_on = (deadline.due_if_by_cutoff if enrolled <= deadline.cutoff
              else enrolled + timedelta(days=deadline.days_after))
    return TaskDue(due_on=due_on, rule_id=rule.rule_id,
                   verification_status=rule.verification_status, past_due=as_of > due_on)


def _office(office: Office, as_of: date) -> TaskOffice:
    """The office as the response shows it, with whether its hours cover as_of."""
    if office.valid_from is None and office.valid_to is None:
        in_effect = None  # the source gave no dates: today's hours, maybe not as_of's
    else:
        in_effect = ((office.valid_from is None or office.valid_from <= as_of)
                     and (office.valid_to is None or as_of <= office.valid_to))
    return TaskOffice(
        **office.model_dump(include={
            "office_id", "name", "address", "timezone", "period_note", "weekly_hours",
            "closures", "source_url", "evidence", "retrieved_on", "verification_status",
            "notes",
        }),
        in_effect=in_effect,
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


def _before_you_go(rules: RulesFile, task: RuleTask) -> BeforeYouGo | None:
    """The response's visit details: the same strings as before, plus one citation per fact."""
    # None = no visit details for this student: never a sign that nothing is needed.
    if task.before_you_go is None:
        return None
    details = task.before_you_go
    citations = [
        Citation(
            field=field,
            text=fact.text,
            rule_id=fact.rule_id,
            # Carried over unchanged, so an unverified fact stays visibly unverified.
            verification_status=rules.rule(fact.rule_id).verification_status,
        )
        for field, fact in details.facts()
    ]
    return BeforeYouGo(
        required_documents=[fact.text for fact in details.required_documents],
        warnings=[fact.text for fact in details.warnings],
        **{
            f: getattr(details, f).text if getattr(details, f) else None
            for f in SINGLE_FIELDS
        },
        citations=citations,
    )


def _task(
    task: RuleTask,
    status: str,
    *,
    sources: list[Source],
    missing: list[str] | None = None,
    blockers: list[Blocker] | None = None,
    next_action: NextAction | None = None,
    visit: BeforeYouGo | None = None,
    offices: list[TaskOffice] | None = None,
    due: TaskDue | None = None,
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
        before_you_go=visit,
        sources=sources,
        offices=offices or [],
        due=due,
    )
