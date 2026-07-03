"""Custom Jinja2 filters."""

import json
from decimal import Decimal, ROUND_HALF_UP

from markupsafe import Markup


def floatformat(value, digits=2):
    """Format a numeric value with fixed decimal places, or '-' for None."""
    if value is None:
        return "-"
    try:
        return f"{float(value):.{int(digits)}f}"
    except Exception:
        return "-"


def default_if_none(value, fallback="-"):
    """Return *fallback* when *value* is None."""
    return fallback if value is None else value


def num_dash(value):
    """Display a number or '-' for None / empty."""
    if value is None or value == "":
        return "-"
    return value


def _json_html_safe(s: str) -> str:
    # Prevent </script> from closing the enclosing script tag.
    return s.replace("</", "<\\/")


def tojson_safe(value):
    """Serialize to JSON and mark safe for embedding in <script>."""
    return Markup(_json_html_safe(json.dumps(value, ensure_ascii=False)))


def jsonld(value):
    """Serialize compact JSON-LD and mark safe for embedding in <script>."""
    return Markup(_json_html_safe(json.dumps(value, ensure_ascii=False, separators=(",", ":"))))


def pct_fmt(value, digits=1):
    """Format a decimal fraction (e.g. 0.345) as a percentage string (34.5%).

    Returns '-' for None.  Commonly used for Statcast percentages stored as
    0.XXX in the database.
    """
    if value is None:
        return "-"
    try:
        places = Decimal("1").scaleb(-int(digits))
        pct = (Decimal(str(value)) * Decimal("100")).quantize(
            places, rounding=ROUND_HALF_UP
        )
        return f"{pct:.{int(digits)}f}%"
    except Exception:
        return "-"
