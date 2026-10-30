"""US-16, US-07: services/report_sections.py, the "Recent syncs" and "Data" report sections (slice 7a).

Counts only: skipped file names, reasons and joiner names never appear. Synthetic data in an in-memory Repo.
"""

from datetime import datetime, timedelta

import pytest
from joiner_fakes import joiner

from riro.core.models import SyncRun
from riro.services import report_sections
from riro.services.joiners import local_id
from riro.store.datafile import RESTORED_FROM_BACKUP, STARTED_EMPTY
from riro.store.repo import MAX_RUNS, Repo

DATA_TITLE = report_sections.DATA_TITLE
SYNCS_TITLE = report_sections.SYNCS_TITLE
data_lines = report_sections.data_lines
sync_run_lines = report_sections.sync_run_lines

T0 = datetime(2026, 10, 30, 9, 0, 5)
SKIPPED = (
    ("Synthetic Joiner A.xlsx", "zz synthetic reason one"),
    ("Synthetic Joiner B.xlsx", "zz synthetic reason two"),
)


def sync_run(at=T0, result="ok", files_read=12, updated=2, unchanged=10, skipped=()):
    return SyncRun(at, result, files_read, updated, unchanged, tuple(skipped))


def repo_with_runs(*runs):
    repo = Repo.in_memory()
    for item in runs:
        repo.add_run(item)
    return repo


def repo_with_joiners(*joiners):
    repo = Repo.in_memory()
    repo.apply([], T0, sync_run(), joiners=joiners)
    return repo


# --- titles ------------------------------------------------------------------------------------------------------


def test_us16_section_titles():
    assert SYNCS_TITLE == "Recent syncs (newest first):"
    assert DATA_TITLE == "Data:"


# --- recent syncs (US-07) ----------------------------------------------------------------------------------------


def test_us07_sync_run_line_format():
    repo = repo_with_runs(sync_run(skipped=SKIPPED[:1]))
    assert sync_run_lines(repo) == [
        "2026-10-30 09:00 ok: files read 12, updated 2, unchanged 10, skipped 1"
    ]


@pytest.mark.parametrize("result", ["ok", "partial", "failed"])
def test_us07_sync_run_line_shows_the_result(result):
    repo = repo_with_runs(sync_run(result=result, files_read=0, updated=0, unchanged=0))
    assert sync_run_lines(repo) == [
        f"2026-10-30 09:00 {result}: files read 0, updated 0, unchanged 0, skipped 0"
    ]


def test_us07_sync_runs_newest_first():
    repo = repo_with_runs(
        sync_run(at=datetime(2026, 10, 28, 8, 0), updated=1),
        sync_run(at=datetime(2026, 10, 29, 8, 0), updated=2),
        sync_run(at=datetime(2026, 10, 30, 8, 0), updated=3),
    )
    lines = sync_run_lines(repo)
    assert [line[:16] for line in lines] == [
        "2026-10-30 08:00",
        "2026-10-29 08:00",
        "2026-10-28 08:00",
    ]
    assert "updated 3" in lines[0]
    assert "updated 1" in lines[2]


def test_us07_sync_runs_at_most_limit_newest_kept():
    runs = [sync_run(at=T0 + timedelta(minutes=i)) for i in range(MAX_RUNS)]
    repo = repo_with_runs(*runs)
    lines = sync_run_lines(repo, limit=5)
    assert len(lines) == 5
    assert lines[0].startswith(f"{runs[-1].at:%Y-%m-%d %H:%M} ")
    assert lines[-1].startswith(f"{runs[-5].at:%Y-%m-%d %H:%M} ")


def test_us07_sync_runs_default_limit_is_twenty():
    runs = [sync_run(at=T0 + timedelta(minutes=i)) for i in range(MAX_RUNS + 5)]
    repo = repo_with_runs(*runs)
    lines = sync_run_lines(repo)
    assert len(lines) == 20
    assert lines[0].startswith(f"{runs[-1].at:%Y-%m-%d %H:%M} ")


def test_us07_no_runs_gives_no_lines():
    assert sync_run_lines(Repo.in_memory()) == []


def test_adr007_skipped_shows_a_count_never_a_file_name_or_reason():
    repo = repo_with_runs(sync_run(skipped=SKIPPED))
    text = "\n".join(sync_run_lines(repo))
    assert "skipped 2" in text
    for name, reason in SKIPPED:
        assert name not in text
        assert reason not in text
    assert "Synthetic" not in text
    assert ".xlsx" not in text
    assert "zz synthetic" not in text


# --- data counts -------------------------------------------------------------------------------------------------


def mixed_joiners():
    return (
        joiner("id-a", name="Synthetic Joiner A", roll_on=T0.date()),
        joiner("id-b", name="Synthetic Joiner B"),  # visible, waiting
        joiner(
            "id-c",
            file_id=local_id("synthetic joiner c"),
            name="Synthetic Joiner C",
            roll_on=T0.date(),
        ),  # visible, imported
        joiner("id-d", name="Synthetic Joiner D", hidden=True),  # hidden, waiting
        joiner(
            "id-e",
            file_id=local_id("synthetic joiner e"),
            name="Synthetic Joiner E",
            hidden=True,
            missing_syncs=2,
        ),  # hidden, imported
    )


def test_us16_data_counts_visible_waiting_hidden_imported():
    repo = repo_with_joiners(*mixed_joiners())
    assert data_lines(repo) == ["joiners 3, waiting 1, hidden 2, imported 1"]


def test_us16_data_counts_on_an_empty_repo():
    assert data_lines(Repo.in_memory()) == [
        "joiners 0, waiting 0, hidden 0, imported 0"
    ]


def test_adr007_data_lines_never_show_joiner_names_or_ids():
    repo = repo_with_joiners(*mixed_joiners())
    text = "\n".join(data_lines(repo, RESTORED_FROM_BACKUP))
    assert "Synthetic" not in text
    assert "id-" not in text
    assert "local-" not in text


@pytest.mark.parametrize("note", [RESTORED_FROM_BACKUP, STARTED_EMPTY])
def test_us16_known_load_note_is_shown(note):
    repo = repo_with_joiners(*mixed_joiners())
    assert data_lines(repo, note) == [
        "joiners 3, waiting 1, hidden 2, imported 1",
        f"data note: {note}",
    ]


@pytest.mark.parametrize(
    "note",
    [
        None,
        "",
        "Synthetic Joiner A",
        RESTORED_FROM_BACKUP + " Synthetic Joiner A",
        RESTORED_FROM_BACKUP.upper(),
    ],
)
def test_adr007_other_load_note_is_not_shown(note):
    repo = repo_with_joiners(*mixed_joiners())
    lines = data_lines(repo, note)
    assert lines == ["joiners 3, waiting 1, hidden 2, imported 1"]
    assert "Synthetic" not in "\n".join(lines)


def test_us16_data_note_defaults_to_none():
    assert data_lines(Repo.in_memory()) == data_lines(Repo.in_memory(), None)
