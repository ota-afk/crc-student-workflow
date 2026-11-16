"""Integration checks for ENG's actual Day 2 rules and the synthetic demo profile."""

from datetime import date
from pathlib import Path

import pytest

from student_workflow.contract import StudentProfile
from student_workflow.engine import resolve
from student_workflow.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
ARRIVAL = date(2026, 8, 11)
AS_OF = date(2026, 8, 14)


def workflow(school_id="crc", *, residency_done=False, as_of=AS_OF):
    completed = ["task_i94_retrieval", "task_sevis_fee"]
    if residency_done:
        completed.append("task_proof_of_residency")
    profile = StudentProfile(
        student_id="demo_001",
        institution="Synthetic review profile",
        school_id=school_id,
        visa_type="F-1",
        arrival_date=ARRIVAL,
        has_ssn=False,
        completed_tasks=completed,
    )
    return resolve(load_rules(ROOT / "data/rules/rules.json"), profile, as_of)


@pytest.mark.parametrize(
    "school_id,count,checkin_rule",
    [
        ("crc", 8, "rule_crc_arrival_reporting"),
        (
            "california_state_university_sacramento",
            7,
            "rule_generic_f1_arrival_reporting",
        ),
        (None, 7, "rule_generic_f1_arrival_reporting"),
    ],
)
def test_demo_tasks_resolve_with_the_correct_school_guidance(
    school_id, count, checkin_rule
):
    result = workflow(school_id)
    tasks = {task.id: task for task in result.workflow}
    assert len(tasks) == count
    assert [s.rule_id for s in tasks["task_school_checkin"].sources] == [checkin_rule]
    assert ("task_crc_fee_payment" in tasks) == (school_id == "crc")
    for task_id in ("task_i94_retrieval", "task_sevis_fee"):
        assert tasks[task_id].status == "Completed"
    assert all(task.sources for task in tasks.values())
    rules = load_rules(ROOT / "data/rules/rules.json")
    assert all(
        source.url
        and source.verification_status == rules.rule(source.rule_id).verification_status
        for task in tasks.values()
        for source in task.sources
    )


@pytest.mark.parametrize("as_of", [ARRIVAL, AS_OF])
def test_dmv_dependency_does_not_turn_the_dso_advisory_into_a_block(as_of):
    blocked = {task.id: task for task in workflow(as_of=as_of).workflow}
    assert blocked["task_dmv_id"].status == "Blocked"
    assert blocked["task_dmv_id"].missing_prerequisites == [
        "task_proof_of_residency"
    ]

    result = workflow(residency_done=True, as_of=as_of)
    tasks = {task.id: task for task in result.workflow}
    assert tasks["task_dmv_id"].status == "Ready"
    assert tasks["task_confirm_sevis_active"].status != "Completed"
    assert tasks["task_school_checkin"].status != "Completed"
    assert not any(task.blockers for task in tasks.values())
    rules = load_rules(ROOT / "data/rules/rules.json")
    assert all(
        source.verification_status == rules.rule(source.rule_id).verification_status
        for task in tasks.values()
        for source in task.sources
    )
