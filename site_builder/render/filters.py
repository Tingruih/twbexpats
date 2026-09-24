"""Custom Jinja2 filters."""

import json
from decimal import Decimal

from jinja2 import Undefined
from markupsafe import Markup

from ..constants import PITCH_TYPE_ZH
from ..util.numbers import round_half_up, safe_float


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
    """Format a numeric value with fixed decimal places (half-up), or '-' for None.

    顯示值可能已被 API 捨入過一次（例如 K/9 給兩位、這裡顯示一位）；用
    round_half_up 至少讓 9.45 顯示成 9.5，而不是 f-string 依二進位值給的 9.4。
    """
    # 樣板取不存在的 key（例如投手頁混入的打擊逐場紀錄沒有 era）
    if isinstance(value, Undefined):
        return "-"
    number = safe_float(value)
    # 缺值或無法解析（例如 API 的 "-.--"、".---"）
    if number is None:
        return "-"
    digits = int(digits)
    return f"{round_half_up(number, digits):.{digits}f}"


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
    # 缺值
    if value is None:
        return "-"
    try:
        # 以十進位乘 100，避免 0.1235 * 100 的浮點尾差落在平手值下方
        scaled = Decimal(str(value)) * 100
    except ArithmeticError:
        # 無法解析成數字
        return "-"
    digits = int(digits)
    return f"{round_half_up(scaled, digits):.{digits}f}%"
