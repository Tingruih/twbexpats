"""週報告的衍生指標（VAA/HAA、感知球速、轉軸時鐘、attack zone…）。

公式見 docs/superpowers/plans/2026-07-09-recents-charts-video.md §0.7。
所有函式對缺欄位回傳 None（best-effort，不 raise）。
"""

import math

from ...util.numbers import float_or_none, mean_round, ratio
from ..core.pitches import filter_known_pitch_events

PLATE_Y_FT = 17 / 12          # 本壘板前緣
RELEASE_MEASURE_Y_FT = 50.0   # MLB 座標系向量的量測點
PLATE_HALF_WIDTH_FT = 0.83    # 半板寬 + 球半徑
DEFAULT_SZ_TOP = 3.4
DEFAULT_SZ_BOT = 1.6
LEAGUE_AVG_EXTENSION = 6.5


def _plate_velocity(p):
    """回傳 (t, vy_f)：到本壘板前緣的剩餘飛行參數；缺資料回 None。"""
    vy0 = float_or_none(p.get("vy0"))
    ay = float_or_none(p.get("ay"))
    if vy0 is None or ay is None or ay == 0:
        return None
    disc = vy0 * vy0 - 2 * ay * (RELEASE_MEASURE_Y_FT - PLATE_Y_FT)
    if disc <= 0:
        return None
    vy_f = -math.sqrt(disc)
    return (vy_f - vy0) / ay, vy_f


def compute_vaa(p: dict):
    base = _plate_velocity(p)
    vz0 = float_or_none(p.get("vz0"))
    az = float_or_none(p.get("az"))
    if base is None or vz0 is None or az is None:
        return None
    t, vy_f = base
    vz_f = vz0 + az * t
    return round(-math.degrees(math.atan(vz_f / vy_f)), 2)


def compute_haa(p: dict):
    base = _plate_velocity(p)
    vx0 = float_or_none(p.get("vx0"))
    ax = float_or_none(p.get("ax"))
    if base is None or vx0 is None or ax is None:
        return None
    t, vy_f = base
    vx_f = vx0 + ax * t
    return round(-math.degrees(math.atan(vx_f / vy_f)), 2)


def effective_velocity(p: dict):
    velo = float_or_none(p.get("start_speed"))
    ext = float_or_none(p.get("extension"))
    if velo is None or ext is None or ext >= 60.5:
        return None
    return round(velo * (60.5 - LEAGUE_AVG_EXTENSION) / (60.5 - ext), 2)


def velocity_decay(p: dict):
    start = float_or_none(p.get("start_speed"))
    end = float_or_none(p.get("end_speed"))
    if start is None or end is None:
        return None
    return round(start - end, 2)


def spin_clock(spin_dir):
    sd = float_or_none(spin_dir)
    if sd is None:
        return None
    total_min = round((((sd - 180) % 360) / 30) * 60 / 15) * 15 % 720
    hh = total_min // 60 or 12
    return f"{int(hh)}:{int(total_min % 60):02d}"


def circular_mean_deg(values):
    vs = [v for v in (float_or_none(v) for v in values) if v is not None]
    if not vs:
        return None
    x = sum(math.cos(math.radians(v)) for v in vs)
    y = sum(math.sin(math.radians(v)) for v in vs)
    if x == 0 and y == 0:
        return None
    result = round(math.degrees(math.atan2(y, x)) % 360, 1)
    return 0.0 if result == 360.0 else result


def normalized_location(p: dict):
    px = float_or_none(p.get("px"))
    pz = float_or_none(p.get("pz"))
    if px is None or pz is None:
        return None
    top = float_or_none(p.get("strike_zone_top")) or DEFAULT_SZ_TOP
    bot = float_or_none(p.get("strike_zone_bottom")) or DEFAULT_SZ_BOT
    if top <= bot:
        return None
    x_norm = px / PLATE_HALF_WIDTH_FT
    z_norm = (pz - (top + bot) / 2) / ((top - bot) / 2)
    return x_norm, z_norm


def attack_zone(p: dict):
    loc = normalized_location(p)
    if loc is None:
        return None
    m = max(abs(loc[0]), abs(loc[1]))
    if m <= 0.67:
        return "heart"
    if m <= 1.33:
        return "shadow"
    if m <= 2.0:
        return "chase"
    return "waste"


def attack_zone_distribution(pitches: list[dict]):
    counts = {"heart": 0, "shadow": 0, "chase": 0, "waste": 0}
    n = 0
    for p in pitches:
        z = attack_zone(p)
        if z:
            counts[z] += 1
            n += 1
    if not n:
        return None
    out = {k: ratio(v, n) for k, v in counts.items()}
    out["n"] = n
    return out


def edge_pct(pitches: list[dict]):
    dist = attack_zone_distribution(pitches)
    return dist["shadow"] if dist else None


def f_strike_pct(pitches: list[dict]):
    first = [
        p for p in pitches
        if p.get("pre_balls") == 0 and p.get("pre_strikes") == 0
    ]
    if not first:
        return None
    strikes = sum(1 for p in first if p.get("is_strike") or p.get("is_in_play"))
    return ratio(strikes, len(first), digits=6)


def derived_by_pitch_type(pitches: list[dict]) -> dict:
    by_type: dict[str, list[dict]] = {}
    for p in filter_known_pitch_events(pitches):
        by_type.setdefault(p.get("pitch_type") or "UN", []).append(p)
    out = {}
    for ptype, ps in by_type.items():
        spin_mean = circular_mean_deg([p.get("spin_dir") for p in ps])
        out[ptype] = {
            "n": len(ps),
            "vaa": mean_round([compute_vaa(p) for p in ps], 1),
            "haa": mean_round([compute_haa(p) for p in ps], 1),
            "eff_velo": mean_round([effective_velocity(p) for p in ps], 1),
            "velo_decay": mean_round([velocity_decay(p) for p in ps], 1),
            "spin_dir_mean": spin_mean,
            "spin_clock": spin_clock(spin_mean),
        }
    return out
