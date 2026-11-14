"""Shared API shapes; missing verification is always explicit rather than inferred."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

Status = Literal['Blocked', 'Ready', 'In Progress', 'Completed']
Priority = Literal['Required', 'Recommended', 'Optional']


class NextAction(BaseModel):
    task_id: str
    text: str


class Blocker(BaseModel):
    type: Literal['timing', 'missing_prerequisite', 'document']
    rule_id: str
    unlocks_on: date | None = None
    verification_status: Literal['verified', 'needs_verification']
    explanation: str


class BeforeYouGo(BaseModel):
    required_documents: list[str] = []
    fees: str | None = None
    hours: str | None = None
    appointment_rules: str | None = None
    phone: str | None = None
    official_url: str | None = None
    warnings: list[str] = []


class Source(BaseModel):
    rule_id: str
    url: str | None = None
    last_verified: date | None = None
    verification_status: Literal['verified', 'needs_verification'] | None = None


class Task(BaseModel):
    id: str
    title: str
    status: Status
    priority: Priority
    prerequisites: list[str] = []
    missing_prerequisites: list[str] = []
    next_action: NextAction | None = None
    blockers: list[Blocker] = []
    before_you_go: BeforeYouGo | None = None
    sources: list[Source] = []


class StudentProfile(BaseModel):
    student_id: str
    institution: str
    visa_type: str
    arrival_date: date
    has_ssn: bool
    completed_tasks: list[str] = []
    school_id: str | None = None
    school_verified: bool = False


class Workflow(BaseModel):
    schema_version: str
    is_mock: bool = False
    as_of: date
    student_profile: StudentProfile
    workflow: list[Task]
