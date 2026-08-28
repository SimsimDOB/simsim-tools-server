import pytest

from simsim_tools_server.services.multi_summonses_count_service import (
    parse_summons_quantity,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Singular and plural, with and without the OCR'd period.
        ("1 summons\n", 1),
        ("1. summonses\n", 1),
        ("1. summons\n", 1),
        ("3 summonses\n", 3),
        ("12 summonses", 12),
        # OCR sometimes eats the space between the digit and the word.
        ("3summonses", 3),
        # The case today's regex misses: text ending exactly after "summons".
        ("2 summons", 2),
        # No legible digit -> not a summons page.
        ("summonses\n", None),
        ("", None),
        # OCR noise in the word itself is not silently accepted.
        ("3 sumnonses", None),
        # Implausible value, most likely two numbers joined by OCR.
        ("400 summonses", None),
        # Zero is not a plausible summons quantity either.
        ("0 summonses\n", None),
        # Real OCR output: any run of non-digits may sit between the number
        # and the word — list markers, brackets, colons, stray letters.
        ("i. (2: summonses)\n\nings,\n", 2),
        ("(3: summonses)", 3),
        ("1) summonses", 1),
        ("2 - summonses", 2),
        # OCR may also break the line between the number and the word.
        ("3\nsummonses\n", 3),
        # The nearest preceding number wins; a digit is never skipped over.
        ("case 7\n2 summonses\n", 2),
    ],
)
def test_parse_summons_quantity(text: str, expected: int | None):
    assert parse_summons_quantity(text) == expected


def test_parse_summons_quantity_accepts_the_ceiling_itself():
    assert parse_summons_quantity("99 summonses\n") == 99


def test_parse_summons_quantity_rejects_one_above_the_ceiling():
    assert parse_summons_quantity("100 summonses\n") is None
