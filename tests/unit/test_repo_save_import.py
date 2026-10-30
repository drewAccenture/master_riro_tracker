"""US-13, ADR-004, ADR-005: Repo.save_import (one save, not a sync) and sync_apply.retire_replaced (pure).

Synthetic records and joiners only.
"""

from dataclasses import replace

import pytest
from import_fakes import SwitchDataFile
from joiner_fakes import D1, D2, T1, by_id, joiner, rec, run

from riro.services.local_import import local_id
from riro.services.sync_apply import retire_replaced
from riro.store.datafile import SaveFailed
from riro.store.repo import Repo

LOCAL_A = local_id("test person a")
LOCAL_B = local_id("test person b")


def stored_repo():
    datafile = SwitchDataFile()
    repo = Repo(datafile)
    repo.apply(
        [rec("id-c", owner="Test Person C")],
        T1,
        run(),
        joiners=[joiner("id-c", name="Test Person C")],
    )
    return repo, datafile


def test_us13_save_import_writes_records_and_joiners_in_one_save():
    repo, datafile = stored_repo()
    saves = datafile.saves
    local = rec(LOCAL_A, owner="Test Person A")
    joiners = [
        joiner("id-c", name="Test Person C"),
        joiner(LOCAL_A, name="Test Person A"),
    ]
    repo.save_import([local], joiners)
    assert datafile.saves == saves + 1
    assert repo.file(LOCAL_A) == local
    assert repo.file("id-c") == rec(
        "id-c", owner="Test Person C"
    )  # other records untouched
    assert [j.id for j in repo.joiners()] == sorted(["id-c", LOCAL_A])


def test_us13_save_import_does_not_touch_last_success_or_sync_runs():
    repo, _ = stored_repo()
    before = (repo.last_success(), repo.runs())
    repo.save_import(
        [rec(LOCAL_A)], [joiner("id-c", name="Test Person C"), joiner(LOCAL_A)]
    )
    assert (repo.last_success(), repo.runs()) == before


def test_us13_save_import_on_an_empty_store_leaves_never_synced():
    repo = Repo.in_memory()
    repo.save_import([rec(LOCAL_A)], [joiner(LOCAL_A)])
    assert (repo.last_success(), repo.runs()) == (None, ())
    assert [j.id for j in repo.joiners()] == [LOCAL_A]


def test_us03_save_import_keeps_a_stored_roll_on_date():
    repo, _ = stored_repo()
    repo.set_roll_on("id-c", D1)
    repo.save_import([], [joiner("id-c", name="Test Person C", roll_on=None)])
    assert by_id(repo.joiners(), "id-c").roll_on == D1
    repo.save_import([], [joiner("id-c", name="Test Person C", roll_on=D2)])
    assert (
        by_id(repo.joiners(), "id-c").roll_on == D1
    )  # only set_roll_on changes a date


def test_us13_save_import_replaces_the_joiners_section():
    repo, _ = stored_repo()
    hidden = joiner("id-c", name="Test Person C", hidden=True, missing_syncs=1)
    repo.save_import([rec(LOCAL_A)], [hidden, joiner(LOCAL_A)])
    assert by_id(repo.joiners(), "id-c") == hidden
    assert by_id(repo.joiners(), LOCAL_A) == joiner(LOCAL_A)


def test_adr004_save_import_that_fails_changes_nothing():
    repo, datafile = stored_repo()
    before = (repo.files(), repo.joiners(), repo.last_success(), repo.runs())
    datafile.fail = True
    with pytest.raises(SaveFailed):
        repo.save_import([rec(LOCAL_A)], [joiner(LOCAL_A)])
    assert (repo.files(), repo.joiners(), repo.last_success(), repo.runs()) == before


# --- retire_replaced (pure) -----------------------------------------------------------------------------------


def test_adr005_local_record_with_a_present_sharepoint_owner_is_retired():
    local = rec(LOCAL_A, owner="Test Person A")
    sharepoint = rec("id-a", owner="  TEST person a")
    result = retire_replaced([local, sharepoint])
    assert result == (replace(local, present=False), sharepoint)
    assert isinstance(result, tuple)


def test_adr005_retire_replaced_keeps_everything_else_and_the_order():
    records = [
        rec("id-x", owner="Test Person X"),
        rec(LOCAL_B, owner="Test Person B"),  # no SharePoint twin: stays
        rec(LOCAL_A, owner="Test Person A"),  # replaced
        rec("id-a", owner="Test Person A"),
        rec("id-y", owner="Test Person Y", present=False),
    ]
    result = retire_replaced(records)
    assert [r.id for r in result] == [r.id for r in records]
    assert [r.present for r in result] == [True, True, False, True, False]
    assert (
        result[0] == records[0]
        and result[1] == records[1]
        and result[3:] == tuple(records[3:])
    )


def test_adr005_sharepoint_file_that_left_does_not_retire_the_import():
    records = [
        rec(LOCAL_A, owner="Test Person A"),
        rec("id-a", owner="Test Person A", present=False),
    ]
    assert retire_replaced(records) == tuple(records)


def test_adr005_never_read_sharepoint_file_does_not_retire_the_import():
    records = [
        rec(LOCAL_A, owner="Test Person A"),
        rec("id-a", read=False, problem="x"),
    ]
    assert retire_replaced(records) == tuple(records)


def test_adr005_sharepoint_record_is_never_retired_by_a_local_one():
    records = [
        rec("id-a", owner="Test Person A"),
        rec("id-b", owner="test person a"),
        rec(LOCAL_A, owner="Test Person A"),
    ]
    result = retire_replaced(records)
    assert result[:2] == tuple(
        records[:2]
    )  # two SharePoint files with one owner stay a US-02 duplicate
    assert result[2].present is False


def test_adr005_empty_owner_import_is_matched_by_file_name_key():
    local = rec(
        local_id("synthetic joiner x"), owner="", name="Synthetic Joiner X.xlsx"
    )
    sharepoint = rec("id-x", owner="Synthetic Joiner X")
    assert retire_replaced([local, sharepoint])[0].present is False
