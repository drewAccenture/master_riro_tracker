"""US-11 (plan slice 5, section 3.3): the optional "Guidelines" column becomes Task.guidelines, kept by the store.

Rows expand to "Full task" and "Guidelines". Synthetic data only, invented names.
"""

import dataclasses
import json
from datetime import date, datetime

from riro.core.checklist import OPTIONAL_HEADERS, REQUIRED_HEADERS, check_headers, read
from riro.core.models import Checklist, FileRecord, SyncRun, Task
from riro.store import codec
from riro.store.datafile import SCHEMA_VERSION, DataFile
from riro.store.repo import Repo

T1 = datetime(2026, 10, 29, 9, 0, 0)

# Same layout as task_row in tests/conftest.py. Not imported: `from conftest import` picks tests/connector/conftest.py
# when the whole suite runs.
CHECKLIST_HEADER = [*REQUIRED_HEADERS, "Assigned Enterprise Id", "Remarks (Tracker)"]


def task_row(number, description):
    return [
        "Test Person A",
        "PMO",
        number,
        description,
        "Not Started",
        None,
        "On Roll On",
        "",
        "",
    ]


def _with_guidelines(header_text="Guidelines", values=()):
    header = list(CHECKLIST_HEADER) + [header_text]
    rows = [
        task_row(n, f"Invented task {n}") + [value] for n, value in enumerate(values, 1)
    ]
    return header, rows


def test_us11_guidelines_is_an_optional_header():
    assert "Guidelines" in OPTIONAL_HEADERS
    assert "Guidelines" not in REQUIRED_HEADERS


def test_us11_task_guidelines_is_the_last_field_and_defaults_to_empty():
    assert dataclasses.fields(Task)[-1].name == "guidelines"
    task = Task(2, "1", "PMO", "Invented task", "On Roll On", "Not Started", None)
    assert task.guidelines == ""


def test_us11_guidelines_column_is_read_into_each_task(make_checklist):
    header, rows = _with_guidelines(
        values=["Invented guideline one", "Line one\nLine two"]
    )
    checklist = read(make_checklist(rows, header=header))
    assert [t.guidelines for t in checklist.tasks] == [
        "Invented guideline one",
        "Line one\nLine two",
    ]


def test_us11_guidelines_text_is_trimmed_and_empty_cell_is_empty(make_checklist):
    header, rows = _with_guidelines(values=["  Invented guideline  \n", None, "   "])
    checklist = read(make_checklist(rows, header=header))
    assert [t.guidelines for t in checklist.tasks] == ["Invented guideline", "", ""]


def test_us11_guidelines_header_matches_any_case_and_spaces(make_checklist):
    header, rows = _with_guidelines(" GUIDELINES ", values=["Invented guideline"])
    checklist = read(make_checklist(rows, header=header))
    assert checklist.tasks[0].guidelines == "Invented guideline"


def test_us11_missing_guidelines_column_gives_empty_text(make_checklist):
    checklist = read(make_checklist([task_row(1, "Invented task 1")]))
    assert checklist.headers_missing == ()
    assert checklist.tasks[0].guidelines == ""


def test_us11_check_headers_finds_guidelines_and_never_reports_it_missing(make_xlsx):
    header, rows = _with_guidelines(values=["Invented guideline"])
    report = check_headers(make_xlsx([("Roll-In Checklist", [header] + rows)]))
    assert "Guidelines" in report.headers_found
    assert report.headers_missing == ()
    without = check_headers(
        make_xlsx([("Roll-In Checklist", [list(REQUIRED_HEADERS)])])
    )
    assert "Guidelines" not in without.headers_found
    assert "Guidelines" not in without.headers_missing


# --- store ---------------------------------------------------------------------------------------------------------


def _record(tasks):
    checklist = Checklist("Roll-In Checklist", "Test Person A", tuple(tasks), (), (), 0)
    return FileRecord(
        "f-a", "Synthetic A.xlsx", "e-a", "2026-10-20", True, checklist, T1, None
    )


def _run():
    return SyncRun(T1, "ok", 1, 1, 0, ())


def test_us11_guidelines_round_trip_through_the_data_file(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    task = Task(
        2,
        "1",
        "PMO",
        "Invented task",
        "On Roll On",
        "Completed",
        date(2026, 11, 2),
        guidelines="Invented guideline\nsecond line",
    )
    Repo(DataFile(path)).apply([_record([task])], T1, _run())
    again = Repo(DataFile(path))
    assert again.file("f-a").checklist.tasks[0].guidelines == (
        "Invented guideline\nsecond line"
    )
    assert again.file("f-a").checklist.tasks[0] == task


def test_us11_stored_task_without_guidelines_key_loads_as_empty(tmp_path):
    path = tmp_path / "tracker.json"
    task = Task(2, "1", "PMO", "Invented task", "On Roll On", "Not Started", None)
    stored = codec.record_out(_record([task]))
    for row in stored["checklist"]["tasks"]:
        row.pop("guidelines", None)  # data saved before slice 5
    data = {"schema_version": SCHEMA_VERSION, "files": {"f-a": stored}}
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = Repo(DataFile(path)).file("f-a")
    assert loaded is not None
    assert loaded.checklist.tasks[0].guidelines == ""
    assert loaded.checklist.tasks[0].description == "Invented task"
