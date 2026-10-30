"""US-03, US-10, ADR-004, ADR-005: the joiners section of the data file (Repo.joiners, apply(..., joiners), set_roll_on)."""

import json

import pytest
from joiner_fakes import D1, D2, T1, joiner, rec, run

from riro.store.datafile import RESTORED_FROM_BACKUP, DataFile, MemoryDataFile
from riro.store.repo import Repo, check_layout


class CountingDataFile:
    def __init__(self):
        self.inner = MemoryDataFile()
        self.saves = 0

    def load(self):
        return self.inner.load()

    def save(self, data):
        self.saves += 1
        self.inner.save(data)


def test_us03_empty_repo_has_no_joiners():
    assert Repo.in_memory().joiners() == ()


def test_us03_apply_with_joiners_stores_them_sorted_by_id():
    repo = Repo.in_memory()
    joiners = [joiner("j-c"), joiner("j-a", hidden=True, missing_syncs=2)]
    repo.apply([rec("j-a"), rec("j-c")], T1, run(), joiners=joiners)
    assert repo.joiners() == (
        joiner("j-a", hidden=True, missing_syncs=2),
        joiner("j-c"),
    )
    assert isinstance(repo.joiners(), tuple)


def test_us03_apply_with_new_joiners_keeps_their_given_roll_on():
    repo = Repo.in_memory()
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a", roll_on=D1)])
    assert repo.joiners() == (joiner("j-a", roll_on=D1),)


def test_adr004_apply_with_joiners_is_still_one_save():
    datafile = CountingDataFile()
    repo = Repo(datafile)
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a")])
    assert datafile.saves == 1


def test_us03_apply_without_joiners_leaves_the_joiners_alone():
    repo = Repo.in_memory()
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a", roll_on=D1)])
    repo.apply([rec("j-a", owner="Test Person Z")], T1, run())
    assert repo.joiners() == (joiner("j-a", roll_on=D1),)


def test_us03_apply_replaces_joiner_fields_from_the_match():
    repo = Repo.in_memory()
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a")])
    moved = joiner(
        "j-a", file_id="f-new", name="Test Person Z", hidden=True, missing_syncs=1
    )
    repo.apply([rec("f-new")], T1, run(), joiners=[moved])
    assert repo.joiners() == (moved,)


def test_us03_set_roll_on_saves_once_and_keeps_the_rest():
    datafile = CountingDataFile()
    repo = Repo(datafile)
    repo.apply(
        [rec("j-a"), rec("j-b")], T1, run(), joiners=[joiner("j-a"), joiner("j-b")]
    )
    repo.set_roll_on("j-a", D1)
    assert datafile.saves == 2
    assert repo.joiners() == (joiner("j-a", roll_on=D1), joiner("j-b"))
    assert [r.id for r in repo.files()] == ["j-a", "j-b"]
    assert repo.last_success() == T1
    assert len(repo.runs()) == 1


def test_us03_set_roll_on_can_change_a_date():
    repo = Repo.in_memory()
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a", roll_on=D1)])
    repo.set_roll_on("j-a", D2)
    assert repo.joiners()[0].roll_on == D2


def test_us03_set_roll_on_unknown_id_raises_key_error_and_saves_nothing():
    datafile = CountingDataFile()
    repo = Repo(datafile)
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a")])
    with pytest.raises(KeyError):
        repo.set_roll_on("no-such-id", D1)
    assert datafile.saves == 1
    assert repo.joiners() == (joiner("j-a"),)


def test_us03_a_date_set_during_a_sync_is_not_lost_by_its_apply():
    # The sync matched joiners while the date was still None (or D1); then the PMO set a date; then apply.
    repo = Repo.in_memory()
    repo.apply(
        [rec("j-a"), rec("j-b")],
        T1,
        run(),
        joiners=[joiner("j-a"), joiner("j-b", roll_on=D1)],
    )
    matched = [
        joiner("j-a", name="Test Person A2"),
        joiner("j-b", roll_on=D1, hidden=True, missing_syncs=1),
    ]
    repo.set_roll_on("j-a", D1)
    repo.set_roll_on("j-b", D2)
    repo.apply([rec("j-a"), rec("j-b", present=False)], T1, run(), joiners=matched)
    assert repo.joiners() == (
        joiner("j-a", name="Test Person A2", roll_on=D1),
        joiner("j-b", roll_on=D2, hidden=True, missing_syncs=1),
    )


def test_us03_joiners_round_trip_through_the_data_file(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    stored = [
        joiner("j-a", file_id="f-new", name="Test Person A", roll_on=D1),
        joiner("j-b", name="Test Person B", hidden=True, missing_syncs=3),
    ]
    repo = Repo(DataFile(path, validate=check_layout))
    repo.apply([rec("f-new"), rec("j-b", present=False)], T1, run(), joiners=stored)
    repo.set_roll_on("j-b", D2)
    again = Repo(DataFile(path, validate=check_layout))
    assert again.load_note is None
    assert again.joiners() == (
        joiner("j-a", file_id="f-new", name="Test Person A", roll_on=D1),
        joiner("j-b", name="Test Person B", roll_on=D2, hidden=True, missing_syncs=3),
    )


def _break_joiners(section):
    """Replace every stored joiner with one that has the wrong layout, whatever the section's own shape."""
    if isinstance(section, dict):
        return {key: {"name": "only a name"} for key in section}
    return [{"name": "only a name"} for _ in section]


def test_adr004_wrong_joiner_layout_loads_the_backup(tmp_path):
    path = tmp_path / "data" / "tracker.json"
    repo = Repo(DataFile(path, validate=check_layout))
    repo.apply([rec("j-a")], T1, run(), joiners=[joiner("j-a")])
    repo.set_roll_on("j-a", D1)  # .bak now holds the first save
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "joiners" in data
    data["joiners"] = _break_joiners(data["joiners"])
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = Repo(DataFile(path, validate=check_layout))
    assert restored.load_note == RESTORED_FROM_BACKUP
    assert restored.joiners() == (joiner("j-a"),)


def test_adr004_check_layout_accepts_a_file_without_joiners():
    check_layout({"schema_version": 1})
