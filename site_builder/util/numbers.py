"""Safe numeric conversions and small math helpers.

全專案的數值捨入只走 :func:`round_half_up` 一個實作。MLB Stats API 的比率欄位
是以「精確分數 + 四捨五入（HALF_UP）」產生的（對照資料庫 season_stats 全部
列驗證：AVG/OBP/SLG/ERA/WHIP 等在平手值上都是進位）。內建 ``round()`` 對二進位
剛好是 .5 的值取偶數（``round(0.0625, 3) == 0.062``），又會吃到除法的浮點誤差
（``9 * 21 / (40 / 3)`` 落在 14.174999…），兩者都會讓結果跟 API 差最後一位。
"""

import math
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from numbers import Rational
from typing import Any


def safe_float(value: Any, default=None):
    """轉成有限浮點數；空值、無法解析或 NaN/inf 時回 *default*。

    NaN/inf 一律視為缺值：API 不會給這種值，若出現代表來源資料壞掉，讓它
    流進比率計算只會產生無意義的結果。
    """
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (ValueError, TypeError):
        return default
    # NaN/inf：當成缺值
    return number if math.isfinite(number) else default


def safe_int(value: Any, default=None):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _round_rational(p: int, q: int, digits: int) -> float:
    """精確分數 p/q 四捨五入到 *digits* 位（負數遠離零），純整數運算。"""
    scale = 10 ** digits
    magnitude = (2 * abs(p) * scale + abs(q)) // (2 * abs(q))
    negative = (p < 0) != (q < 0)
    # int / int 在 Python 是正確捨入的除法，結果即為該十進位數最接近的 float
    return (-magnitude if negative else magnitude) / scale


def _to_fraction(value) -> Fraction:
    """精確轉成 Fraction；float 以最短 repr（人眼看到的十進位）為準。"""
    if isinstance(value, (Rational, Decimal)):
        return Fraction(value)
    return Fraction(Decimal(repr(float(value))))


def round_half_up(value, digits: int) -> float:
    """四捨五入到 *digits* 位小數（負數遠離零），回傳 float。

    接受 int / Fraction / Decimal / float。float 以最短 repr 為準：直接取
    二進位展開的話 2.675 會是 2.67499999…，捨入結果就跟畫面上看到的數字
    對不起來。Fraction 走純整數運算，極接近但未達平手的分數不會被誤判。
    """
    if isinstance(value, Rational):
        return _round_rational(value.numerator, value.denominator, digits)
    number = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
    return float(number.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def ratio(num, den, digits=3):
    """Exact division rounded half-up, or None when the denominator is 0/None."""
    # 分母為零或缺值
    if not den:
        return None
    # 計數相除（絕大多數呼叫）走純整數快速路徑
    if isinstance(num, int) and isinstance(den, int):
        return _round_rational(num, den, digits)
    return round_half_up(_to_fraction(num) / _to_fraction(den), digits)


def mean(values):
    """Mean of non-None values, or None if empty."""
    vs = [v for v in values if v is not None]
    # 沒有任何有效值
    if not vs:
        return None
    return sum(vs) / len(vs)


def mean_round(values, digits=1):
    """Mean of non-None values, rounded half-up. Returns None if no valid values."""
    v = mean(values)
    # 沒有任何有效值
    return round_half_up(v, digits) if v is not None else None

