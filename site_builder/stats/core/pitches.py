"""Pitch-level classification and the shared single-pass aggregation.

Everything here operates on lists of pitch dicts as produced by
``site_builder.sync.extract.extract_pitch_logs`` and cached in
``game_logs.pitches_json`` — that function defines the dict schema.
"""

from typing import Iterator, Optional

from ..batted_ball.barrel import is_barrel
from ..batted_ball.hard_hit import is_hard_hit
from ..batted_ball.spray import compute_spray
from ...constants import (
    CALLED_STRIKE_CODES,
    FB_TRAJECTORIES,
    GB_TRAJECTORIES,
    LD_TRAJECTORIES,
    NON_PITCH_TYPE_CODES,
    PU_TRAJECTORIES,
    SWING_CODES,
    UNKNOWN_PITCH_TOKENS,
    WHIFF_CODES,
)
from ...util.numbers import ratio


# ── Result-code classification ──


def is_swing(p: dict) -> bool:
    return p.get("result_code", "") in SWING_CODES


def is_whiff(p: dict) -> bool:
    return p.get("result_code", "") in WHIFF_CODES


def is_called_strike(p: dict) -> bool:
    return p.get("result_code", "") in CALLED_STRIKE_CODES


def is_in_zone(p: dict) -> bool:
    z = p.get("zone")
    return z is not None and 1 <= z <= 9


def is_out_of_zone(p: dict) -> bool:
    z = p.get("zone")
    return z is not None and 11 <= z <= 14


# ── Pitch-type helpers ──


def is_unknown_pitch_type(
    pitch_type: Optional[str], pitch_name: Optional[str] = None
) -> bool:
    """Return True for missing/placeholder pitch types, plus codes that don't
    represent an actual delivered pitch (intentional ball, pitchout,
    automatic ball/strike, no pitch — see ``NON_PITCH_TYPE_CODES``)."""
    type_token = str(pitch_type or "").strip().upper()
    name_token = str(pitch_name or "").strip().upper()
    if not type_token:
        return True
    return (
        type_token in UNKNOWN_PITCH_TOKENS
        or type_token in NON_PITCH_TYPE_CODES
        or name_token in UNKNOWN_PITCH_TOKENS
    )


def filter_known_pitch_events(pitches: list[dict]) -> list[dict]:
    """Drop unknown/non-delivery pitch-type events from pitch-type breakdowns."""
    return [
        p for p in pitches
        if not is_unknown_pitch_type(p.get("pitch_type"), p.get("pitch_name"))
    ]


def pitch_type_key(p: dict) -> str:
    # API 沒給球種代碼時歸入 "UN"，讓這些球仍有一個分組可放
    return p.get("pitch_type") or "UN"


def group_by_pitch_type(pitches: list[dict]) -> dict[str, list[dict]]:
    """``{pitch_type: [pitch, ...]}``，保留各球種第一次出現的順序。"""
    by_type: dict[str, list[dict]] = {}
    for p in pitches:
        by_type.setdefault(pitch_type_key(p), []).append(p)
    return by_type


def pitch_type_shares(type_counts: dict[str, int], total: int) -> list[dict]:
    """``[{type, count, pct}]``，依顆數由多到少；同顆數維持 ``type_counts`` 的順序。

    ``pct`` 以 ``total`` 為分母取 4 位小數，``total`` 為 0 時是 None（見 ``ratio``）。
    """
    ordered = sorted(type_counts, key=lambda t: type_counts[t], reverse=True)
    return [
        {"type": t, "count": type_counts[t], "pct": ratio(type_counts[t], total, digits=4)}
        for t in ordered
    ]


def pitch_type_display_name(pitches: list[dict], pitch_type: str) -> str:
    """同一球種中第一個非空的 ``pitch_name``；整組都沒有時退回球種代碼。

    不能只看第一球：舊快取或 playByPlay 偶有 ``details.type.description``
    為空的球，只看第一球會讓同一球種在不同表格顯示成代碼或全名兩種樣子。
    """
    return next((p["pitch_name"] for p in pitches if p.get("pitch_name")), pitch_type)


# ── Ball-strike count helpers ──


