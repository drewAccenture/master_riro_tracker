"""ADR-005, US-02, US-03, US-10: match_joiners keeps each joiner (and its roll-on date) with the right file.

Pure function tests: FileRecords and Joiners built in code. A "sync" is one call; its joiners feed the next call.
"""

from joiner_fakes import D1, by_id, joiner, rec

from riro.core.models import Joiner
from riro.services.joiners import Match, match_joiners, normalize_owner


def test_adr005_normalize_owner_trims_lower_cases_and_makes_spaces_single():
    assert normalize_owner("  Test   Person\tA  ") == "test person a"
    assert normalize_owner("TEST PERSON A") == "test person a"
    assert normalize_owner("") == ""
    assert normalize_owner("   ") == ""


def test_us02_new_read_file_gives_a_new_waiting_joiner():
    match = match_joiners([rec("f1", owner="  Test  Person A ")], [])
    assert isinstance(match, Match)
    assert match.joiners == (
        Joiner("f1", "f1", "Test  Person A", "test person a", None, False, 0),
    )
    assert (match.warnings, match.moved, match.duplicates) == ((), 0, 0)


def test_us02_each_different_owner_is_one_joiner_sorted_by_id():
    records = [rec("f2", owner="Test Person B"), rec("f1", owner="Test Person A")]
    match = match_joiners(records, [])
    assert [(j.id, j.name) for j in match.joiners] == [
        ("f1", "Test Person A"),
        ("f2", "Test Person B"),
    ]
    assert isinstance(match.joiners, tuple)


def test_us02_never_read_file_has_no_joiner():
    match = match_joiners([rec("f1", read=False)], [])
    assert match.joiners == ()
    assert match.warnings == ()


def test_us02_absent_file_never_seen_as_joiner_gives_no_joiner():
    assert match_joiners([rec("f1", present=False)], []).joiners == ()


def test_us09_file_that_failed_to_read_now_but_has_old_data_keeps_its_joiner():
    stored = [joiner("f1", roll_on=D1)]
    record = rec("f1", problem="could not be read. It may be open")
    (only,) = match_joiners([record], stored).joiners
    assert (only.hidden, only.roll_on, only.missing_syncs) == (False, D1, 0)


def test_us02_empty_owner_uses_the_file_name_as_name_and_key():
    record = rec("f1", owner="   ", name="Synthetic Joiner C.xlsx")
    (only,) = match_joiners([record], []).joiners
    assert only.name == "Synthetic Joiner C"
    assert only.owner_key == "synthetic joiner c"


def test_adr005_empty_owner_key_drops_xlsx_in_any_case_and_normalizes():
    record = rec("f1", owner="", name="Synthetic  Joiner C.XLSX")
    (only,) = match_joiners([record], []).joiners
    assert only.owner_key == "synthetic joiner c"


def test_us03_owner_text_corrected_keeps_roll_on_and_takes_the_new_name():
    stored = [joiner("f1", name="Test Persn A", roll_on=D1)]
    match = match_joiners([rec("f1", owner="Test Person A")], stored)
    assert match.joiners == (
        Joiner("f1", "f1", "Test Person A", "test person a", D1, False, 0),
    )
    assert match.moved == 0


def test_us03_renamed_file_keeps_roll_on():
    stored = [joiner("f1", name="Synthetic Old Name", roll_on=D1)]
    record = rec("f1", owner="", name="Synthetic New Name.xlsx")
    (only,) = match_joiners([record], stored).joiners
    assert (only.id, only.file_id, only.roll_on) == ("f1", "f1", D1)
    assert (only.name, only.owner_key) == ("Synthetic New Name", "synthetic new name")


def test_us02_case_and_space_differences_in_owner_are_the_same_joiner():
    stored = [joiner("f1", name="Test Person A", roll_on=D1)]
    match = match_joiners([rec("f1", owner=" TEST   person a ")], stored)
    (only,) = match.joiners
    assert (only.id, only.roll_on, only.owner_key) == ("f1", D1, "test person a")


def test_us10_file_leaves_joiner_is_hidden_and_keeps_everything():
    stored = [joiner("f1", name="Test Person A", roll_on=D1)]
    match = match_joiners([rec("f1", present=False)], stored)
    assert match.joiners == (
        Joiner("f1", "f1", "Test Person A", "test person a", D1, True, 1),
    )
    again = match_joiners([rec("f1", present=False)], match.joiners)
    assert again.joiners == (
        Joiner("f1", "f1", "Test Person A", "test person a", D1, True, 2),
    )


