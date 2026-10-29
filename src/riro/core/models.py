"""Plain dataclasses shared by all layers."""

from dataclasses import dataclass, field
from datetime import date, datetime


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


@dataclass(frozen=True)
class FileRecord:
    """What the app keeps about one checklist file, by its SharePoint UniqueId (US-09, US-10, ADR-005)."""

    id: str
    name: str
    etag: str
    modified: str
    present: bool  # False once the file left the folder (US-10); its data is kept
    checklist: Checklist | None  # last good read, None if never read
    read_at: datetime | None
    problem: str | None  # reason the last read failed, None when it worked


@dataclass(frozen=True)
class SyncRun:
    """One sync, for the summary and diagnostics (US-07)."""

    at: datetime
    result: str  # "ok", "partial" or "failed"
    files_read: int
    updated: int
    unchanged: int
    skipped: tuple[tuple[str, str], ...]  # (file name, reason)


@dataclass(frozen=True)
class Joiner:
    """One new joiner (ADR-005). The roll-on date lives here, never on the file (US-03)."""

    id: str  # stable: the UniqueId of the first file seen, never changes
    file_id: str  # the file read now; moves on a re-upload
    name: str
    owner_key: str  # normalized Checklist Owner, else normalized file name
    roll_on: date | None  # None = "Waiting for a roll-on date"
    hidden: bool  # no file in use now (left the folder, or lost a same-owner tie); data kept (US-10)
    missing_syncs: int  # syncs in a row while hidden; drives the re-upload window


@dataclass(frozen=True)
class JoinerView:
    """What the page needs for one joiner. status is None while waiting for a roll-on date."""

    joiner: Joiner
    checklist: Checklist | None
    status: JoinerStatus | None
    problem: str | None
    read_at: datetime | None
