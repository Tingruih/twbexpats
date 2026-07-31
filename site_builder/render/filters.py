"""Custom Jinja2 filters."""

import json
from decimal import Decimal, ROUND_HALF_UP

from markupsafe import Markup

from ..constants import PITCH_TYPE_ZH


def pitch_legend(rows):
    """球種欄表頭 tooltip 的中英對照，序列化成 ``data-legend`` 的 JSON 字串。

    輸入是球種表格自己的資料列（每列有 ``type`` 代碼與 ``name`` 英文名），輸出
    ``[[英文名, 中文], ...]``：只列出該表實際出現過的球種，順序沿用資料列既有
    的球數降冪，與逐球紀錄 Result 欄的 legend 慣例一致。

    查不到中文的代碼（IN/PO/AB/AS/NP 等非球種事件）直接略過，回傳空清單時給
    ``None``，讓呼叫端省掉 ``data-legend`` 屬性。
    """
    pairs = []
    seen = set()
    for row in rows or []:
        code = str((row.get("type") or "")).upper()
        zh = PITCH_TYPE_ZH.get(code)
        name = row.get("name") or code
        if not zh or name in seen:
            continue
        seen.add(name)
        pairs.append([name, zh])
    return json.dumps(pairs, ensure_ascii=False) if pairs else None


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
