"""US-04: Deadline text -> day offset from the roll-on date (plan slice 2, section 3.2).

The 11 readable texts come from docs/requirements.md section 8, open question 2.
"""

import pytest

from riro.core.deadlines import day_offset

REQUIREMENTS_TABLE = [
    ("10 days Before Roll On", -10),
    ("1 days Before Roll On", -1),
    ("On Roll On", 0),
    ("1 days After Roll On", 1),
    ("2 days After Roll On", 2),
    ("3 days After Roll On", 3),
    ("5 days After Roll On", 5),
    ("10 days After Roll On", 10),
    ("15 days After Roll On", 15),
    ("30 days After Roll On", 30),
    ("42 days After Roll On", 42),
]


def test_us04_requirements_table_has_eleven_readable_texts():
    assert len(REQUIREMENTS_TABLE) == 11


@pytest.mark.parametrize("text, offset", REQUIREMENTS_TABLE)
def test_us04_requirements_table_text_gives_its_offset(text, offset):
    assert day_offset(text) == offset


@pytest.mark.parametrize(
    "text, offset",
    [
        ("  5  DAYS after roll on ", 5),
        ("1 day Before Roll On", -1),
        ("1 day After Roll On", 1),
        ("on roll on", 0),
        ("ON ROLL ON", 0),
        ("  On   Roll   On  ", 0),
        ("On Roll-On", 0),
        ("On RollOn", 0),
        ("10 days Before Roll-On", -10),
        ("10 days before rollon", -10),
        ("3 Days After ROLL-ON", 3),
        ("7 days after RollOn", 7),
    ],
)
def test_us04_case_spaces_and_roll_on_spelling_variants(text, offset):
    assert day_offset(text) == offset


@pytest.mark.parametrize(
    "text",
    [
        "Day 0",
        "",
        "   ",
        None,
        "Never",
        "5 days",
        "Before Roll On",
        "After Roll On",
        "TBD",
    ],
)
def test_us04_unreadable_deadline_text_is_none(text):
    assert day_offset(text) is None


def test_us04_offset_is_an_int():
    assert type(day_offset("3 days After Roll On")) is int
    assert type(day_offset("On Roll On")) is int
