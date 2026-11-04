"""Summonses Updater: ECB ticket-finder lookups over an AVPS workbook."""

import datetime as dt
import logging
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

MIN_YEAR = 2021
NO_RECORD = "No Record Available"

ECB_SEARCH_URL = "http://a820-ecbticketfinder.nyc.gov/searchHome.action"
ECB_LOOKUP_URL = "http://a820-ecbticketfinder.nyc.gov/getViolationbyID.action"

PAUSE_SECONDS = 3.0
MAX_CONSECUTIVE_ERRORS = 5
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SITE_DOWN_MESSAGE = "The ECB site is not responding"

# Fixed columns of the AVPS sheet: B, G, Q.
NUMBER_COL = 2
DATE_COL = 7
RESULT_COL = 17

# Column Q values that mean "not decided yet": these rows get looked up.
CANDIDATE_RESULTS = frozenset(
    {"", "adjourned", "new issuance", "rescheduled", "no record available"}
)


def normalize_number(value: object) -> str:
    """Apply the script's fix-ups to a raw column-B value."""
    number = str(value).replace(" ", "")
    if len(number) == 9 and "E" not in number:
        number = "0" + number
    elif len(number) == 10 and "E" in number:
        number = number.replace("E", "0")
    return number


def is_valid_number(number: str) -> bool:
    return len(number) == 10 and number.startswith("0")


@dataclass(frozen=True)
class RowDecision:
    """`skip` is a reason to leave the row alone, or None to look it up."""

    skip: str | None
    number: str


def decide_row(number: object, date: object, result: object) -> RowDecision:
    if number is None or str(number).strip() == "":
        return RowDecision("empty", "")
    normalized = normalize_number(number)
    # datetime.datetime subclasses datetime.date; datetime.time does not.
    if not isinstance(date, dt.date):
        return RowDecision("bad date", normalized)
    if date.year < MIN_YEAR:
        return RowDecision("before 2021", normalized)
    current = "" if result is None else str(result).strip().lower()
    if current not in CANDIDATE_RESULTS:
        return RowDecision("has result", normalized)
    if not is_valid_number(normalized):
        return RowDecision("invalid number", normalized)
    return RowDecision(None, normalized)


def map_result(status: str, hearing_result: str) -> str | None:
    """Value to write to column Q for a found record, or None to leave it."""
    if status == "PAID IN FULL":
        return "Paid before Hearing"
    if hearing_result:
        if hearing_result == "SETTL/IN-VIOLATION":
            return "In Violation"
        return hearing_result.capitalize()
    if status == "SETTL/IN-VIOLATION":
        return "In Violation"
    if status == "NEW ISSUANCE":
        return "New Issuance"
    if status == "RESCHEDULED":
        return "Adjourned"
    return None


class SessionLostError(Exception):
    """The ECB site answered without a result table (session expired)."""


@dataclass(frozen=True)
class LookupResult:
    found: bool
    status: str
    hearing_result: str


def parse_result_page(html: str) -> LookupResult:
    """Read the ECB result page the way the original script did."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one('table[id="vioContent"]')
    if content is None:
        raise SessionLostError("no vioContent table in response")
    summons_number = content.select("td")[1].get_text().strip()
    if summons_number == NO_RECORD:
        return LookupResult(False, "", "")
    details = soup.select_one('div[id="moreDetails"]').select("td")
    status = details[1].get_text().strip()
    hearing_result = details[3].get_text().strip()
    return LookupResult(True, status, hearing_result)


class EcbClient:
    """Cookie-session client for the ECB ticket finder."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    def start_session(self) -> None:
        self._client.get(ECB_SEARCH_URL).raise_for_status()

    def lookup(self, number: str) -> LookupResult:
        try:
            return self._lookup(number)
        except SessionLostError:
            self.start_session()
            return self._lookup(number)

    def _lookup(self, number: str) -> LookupResult:
        response = self._client.post(
            ECB_LOOKUP_URL,
            data={
                "searchViolationObject.violationNo": number,
                "searchViolationObject.searchType": "violationNumber",
                "submit": "  Search  ",
            },
        )
        response.raise_for_status()
        return parse_result_page(response.text)

    def close(self) -> None:
        self._client.close()


def check_headers(sheet: Worksheet) -> None:
    b = sheet.cell(1, NUMBER_COL).value
    g = sheet.cell(1, DATE_COL).value
    q = sheet.cell(1, RESULT_COL).value
    if (
        "number" not in str(b).lower()
        or "date" not in str(g).lower()
        or "result" not in str(q).lower()
    ):
        raise ValueError(
            f"Unexpected headers: B1={b!r}, G1={g!r}, Q1={q!r}. Expected the "
            "summons Number, Date of Offense and Results of Hearing columns."
        )


def load_workbook_bytes(data: bytes) -> tuple[Workbook, Worksheet]:
    try:
        workbook = load_workbook(BytesIO(data))
    except Exception as e:
        raise ValueError("Could not read the workbook") from e
    sheet = workbook.active
    check_headers(sheet)
    return workbook, sheet


