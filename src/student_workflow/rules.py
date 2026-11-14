"""Shape of ENG's rules file (data/rules/rules.json) and how to load it (STU-D02-BE).

docs/contract.md, section "The rules file", is the written version of these models.
"""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import rules_path
from .contract import Priority

# extra='forbid': an unknown key (a typo like "timming") is an error, not silently ignored.
STRICT = ConfigDict(extra="forbid")

# school_id of ENG's generic F-1 check-in rules, used when a school has no rule of its own.
GENERIC = "_generic"


class Timing(BaseModel):
    """Proposed: blocks a task until `days` after a date in the student's profile."""

    model_config = STRICT

    # "from" is a Python keyword, so the field is called from_ and read from the JSON key "from".
    from_: Literal["arrival_date"] = Field(alias="from")
    # ge=0: a negative wait makes no sense, so it fails loudly.
    days: int = Field(ge=0)


class Rule(BaseModel):
    model_config = STRICT

    rule_id: str
    statement: str
    layer: Literal["federal", "california", "school"]
    school_id: str | None = None
    # Required on purpose: a missing flag must never quietly mean "not high risk".
    high_risk: bool
    verification_status: Literal["verified", "needs_verification"]
    # None = not recorded yet. Such a rule can only be needs_verification (checked below).
    source_url: str | None = None
    evidence: str | None = None
    last_checked: date | None = None
    last_verified: date | None = None
    verified_by: str | None = None
    second_checker: str | None = None
    second_check_date: date | None = None
    # None = the Day 4 source checker has not looked at this page yet.
    changed: bool | None = None
    # None = this rule never blocks a task on its own.
    timing: Timing | None = None

    @model_validator(mode="after")
    def _school_id_matches_layer(self) -> "Rule":
        # The plan: school rules name a school (or "_generic"); federal and california use null.
        if self.layer == "school":
            if not self.school_id or not self.school_id.strip():
                raise ValueError(f"school rule {self.rule_id} needs a school_id")
            self.school_id = self.school_id.strip()
        elif self.school_id is not None:
            raise ValueError(
                f"{self.layer} rule {self.rule_id} must have school_id null"
            )
        return self

    @model_validator(mode="after")
    def _verified_needs_evidence(self) -> "Rule":
        # The plan: a rule changes to verified only when all of its evidence is filled in.
        if self.verification_status == "verified":
            evidence = {
                "source_url": self.source_url,
                "evidence": self.evidence,
                "last_verified": self.last_verified,
                "verified_by": self.verified_by,
                "second_checker": self.second_checker,
            }
            missing = [
                name
                for name, value in evidence.items()
                if not value or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                raise ValueError(
                    f"rule {self.rule_id} is verified but missing: {', '.join(missing)}"
                )
            first = " ".join(self.verified_by.split()).casefold()
            second = " ".join(self.second_checker.split()).casefold()
            if first == second:
                raise ValueError(f"rule {self.rule_id} needs two different checkers")
        return self


class RuleTask(BaseModel):
    """A task as ENG writes it. The engine turns it into a contract Task with a status."""

    model_config = STRICT

    id: str
    title: str
    priority: Priority
    prerequisites: list[str] = []
    # min_length=1: every task needs a source. Unfinished research still cites a rule,
    # marked needs_verification, so it shows as "Not verified" instead of looking sourced.
    rule_ids: list[str] = Field(min_length=1)


class RulesFile(BaseModel):
    model_config = STRICT

    tasks: list[RuleTask]
    rules: list[Rule]

    @model_validator(mode="after")
    def _ids_are_consistent(self) -> "RulesFile":
        task_ids = _unique([t.id for t in self.tasks], "task")
        rule_ids = _unique([r.rule_id for r in self.rules], "rule")
        for task in self.tasks:
            for prerequisite in task.prerequisites:
                if prerequisite not in task_ids:
                    raise ValueError(
                        f"task {task.id} needs unknown task {prerequisite}"
                    )
            for rule_id in task.rule_ids:
                if rule_id not in rule_ids:
                    raise ValueError(f"task {task.id} cites unknown rule {rule_id}")
        _reject_loops(self.tasks)
        return self

    def task(self, task_id: str) -> RuleTask:
        return next(t for t in self.tasks if t.id == task_id)

    def rule(self, rule_id: str) -> Rule:
        return next(r for r in self.rules if r.rule_id == rule_id)


def _unique(ids: list[str], kind: str) -> set[str]:
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise ValueError(f"duplicate {kind} id {item}")
        seen.add(item)
    return seen


def _reject_loops(tasks: list[RuleTask]) -> None:
    """Fail if prerequisites go in a circle (A needs B, B needs A): no task could ever start."""
    needs = {t.id: t.prerequisites for t in tasks}
    done: set[str] = set()  # tasks already checked, so each is walked only once

    def walk(task_id: str, path: list[str]) -> None:
        if task_id in path:
            loop = " -> ".join([*path[path.index(task_id) :], task_id])
            raise ValueError(f"prerequisite loop: {loop}")
        if task_id in done:
            return
        for prerequisite in needs[task_id]:
            walk(prerequisite, [*path, task_id])
        done.add(task_id)

    for task_id in needs:
        walk(task_id, [])


def applicable_rules(
    rules: RulesFile, task: RuleTask, school_id: str | None
) -> list[Rule]:
    """The rules of one task that apply to this school, in the order the task cites them.

    Federal and California rules always apply. For school rules, the school's own rule
    replaces the generic one, but only for this task: a task the school has not covered
    keeps its generic steps. An empty list means the task does not apply to this school.
    """
    cited = [rules.rule(rule_id) for rule_id in task.rule_ids]
    # None or "_generic" = no school picked, so only generic school rules can apply.
    has_own = school_id not in (None, GENERIC) and any(
        r.layer == "school" and r.school_id == school_id for r in cited
    )
    scope = school_id if has_own else GENERIC
    # Another school's rule never applies here; it is skipped, not substituted.
    return [r for r in cited if r.layer != "school" or r.school_id == scope]


def load_rules(path: Path | None = None) -> RulesFile:
    # None = use RULES_PATH (default data/rules/rules.json), read fresh on every call.
    source = path or rules_path()
    return RulesFile.model_validate_json(source.read_text(encoding="utf-8"))
