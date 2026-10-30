"""US-07, US-09, US-10, ADR-004: store/repo.py keeps file records, the last successful sync and the last runs."""

import os
from dataclasses import replace
from datetime import date, datetime

import pytest

from riro.core.models import Checklist, FileRecord, SkippedRow, SyncRun, Task
from riro.store.datafile import (
    RESTORED_FROM_BACKUP,
    DataFile,
    MemoryDataFile,
    SaveFailed,
)
from riro.store.repo import MAX_RUNS, Repo

T1 = datetime(2026, 10, 29, 9, 0, 0)
T2 = datetime(2026, 10, 29, 9, 5, 30)

CHECKLIST = Checklist(
    sheet_name="Roll-In Checklist",
    owner="Test Person A",
    tasks=(
        Task(
            row_number=2,
            number="1",
            role="PMO",
            description="Invented task one",
            deadline="On Roll On",
            status="Completed",
            completion_date=date(2026, 10, 21),
            assigned_id="test.person.a",
            remarks="synthetic remark",
        ),
        Task(
            row_number=3,
            number="2",
            role="PMO",
            description="Invented task two",
            deadline="1 days After Roll On",
            status="Not Started",
            completion_date=None,
        ),
        Task(
            row_number=4,
            number="3",
            role="PMO",
            description="Invented task three",
            deadline="On Roll On",
            status="Completed",
            completion_date=None,
            note="completion date unclear",
        ),
    ),
    skipped_rows=(SkippedRow(5, "no task number or description"),),
    headers_missing=(),
    unknown_status_rows=1,
)


def record(file_id, **changes):
    base = FileRecord(
        id=file_id,
        name=f"Synthetic Joiner {file_id}.xlsx",
        etag=f"e-{file_id}",
        modified="2026-10-20T08:00:00Z",
        present=True,
        checklist=CHECKLIST,
        read_at=T1,
        problem=None,
    )
    return replace(base, **changes)


def run(at=T1, result="ok", **changes):
    base = SyncRun(
        at=at, result=result, files_read=1, updated=1, unchanged=0, skipped=()
    )
    return replace(base, **changes)


class CountingDataFile:
    def __init__(self):
        self.inner = MemoryDataFile()
        self.loads = 0
        self.saves = 0

    def load(self):
        self.loads += 1
        return self.inner.load()

    def save(self, data):
        self.saves += 1
        self.inner.save(data)


class Refusing:
    """os.replace that refuses while `on` is True."""

    def __init__(self):
        self.on = False

    def __call__(self, src, dst):
        if self.on:
            raise PermissionError("synthetic: file in use")
        os.replace(src, dst)


def test_adr004_max_runs_is_20():
    assert MAX_RUNS == 20


def test_us07_empty_repo_has_nothing():
    repo = Repo.in_memory()
    assert repo.files() == ()
    assert repo.file("missing") is None
    assert repo.last_success() is None
    assert repo.runs() == ()
    assert repo.load_note is None


def test_adr004_repo_loads_at_once_and_apply_saves_once():
    datafile = CountingDataFile()
    repo = Repo(datafile)
    assert datafile.loads == 1
    repo.apply([record("a"), record("b")], T1, run())
    assert datafile.saves == 1


def test_us07_apply_stores_records_last_success_and_run():
    repo = Repo.in_memory()
    repo.apply([record("a")], T1, run(T1))
    assert repo.file("a") == record("a")
    assert repo.last_success() == T1
    assert repo.runs() == (run(T1),)


def test_us07_files_are_sorted_by_id():
    repo = Repo.in_memory()
    repo.apply([record("c"), record("a"), record("b")], T1, run())
    assert [r.id for r in repo.files()] == ["a", "b", "c"]
    assert isinstance(repo.files(), tuple)


def test_us09_apply_replaces_same_id_and_keeps_others():
    repo = Repo.in_memory()
    repo.apply([record("a"), record("b")], T1, run(T1))
    newer_b = record("b", etag="e-b-2", problem="synthetic reason")
    repo.apply([newer_b], T2, run(T2))
    assert repo.file("a") == record("a")
    assert repo.file("b") == newer_b
    assert repo.last_success() == T2


def test_us10_hidden_file_record_is_kept():
    repo = Repo.in_memory()
    repo.apply([record("a", present=False)], T1, run())
    assert repo.file("a").present is False
    assert repo.file("a").checklist == CHECKLIST


def test_us07_add_run_keeps_files_and_last_success():
    repo = Repo.in_memory()
    repo.apply([record("a")], T1, run(T1))
    repo.add_run(run(T2, "failed", files_read=0, updated=0))
    assert repo.file("a") == record("a")
    assert repo.last_success() == T1
    assert [r.result for r in repo.runs()] == ["ok", "failed"]


def test_us07_runs_are_oldest_first_and_at_most_20():
    repo = Repo.in_memory()
    runs = [
        run(datetime(2026, 10, 29, 9, minute), files_read=minute)
        for minute in range(25)
    ]
    for r in runs:
        repo.add_run(r)
    assert repo.runs() == tuple(runs[5:])
    assert len(repo.runs()) == MAX_RUNS


def test_us07_apply_also_drops_runs_over_20():
    repo = Repo.in_memory()
    for minute in range(MAX_RUNS):
        repo.add_run(run(datetime(2026, 10, 29, 8, minute)))
    repo.apply([record("a")], T2, run(T2, "partial"))
    assert len(repo.runs()) == MAX_RUNS
    assert repo.runs()[-1] == run(T2, "partial")
    assert repo.runs()[0].at == datetime(2026, 10, 29, 8, 1)


def test_adr004_round_trip_through_the_data_file(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    never_read = record(
        "b", etag="", checklist=None, read_at=None, problem="synthetic reason b"
    )
    kept = record("c", present=False, problem="synthetic reason c", read_at=T2)
    partial = run(
        T2,
        "partial",
        files_read=2,
        updated=1,
        unchanged=1,
        skipped=(("Synthetic Joiner B.xlsx", "synthetic reason b"),),
    )
    repo = Repo(DataFile(path))
    repo.apply([record("a"), never_read, kept], T2, partial)
    repo.add_run(run(T2, "failed", files_read=0, updated=0))

    again = Repo(DataFile(path))
    assert again.files() == (record("a"), never_read, kept)
    assert again.file("a").checklist == CHECKLIST
    assert again.last_success() == T2
    assert again.runs() == repo.runs()
    assert again.runs()[0] == partial
    assert again.load_note is None


def test_adr004_load_note_comes_from_the_data_file(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    repo = Repo(DataFile(path))
    repo.apply([record("a")], T1, run(T1))
    repo.apply([record("b")], T2, run(T2))  # .bak holds the first save
    path.write_bytes(b"{broken synthetic")
    restored = Repo(DataFile(path))
    assert restored.load_note == RESTORED_FROM_BACKUP
    assert restored.file("a") == record("a")
    assert restored.last_success() == T1


def test_adr004_save_failed_propagates_and_memory_is_unchanged(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    refusing = Refusing()
    repo = Repo(DataFile(path, replace=refusing, sleep=lambda s: None))
    repo.apply([record("a")], T1, run(T1))
    refusing.on = True
    with pytest.raises(SaveFailed):
        repo.apply([record("a", etag="e-a-2"), record("b")], T2, run(T2))
    assert repo.files() == (record("a"),)
    assert repo.last_success() == T1
    assert repo.runs() == (run(T1),)
    with pytest.raises(SaveFailed):
        repo.add_run(run(T2, "failed"))
    refusing.on = False
    assert Repo(DataFile(path)).files() == (record("a"),)
