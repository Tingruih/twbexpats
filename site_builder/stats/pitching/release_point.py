"""出手點——球真正離手時的位置（英尺）。

為什麼不能直接用 x0/z0
----------------------
API 的 ``coordinates.x0`` / ``z0`` 不是出手點，而是球飛到**軌跡擬合原點平面**
（``y0``，現行為距本壘板 50 呎）時的位置。以 extension 約 6.7 呎的投手為例，
出手發生在 60.5 - 6.7 = 53.8 呎處，也就是說球在被記錄下 x0/z0 之前，已經飛了
將近 4 呎、約 30 毫秒。

那段路上球一直在移動，而且主導項是**等速項 v·t**，不是重力或球種位移：

    水平  vX0·t ≈ 0.105 呎    ½·aX·t² ≈ 0.002 呎
    垂直  vZ0·t ≈ 0.164 呎    ½·aZ·t² ≈ -0.008 呎

所以直接讀 x0/z0 會有系統性偏差，而且不是可以忽略的常數偏移：

  * 偏移量取決於 extension（延伸越長，離原點平面越遠，差距越大）。
  * vZ0 恆為負（球往下飛），乘上負的 t 恆為正 → 真正的出手點永遠比 x0/z0 高。
  * vX0 的正負隨慣用手相反 → 右投往負向修、左投往正向修，但兩者都是「離中線
    更遠」。實測右投 hRel 差 -2.2 吋、左投 +2.0 吋，等於把左右投的出手寬度差
    壓縮了約 4 吋。

出手平面是 60.5 - extension 這件事有 API 自己的證據：把軌跡求值在該平面上，
算出的球速可還原 ``startSpeed`` 到 0.04 mph 誤差；求值在 50 呎平面則差 0.51 mph。

兩個會用到的平面
----------------
1. ``60.5 - extension``——出手點本身。只有 2017 年起算得出來，API 在那之前
   不提供 ``extension``。
2. ``PITCH_TRAJECTORY_ORIGIN_Y_FT``（50 呎）——2017 年前的球季退回這裡。退回
   的目的不只是「有值可顯示」，而是**把該年度所有球正規化到同一個平面**：
   PITCHf/x 上線期的原點在 40/45/50/55 之間變動，不正規化的話同一欄會把沿
   飛行路徑相距最多 15 呎的位置平均在一起（郭泓志 2007 因此差了 5.7 吋）。
"""

import math
from typing import Optional

from ...constants import PITCH_TRAJECTORY_ORIGIN_Y_FT, RUBBER_TO_PLATE_FT
from ...util.numbers import mean_round

# 九參數軌跡擬合的完整欄位。少任何一個都無法求值到其他平面。
_TRAJECTORY_FIELDS = ("x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")


def _origin_plane(p: dict) -> float:
    """這顆球的軌跡擬合原點平面（距本壘板幾呎）。

    y0 是逐球屬性，不能整組共用——2009-07-28 的 Fenway 那場就在同一場比賽裡
    從 45 呎切換到 50 呎。在 y0 開始儲存之前寫入的舊列沒有這一欄，退回預設的
    50 呎；該預設值對現有資料的正確性依據寫在
    ``constants.PITCH_TRAJECTORY_ORIGIN_Y_FT``。
    """
    y0 = p.get("y0")
    return PITCH_TRAJECTORY_ORIGIN_Y_FT if y0 is None else y0


def _at_plane(p: dict, y_target: float) -> Optional[tuple[float, float]]:
    """把軌跡求值在 ``y_target`` 平面上，回傳 ``(x, z)``；資料不全則回 None。

    這是本模組唯一的幾何實作，出手點與 50 呎正規化都走這裡。

    解 ``y(t) = y_target``，也就是

        0.5 * ay * t² + vy0 * t + (y0 - y_target) = 0

    取距離原點平面較近的那個根（|t| 較小者）。求值在出手平面時 t 為負，因為
    出手發生在原點平面之前；求值在原點平面本身時 t = 0，會原封不動回傳
    x0/z0。
    """
    if any(p.get(f) is None for f in _TRAJECTORY_FIELDS):
        return None

    a = 0.5 * p["ay"]
    b = p["vy0"]
    c = _origin_plane(p) - y_target
    if a == 0:
        # ay = 0 代表沒有縱向阻力項，退化成等速直線。
        if b == 0:
            return None
        t = -c / b
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        root = math.sqrt(disc)
        t = min((-b + root) / (2 * a), (-b - root) / (2 * a), key=abs)

    return (
        p["x0"] + p["vx0"] * t + 0.5 * p["ax"] * t * t,
        p["z0"] + p["vz0"] * t + 0.5 * p["az"] * t * t,
    )


def compute_release_point(p: dict) -> Optional[tuple[float, float]]:
    """單一顆球的出手點 ``(h_rel, v_rel)``；算不出來則回 None。

    缺 ``extension``（2017 年前的球季）或軌跡欄位不齊時回 None——沒有
    extension 就定不出出手平面，這不是可以估算的東西。
    """
    extension = p.get("extension")
    if extension is None:
        return None
    return _at_plane(p, RUBBER_TO_PLATE_FT - extension)


def compute_avg_release_point(
    pitches: list[dict],
) -> tuple[Optional[float], Optional[float]]:
    """一組球的平均出手點 ``(h_rel, v_rel)``。

    只要組內有任何一顆球帶 ``extension``，就只用那些球算出手點；缺 extension
    的球像其他欄位遇到 None 一樣被濾掉（例如 2024 年 A 級有 2921/2922 顆帶
    extension，那一顆直接不計入）。

    只有在**整組都沒有** extension 時——也就是 2017 年前的球季——才整組退回
    50 呎平面。退回時同樣逐球用 ``_at_plane`` 正規化，而不是直接平均原始
    x0/z0，否則 PITCHf/x 上線期的多平面資料會被混在一起。

    「全有或全無」是刻意的：一個平均值裡永遠不會同時出現出手點與 50 呎平面
    兩種基準。
    """
    points = [rp for rp in (compute_release_point(p) for p in pitches) if rp]
    if not points:
        points = [
            rp
            for rp in (_at_plane(p, PITCH_TRAJECTORY_ORIGIN_Y_FT) for p in pitches)
            if rp
        ]
    return (
        mean_round([h for h, _ in points], 2),
        mean_round([v for _, v in points], 2),
    )
