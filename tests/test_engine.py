"""Tests for the dependency resolver and the rules file (STU-D02-BE).

The rules here are made up ("(sample)"), so the tests never depend on ENG's real rules.
The dates match the demo: arrived 2026-08-11, "as of" 2026-08-14 (3 days later).
"""

import json
from datetime import date
from typing import Any

import pytest

from student_workflow.contract import StudentProfile, Workflow
from student_workflow.engine import RulesError, resolve
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
            task("task_checkin", rule_ids=["rule_checkin"]),
            task("task_residency", rule_ids=["rule_residency"]),
            task("task_dmv", ["task_checkin", "task_residency"], rule_ids=["rule_dmv"]),
        ],
        # rule_dmv stays first: several tests below change rules["rules"][0].
        "rules": [
            rule("rule_dmv", timing=timing),
            rule("rule_checkin"),
            rule("rule_residency"),
        ],
    }


def profile(
    completed: list[str] | None = None,
    arrival: date = ARRIVAL,
    awaiting: list[str] | None = None,
) -> StudentProfile:
    return StudentProfile(
        student_id="demo_001",
        institution="Cosumnes River College",
        visa_type="F-1",
        arrival_date=arrival,
        has_ssn=False,
        completed_tasks=completed or [],
        awaiting_reply=awaiting or [],
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
    """Synthetic data: shared, generic, CRC-only and other-school steps.

    task "checkin" cites both the generic rule and CRC's own rule, so CRC students get
    CRC's version and everyone else gets the generic one. "dmv" is shared and needs it.
    """
    return {
        "tasks": [
            task("shared", rule_ids=["shared_rule"]),
            task("checkin", ["shared"], rule_ids=["generic_checkin", "crc_checkin"]),
            task("crc_fee", ["checkin"], rule_ids=["crc_fee_rule"]),
            task("other_task", ["shared"], rule_ids=["other_rule"]),
            task("dmv", ["checkin"], rule_ids=["dmv_rule"]),
        ],
        "rules": [
            rule("shared_rule", layer="federal"),
            rule("generic_checkin", layer="school", school_id="_generic"),
            rule("crc_checkin", layer="school", school_id="crc"),
            rule("crc_fee_rule", layer="school", school_id="crc"),
            rule("other_rule", layer="school", school_id="other_school"),
            rule("dmv_rule", layer="california"),
        ],
    }


def for_school(
    school_id: str | None, raw: dict[str, Any] | None = None, completed=None
) -> Workflow:
    selected = profile(completed).model_copy(update={"school_id": school_id})
    return resolve(RulesFile.model_validate(raw or school_rules()), selected, AS_OF)


def source_ids(workflow: Workflow, task_id: str) -> list[str]:
    return [source.rule_id for source in by_id(workflow, task_id).sources]


@pytest.mark.parametrize(
    ("school_id", "expected"),
    [
        ("crc", ["shared", "checkin", "crc_fee", "dmv"]),
        ("other_school", ["shared", "checkin", "other_task", "dmv"]),
        ("unknown_school", ["shared", "checkin", "dmv"]),
        (None, ["shared", "checkin", "dmv"]),
        ("_generic", ["shared", "checkin", "dmv"]),
    ],
)
def test_each_school_gets_shared_tasks_plus_its_own_or_generic(school_id, expected):
    workflow = for_school(school_id)

    assert [task.id for task in workflow.workflow] == expected
    assert workflow.student_profile.school_verified is False


def test_school_rule_replaces_the_generic_rule_only_for_its_own_school():
    assert source_ids(for_school("crc"), "checkin") == ["crc_checkin"]
    assert source_ids(for_school("other_school"), "checkin") == ["generic_checkin"]


def test_one_school_rule_keeps_generic_steps_for_its_other_tasks():
    # PR #13 review: CRC's fee rule must not hide the generic check-in, or the DMV task
    # that depends on it.
    raw = {
        "tasks": [
            task("checkin", rule_ids=["generic_checkin"]),
            task("crc_fee", rule_ids=["crc_fee_rule"]),
            task("dmv", ["checkin"], rule_ids=["dmv_rule"]),
        ],
        "rules": [
            rule("generic_checkin", layer="school", school_id="_generic"),
            rule("crc_fee_rule", layer="school", school_id="crc"),
            rule("dmv_rule", layer="california"),
        ],
    }

    workflow = for_school("crc", raw)

    assert [task.id for task in workflow.workflow] == ["checkin", "crc_fee", "dmv"]
    assert source_ids(workflow, "checkin") == ["generic_checkin"]
    assert workflow.student_profile.school_verified is False


def test_dependency_on_another_schools_task_is_rejected_instead_of_removed():
    raw = school_rules()
    raw["tasks"][2]["prerequisites"] = ["other_task"]

    with pytest.raises(ValueError, match="needs other_task, which does not apply"):
        for_school("crc", raw)


def test_completed_task_from_another_school_is_rejected():
    with pytest.raises(ValueError, match="unknown task ids: other_task"):
        for_school("crc", completed=["shared", "other_task"])


def test_client_cannot_claim_its_school_is_verified():
    selected = profile().model_copy(
        update={"school_id": "crc", "school_verified": True}
    )

    result = resolve(RulesFile.model_validate(school_rules()), selected, AS_OF)

    assert result.student_profile.school_verified is False
    # Resolving returns a copy; the caller's profile is not changed.
    assert selected.school_verified is True


def crc_verified(raw: dict[str, Any], *rule_ids: str) -> dict[str, Any]:
    raw["rules"] = [
        verified_rule(rule_id=r["rule_id"], layer="school", school_id="crc")
        if r["rule_id"] in rule_ids
        else r
        for r in raw["rules"]
    ]
    return raw


def test_school_is_verified_when_all_its_own_steps_are_verified():
    raw = crc_verified(school_rules(), "crc_checkin", "crc_fee_rule")

    assert for_school("crc", raw).student_profile.school_verified is True


def test_school_is_not_verified_while_a_task_uses_the_generic_steps():
    raw = crc_verified(school_rules(), "crc_checkin", "crc_fee_rule")
    raw["tasks"][1]["rule_ids"] = ["generic_checkin"]  # CRC has no check-in rule of its own

    assert for_school("crc", raw).student_profile.school_verified is False


@pytest.mark.parametrize(
    "changes",
    [{"layer": "school"}, {"layer": "school", "school_id": "  "}, {"school_id": "crc"}],
)
def test_ambiguous_school_scope_is_rejected(changes):
    with pytest.raises(ValueError, match="school_id"):
        Rule.model_validate(rule("bad_scope", **changes))


def test_no_applicable_rules_returns_an_explicit_error():
    raw = school_rules()
    raw["tasks"] = [task("crc_fee", rule_ids=["crc_fee_rule"])]

    with pytest.raises(ValueError, match="No tasks found for this school"):
        for_school(None, raw)


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
    rules["tasks"].append(task("task_checkin", rule_ids=["rule_checkin"]))
    with pytest.raises(ValueError, match="duplicate task id task_checkin"):
        RulesFile.model_validate(rules)


def test_task_without_a_rule_is_rejected():
    # PR #13 review: a task with no rule would show with no source at all.
    rules = demo_rules()
    rules["tasks"][0]["rule_ids"] = []
    with pytest.raises(ValueError, match="rule_ids"):
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


# "Awaiting reply" (STU-D03-BE): the state "Resolve blocker" leaves behind


def test_task_awaiting_a_reply_is_in_progress():
    workflow = run(demo_rules(), awaiting=["task_residency"])
    assert status_of(workflow, "task_residency") == "In Progress"


def test_awaiting_a_reply_does_not_unblock_the_task_that_needs_it():
    # Writing to the office is not finishing the step: the DMV task stays Blocked.
    workflow = run(demo_rules(), ["task_checkin"], awaiting=["task_residency"])
    assert status_of(workflow, "task_dmv") == "Blocked"


def test_blocked_wins_over_awaiting_a_reply():
    workflow = run(demo_rules(), awaiting=["task_dmv"])
    assert status_of(workflow, "task_dmv") == "Blocked"


def test_unknown_awaiting_task_is_rejected():
    with pytest.raises(ValueError, match="awaiting_reply has unknown task ids: task_typo"):
        run(demo_rules(), awaiting=["task_typo"])


def test_task_both_completed_and_awaiting_is_rejected():
    with pytest.raises(ValueError, match="both completed and awaiting a reply"):
        run(demo_rules(), ["task_checkin"], awaiting=["task_checkin"])


@pytest.mark.parametrize("field", ["completed", "awaiting"])
def test_task_listed_twice_is_rejected(field):
    with pytest.raises(ValueError, match="more than once: task_checkin"):
        run(demo_rules(), **{field: ["task_checkin", "task_checkin"]})


def test_rules_that_cannot_serve_a_school_raise_rules_error():
    # RulesError, not a plain ValueError: the API answers 503 (our data), not 422.
    raw = {"tasks": [task("task_crc", rule_ids=["rule_crc"])], "rules": []}
    raw["rules"] = [rule("rule_crc", layer="school", school_id="crc")]
    with pytest.raises(RulesError):
        resolve(RulesFile.model_validate(raw), profile(), AS_OF)


def test_unknown_profile_key_is_rejected():
    raw = profile().model_dump(mode="json") | {"completed_task": ["task_checkin"]}
    with pytest.raises(ValueError, match="completed_task"):
        StudentProfile.model_validate(raw)


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
