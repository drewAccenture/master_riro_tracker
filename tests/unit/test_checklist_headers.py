"""Architecture section 10 (slice 1): header check on synthetic .xlsx bytes.

Rules from docs/requirements.md section 3: sheet = first whose name contains "roll-in" or "rollin" (any case),
else the first sheet. Row 1 holds the headers, matched in any letter case.
"""

import dataclasses

import pytest

from riro.core.checklist import check_headers
from riro.core.models import HeaderReport

REQUIRED = (
    "Checklist Owner",
    "Role",
    "Task Number",
    "Description",
    "Completion Status",
    "Completion Date",
    "Deadline",
)
OPTIONAL = ("Assigned Enterprise Id", "Remarks (Tracker)")
OTHER_SHEET = [["Unrelated"], ["x"]]


def _rows(headers, n=2):
    return [list(headers)] + [
        [f"v{r}{c}" for c in range(len(headers))] for r in range(n)
    ]


def test_arch10_returns_frozen_header_report(make_xlsx):
    report = check_headers(make_xlsx([("Roll-In Checklist", _rows(REQUIRED))]))
    assert isinstance(report, HeaderReport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.row_count = 99


@pytest.mark.parametrize(
    "sheet_name",
    ["Roll-In Checklist", "ROLL-IN", "my rollin tasks", "RollIn"],
)
def test_arch10_sheet_with_roll_in_in_name_is_chosen_over_first(make_xlsx, sheet_name):
    data = make_xlsx([("Summary", OTHER_SHEET), (sheet_name, _rows(REQUIRED))])
    report = check_headers(data)
    assert report.sheet_name == sheet_name
    assert report.sheet_matched is True
    assert report.headers_missing == ()


def test_arch10_first_matching_sheet_wins_when_two_match(make_xlsx):
    data = make_xlsx(
        [
            ("Summary", OTHER_SHEET),
            ("Roll-In A", _rows(REQUIRED, n=1)),
            ("rollin B", _rows(REQUIRED, n=4)),
        ]
    )
    report = check_headers(data)
    assert report.sheet_name == "Roll-In A"
    assert report.row_count == 1


def test_arch10_no_matching_sheet_falls_back_to_first_sheet(make_xlsx):
    data = make_xlsx([("Tasks", _rows(REQUIRED, n=3)), ("Other", OTHER_SHEET)])
    report = check_headers(data)
    assert report.sheet_name == "Tasks"
    assert report.sheet_matched is False
    assert report.row_count == 3


def test_arch10_headers_match_any_case_and_surrounding_spaces(make_xlsx):
    messy = [
        "  checklist owner ",
        "ROLE",
        "task number",
        " Description",
        "COMPLETION status",
    ]
    messy += [
        "completion DATE  ",
        "deadline",
        " assigned enterprise ID ",
        "REMARKS (TRACKER)",
    ]
    report = check_headers(make_xlsx([("Roll-In", _rows(messy))]))
    assert report.headers_missing == ()
    assert set(report.headers_found) == set(REQUIRED) | set(OPTIONAL)
    assert len(report.headers_found) == len(REQUIRED) + len(OPTIONAL)


def test_arch10_missing_required_headers_are_listed(make_xlsx):
    headers = [h for h in REQUIRED if h not in ("Role", "Deadline")]
    report = check_headers(make_xlsx([("Roll-In", _rows(headers))]))
    assert set(report.headers_missing) == {"Role", "Deadline"}
    assert "Role" not in report.headers_found
    assert "Deadline" not in report.headers_found


def test_arch10_missing_optional_headers_are_not_reported_missing(make_xlsx):
    report = check_headers(make_xlsx([("Roll-In", _rows(REQUIRED))]))
    assert report.headers_missing == ()
    assert set(report.headers_found) == set(REQUIRED)


def test_arch10_unknown_headers_are_not_in_found(make_xlsx):
    report = check_headers(make_xlsx([("Roll-In", _rows(list(REQUIRED) + ["Notes"]))]))
    assert "Notes" not in report.headers_found
    assert set(report.headers_found) == set(REQUIRED)


def test_arch10_row_count_skips_empty_rows(make_xlsx):
    empty = [None] * len(REQUIRED)
    rows = _rows(REQUIRED, n=2) + [empty] + _rows(REQUIRED, n=3)[1:] + [empty, empty]
    report = check_headers(make_xlsx([("Roll-In", rows)]))
    assert report.row_count == 5


def test_arch10_row_count_zero_when_only_header_row(make_xlsx):
    report = check_headers(make_xlsx([("Roll-In", [list(REQUIRED)])]))
    assert report.row_count == 0


def test_arch10_distinct_deadline_and_status_values_with_counts(make_xlsx):
    # Deadline and Completion Status placed out of the usual order: values are read by header position.
    headers = ["Deadline", "Checklist Owner", "Role", "Task Number", "Description"]
    headers += ["Completion Date", "Completion Status"]
    rows = [
        headers,
        ["10 days Before Roll On", "Test Person A", "PMO", 1, "t1", None, "Completed"],
        [" On Roll On ", "Test Person A", "PMO", 2, "t2", None, "Not Started"],
        ["On Roll On", "Test Person A", "PMO", 3, "t3", None, " Completed "],
        [
            "10 days Before Roll On",
            "Test Person A",
            "PMO",
            4,
            "t4",
            None,
            "In Progress",
        ],
        [None, "Test Person A", "PMO", 5, "t5", None, None],
        ["", "Test Person A", "PMO", 6, "t6", None, ""],
    ]
    report = check_headers(make_xlsx([("Roll-In", rows)]))
    assert report.deadline_counts == {"10 days Before Roll On": 2, "On Roll On": 2}
    assert report.status_counts == {"Completed": 2, "Not Started": 1, "In Progress": 1}
    assert report.row_count == 6
