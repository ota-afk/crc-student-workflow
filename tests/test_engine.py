"""Tests for the dependency resolver and the rules file (STU-D02-BE).

The rules here are made up ("(sample)"), so the tests never depend on ENG's real rules.
The dates match the demo: arrived 2026-08-11, "as of" 2026-08-14 (3 days later).
"""

import json
from datetime import date
from typing import Any

import pytest

from student_workflow.contract import StudentProfile, Workflow
from student_workflow.engine import resolve
from student_workflow.rules import Rule, RulesFile, load_rules

ARRIVAL = date(2026, 8, 11)
AS_OF = date(2026, 8, 14)


def rule(rule_id: str, **changes: Any) -> dict[str, Any]:
    base = {
        "rule_id": rule_id,
        "statement": f"Sample statement for {rule_id} (sample)",
        "layer": "california",
        "high_risk": False,
        "verification_status": "needs_verification",
    }
    return {**base, **changes}


def task(
    task_id: str, prerequisites: list[str] | None = None, **changes: Any
) -> dict[str, Any]:
    base = {
        "id": task_id,
        "title": f"Title of {task_id} (sample)",
        "priority": "Required",
        "prerequisites": prerequisites or [],
    }
    return {**base, **changes}


def demo_rules(**dmv_timing: Any) -> dict[str, Any]:
    """check-in and residency first, then the DMV task, which also has a timing rule."""
    timing = {"from": "arrival_date", "days": 10, **dmv_timing}
    return {
        "tasks": [
            task("task_checkin"),
            task("task_residency"),
            task("task_dmv", ["task_checkin", "task_residency"], rule_ids=["rule_dmv"]),
        ],
        "rules": [rule("rule_dmv", timing=timing)],
    }


def profile(
    completed: list[str] | None = None, arrival: date = ARRIVAL
) -> StudentProfile:
    return StudentProfile(
        student_id="demo_001",
        institution="Cosumnes River College",
        visa_type="F-1",
        arrival_date=arrival,
        has_ssn=False,
        completed_tasks=completed or [],
    )


def run(
    rules: dict[str, Any], completed: list[str] | None = None, **kwargs: Any
) -> Workflow:
    as_of = kwargs.pop("as_of", AS_OF)
    return resolve(RulesFile.model_validate(rules), profile(completed, **kwargs), as_of)


def status_of(workflow: Workflow, task_id: str) -> str:
    return next(t.status for t in workflow.workflow if t.id == task_id)


def by_id(workflow: Workflow, task_id: str):
    return next(t for t in workflow.workflow if t.id == task_id)


# The plan's 8 edge cases


def test_task_without_prerequisites_is_ready():
    assert status_of(run(demo_rules()), "task_checkin") == "Ready"


def test_completed_task_is_completed():
    assert status_of(run(demo_rules(), ["task_checkin"]), "task_checkin") == "Completed"


def test_missing_prerequisite_blocks_and_points_to_it():
    dmv = by_id(run(demo_rules(), ["task_checkin"]), "task_dmv")
    assert dmv.status == "Blocked"
    assert dmv.missing_prerequisites == ["task_residency"]
    assert dmv.next_action.task_id == "task_residency"


def test_task_is_ready_once_prerequisites_and_wait_are_done():
    workflow = run(
        demo_rules(), ["task_checkin", "task_residency"], as_of=date(2026, 8, 21)
    )
    assert status_of(workflow, "task_dmv") == "Ready"


def test_timing_blocks_until_unlock_date_and_stays_unverified():
    dmv = by_id(run(demo_rules(), ["task_checkin", "task_residency"]), "task_dmv")
    assert dmv.status == "Blocked"
    assert dmv.blockers[0].type == "timing"
    assert dmv.blockers[0].unlocks_on == date(2026, 8, 21)
    assert dmv.blockers[0].verification_status == "needs_verification"


def test_timing_unlocks_on_the_unlock_date_itself():
    done = ["task_checkin", "task_residency"]
    assert (
        status_of(run(demo_rules(), done, as_of=date(2026, 8, 20)), "task_dmv")
        == "Blocked"
    )
    assert (
        status_of(run(demo_rules(), done, as_of=date(2026, 8, 21)), "task_dmv")
        == "Ready"
    )


def test_arrived_three_days_ago_shows_when_ready():
    # The demo's "Are you ready, and when will you be?": 3 days in, a 10-day wait ends in 7.
    dmv = by_id(run(demo_rules(), ["task_checkin", "task_residency"]), "task_dmv")
    assert (dmv.blockers[0].unlocks_on - AS_OF).days == 7


def test_missing_prerequisite_and_timing_both_show():
    dmv = by_id(run(demo_rules()), "task_dmv")
    assert dmv.missing_prerequisites == ["task_checkin", "task_residency"]
    assert [b.type for b in dmv.blockers] == ["timing"]


