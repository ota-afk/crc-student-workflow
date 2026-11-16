"""Integration checks for ENG's sourced rules and the synthetic demo profile."""

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
    checkin = tasks["task_school_checkin"]
    assert checkin.sources[0].rule_id == checkin_rule
    if school_id == "crc":
        assert checkin.before_you_go is not None
        assert checkin.before_you_go.phone == "(916) 691-7411"
        assert checkin.before_you_go.required_documents == []
        assert checkin.before_you_go.fees is None
        assert checkin.before_you_go.hours is None
    else:
        assert checkin.before_you_go is None
        assert [source.rule_id for source in checkin.sources] == [checkin_rule]

    dmv = tasks["task_dmv_id"]
    assert dmv.before_you_go is not None
    assert dmv.before_you_go.hours and "DMV office finder" in dmv.before_you_go.hours
    verification = {source.rule_id: source.verification_status for source in dmv.sources}
    assert dmv.before_you_go.citations
    assert all(
        citation.rule_id in verification
        and citation.verification_status == verification[citation.rule_id]
        for citation in dmv.before_you_go.citations
    )
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


def test_dso_recommendation_title_keeps_drivers_license_context():
    task = next(
        task for task in workflow().workflow if task.id == "task_confirm_sevis_active"
    )
    assert "before applying for a driver's license" in task.title.casefold()


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