def test_us10_file_comes_back_joiner_is_shown_with_its_roll_on():
    stored = [joiner("f1", roll_on=D1, hidden=True, missing_syncs=5)]
    (only,) = match_joiners([rec("f1")], stored).joiners
    assert (only.hidden, only.missing_syncs, only.roll_on) == (False, 0, D1)


def test_adr005_reupload_in_the_same_sync_moves_the_joiner_to_the_new_file():
    stored = [joiner("f1", roll_on=D1)]
    records = [rec("f1", present=False), rec("f2")]
    match = match_joiners(records, stored)
    assert match.joiners == (
        Joiner("f1", "f2", "Test Person A", "test person a", D1, False, 0),
    )
    assert match.moved == 1
    assert match.duplicates == 0


def test_adr005_reupload_in_the_next_sync_moves_the_joiner_to_the_new_file():
    first = match_joiners([rec("f1", present=False)], [joiner("f1", roll_on=D1)])
    assert first.moved == 0
    second = match_joiners([rec("f1", present=False), rec("f2")], first.joiners)
    assert second.joiners == (
        Joiner("f1", "f2", "Test Person A", "test person a", D1, False, 0),
    )
    assert second.moved == 1


def test_adr005_reupload_matches_owner_with_case_and_space_differences():
    stored = [joiner("f1", name="Test Person A", roll_on=D1)]
    records = [rec("f1", present=False), rec("f2", owner="test  PERSON a")]
    (only,) = match_joiners(records, stored).joiners
    assert (only.id, only.file_id, only.roll_on) == ("f1", "f2", D1)


def test_adr005_reupload_two_syncs_later_is_a_new_waiting_joiner():
    joiners = [joiner("f1", roll_on=D1)]
    for _ in range(2):  # gone in sync 1 and sync 2
        joiners = match_joiners([rec("f1", present=False)], joiners).joiners
    assert by_id(joiners, "f1").missing_syncs == 2
    match = match_joiners([rec("f1", present=False), rec("f2")], joiners)
    assert match.moved == 0
    assert match.joiners == (
        Joiner("f1", "f1", "Test Person A", "test person a", D1, True, 3),
        Joiner("f2", "f2", "Test Person A", "test person a", None, False, 0),
    )


def test_adr005_reupload_needs_the_same_owner():
    stored = [joiner("f1", name="Test Person A", roll_on=D1)]
    match = match_joiners(
        [rec("f1", present=False), rec("f2", owner="Test Person B")], stored
    )
    assert match.moved == 0
    assert by_id(match.joiners, "f1").hidden is True
    assert by_id(match.joiners, "f2").roll_on is None


def test_adr005_reupload_with_several_candidates_prefers_the_one_with_a_date():
    stored = [
        joiner("j-b", file_id="f-b", roll_on=None),
        joiner("j-c", file_id="f-c", roll_on=D1),
    ]
    records = [rec("f-b", present=False), rec("f-c", present=False), rec("f-new")]
    match = match_joiners(records, stored)
    assert match.moved == 1
    assert by_id(match.joiners, "j-c").file_id == "f-new"
    assert by_id(match.joiners, "j-c").hidden is False
    loser = by_id(match.joiners, "j-b")
    assert (loser.hidden, loser.missing_syncs, loser.file_id) == (True, 1, "f-b")
    assert [j.id for j in match.joiners] == ["j-b", "j-c"]


def test_adr005_reupload_with_several_undated_candidates_takes_the_smallest_id():
    stored = [joiner("j-c", file_id="f-c"), joiner("j-b", file_id="f-b")]
    records = [rec("f-b", present=False), rec("f-c", present=False), rec("f-new")]
    match = match_joiners(records, stored)
    assert by_id(match.joiners, "j-b").file_id == "f-new"
    assert by_id(match.joiners, "j-c").hidden is True


def test_adr005_reupload_skips_a_candidate_outside_the_window():
    stored = [
        joiner("j-b", file_id="f-b", roll_on=D1, hidden=True, missing_syncs=2),
        joiner("j-c", file_id="f-c", roll_on=None, hidden=True, missing_syncs=1),
    ]
    records = [rec("f-b", present=False), rec("f-c", present=False), rec("f-new")]
    match = match_joiners(records, stored)
    assert by_id(match.joiners, "j-c").file_id == "f-new"
    assert by_id(match.joiners, "j-b").missing_syncs == 3


def test_us10_match_never_changes_or_drops_a_roll_on():
    stored = [
        joiner("f1", name="Test Person A", roll_on=D1),
        joiner("f2", name="Test Person B", roll_on=None),
    ]
    records = [rec("f1", owner="Test Person A2"), rec("f2", present=False)]
    match = match_joiners(records, stored)
    assert [(j.id, j.roll_on) for j in match.joiners] == [("f1", D1), ("f2", None)]
