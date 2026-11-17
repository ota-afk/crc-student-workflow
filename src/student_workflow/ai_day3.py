"""Build cited workflow explanations and placeholder-only email drafts."""

import json
from typing import Literal

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict

from .contract import Blocker, Source, Task


class CitationChoice(BaseModel):
    """Rule IDs to highlight, in order of relevance."""

    model_config = ConfigDict(extra='forbid')

    rule_ids: list[str]


class CitedBlocker(BaseModel):
    blocker: Blocker
    source: Source
    verified: bool


class TaskExplanation(BaseModel):
    outcome: Literal['explained', 'dso_referral', 'unavailable']
    message: str
    next_action: str | None = None
    citations: list[CitedBlocker] = []


class EmailDraft(BaseModel):
    subject: str
    body: str


def validate_citations(
    rule_ids: list[str], available: dict[str, CitedBlocker],
) -> bool:
    """Accept only distinct rule IDs grounded in this task's current blockers."""
    return (
        bool(rule_ids)
        and len(rule_ids) == len(set(rule_ids))
        and all(rule_id in available for rule_id in rule_ids)
    )


def explain_task(
    task: Task,
    *,
    high_risk: bool | None,
    prerequisite: Task | None = None,
    client: OpenAI | None = None,
    model: str | None = None,
) -> TaskExplanation:
    """Explain an engine-resolved task. The caller supplies its authoritative risk flag."""
    if high_risk is True:
        return TaskExplanation(
            outcome='dso_referral',
            message="Please contact your school's international student office (DSO) for guidance.",
        )
    if high_risk is not False:
        return TaskExplanation(
            outcome='unavailable',
            message='This explanation is unavailable. Please consult your workflow or office.',
        )

    sources = {source.rule_id: source for source in task.sources if source.url}
    available = {}
    for blocker in task.blockers:
        if (source := sources.get(blocker.rule_id)) is not None:
            available[blocker.rule_id] = CitedBlocker(
                blocker=blocker,
                source=source,
                verified=(
                    blocker.verification_status == 'verified'
                    and source.verification_status == 'verified'
                ),
            )
    next_action = task.next_action
    if (
        next_action and prerequisite
        and prerequisite.id == next_action.task_id
        and prerequisite.id in task.missing_prerequisites
    ):
        # Visit-only material does not establish what the prerequisite is about.
        visit_rule_ids = {
            item.rule_id for item in prerequisite.before_you_go.citations
        } if prerequisite.before_you_go else set()
        for source in prerequisite.sources:
            if source.url and source.rule_id not in visit_rule_ids and source.rule_id not in available:
                verified = source.verification_status == 'verified'
                available[source.rule_id] = CitedBlocker(
                    blocker=Blocker(
                        type='missing_prerequisite',
                        rule_id=source.rule_id,
                        verification_status='verified' if verified else 'needs_verification',
                        explanation=next_action.text,
                    ),
                    source=source,
                    verified=verified,
                )
    # The model may reorder entries. The engine supplies their wording and sources.
    order = list(available)
    if available and client is not None and model:
        try:
            response = client.responses.parse(
                model=model,
                instructions=(
                    'Select the most relevant blocker rule IDs for this workflow task. '
                    'Use only rule IDs present in the supplied blocker list.'
                ),
                input=json.dumps({
                    'title': task.title,
                    'blockers': [
                        {'rule_id': rule_id, 'type': item.blocker.type}
                        for rule_id, item in available.items()
                    ],
                }),
                text_format=CitationChoice,
                reasoning={'effort': 'none'},
                max_output_tokens=200,
                store=False,
            )
            choice = response.output_parsed
            if choice and validate_citations(choice.rule_ids, available):
                highlighted = set(choice.rule_ids)
                order = choice.rule_ids + [rule_id for rule_id in order if rule_id not in highlighted]
        except (OpenAIError, ValueError):
            # Keep the engine's original order if the model is unavailable.
            pass

    message = f'Task status: {task.status}.'
    if any(blocker.rule_id not in available for blocker in task.blockers):
        message += ' Some blocker details lack a source. Confirm them with the relevant office.'
    if any(not item.verified for item in available.values()):
        message += ' Some cited details are not verified.'
    return TaskExplanation(
        outcome='explained',
        message=message,
        next_action=task.next_action.text if task.next_action else None,
        citations=[available[rule_id] for rule_id in order],
    )


def generate_email(task: Task) -> EmailDraft | None:
    """Draft a request for guidance on a blocked task with a missing prerequisite."""
    if (
        task.status != 'Blocked'
        or task.next_action is None
        or task.next_action.task_id not in task.missing_prerequisites
    ):
        return None

    return EmailDraft(
        subject=f'Request for guidance: {task.title}',
        body=(
            'Dear [Office or DSO],\n\n'
            f'I am working on this task: {task.title}. My checklist shows a pending step:\n'
            f'{task.next_action.text}\n\n'
            'Could you confirm the applicable requirements, the next step, '
            'and the right office to contact?\n\n'
            'Thank you,\n[Your Name]\n[Student ID]'
        ),
    )