@dataclass
class LogEntry:
    i: int
    row: int
    number: str
    kind: str
    text: str


@dataclass
class Change:
    row: int
    number: str
    before: str | None
    after: str


@dataclass
class Problem:
    row: int
    reason: str


def _new_counts() -> dict[str, int]:
    return {"looked_up": 0, "changed": 0, "no_record": 0, "skipped": 0, "errors": 0}


@dataclass
class Job:
    id: str
    filename: str
    workbook: Workbook
    sheet: Worksheet
    total_rows: int
    status: str = "running"
    current_row: int = 1
    counts: dict[str, int] = field(default_factory=_new_counts)
    log: list[LogEntry] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    error: str | None = None
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finished_at: dt.datetime | None = None
    cancel_requested: bool = False
    file_bytes: bytes | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def snapshot(self, after: int = 0) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "current_row": self.current_row,
                "total_rows": self.total_rows,
                "counts": dict(self.counts),
                "started_at": self.started_at.isoformat(),
                "finished_at": (
                    self.finished_at.isoformat() if self.finished_at else None
                ),
                "error": self.error,
                "log": [asdict(e) for e in self.log[max(after, 0) :]],
                "next": len(self.log),
                "changes": [asdict(c) for c in self.changes],
                "problems": [asdict(p) for p in self.problems],
            }

    def _append(self, row: int, number: str, kind: str, text: str) -> None:
        with self.lock:
            self.log.append(LogEntry(len(self.log), row, number, kind, text))

    def _finish(self, status: str, error: str | None = None) -> None:
        with self.lock:
            self.status = status
            self.error = error
            self.finished_at = dt.datetime.now(dt.UTC)
            if status in ("done", "cancelled"):
                buffer = BytesIO()
                self.workbook.save(buffer)
                self.file_bytes = buffer.getvalue()


def run_job(
    job: Job,
    lookup: Callable[[str], LookupResult],
    *,
    pause: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Walk every data row of the sheet; always leaves the job terminal."""
    if pause is None:
        pause = PAUSE_SECONDS
    try:
        _walk_rows(job, lookup, pause, sleep)
    except Exception as e:
        logging.error(f"Summonses job {job.id} crashed: {e}\n{traceback.format_exc()}")
        job._finish("failed", str(e))


def _walk_rows(
    job: Job,
    lookup: Callable[[str], LookupResult],
    pause: float,
    sleep: Callable[[float], None],
) -> None:
    sheet = job.sheet
    consecutive_errors = 0
    for row in range(2, sheet.max_row + 1):
        with job.lock:
            job.current_row = row
        decision = decide_row(
            sheet.cell(row, NUMBER_COL).value,
            sheet.cell(row, DATE_COL).value,
            sheet.cell(row, RESULT_COL).value,
        )
        number = decision.number
        if decision.skip is not None:
            _skip_row(job, row, number, decision.skip)
        else:
            try:
                result = lookup(number)
            except Exception as e:
                consecutive_errors += 1
                logging.error(
                    f"Lookup failed for row {row} ({number}): {e}\n"
                    f"{traceback.format_exc()}"
                )
                with job.lock:
                    job.counts["errors"] += 1
                job._append(row, number, "error", f"error: {e}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    job._finish("failed", SITE_DOWN_MESSAGE)
                    return
            else:
                consecutive_errors = 0
                _apply_result(job, row, number, result)
            sleep(pause)
        if job.cancel_requested:
            job._finish("cancelled")
            return
    job._finish("done")


def _skip_row(job: Job, row: int, number: str, reason: str) -> None:
    with job.lock:
        job.counts["skipped"] += 1
    if reason == "bad date":
        job.problems.append(Problem(row, reason))
        job._append(row, number, "bad_date", f"skipped ({reason})")
    elif reason == "invalid number":
        logging.warning(f"Row {row}: invalid summons number {number!r}")
        job.problems.append(Problem(row, reason))
        job._append(row, number, "invalid", f"skipped ({reason})")
    else:
        job._append(row, number, "skipped", f"skipped ({reason})")


def _apply_result(job: Job, row: int, number: str, result: LookupResult) -> None:
    cell = job.sheet.cell(row, RESULT_COL)
    with job.lock:
        job.counts["looked_up"] += 1
    if not result.found:
        cell.value = NO_RECORD
        with job.lock:
            job.counts["no_record"] += 1
        job._append(row, number, "no_record", NO_RECORD)
        return
    after = map_result(result.status, result.hearing_result)
    if after is None:
        job._append(row, number, "same", f"left unchanged ({result.status})")
        return
    before = cell.value
    cell.value = after
    if before != after:
        with job.lock:
            job.counts["changed"] += 1
            job.changes.append(Change(row, number, before, after))
        job._append(
            row, number, "changed", f"{before or '(blank)'} → {after} (changed)"
        )
    else:
        job._append(row, number, "same", f"{after} (same)")
