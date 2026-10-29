"""US-02 / US-05: read() turns one synthetic checklist into Task rows (plan slice 2, section 3.1).

Row numbers are 1-based Excel rows: the header is row 1, the first data row is row 2.
"""

import dataclasses
from datetime import date, datetime

import pytest

from riro.core.checklist import OPTIONAL_HEADERS, REQUIRED_HEADERS, UnreadableFile, read
from riro.core.models import Checklist, SkippedRow, Task

HEADER = list(REQUIRED_HEADERS) + list(OPTIONAL_HEADERS)
SKIP_REASON = "no task number or description"
UNCLEAR = "completion date unclear"


def _only_task(make_checklist, row):
    checklist = read(make_checklist([row]))
    assert len(checklist.tasks) == 1
    return checklist.tasks[0]


def test_us02_read_returns_frozen_checklist_with_every_field(make_checklist, make_row):
    row = make_row(
        7,
        "Invented task seven",
        status="Completed",
        completion_date=datetime(2026, 3, 5, 14, 30),
        deadline="1 days After Roll On",
        owner="Test Person A",
        role="Hiring Manager",
        assigned_id="invented.id",
        remarks="Invented remark",
    )
    checklist = read(make_checklist([row]))
    assert isinstance(checklist, Checklist)
    assert checklist.sheet_name == "Roll-In Checklist"
    assert checklist.owner == "Test Person A"
    assert checklist.headers_missing == ()
    assert checklist.skipped_rows == ()
    assert checklist.unknown_status_rows == 0
    assert checklist.tasks == (
        Task(
            row_number=2,
            number="7",
            role="Hiring Manager",
            description="Invented task seven",
            deadline="1 days After Roll On",
            status="Completed",
            completion_date=date(2026, 3, 5),
            assigned_id="invented.id",
            remarks="Invented remark",
            note="",
        ),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        checklist.owner = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        checklist.tasks[0].status = "x"


def test_us02_tasks_are_exactly_the_rows_in_file_order(make_checklist, make_row):
    rows = [make_row(n, f"Invented task {n}") for n in (3, 1, 2)]
    checklist = read(make_checklist(rows))
    assert [t.number for t in checklist.tasks] == ["3", "1", "2"]
    assert [t.row_number for t in checklist.tasks] == [2, 3, 4]
    assert [t.description for t in checklist.tasks] == [
        "Invented task 3",
        "Invented task 1",
        "Invented task 2",
    ]


def test_us02_header_row_only_gives_no_tasks(make_checklist):
    checklist = read(make_checklist([]))
    assert checklist.tasks == ()
    assert checklist.skipped_rows == ()
    assert checklist.headers_missing == ()


@pytest.mark.parametrize(
    "cell, expected",
    [(3, "3"), (3.0, "3"), ("1.5", "1.5"), ("A1", "A1"), ("  12 ", "12")],
)
def test_us02_task_number_int_like_or_trimmed_text(
    make_checklist, make_row, cell, expected
):
    assert _only_task(make_checklist, make_row(cell, "Invented")).number == expected


def test_us02_text_fields_are_trimmed_and_none_is_empty(make_checklist, make_row):
    row = make_row(
        1,
        "  Invented task  ",
        deadline="  On Roll On ",
        role=" PMO ",
        assigned_id=None,
        remarks="  ",
    )
    no_deadline = make_row(2, "Second", deadline=None, role=None)
    task, second = read(make_checklist([row, no_deadline])).tasks
    assert task.description == "Invented task"
    assert task.deadline == "On Roll On"
    assert task.role == "PMO"
    assert task.assigned_id == ""
    assert task.remarks == ""
    assert (second.deadline, second.role) == ("", "")


def test_us02_headers_any_case_any_order_optional_missing(make_checklist):
    header = ["deadline", "COMPLETION STATUS", " description ", "Task number"]
    header += ["completion date", "ROLE", "checklist owner"]
    row = ["3 days After Roll On", "in progress", "Invented", 4, None, "Buddy"]
    row += ["Test Person B"]
    checklist = read(make_checklist([row], header=header))
    assert checklist.headers_missing == ()
    assert checklist.owner == "Test Person B"
    assert checklist.tasks == (
        Task(
            row_number=2,
            number="4",
            role="Buddy",
            description="Invented",
            deadline="3 days After Roll On",
            status="In Progress",
            completion_date=None,
        ),
    )


@pytest.mark.parametrize(
    "cell, expected",
    [
        ("Not Started", "Not Started"),
        ("In Progress", "In Progress"),
        ("Completed", "Completed"),
        ("Not Applicable", "Not Applicable"),
        ("completed ", "Completed"),
        ("IN PROGRESS", "In Progress"),
        ("  not applicable", "Not Applicable"),
        ("NOT started", "Not Started"),
    ],
)
def test_us02_status_matches_any_case_and_spaces(
    make_checklist, make_row, cell, expected
):
    checklist = read(make_checklist([make_row(1, "Invented", status=cell)]))
    assert checklist.tasks[0].status == expected
    assert checklist.unknown_status_rows == 0


def test_us02_unknown_or_empty_status_is_not_started_and_counted(
    make_checklist, make_row
):
    cells = ["Done", "", None, "Completed", "Blocked"]
    rows = [make_row(n, "Invented", status=c) for n, c in enumerate(cells, 1)]
    checklist = read(make_checklist(rows))
    ns = "Not Started"
    assert [t.status for t in checklist.tasks] == [ns, ns, ns, "Completed", ns]
    assert checklist.unknown_status_rows == 4


@pytest.mark.parametrize(
    "cell, expected",
    [
        (datetime(2026, 3, 5, 14, 30), date(2026, 3, 5)),
        (datetime(2026, 3, 5), date(2026, 3, 5)),
        (date(2026, 3, 6), date(2026, 3, 6)),
        ("2026-03-05", date(2026, 3, 5)),
        (" 2026-03-05 ", date(2026, 3, 5)),
    ],
)
def test_us02_completed_date_cell_or_iso_text_is_a_date(
    make_checklist, make_row, cell, expected
):
    task = _only_task(make_checklist, make_row(1, "Invented", "Completed", cell))
    assert task.completion_date == expected
    assert type(task.completion_date) is date
    assert task.note == ""


@pytest.mark.parametrize("cell", ["05/03/2026", "soon", "2026-13-45"])
def test_us02_completed_with_other_text_date_is_unclear(make_checklist, make_row, cell):
    task = _only_task(make_checklist, make_row(1, "Invented", "Completed", cell))
    assert task.status == "Completed"
    assert task.completion_date is None
    assert task.note == UNCLEAR


@pytest.mark.parametrize("cell", [None, "", "   "])
def test_us02_completed_without_date_has_no_note(make_checklist, make_row, cell):
    task = _only_task(make_checklist, make_row(1, "Invented", "Completed", cell))
    assert task.completion_date is None
    assert task.note == ""


@pytest.mark.parametrize(
    "status", ["Not Started", "In Progress", "Not Applicable", "Done"]
)
@pytest.mark.parametrize("cell", [datetime(2026, 3, 5), "2026-03-05", "soon"])
def test_us02_completion_date_ignored_when_not_completed(
    make_checklist, make_row, status, cell
):
    task = _only_task(make_checklist, make_row(1, "Invented", status, cell))
    assert task.completion_date is None
    assert task.note == ""


def test_us02_owner_is_first_non_empty_owner_cell_trimmed(make_checklist, make_row):
    rows = [
        make_row(1, "a", owner=None),
        make_row(2, "b", owner="   "),
        make_row(3, "c", owner="  Test Person C  "),
        make_row(4, "d", owner="Test Person D"),
    ]
    assert read(make_checklist(rows)).owner == "Test Person C"


def test_us02_owner_empty_when_no_owner_cell_has_text(make_checklist, make_row):
    rows = [make_row(1, "a", owner=None), make_row(2, "b", owner="")]
    assert read(make_checklist(rows)).owner == ""


def test_us05_row_without_number_and_description_is_skipped_with_reason(
    make_checklist, make_row
):
    rows = [
        make_row(1, "Invented one"),
        make_row(None, None, status="Completed"),
        make_row("  ", "", deadline="On Roll On"),
        make_row(4, "Invented four"),
    ]
    checklist = read(make_checklist(rows))
    assert [t.row_number for t in checklist.tasks] == [2, 5]
    assert checklist.skipped_rows == (
        SkippedRow(row_number=3, reason=SKIP_REASON),
        SkippedRow(row_number=4, reason=SKIP_REASON),
    )


def test_us05_row_with_only_number_or_only_description_is_a_task(
    make_checklist, make_row
):
    rows = [make_row(None, "Only a description"), make_row(9, None)]
    checklist = read(make_checklist(rows))
    assert checklist.skipped_rows == ()
    assert [(t.number, t.description) for t in checklist.tasks] == [
        ("", "Only a description"),
        ("9", ""),
    ]


def test_us05_fully_blank_rows_are_ignored_and_keep_excel_row_numbers(
    make_checklist, make_row
):
    blank = [None] * 9
    spaces = ["  ", "", None, " ", None, None, "", None, None]
    rows = [make_row(1, "a"), blank, spaces, make_row(2, "b"), blank]
    checklist = read(make_checklist(rows))
    assert checklist.skipped_rows == ()
    assert [t.row_number for t in checklist.tasks] == [2, 5]


def test_us02_missing_required_headers_gives_no_tasks(make_checklist, make_row):
    header = [h for h in REQUIRED_HEADERS if h not in ("Deadline", "Role")]
    row = ["Test Person A", 1, "Invented", "Completed", None]
    checklist = read(
        make_checklist([row, [None, None, None, None, None]], header=header)
    )
    assert checklist.headers_missing == ("Role", "Deadline")
    assert checklist.tasks == ()
    assert checklist.skipped_rows == ()
    assert checklist.sheet_name == "Roll-In Checklist"


def test_us02_missing_headers_listed_in_required_order(make_checklist):
    checklist = read(make_checklist([], header=["Remarks (Tracker)"]))
    assert checklist.headers_missing == tuple(REQUIRED_HEADERS)
    assert checklist.tasks == ()


def test_us02_sheet_with_roll_in_name_is_read_over_first(make_xlsx, make_row):
    other = [HEADER, make_row(1, "Wrong sheet task")]
    chosen = [HEADER, make_row(1, "Right sheet task"), make_row(2, "Second")]
    checklist = read(make_xlsx([("Summary", other), ("my ROLLIN tasks", chosen)]))
    assert checklist.sheet_name == "my ROLLIN tasks"
    assert [t.description for t in checklist.tasks] == ["Right sheet task", "Second"]


def test_us02_no_matching_sheet_falls_back_to_first_sheet(make_xlsx, make_row):
    first = [HEADER, make_row(1, "First sheet task")]
    second = [HEADER, make_row(1, "Second sheet task")]
    checklist = read(make_xlsx([("Tasks", first), ("Other", second)]))
    assert checklist.sheet_name == "Tasks"
    assert [t.description for t in checklist.tasks] == ["First sheet task"]


def test_us02_unreadable_bytes_raise_unreadable_file():
    with pytest.raises(UnreadableFile):
        read(b"this is not an xlsx file")
