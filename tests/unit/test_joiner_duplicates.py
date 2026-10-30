"""US-02, ADR-005: two files with the same Checklist Owner are one joiner on the newest file, with a warning."""

from joiner_fakes import D1, D2, by_id, joiner, rec

from riro.core.models import Joiner
from riro.services.joiners import duplicate_warning, match_joiners

OLD = "2026-10-21T08:00:00Z"
NEW = "2026-10-22T08:00:00Z"


def test_us02_duplicate_warning_text_names_both_files():
    assert duplicate_warning("Synthetic A.xlsx", "Synthetic B.xlsx") == (
        "Two files have the same Checklist Owner: Synthetic A.xlsx and Synthetic B.xlsx."
        " Using Synthetic B.xlsx."
    )


def test_us02_two_new_files_same_owner_are_one_joiner_on_the_newest_file():
    records = [
        rec("f1", name="Synthetic A.xlsx", modified=OLD),
        rec("f2", name="Synthetic B.xlsx", modified=NEW),
    ]
    match = match_joiners(records, [])
    assert match.joiners == (
        Joiner("f2", "f2", "Test Person A", "test person a", None, False, 0),
    )
    expected = (
        "Two files have the same Checklist Owner: Synthetic A.xlsx and Synthetic B.xlsx."
        " Using Synthetic B.xlsx."
    )
    assert match.warnings == (expected,)
    assert (match.duplicates, match.moved) == (1, 0)


def test_us02_newest_is_found_whatever_the_listing_order():
    records = [
        rec("f2", name="Synthetic B.xlsx", modified=NEW),
        rec("f1", name="Synthetic A.xlsx", modified=OLD),
    ]
    match = match_joiners(records, [])
    assert [j.file_id for j in match.joiners] == ["f2"]
    assert match.warnings == (
        duplicate_warning("Synthetic A.xlsx", "Synthetic B.xlsx"),
    )


def test_us02_owner_case_and_space_differences_are_duplicates():
    records = [
        rec("f1", owner="Test Person A", modified=OLD),
        rec("f2", owner="  test   PERSON a ", modified=NEW),
    ]
    match = match_joiners(records, [])
    assert len(match.joiners) == 1
    assert match.duplicates == 1


def test_adr005_missing_modified_counts_as_oldest():
    records = [
        rec("f2", name="Synthetic B.xlsx", modified=""),
        rec("f1", name="Synthetic A.xlsx", modified="2026-10-01T08:00:00Z"),
    ]
    match = match_joiners(records, [])
    assert [j.file_id for j in match.joiners] == ["f1"]
    assert match.warnings == (
        duplicate_warning("Synthetic B.xlsx", "Synthetic A.xlsx"),
    )


def test_adr005_same_modified_takes_the_larger_id():
    records = [
        rec("f2", name="Synthetic B.xlsx", modified=OLD),
        rec("f1", name="Synthetic A.xlsx", modified=OLD),
    ]
    assert [j.file_id for j in match_joiners(records, []).joiners] == ["f2"]


def test_us02_three_files_same_owner_warn_once_per_other_file_in_listing_order():
    records = [
        rec("f3", name="Synthetic C.xlsx", modified=OLD),
        rec("f2", name="Synthetic B.xlsx", modified=NEW),
        rec("f1", name="Synthetic A.xlsx", modified="2026-10-20T08:00:00Z"),
    ]
    match = match_joiners(records, [])
    assert match.warnings == (
        duplicate_warning("Synthetic C.xlsx", "Synthetic B.xlsx"),
        duplicate_warning("Synthetic A.xlsx", "Synthetic B.xlsx"),
    )
    assert match.duplicates == 2
    assert [j.file_id for j in match.joiners] == ["f2"]


def test_us02_duplicate_without_dates_keeps_the_newest_files_joiner():
    stored = [joiner("f1"), joiner("f2")]
    records = [rec("f1", modified=OLD), rec("f2", modified=NEW)]
    match = match_joiners(records, stored)
    winner, loser = by_id(match.joiners, "f2"), by_id(match.joiners, "f1")
    assert (winner.file_id, winner.hidden, winner.missing_syncs) == ("f2", False, 0)
    assert (loser.hidden, loser.missing_syncs, loser.file_id) == (True, 1, "f1")
    assert match.duplicates == 1


def test_us03_duplicate_keeps_the_joiner_with_a_roll_on_reading_the_newest_file():
    stored = [
        joiner("f1", name="Test Person A", roll_on=D1),
        joiner("f2", name="Test Person A", roll_on=None),
    ]
    records = [
        rec("f1", owner="Test Person A", name="Synthetic A.xlsx", modified=OLD),
        rec("f2", owner="Test  Person A ", name="Synthetic B.xlsx", modified=NEW),
    ]
    match = match_joiners(records, stored)
    assert match.joiners == (
        Joiner("f1", "f2", "Test  Person A", "test person a", D1, False, 0),
        Joiner("f2", "f2", "Test Person A", "test person a", None, True, 1),
    )
    assert match.warnings == (
        duplicate_warning("Synthetic A.xlsx", "Synthetic B.xlsx"),
    )
    assert (match.duplicates, match.moved) == (1, 0)


def test_us03_duplicate_where_both_have_dates_keeps_the_newest_files_joiner():
    stored = [joiner("f1", roll_on=D1), joiner("f2", roll_on=D2)]
    records = [rec("f1", modified=NEW), rec("f2", modified=OLD)]
    match = match_joiners(records, stored)
    assert by_id(match.joiners, "f1").hidden is False
    assert by_id(match.joiners, "f1").roll_on == D1
    assert by_id(match.joiners, "f2").hidden is True
    assert by_id(match.joiners, "f2").roll_on == D2


def test_us02_duplicate_never_read_file_is_not_a_duplicate():
    records = [rec("f1", modified=OLD), rec("f2", modified=NEW, read=False)]
    match = match_joiners(records, [])
    assert [j.file_id for j in match.joiners] == ["f1"]
    assert (match.warnings, match.duplicates) == ((), 0)


def test_us02_duplicate_absent_file_is_not_a_duplicate():
    stored = [joiner("f1", roll_on=D1), joiner("f2")]
    records = [rec("f1", modified=OLD), rec("f2", modified=NEW, present=False)]
    match = match_joiners(records, stored)
    assert (match.warnings, match.duplicates) == ((), 0)
    assert by_id(match.joiners, "f1").hidden is False
    assert by_id(match.joiners, "f2").hidden is True


def test_us02_different_owners_give_no_warning():
    records = [rec("f1", owner="Test Person A"), rec("f2", owner="Test Person B")]
    match = match_joiners(records, [])
    assert (match.warnings, match.duplicates, len(match.joiners)) == ((), 0, 2)
