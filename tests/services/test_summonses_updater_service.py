import datetime as dt
from pathlib import Path

import httpx
import pytest

from simsim_tools_server.services.summonses_updater_service import (
    ECB_LOOKUP_URL,
    ECB_SEARCH_URL,
    EcbClient,
    LookupResult,
    RowDecision,
    SessionLostError,
    decide_row,
    is_valid_number,
    map_result,
    normalize_number,
    parse_result_page,
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


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_found_page():
    html = (FIXTURES / "ecb_found.html").read_text()
    assert parse_result_page(html) == LookupResult(True, "RESCHEDULED", "DEFAULTED")


def test_parse_no_record_page():
    html = (FIXTURES / "ecb_no_record.html").read_text()
    assert parse_result_page(html) == LookupResult(False, "", "")


def test_parse_page_without_table_raises():
    with pytest.raises(SessionLostError):
        parse_result_page((FIXTURES / "ecb_no_table.html").read_text())


def _ecb(handler):
    return EcbClient(httpx.Client(transport=httpx.MockTransport(handler)))


def test_lookup_posts_form_and_parses():
    seen = []

    def handler(request):
        seen.append(request)
        if str(request.url) == ECB_SEARCH_URL:
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text=(FIXTURES / "ecb_found.html").read_text())

    ecb = _ecb(handler)
    ecb.start_session()
    assert ecb.lookup("0213681142") == LookupResult(True, "RESCHEDULED", "DEFAULTED")
    post = seen[-1]
    assert post.method == "POST"
    assert str(post.url) == ECB_LOOKUP_URL
    body = post.content.decode()
    assert "searchViolationObject.violationNo=0213681142" in body
    assert "searchViolationObject.searchType=violationNumber" in body


def test_lookup_refreshes_session_once_on_lost_session():
    calls = {"search": 0, "lookup": 0}

    def handler(request):
        if str(request.url) == ECB_SEARCH_URL:
            calls["search"] += 1
            return httpx.Response(200, text="")
        calls["lookup"] += 1
        name = "ecb_no_table.html" if calls["lookup"] == 1 else "ecb_no_record.html"
        return httpx.Response(200, text=(FIXTURES / name).read_text())

    ecb = _ecb(handler)
    ecb.start_session()
    assert ecb.lookup("0213681142") == LookupResult(False, "", "")
    assert calls == {"search": 2, "lookup": 2}


def test_lookup_gives_up_after_one_retry():
    def handler(request):
        return httpx.Response(200, text=(FIXTURES / "ecb_no_table.html").read_text())

    ecb = _ecb(handler)
    with pytest.raises(SessionLostError):
        ecb.lookup("0213681142")
