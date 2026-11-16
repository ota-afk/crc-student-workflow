"""Shared API shapes; missing verification is always explicit rather than inferred."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

# extra='forbid': an unknown key in a request (a typo like 'completed_task') is a 422, not ignored.
STRICT = ConfigDict(extra='forbid')

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


class Citation(BaseModel):
    """Where one before-you-go fact comes from, so FE can label it "Not verified"."""

    field: Literal[
        'required_documents', 'fees', 'hours', 'appointment_rules', 'phone',
        'official_url', 'warnings',
    ]
    text: str
    rule_id: str
    verification_status: Literal['verified', 'needs_verification']


class BeforeYouGo(BaseModel):
    required_documents: list[str] = []
    fees: str | None = None
    hours: str | None = None
    appointment_rules: str | None = None
    phone: str | None = None
    official_url: str | None = None
    warnings: list[str] = []
    # Added beside the strings (not replacing them), so dashboards that read the strings keep
    # working. [] = no per-fact source supplied (the mock), so every fact counts as unverified.
    citations: list[Citation] = []


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
    # The dashboard sends back the profile it received, so a strict model costs it nothing.
    model_config = STRICT

    student_id: str
    institution: str
    visa_type: str
    arrival_date: date
    has_ssn: bool
    completed_tasks: list[str] = []
    # Tasks whose office the student has written to ("Resolve blocker"); shown as In Progress.
    awaiting_reply: list[str] = []
    school_id: str | None = None
    school_verified: bool = False


class Workflow(BaseModel):
    schema_version: str
    is_mock: bool = False
    as_of: date
    student_profile: StudentProfile
    workflow: list[Task]


class WorkflowRequest(BaseModel):
    """Body of POST /workflow and both task actions: the server stores nothing between calls."""

    model_config = STRICT

    # None = not sent, so the API uses today's date in California (see docs/contract.md).
    as_of: date | None = None
    student_profile: StudentProfile


class ResolveResult(BaseModel):
    """Answer of POST /tasks/{task_id}/resolve."""

    workflow: Workflow
    # Always None for now: no draft exists until AI's generate_email() is built and agreed.
    # FE shows "Email draft not available yet" and never a made-up draft.
    email_draft: None = None
