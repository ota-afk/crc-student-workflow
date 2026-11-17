"""Build a dashboard answer from the current, engine-resolved workflow."""

import os
from collections.abc import Callable
from functools import partial

from anyio import move_on_after, to_thread
from openai import OpenAIError

from .ai_assistant import ERROR_MESSAGE, map_intent, openai_client
from .ai_day3 import TaskExplanation, explain_task
from .contract import AnswerSource, AssistantAnswer, AssistantRequest, Task, Workflow
from .rules import RulesFile

# The dashboard's shared API client waits 10 seconds. Limit each stage, including
# time waiting for a worker, and keep the rules-based explanation if ranking runs out of time.
INTENT_TIMEOUT = 5.0
CITATION_TIMEOUT = 2.0
DSO_CONTACT = "Your school's international student office (DSO)"


async def _within[T](seconds: float, call: Callable[[], T]) -> T | None:
    with move_on_after(seconds):
        return await to_thread.run_sync(call, abandon_on_cancel=True)
    return None


async def answer_question(
    request: AssistantRequest, workflow: Workflow, rules: RulesFile
) -> AssistantAnswer:
    tasks = {task.id: task for task in workflow.workflow}
    # The resolver has already scoped each task's sources to this school.
    risk = {
        task.id: not task.sources or any(rules.rule(s.rule_id).high_risk for s in task.sources)
        for task in tasks.values()
    }
    candidates = [
        {'id': task.id, 'title': task.title, 'high_risk': risk[task.id]}
        for task in tasks.values()
    ]
    intent = await _within(
        INTENT_TIMEOUT,
        partial(map_intent, request.question, candidates, active_task_id=request.task_id,
                timeout=INTENT_TIMEOUT),
    )
    if intent is None:
        return _reply(ERROR_MESSAGE)
    if intent.outcome != 'matched' or intent.task_id not in tasks:
        contact = DSO_CONTACT if intent.outcome == 'dso_referral' else None
        return _reply(intent.message or ERROR_MESSAGE, contact=contact)

    task = tasks[intent.task_id]
    prerequisite = tasks.get(task.next_action.task_id) if task.next_action else None
    high_risk = risk[task.id] or (prerequisite is not None and risk[prerequisite.id])
    explanation = explain_task(task, high_risk=high_risk, prerequisite=prerequisite)
    # The model only affects citation order, so one or zero citations need no second call.
    if len(explanation.citations) > 1:
        ranked = await _within(CITATION_TIMEOUT, partial(_rank_citations, task, prerequisite))
        if ranked is not None:
            explanation = ranked
    return _adapt_explanation(task, explanation)


def _rank_citations(task: Task, prerequisite: Task | None) -> TaskExplanation | None:
    key, model = os.getenv('OPENAI_API_KEY'), os.getenv('OPENAI_MODEL')
    if not key or not model:
        return None
    try:
        with openai_client(key, CITATION_TIMEOUT) as client:
            return explain_task(
                task, high_risk=False, prerequisite=prerequisite, client=client, model=model
            )
    except (OpenAIError, ValueError):
        return None


def _reply(message: str, *, contact: str | None = None) -> AssistantAnswer:
    return AssistantAnswer(answer=message, steps=[], sources=[], verified=False, contact=contact,
                           task_id=None, is_mock=False)


def _adapt_explanation(task: Task, explanation: TaskExplanation) -> AssistantAnswer:
    if explanation.outcome != 'explained':
        contact = DSO_CONTACT if explanation.outcome == 'dso_referral' else None
        return _reply(explanation.message, contact=contact)

    steps = [explanation.next_action] if explanation.next_action else []
    sources = []
    for citation in explanation.citations:
        blocker, source = citation.blocker, citation.source
        step = blocker.explanation
        if blocker.unlocks_on is not None:
            step += f' Unlock date: {blocker.unlocks_on.isoformat()}.'
        if step not in steps:
            steps.append(step)
        sources.append(AnswerSource(
            rule_id=source.rule_id,
            url=source.url,
            last_verified=source.last_verified,
            verification_status='verified' if citation.verified else 'needs_verification',
        ))

    cited_ids = {source.rule_id for source in sources}
    next_action_cited = not explanation.next_action or any(
        citation.blocker.type == 'missing_prerequisite' for citation in explanation.citations
    )
    verified = (
        bool(sources)
        and next_action_cited
        and all(citation.verified for citation in explanation.citations)
        and all(blocker.rule_id in cited_ids for blocker in task.blockers)
    )
    return AssistantAnswer(answer=explanation.message, steps=steps, sources=sources,
                           verified=verified, contact=None, task_id=task.id, is_mock=False)
