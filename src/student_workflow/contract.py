"""Shared API shapes; missing verification is always explicit rather than inferred."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# extra='forbid': an unknown key in a request (a typo like 'completed_task') is a 422, not ignored.
STRICT = ConfigDict(extra='forbid')

# The demo has eight tasks. Leave room to grow while bounding untrusted progress lists.
MAX_PROGRESS_TASKS = 1000
MAX_ASSISTANT_QUESTION_CHARS = 500

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
    completed_tasks: list[str] = Field(default_factory=list, max_length=MAX_PROGRESS_TASKS)
    # Tasks whose office the student has written to ("Resolve blocker"); shown as In Progress.
    awaiting_reply: list[str] = Field(default_factory=list, max_length=MAX_PROGRESS_TASKS)
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


class AssistantProfile(BaseModel):
    """The workflow inputs needed for an answer, without a student identifier."""

    model_config = STRICT

    institution: str
    visa_type: str
    arrival_date: date
    has_ssn: bool
    school_id: str | None = None
    completed_tasks: list[str] = Field(default_factory=list, max_length=MAX_PROGRESS_TASKS)
    awaiting_reply: list[str] = Field(default_factory=list, max_length=MAX_PROGRESS_TASKS)


class AssistantRequest(BaseModel):
    model_config = STRICT

    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_ASSISTANT_QUESTION_CHARS
        ),
    ]
    task_id: str | None = None
    as_of: date
    student_profile: AssistantProfile


class AnswerSource(BaseModel):
    model_config = STRICT

    rule_id: str
    url: str | None
    last_verified: date | None
    verification_status: Literal['verified', 'needs_verification', 're-checking']


class AssistantAnswer(BaseModel):
    model_config = STRICT

    answer: str = Field(min_length=1)
    steps: list[str]
    sources: list[AnswerSource]
    verified: bool = Field(strict=True)
    contact: str | None
    task_id: str | None
    is_mock: bool = Field(strict=True)


class EmailDraft(BaseModel):
    """A placeholder draft for the student to review and send."""

    subject: str
    body: str


class ResolveResult(BaseModel):
    """Answer of POST /tasks/{task_id}/resolve."""

    workflow: Workflow
    email_draft: EmailDraft | None = None
