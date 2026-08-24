import logging
import re

_MAX_QUANTITY = 99
_QUANTITY = re.compile(r"(\d+)\s*\.?\s*summons(?:es)?\b", re.IGNORECASE)


def parse_summons_quantity(text: str) -> int | None:
    """Read the summons quantity from a page's OCR'd text.

    Returns None when no quantity is legible, or when the value exceeds
    _MAX_QUANTITY. OCR joining two numbers is the realistic failure mode
    here, and it would otherwise be invisible in a bare total.
    """
    match = _QUANTITY.search(text)
    if match is None:
        return None
    quantity = int(match.group(1))
    if quantity > _MAX_QUANTITY:
        logging.warning(f"Implausible summons quantity {quantity} in {text!r}")
        return None
    return quantity
