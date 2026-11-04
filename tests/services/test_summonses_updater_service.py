import datetime as dt

import pytest

from simsim_tools_server.services.summonses_updater_service import (
    RowDecision,
    decide_row,
    is_valid_number,
    map_result,
    normalize_number,
)

D = dt.datetime(2024, 7, 31)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("213681142", "0213681142"),
        ("E213681142", "0213681142"),
        (" 0213 681142 ", "0213681142"),
        # Review Focus 1: Excel stores the number as an int, not text.
        (213681142, "0213681142"),
        ("0213681142", "0213681142"),
        # Untouched; rejected later by is_valid_number.
        ("1234567890", "1234567890"),
        # 9 chars with an E: neither rule applies.
        ("E12345678", "E12345678"),
    ],
)
def test_normalize_number(value, expected):
    assert normalize_number(value) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("0213681142", True),
        ("1234567890", False),
        ("021368114", False),
        ("E12345678", False),
    ],
)
def test_is_valid_number(number, expected):
    assert is_valid_number(number) is expected


@pytest.mark.parametrize(
    ("number", "date", "result", "expected"),
    [
        (None, D, None, RowDecision("empty", "")),
        ("", D, None, RowDecision("empty", "")),
        ("213681142", dt.time(4, 48), None, RowDecision("bad date", "0213681142")),
        # Review Focus 2: a text date is unreadable, not a crash.
        ("213681142", "2024-07-31", None, RowDecision("bad date", "0213681142")),
        ("213681142", None, None, RowDecision("bad date", "0213681142")),
        (
            "213681142",
            dt.datetime(2020, 12, 31),
            None,
            RowDecision("before 2021", "0213681142"),
        ),
        ("213681142", D, "Defaulted", RowDecision("has result", "0213681142")),
        # Review Focus 3: a non-string result still counts as a result.
        ("213681142", D, 5, RowDecision("has result", "0213681142")),
        ("213681142", D, "Adjourned ", RowDecision(None, "0213681142")),
        ("213681142", D, "NEW ISSUANCE", RowDecision(None, "0213681142")),
        ("213681142", D, "rescheduled", RowDecision(None, "0213681142")),
        ("213681142", D, "No Record Available", RowDecision(None, "0213681142")),
        ("213681142", D, None, RowDecision(None, "0213681142")),
        ("213681142", dt.date(2021, 1, 1), "", RowDecision(None, "0213681142")),
        ("1234567890", D, None, RowDecision("invalid number", "1234567890")),
        ("E12345678", D, None, RowDecision("invalid number", "E12345678")),
    ],
)
def test_decide_row(number, date, result, expected):
    assert decide_row(number, date, result) == expected


@pytest.mark.parametrize(
    ("status", "hearing", "expected"),
    [
        ("PAID IN FULL", "", "Paid before Hearing"),
        ("PAID IN FULL", "DEFAULTED", "Paid before Hearing"),
        ("RESCHEDULED", "DEFAULTED", "Defaulted"),
        ("HEARING HELD", "SETTL/IN-VIOLATION", "In Violation"),
        # str.capitalize() lowercases the rest; kept on purpose (spec).
        ("HEARING HELD", "ADMIN. DISMISSAL", "Admin. dismissal"),
        ("SETTL/IN-VIOLATION", "", "In Violation"),
        ("NEW ISSUANCE", "", "New Issuance"),
        ("RESCHEDULED", "", "Adjourned"),
        ("HEARING SCHEDULED", "", None),
    ],
)
def test_map_result(status, hearing, expected):
    assert map_result(status, hearing) == expected
