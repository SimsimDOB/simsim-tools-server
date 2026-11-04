"""Summonses Updater: ECB ticket-finder lookups over an AVPS workbook."""

import datetime as dt
from dataclasses import dataclass

from bs4 import BeautifulSoup

MIN_YEAR = 2021
NO_RECORD = "No Record Available"

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
