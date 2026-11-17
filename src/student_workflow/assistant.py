"""Build a dashboard answer from the current, engine-resolved workflow."""

import os
import time
from collections.abc import Callable
from functools import partial

from anyio import move_on_after, to_thread
from openai import OpenAIError

from .ai_assistant import (
    DSO_MESSAGE,
    ERROR_MESSAGE,
    LANGUAGE_MESSAGE,
    REPHRASE_MESSAGE,
    has_name,
    has_sensitive_data,
    is_high_risk,
    is_supported_language,
    map_intent,
    openai_client,
)
from .ai_day3 import TaskExplanation, explain_task
from .contract import AnswerSource, AssistantAnswer, AssistantRequest, Task, Workflow
from .rules import RulesFile

# The dashboards wait 10 seconds. Intent matching gets two tries of 4 seconds (a cold first
# model call can be slow), so the worst case stays near 8 seconds. Optional citation ranking
# runs only if it still fits (RANKING_DEADLINE); otherwise the rules-based order is kept.
INTENT_TIMEOUT = 4.0
INTENT_ATTEMPTS = 2
CITATION_TIMEOUT = 2.0
RANKING_DEADLINE = 6.0
SELECTED_STEP_NOTE = 'The assistant was busy, so this answer is about the step you selected.'
DSO_CONTACT = "Your school's international student office (DSO)"
# One fixed lead per PageContext (docs/contract.md). A KeyError here means the contract's
# Literal gained a page without a lead: fail loudly rather than answer unframed.
PAGE_LEADS = {
    'journey': 'Where this step stands on your journey.',
    'readiness': 'What this step needs before you go.',
    'airshow': 'What to confirm with the office for this step.',
}


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
    started = time.monotonic()
    intent = None
    for _ in range(INTENT_ATTEMPTS):
        intent = await _within(
            INTENT_TIMEOUT,
            partial(map_intent, request.question, candidates, active_task_id=request.task_id,
                    timeout=INTENT_TIMEOUT),
        )
        # None = this try ran out of time; 'error' = the model failed. Both get one more try.
        if intent is not None and intent.outcome != 'error':
            break
    if intent is None or intent.outcome == 'error':
        # The model couldn't answer. Never leave the student with nothing: answer about the
        # step they have selected, from the rules alone (no model), after the same checks.
        fallback = _selected_step_answer(request, tasks, risk)
        return _frame(fallback, request.page_context) if fallback else _reply(ERROR_MESSAGE)
    if intent.outcome != 'matched' or intent.task_id not in tasks:
        contact = DSO_CONTACT if intent.outcome == 'dso_referral' else None
        return _reply(intent.message or ERROR_MESSAGE, contact=contact)

    task = tasks[intent.task_id]
    prerequisite, explanation = _explain(task, tasks, risk)
    # The model only affects citation order, so one or zero citations need no second call,
    # and it is skipped when a retry already used most of the time budget.
    if len(explanation.citations) > 1 and time.monotonic() - started < RANKING_DEADLINE:
        ranked = await _within(CITATION_TIMEOUT, partial(_rank_citations, task, prerequisite))
        if ranked is not None:
            explanation = ranked
    return _frame(_adapt_explanation(task, explanation), request.page_context)


def _explain(task: Task, tasks: dict[str, Task], risk: dict[str, bool]):
    """The rules-based explanation of one task (no model call) and its prerequisite."""
    prerequisite = tasks.get(task.next_action.task_id) if task.next_action else None
    high_risk = risk[task.id] or (prerequisite is not None and risk[prerequisite.id])
    return prerequisite, explain_task(task, high_risk=high_risk, prerequisite=prerequisite)


def _selected_step_answer(request: AssistantRequest, tasks: dict[str, Task],
                          risk: dict[str, bool]) -> AssistantAnswer | None:
    """Fallback when the model can't answer: explain the step the dashboard has selected.

    The question's checks run here again, because a model call that timed out may not have
    reached them: a status or work question is still referred to the DSO, and personal
    details or another language still get the rephrase messages. None = no step selected,
    so the caller returns the generic error message.
    """
    question = request.question
    if is_high_risk(question):
        return _reply(DSO_MESSAGE, contact=DSO_CONTACT)
    if has_name(question) or has_sensitive_data(question):
        return _reply(REPHRASE_MESSAGE)
    if not is_supported_language(question):
        return _reply(LANGUAGE_MESSAGE)
    task = tasks.get(request.task_id) if request.task_id else None
    if task is None:
        return None
    _, explanation = _explain(task, tasks, risk)
    answer = _adapt_explanation(task, explanation)
    if answer.task_id is None:
        return answer  # a high-risk step is a DSO referral, never a guessed explanation
    return answer.model_copy(update={'answer': f'{answer.answer} {SELECTED_STEP_NOTE}'})


def _frame(answer: AssistantAnswer, page: str | None) -> AssistantAnswer:
    """Lead an explained answer with one fixed sentence for the page it was asked on.

    Deterministic and server-side: the page never reaches the model, and the steps, sources
    and `verified` stay exactly as the cited explanation made them. Referrals and fallbacks
    (task_id None) are not framed, and page None leaves the answer unchanged.
    """
    if page is None or answer.task_id is None:
        return answer
    return answer.model_copy(update={'answer': f'{PAGE_LEADS[page]} {answer.answer}'})


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
