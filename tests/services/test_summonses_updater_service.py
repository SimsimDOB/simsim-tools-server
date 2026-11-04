import datetime as dt
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from openpyxl import Workbook, load_workbook

from simsim_tools_server.services import summonses_updater_service as svc
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


def _xlsx(rows):
    """Workbook bytes with the AVPS headers; rows are (number, date, result)."""
    wb = Workbook()
    ws = wb.active
    ws.cell(1, 2, "Number")
    ws.cell(1, 7, "Date of Offense")
    ws.cell(1, 17, "Results of Hearing")
    for r, (n, d, q) in enumerate(rows, start=2):
        ws.cell(r, 2, n)
        ws.cell(r, 7, d)
        ws.cell(r, 17, q)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _job(rows):
    wb, ws = svc.load_workbook_bytes(_xlsx(rows))
    return svc.Job(
        id="j", filename="a.xlsx", workbook=wb, sheet=ws, total_rows=ws.max_row - 1
    )


def _q(job):
    """Column Q of the saved file, rows 2.."""
    ws = load_workbook(BytesIO(job.file_bytes)).active
    return [ws.cell(r, 17).value for r in range(2, ws.max_row + 1)]


def _no_sleep(_seconds):
    return None


def test_check_headers_rejects_wrong_file():
    wb = Workbook()
    wb.active.cell(1, 2, "Name")
    with pytest.raises(ValueError, match="B1='Name'"):
        svc.check_headers(wb.active)


def test_load_workbook_bytes_rejects_garbage():
    with pytest.raises(ValueError, match="Could not read the workbook"):
        svc.load_workbook_bytes(b"nope")


def test_run_job_writes_results_and_counts():
    rows = [
        ("213681142", D, None),
        ("213681143", D, "Adjourned"),
        ("213681144", D, "Defaulted"),
        ("213681145", dt.datetime(2019, 1, 1), None),
        ("213681146", D, None),
        (None, D, None),
    ]
    answers = {
        "0213681142": svc.LookupResult(True, "RESCHEDULED", "DEFAULTED"),
        "0213681143": svc.LookupResult(True, "RESCHEDULED", ""),
        "0213681146": svc.LookupResult(False, "", ""),
    }
    slept = []
    job = _job(rows)
    svc.run_job(job, answers.__getitem__, pause=0, sleep=slept.append)
    assert job.status == "done"
    assert job.finished_at is not None
    assert job.counts == {
        "looked_up": 3,
        "changed": 1,
        "no_record": 1,
        "skipped": 3,
        "errors": 0,
    }
    assert _q(job) == [
        "Defaulted",
        "Adjourned",
        "Defaulted",
        None,
        "No Record Available",
        None,
    ]
    assert job.changes == [svc.Change(2, "0213681142", None, "Defaulted")]
    assert [e.kind for e in job.log] == [
        "changed",
        "same",
        "skipped",
        "skipped",
        "no_record",
        "skipped",
    ]
    assert job.log[0].text == "(blank) → Defaulted (changed)"
    assert job.log[2].text == "skipped (has result)"
    assert slept == [0, 0, 0]


def test_run_job_records_problems():
    job = _job([("213681142", dt.time(4, 48), None), ("1234567890", D, None)])
    svc.run_job(
        job, lambda n: pytest.fail("no lookup expected"), pause=0, sleep=_no_sleep
    )
    assert job.problems == [
        svc.Problem(2, "bad date"),
        svc.Problem(3, "invalid number"),
    ]
    assert [e.kind for e in job.log] == ["bad_date", "invalid"]
    assert job.counts["skipped"] == 2


def test_run_job_fails_after_five_consecutive_errors():
    rows = [(f"21368114{i}", D, None) for i in range(7)]

    def boom(_number):
        raise httpx.ConnectError("down")

    job = _job(rows)
    svc.run_job(job, boom, pause=0, sleep=_no_sleep)
    assert job.status == "failed"
    assert job.error == svc.SITE_DOWN_MESSAGE
    assert job.counts["errors"] == 5
    assert job.file_bytes is None


def test_run_job_error_streak_resets_on_success():
    rows = [(f"21368114{i}", D, None) for i in range(9)]

    def lookup(number):  # 4 errors, 1 success, 4 errors
        if number == "0213681144":
            return svc.LookupResult(False, "", "")
        raise httpx.ConnectError("down")

    job = _job(rows)
    svc.run_job(job, lookup, pause=0, sleep=_no_sleep)
    assert job.status == "done"
    assert job.counts["errors"] == 8
    assert job.counts["no_record"] == 1


def test_run_job_cancel_stops_after_current_row_and_saves():
    job = _job([("213681142", D, None), ("213681143", D, None)])

    def lookup(_number):
        job.request_cancel()
        return svc.LookupResult(True, "PAID IN FULL", "")

    svc.run_job(job, lookup, pause=0, sleep=_no_sleep)
    assert job.status == "cancelled"
    assert job.counts["looked_up"] == 1
    assert _q(job) == ["Paid before Hearing", None]


def test_snapshot_after_cursor():
    job = _job([("213681142", D, None), ("213681143", D, "Defaulted")])
    svc.run_job(
        job, lambda n: svc.LookupResult(False, "", ""), pause=0, sleep=_no_sleep
    )
    snap = job.snapshot(after=1)
    assert [e["i"] for e in snap["log"]] == [1]
    assert snap["next"] == 2
    assert snap["status"] == "done"
    assert snap["counts"]["no_record"] == 1
    assert snap["total_rows"] == 2
    assert isinstance(snap["started_at"], str)
    # Review Focus 4: a cursor past the end is harmless.
    assert job.snapshot(after=99)["log"] == []
    assert job.snapshot(after=99)["next"] == 2


def test_finish_publishes_status_and_file_together():
    """Nobody may observe status != running before file_bytes exists."""
    job = _job([("213681142", D, "Defaulted")])
    observed = {}
    real_save = job.workbook.save

    def spy_save(buffer):
        observed["status_during_save"] = job.status
        real_save(buffer)

    job.workbook.save = spy_save
    svc.run_job(job, lambda n: pytest.fail("no lookup"), pause=0, sleep=_no_sleep)
    assert observed["status_during_save"] == "running"
    assert job.status == "done"
    assert job.file_bytes is not None


def test_bad_date_row_is_logged_as_warning(caplog):
    job = _job([("213681142", "2024-07-31", None)])
    with caplog.at_level("WARNING"):
        svc.run_job(job, lambda n: pytest.fail("no lookup"), pause=0, sleep=_no_sleep)
    assert any("bad date" in r.message and "2" in r.message for r in caplog.records)
