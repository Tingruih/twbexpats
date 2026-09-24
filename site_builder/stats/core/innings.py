"""Innings-pitched notation conversions.

Baseball decimal notation (7.2 = 7⅔ innings) must be converted to outs before
any rate math, otherwise ERA/WHIP/per-9 stats come out slightly wrong.

投手率一律以 outs（整數）當分母做精確分數運算，不先除成「真實局數」浮點數：
``outs / 3.0`` 會讓剛好落在平手值的結果（例如 ERA 14.175）變成 14.174999…，
捨入後比 API 少 0.01。
"""

from ...util.numbers import ratio


def ip_to_outs(ip_value) -> int:
    if ip_value is None:
        return 0
    whole = int(ip_value)
    # 小數部分只會是 .0/.1/.2 的浮點近似值，round 用來消除尾差，不是數據捨入
    thirds = round((ip_value - whole) * 10)
    return whole * 3 + thirds


def outs_to_ip(outs: int):
    if outs == 0:
        return None
    whole = outs // 3
    remainder = outs % 3
    return round(whole + remainder / 10, 1)


def per_nine(count, outs, digits=2):
    """每九局比率：count × 27 / outs（27 outs = 9 局）。

    兩位小數對應 MLB API 的 ``era`` / ``strikeoutsPer9Inn`` 等欄位精度。
    ``digits=None`` 不捨入：只給會再被拿去計算的中間值用（聯盟 ERA 是 FIP
    常數的輸入，見 stats/advanced/fip.py），先捨入會把誤差傳給每位投手的 FIP。
    """
    # 計數缺值（未知不等於 0）或沒有投球局數
    if count is None or not outs or outs <= 0:
        return None
    if digits is None:
        return 27 * count / outs
    return ratio(27 * count, outs, digits)
