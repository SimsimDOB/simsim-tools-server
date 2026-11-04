"""Summonses Updater: ECB ticket-finder lookups over an AVPS workbook."""

import datetime as dt
from dataclasses import dataclass

MIN_YEAR = 2021

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