# The result keeps the contract's promises


def test_result_is_consistent_like_the_mock():
    workflow = run(demo_rules(), ["task_checkin"])
    completed = {t.id for t in workflow.workflow if t.status == "Completed"}
    assert set(workflow.student_profile.completed_tasks) == completed
    for t in workflow.workflow:
        assert set(t.missing_prerequisites) == set(t.prerequisites) - completed
        if t.status == "Blocked":
            assert t.missing_prerequisites or t.blockers
        else:
            assert not t.missing_prerequisites and not t.blockers


def test_result_is_live_data_with_sources():
    workflow = run(demo_rules())
    assert workflow.is_mock is False
    assert by_id(workflow, "task_dmv").sources[0].rule_id == "rule_dmv"


@pytest.mark.parametrize(
    "completed", [[], ["task_checkin", "task_residency", "task_dmv"]]
)
def test_unverified_source_state_survives_timing_expiry_and_completion(completed):
    rules = demo_rules()
    rules["rules"][0].update(
        source_url="https://example.org/test", last_verified="2026-08-01"
    )

    workflow = run(rules, completed, as_of=date(2026, 8, 21))

    dmv = by_id(workflow, "task_dmv")
    assert not dmv.blockers
    assert dmv.sources[0].verification_status == "needs_verification"
    assert dmv.sources[0].last_verified == date(2026, 8, 1)


def test_non_timing_rule_preserves_its_unverified_state():
    rules = demo_rules()
    rules["rules"][0].pop("timing")
    rules["rules"][0].update(
        source_url="https://example.org/test", last_verified="2026-08-01"
    )

    workflow = run(rules, ["task_checkin", "task_residency"])

    dmv = by_id(workflow, "task_dmv")
    assert dmv.status == "Ready"
    assert dmv.sources[0].verification_status == "needs_verification"


def verified_rule(**changes: Any) -> dict[str, Any]:
    return rule(
        changes.pop("rule_id", "verified_rule"),
        **{
            "verification_status": "verified",
            "source_url": "https://example.org/test",
            "evidence": "Test evidence (sample)",
            "last_verified": "2026-08-01",
            "verified_by": "First Checker",
            "second_checker": "Second Checker",
            **changes,
        },
    )


@pytest.mark.parametrize("second", ["First Checker", "  FIRST   checker  "])
def test_same_person_cannot_supply_both_verification_checks(second):
    with pytest.raises(ValueError, match="two different checkers"):
        Rule.model_validate(verified_rule(second_checker=second))


@pytest.mark.parametrize(
    "field", ["source_url", "evidence", "verified_by", "second_checker"]
)
def test_whitespace_is_not_verification_evidence(field):
    with pytest.raises(ValueError, match=field):
        Rule.model_validate(verified_rule(**{field: "  "}))


def test_different_checkers_can_verify_a_rule():
    assert Rule.model_validate(verified_rule()).verification_status == "verified"


def school_rules() -> dict[str, Any]:
    """Synthetic data covers shared, school-specific, and generic applicability."""
    return {
        "tasks": [
            task("shared", rule_ids=["shared_rule"]),
            task("crc_task", ["shared"], rule_ids=["crc_rule"]),
            task("other_task", ["shared"], rule_ids=["other_rule"]),
            task("generic_checkin", ["shared"], rule_ids=["generic_rule"]),
        ],
        "rules": [
            rule("shared_rule", layer="federal"),
            rule("crc_rule", layer="school", school_id="crc"),
            rule("other_rule", layer="school", school_id="other_school"),
            rule("generic_rule", layer="school", school_id="_generic"),
        ],
    }


@pytest.mark.parametrize(
    ("school_id", "expected"),
    [
        ("crc", ["shared", "crc_task"]),
        ("other_school", ["shared", "other_task"]),
        ("unknown_school", ["shared", "generic_checkin"]),
        (None, ["shared", "generic_checkin"]),
    ],
)
def test_resolver_selects_shared_and_matching_or_generic_school_rules(
    school_id, expected
):
    selected = profile().model_copy(update={"school_id": school_id})

    result = resolve(RulesFile.model_validate(school_rules()), selected, AS_OF)

    assert [task.id for task in result.workflow] == expected
    assert result.student_profile.school_verified is False


def test_unused_school_rule_does_not_hide_generic_fallback():
    raw = school_rules()
    raw["tasks"] = [task for task in raw["tasks"] if task["id"] != "crc_task"]

    result = resolve(
        RulesFile.model_validate(raw),
        profile().model_copy(update={"school_id": "crc"}),
        AS_OF,
    )

    assert [task.id for task in result.workflow] == ["shared", "generic_checkin"]


