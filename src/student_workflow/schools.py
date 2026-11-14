"""Search ENG's sourced California school directory without inventing missing records."""

import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import schools_path
from .rules import RulesFile


class School(BaseModel):
    """A directory entry; certification does not verify our workflow requirements."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    school_id: str = Field(min_length=1)
    institution: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: Literal["CA"]
    school_verified: bool = False

    @model_validator(mode="after")
    def _id_is_not_reserved(self) -> "School":
        if self.school_id == "_generic":
            raise ValueError("_generic is reserved for generic rules")
        return self


def school_is_verified(rules: RulesFile, school_id: str | None) -> bool:
    """Only applicable school rules with completed verification can establish this flag."""
    if not school_id or school_id == "_generic":
        return False
    used = {rule_id for task in rules.tasks for rule_id in task.rule_ids}
    specific = [
        rule
        for rule in rules.rules
        if rule.layer == "school"
        and rule.school_id == school_id
        and rule.rule_id in used
    ]
    return bool(specific) and all(
        rule.verification_status == "verified" for rule in specific
    )


def load_schools(path: Path | None = None) -> list[School]:
    """Read fresh, reject malformed data, and let callers report an unavailable directory."""
    try:
        return _read_schools(path or schools_path())
    except csv.Error as error:
        raise ValueError("school CSV is malformed") from error


def _read_schools(path: Path) -> list[School]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        expected = {"school_id", "institution", "city", "state"}
        if not reader.fieldnames or set(reader.fieldnames) != expected:
            raise ValueError(
                "school CSV must have school_id,institution,city,state columns"
            )
        if len(reader.fieldnames) != len(expected):
            raise ValueError("school CSV has duplicate columns")
        schools = [School.model_validate(row) for row in reader]
    if not schools:
        raise ValueError("school CSV has no entries")
    ids = [school.school_id for school in schools]
    if len(set(ids)) != len(ids):
        raise ValueError("school CSV has duplicate school IDs")
    return schools


def search_schools(query: str, limit: int, rules: RulesFile) -> list[School]:
    """Search the supplied names and cities; never fetch or generate school data."""
    term = query.strip().casefold()
    matches = [
        school
        for school in load_schools()
        if term in school.institution.casefold() or term in school.city.casefold()
    ]
    return [
        school.model_copy(
            update={"school_verified": school_is_verified(rules, school.school_id)}
        )
        for school in matches[:limit]
    ]
