"""Spray direction — pull / straight / oppo classification of batted balls."""

import math
from typing import Optional

from ...constants import (
    AIR_TRAJECTORIES,
    GAMEDAY_HOME_X,
    GAMEDAY_HOME_Y,
    GAMEDAY_LEFT_FIELD_THRESHOLD_DEG,
    GAMEDAY_RIGHT_FIELD_THRESHOLD_DEG,
    GAMEDAY_SPRAY_CORRECTION,
    HIT_LOCATION_ZONE,
)


def spray_direction_from_location(p: dict) -> Optional[str]:
    """Fallback: classify spray direction using hitData.location fielder code.

    Used when hit coordinates are unavailable.  The location code is mapped
    to a broad field zone (LF / CF / RF) via ``HIT_LOCATION_ZONE``, then
    combined with the batter's handedness to produce pull / straight / oppo.
    """
    zone = HIT_LOCATION_ZONE.get(str(p.get("hit_location", "") or ""))
    if zone is None:
        return None
    if zone == "CF":
        return "straight"
    bat = p.get("bat_side", "R")
    if bat == "L":
        return "pull" if zone == "RF" else "oppo"
    return "pull" if zone == "LF" else "oppo"


def spray_direction_from_coordinates(p: dict) -> Optional[str]:
    """Classify batted-ball direction from MLB Gameday hit coordinates.

    座標系統說明（MLB Gameday 250×250 像素噴射圖）：
      - 原點 (0, 0) 在圖片左上角
      - X 軸向右遞增（從打者視角：朝右外野方向）
      - Y 軸向下遞增（朝本壘板 / 捕手方向）
      - 本壘板位於圖片下方中央 (HOME_X ≈ 125, HOME_Y ≈ 198)

    角度計算公式：
      angle = atan2(hc_x − HOME_X,  HOME_Y − hc_y) × 0.75

      atan2 的兩個引數（dx, dy）：
        dx = hc_x − HOME_X  正值 → 球落在本壘板右側（RF 方向）
                             負值 → 球落在本壘板左側（LF 方向）
        dy = HOME_Y − hc_y  正值 → 球落在本壘板前方（往外野方向，正常擊球）
                             負值 → 球落在本壘板後方（捕手後方的高飛球）

      atan2(dx, dy) 而非 atan2(dy, dx)：
        標準 atan2(y, x) 以「正 X 軸」為 0°。這裡將引數對調，
        改以「正 dy 軸（直線方向 / CF）」為 0°，左負右正，
        使得 0° = 中外野正中, +45° ≈ 一壘線, −45° ≈ 三壘線。

      × 0.75 修正係數：
        Gameday 噴射圖是從斜上方的俯瞰視角，圖像在橫向（左右）比
        縱深（本壘→外野）更「壓縮」，導致同樣真實角度在圖上橫向偏移
        看起來比實際大。乘以 0.75 補正此透視變形，修正後的角度尺度中
        −45° = 三壘界外線, +45° = 一壘界外線。

    閾值說明：
      修正後 ±15° 作為 Pull / Straight / Oppo 的分界，
      對應修正前原始角度的約 ±20°（±15° / 0.75 = ±20°）。

    參考來源：
      Jeff & Darrell Zimmerman / Bill Petti, The Hardball Times (2017)
      https://tht.fangraphs.com/research-notebook-new-format-for-statcast-data-export-at-baseball-savant/
    """
    x = p.get("hit_coord_x")
    y = p.get("hit_coord_y")
    if x is None or y is None:
        return None
    try:
        # dx > 0 → RF 側；dy > 0 → 外野方向（正常擊球）
        # atan2(dx, dy) 使 0° 指向 CF，正角往 RF，負角往 LF
        # × 0.75 補正噴射圖的透視壓縮變形
        angle = math.degrees(
            math.atan2(float(x) - GAMEDAY_HOME_X, GAMEDAY_HOME_Y - float(y))
        ) * GAMEDAY_SPRAY_CORRECTION
    except (TypeError, ValueError):
        return None

    if angle < -GAMEDAY_LEFT_FIELD_THRESHOLD_DEG:
        field = "LF"
    elif angle > GAMEDAY_RIGHT_FIELD_THRESHOLD_DEG:
        field = "RF"
    else:
        field = "CF"

    if field == "CF":
        return "straight"
    bat = p.get("bat_side", "R")
    if bat == "L":
        return "pull" if field == "RF" else "oppo"
    return "pull" if field == "LF" else "oppo"


def compute_spray(in_play: list[dict]) -> dict:
    """Return batted-ball direction counts from in-play pitch dicts.

    For each batted ball, tries coordinate-based classification first;
    falls back to hitData.location + bat_side when coordinates are absent.
    """
    pull = straight = oppo = pull_air = spray_total = 0
    for p in in_play:
        direction = spray_direction_from_coordinates(p)
        if direction is None:
            direction = spray_direction_from_location(p)
        if direction is None:
            continue
        spray_total += 1
        if direction == "straight":
            straight += 1
        elif direction == "pull":
            pull += 1
            if p.get("trajectory", "") in AIR_TRAJECTORIES:
                pull_air += 1
        elif direction == "oppo":
            oppo += 1
    return {
        "pull": pull,
        "straight": straight,
        "oppo": oppo,
        "pull_air": pull_air,
        "spray_total": spray_total,
    }