def test_cross_school_dependency_is_rejected_instead_of_removed():
    raw = school_rules()
    raw["tasks"][1]["prerequisites"] = ["other_task"]

    with pytest.raises(ValueError, match="unknown task other_task"):
        resolve(
            RulesFile.model_validate(raw),
            profile().model_copy(update={"school_id": "crc"}),
            AS_OF,
        )


def test_completed_task_from_another_school_is_rejected():
    selected = profile(["other_task", "shared"]).model_copy(update={"school_id": "crc"})

    with pytest.raises(ValueError, match="unknown task ids: other_task"):
        resolve(RulesFile.model_validate(school_rules()), selected, AS_OF)


def test_client_cannot_claim_its_school_is_verified():
    selected = profile().model_copy(
        update={"school_id": "crc", "school_verified": True}
    )

    result = resolve(RulesFile.model_validate(school_rules()), selected, AS_OF)

    assert result.student_profile.school_verified is False
    assert (
        selected.school_verified is True
    )  # resolving did not mutate the caller's profile


def test_school_verification_requires_verified_school_specific_rules():
    raw = school_rules()
    raw["rules"][1] = verified_rule(rule_id="crc_rule", layer="school", school_id="crc")

    result = resolve(
        RulesFile.model_validate(raw),
        profile().model_copy(update={"school_id": "crc"}),
        AS_OF,
    )

    assert result.student_profile.school_verified is True


@pytest.mark.parametrize(
    "changes",
    [{"layer": "school"}, {"layer": "school", "school_id": "  "}, {"school_id": "crc"}],
)
def test_ambiguous_school_scope_is_rejected(changes):
    with pytest.raises(ValueError, match="school_id"):
        Rule.model_validate(rule("bad_scope", **changes))


def test_no_applicable_rules_returns_an_explicit_error():
    raw = school_rules()
    raw["tasks"] = [task for task in raw["tasks"] if task["id"] == "crc_task"]
    raw["tasks"][0]["prerequisites"] = []

    with pytest.raises(ValueError, match="No tasks found for this school"):
        resolve(RulesFile.model_validate(raw), profile(), AS_OF)


# Fail loudly on a bad rules file


def test_unknown_key_in_rules_file_is_rejected():
    rules = demo_rules()
    rules["rules"][0]["timming"] = {}
    with pytest.raises(ValueError, match="timming"):
        RulesFile.model_validate(rules)


def test_unknown_prerequisite_is_rejected():
    rules = demo_rules()
    rules["tasks"][0]["prerequisites"] = ["task_typo"]
    with pytest.raises(ValueError, match="unknown task task_typo"):
        RulesFile.model_validate(rules)


def test_prerequisite_loop_is_rejected():
    rules = demo_rules()
    rules["tasks"][0]["prerequisites"] = ["task_dmv"]
    with pytest.raises(ValueError, match="prerequisite loop"):
        RulesFile.model_validate(rules)


def test_duplicate_task_id_is_rejected():
    rules = demo_rules()
    rules["tasks"].append(task("task_checkin"))
    with pytest.raises(ValueError, match="duplicate task id task_checkin"):
        RulesFile.model_validate(rules)


def test_verified_rule_without_evidence_is_rejected():
    rules = demo_rules()
    rules["rules"][0]["verification_status"] = "verified"
    with pytest.raises(ValueError, match="verified but missing"):
        RulesFile.model_validate(rules)


def test_rule_without_high_risk_flag_is_rejected():
    rules = demo_rules()
    del rules["rules"][0]["high_risk"]
    with pytest.raises(ValueError, match="high_risk"):
        RulesFile.model_validate(rules)


# Fail loudly on a bad profile


def test_unknown_completed_task_is_rejected():
    with pytest.raises(ValueError, match="unknown task ids: task_typo"):
        run(demo_rules(), ["task_typo"])


def test_task_completed_before_its_prerequisites_is_rejected():
    with pytest.raises(ValueError, match="task_dmv is completed"):
        run(demo_rules(), ["task_dmv"])


# Loading the real file


def test_load_rules_reads_rules_path(monkeypatch, tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(demo_rules()), encoding="utf-8")
    monkeypatch.setenv("RULES_PATH", str(path))
    assert [t.id for t in load_rules().tasks] == [
        "task_checkin",
        "task_residency",
        "task_dmv",
    ]


def test_real_rules_file_matches_the_contract(monkeypatch):
    # Catches typos in ENG's data/rules/rules.json in CI, before the engine ever runs on it.
    monkeypatch.delenv("RULES_PATH", raising=False)
    assert load_rules().tasks


def test_real_crc_rule_is_available_for_crc(monkeypatch):
    monkeypatch.delenv("RULES_PATH", raising=False)
    selected = profile().model_copy(update={"school_id": "crc"})

    workflow = resolve(load_rules(), selected, AS_OF)

    assert "task_crc_fee_payment" in {task.id for task in workflow.workflow}
