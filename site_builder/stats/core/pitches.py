"""Pitch-level classification and the shared single-pass aggregation.

Everything here operates on lists of pitch dicts as produced by
``site_builder.sync.extract.extract_pitch_logs`` and cached in
``game_logs.pitches_json`` — that function defines the dict schema.
"""

from typing import Optional

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


def ensure_pre_strikes(pitches: list[dict]) -> None:
    """Annotate pre-pitch count fields on pitches that lack them.

    Walks the list in order, grouped by ``game_pk``. Within each game the
    pitches are assumed to be in chronological PA order (as produced by
    ``extract_pitch_logs``). The first pitch of each PA starts at 0-0;
    subsequent pitches inherit the previous pitch's post-pitch count.

    Always recomputes for pitches missing the field, even when other pitches
    in the same list already have it (handles mixed old/new cached data).
    """
    if not pitches:
        return
    # Fast path: if ALL pitches already have the fields, nothing to do.
    if all("pre_balls" in p and "pre_strikes" in p for p in pitches):
        return

    pre_balls = 0
    pre_strikes = 0
    last_game_pk = None
    for p in pitches:
        gpk = p.get("game_pk")
        if gpk != last_game_pk:
            # New game boundary — reset to start of a fresh PA.
            pre_balls = 0
            pre_strikes = 0
            last_game_pk = gpk

        p["pre_balls"] = pre_balls
        p["pre_strikes"] = pre_strikes

        if p.get("is_pa_final"):
            pre_balls = 0
            pre_strikes = 0  # next pitch starts a new PA
        else:
            pre_balls = p.get("balls", 0) or 0
            pre_strikes = p.get("strikes", 0) or 0


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