def pre_count_tuple(p: dict) -> Optional[tuple[int, int]]:
    """Return the pre-pitch (balls, strikes) tuple when available."""
    try:
        balls = p.get("pre_balls")
        strikes = p.get("pre_strikes")
        if balls is None or strikes is None:
            return None
        return int(balls), int(strikes)
    except (TypeError, ValueError):
        return None


def post_count_tuple(p: dict) -> Optional[tuple[int, int]]:
    try:
        balls = p.get("balls")
        strikes = p.get("strikes")
        if balls is None or strikes is None:
            return None
        return int(balls), int(strikes)
    except (TypeError, ValueError):
        return None


def count_label(count: tuple[int, int]) -> str:
    return f"{count[0]}-{count[1]}"


# ── Plate-appearance grouping ──


def iter_plate_appearances(pitches: list[dict]) -> Iterator[list[dict]]:
    """依序把逐球列表切成一個個打席，每次 yield 一個非空的 list。

    打席邊界的唯一定義：換 ``game_pk`` 或遇到 ``is_pa_final`` 為真的那一球。
    假設同一場內已按時間順序排列（``extract_pitch_logs`` 的輸出順序）。
    結尾沒有 ``is_pa_final`` 的殘段（被截斷的 game log）也會 yield，
    是否採信由呼叫端決定。
    """
    group: list[dict] = []
    last_game_pk = object()  # sentinel，不會等於任何真實 game_pk
    for p in pitches:
        gpk = p.get("game_pk")
        if gpk != last_game_pk:
            if group:
                yield group
            group = []
            last_game_pk = gpk
        group.append(p)
        if p.get("is_pa_final"):
            yield group
            group = []
    if group:
        yield group


# ── Single-pass aggregation ──


def aggregate_pitches(pitches: list[dict]) -> dict:
    """Classify a list of pitches into common categories.

    Returns a dict with pre-filtered lists and counts shared by both
    pitcher and batter aggregation paths.
    """
    swings: list[dict] = []
    whiffs: list[dict] = []
    called: list[dict] = []
    in_zone: list[dict] = []
    out_zone: list[dict] = []
    in_zone_swings: list[dict] = []
    out_zone_swings: list[dict] = []
    in_zone_contact: list[dict] = []
    in_play: list[dict] = []
    bbe_ev: list[dict] = []
    pa_final: list[dict] = []
    gb = fb = ld = pu = barrels = hard_hits = 0

    for p in pitches:
        is_sw = is_swing(p)
        is_wh = is_whiff(p)
        in_z  = is_in_zone(p)
        out_z = is_out_of_zone(p)

        if is_sw:
            swings.append(p)
        if is_wh:
            whiffs.append(p)
        if is_called_strike(p):
            called.append(p)
        if in_z:
            in_zone.append(p)
            if is_sw:
                in_zone_swings.append(p)
                if not is_wh:
                    in_zone_contact.append(p)
        if out_z:
            out_zone.append(p)
            if is_sw:
                out_zone_swings.append(p)
        if p.get("is_in_play"):
            in_play.append(p)
            ev = p.get("ev")
            if ev is not None:
                bbe_ev.append(p)
                if is_hard_hit(ev):
                    hard_hits += 1
            if is_barrel(ev, p.get("la")):
                barrels += 1
            traj = p.get("trajectory", "")
            if traj in GB_TRAJECTORIES:
                gb += 1
            elif traj in LD_TRAJECTORIES:
                ld += 1
            elif traj in FB_TRAJECTORIES:
                fb += 1
            elif traj in PU_TRAJECTORIES:
                pu += 1
        if p.get("is_pa_final"):
            pa_final.append(p)

    spray = compute_spray(in_play)
    return {
        "total": len(pitches),
        "swings": swings,
        "whiffs": whiffs,
        "called": called,
        "in_zone": in_zone,
        "out_zone": out_zone,
        "in_zone_swings": in_zone_swings,
        "out_zone_swings": out_zone_swings,
        "in_zone_contact": in_zone_contact,
        "in_play": in_play,
        "bbe_ev": bbe_ev,
        "pa_final": pa_final,
        "gb": gb,
        "fb": fb,
        "ld": ld,
        "pu": pu,
        "pull": spray["pull"],
        "straight": spray["straight"],
        "oppo": spray["oppo"],
        "pull_air": spray["pull_air"],
        "spray_total": spray["spray_total"],
        "barrels": barrels,
        "hard_hits": hard_hits,
    }
