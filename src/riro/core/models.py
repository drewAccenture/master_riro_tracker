"""Plain dataclasses shared by all layers."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class HeaderReport:
    """Slice 1 header check of one checklist file (architecture section 10)."""

    sheet_name: str
    sheet_matched: bool  # True if chosen because its name has "roll-in" or "rollin"
    headers_found: tuple[str, ...]
    headers_missing: tuple[str, ...]
    row_count: int
    deadline_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    """One row of a checklist file (US-02). status is always one of the four canonical texts."""

    row_number: int  # Excel row, header is row 1
    number: str
    role: str
    description: str
    deadline: str
    status: str
    completion_date: date | None
    assigned_id: str = ""
    remarks: str = ""
    note: str = ""  # "" or "completion date unclear"


@dataclass(frozen=True)
class SkippedRow:
    """A non-blank row that could not become a task (US-05: never dropped without a message)."""

    row_number: int
    reason: str


@dataclass(frozen=True)
class Checklist:
    """Everything read from one checklist file (US-02)."""

    sheet_name: str
    owner: str
    tasks: tuple[Task, ...]
    skipped_rows: tuple[SkippedRow, ...]
    headers_missing: tuple[str, ...]
    unknown_status_rows: int


@dataclass(frozen=True)
class TaskStatus:
    """Status of one task on a given "Status as of" date (US-04)."""

    track: str
    due: date | None
    days: int | None


@dataclass(frozen=True)
class JoinerStatus:
    """Statuses, tile counts and percent done of one joiner (US-04, US-05)."""

    tasks: tuple[TaskStatus, ...]
    counts: dict[str, int]
    applicable: int
    done: int
    percent: int
    delayed: bool
    delayed_count: int
    warnings: tuple[str, ...]
