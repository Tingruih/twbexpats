"""Pitch extraction from live-feed JSON.

``extract_pitch_logs`` defines the pitch dict schema that gets cached in
``game_logs.pitches_json`` — every downstream stat module reads these keys.

歸屬原則對齊 Baseball Savant 的逐球資料：每顆球（含結束打席那一球帶的打席結果）
都歸「實際投、打那顆球的人」，``batter_id`` / ``pitch_hand`` / ``bat_side`` 也是
那顆球的實際值。打席中換投、代打時，被換下的人只有自己那段球、沒有打席結果。
刻意不套用官方記錄規則 9.15(b)（兩好球被代打、代打者三振算原打者）與
9.16(h)（換投時球數對打者有利、最後保送算前一位投手）：Savant 多數情況也不套用，
逐球算出的 K / BB 在這類打席會與官方 box score 差一筆（見 docs/fields.md）。
"""

import logging
from typing import Optional

from ..positions import BATTER, PITCHER

logger = logging.getLogger(__name__)

# playEvents[].position.code：換人事件的新守位；"11" = Pinch Hitter（"12" 是 Pinch Runner）
_PINCH_HITTER_CODE = "11"


def _extract_runners(play: dict) -> list[dict]:
    """Condense a play's ``runners`` node (baserunning movement + defensive
    credit) into a compact list, dropping the API's verbose link/copyright
    boilerplate.

    Only called on the last pitch of a PA — this data describes the play's
    final outcome, not a single pitch.
    """
    out: list[dict] = []
    for r in play.get("runners", []) or []:
        movement = r.get("movement", {}) or {}
        details = r.get("details", {}) or {}
        runner = details.get("runner", {}) or {}
        responsible_pitcher = details.get("responsiblePitcher") or {}
        credits = [
            {
                "player_id": c.get("player", {}).get("id"),
                "position": c.get("position", {}).get("abbreviation", ""),
                "credit": c.get("credit", ""),
            }
            for c in r.get("credits", []) or []
        ]
        out.append({
            "runner_id": runner.get("id"),
            "origin_base": movement.get("originBase"),
            "start_base": movement.get("start"),
            "end_base": movement.get("end"),
            "out_base": movement.get("outBase"),
            "is_out": bool(movement.get("isOut")),
            "out_number": movement.get("outNumber"),
            "event": details.get("event", ""),
            "event_type": details.get("eventType", ""),
            "movement_reason": details.get("movementReason", ""),
            "is_scoring_event": bool(details.get("isScoringEvent")),
            "rbi": bool(details.get("rbi")),
            "earned": details.get("earned"),
            "responsible_pitcher_id": responsible_pitcher.get("id"),
            "credits": credits,
        })
    return out


def _condense_defense(d: dict | None) -> dict:
    d = d or {}
    return {
        "p": (d.get("pitcher") or {}).get("id"),
        "c": (d.get("catcher") or {}).get("id"),
        "1b": (d.get("first") or {}).get("id"),
        "2b": (d.get("second") or {}).get("id"),
        "3b": (d.get("third") or {}).get("id"),
        "ss": (d.get("shortstop") or {}).get("id"),
        "lf": (d.get("left") or {}).get("id"),
        "cf": (d.get("center") or {}).get("id"),
        "rf": (d.get("right") or {}).get("id"),
    }


def _condense_offense(d: dict | None) -> dict:
    d = d or {}
    return {
        "on_1b": (d.get("first") or {}).get("id"),
        "on_2b": (d.get("second") or {}).get("id"),
        "on_3b": (d.get("third") or {}).get("id"),
        "post_2b": (d.get("postOnSecond") or {}).get("id"),
        "post_3b": (d.get("postOnThird") or {}).get("id"),
        "batter_pos": (d.get("batterPosition") or {}).get("code", ""),
    }


def _condense_nonpitch_event(
    ev: dict, play: dict, pitcher_id: Optional[int], batter_id: Optional[int]
) -> dict:
    """``pitcher_id`` / ``batter_id``：事件發生當下實際的投手與打者（見 ``_actual_participants``）。"""
    details = ev.get("details", {}) or {}
    pre_count = ev.get("preCount", {}) or {}
    count = ev.get("count", {}) or {}
    about = play.get("about", {}) or {}
    return {
        "type": ev.get("type", ""),
        "index": ev.get("index"),
        "play_id": ev.get("playId"),
        "inning": about.get("inning"),
        "pre_balls": pre_count.get("balls"),
        "pre_strikes": pre_count.get("strikes"),
        "pre_outs": pre_count.get("outs"),
        "balls": count.get("balls"),
        "strikes": count.get("strikes"),
        "outs": count.get("outs"),
        "result_code": details.get("code", ""),
        "result_desc": details.get("description", ""),
        "disengagement_num": details.get("disengagementNum"),
        "from_catcher": details.get("fromCatcher"),
        "runner_going": details.get("runnerGoing"),
        "is_out": details.get("isOut"),
        "pitcher_id": pitcher_id,
        "batter_id": batter_id,
    }


def _actual_participants(play: dict) -> list[tuple[Optional[int], Optional[int]]]:
    """``playEvents[]`` 每個事件當下實際的 ``(投手, 打者)``，與 ``playEvents`` 一一對應。

    ``matchup`` 只記「打完這個打席的人」，打席中換投、代打時，換人前的球不能用它。
    - 投手：事件自己的 ``defense.pitcher.id``（換投後每球各自標記），缺值退回
      ``matchup.pitcher.id``。
    - 打者：API 的每一球沒有打者欄位，只能靠換人事件切分。只有
      ``details.eventType == "offensive_substitution"`` 且 ``position.code == "11"``
      （代打）才換打者；代跑（"12"）換的是壘上跑者，與打者無關。打席開始的打者是
      第一個代打事件的 ``replacedPlayer.id``，沒有代打時就是 ``matchup.batter.id``。
    """
    matchup = play.get("matchup", {}) or {}
    pa_pitcher_id = (matchup.get("pitcher") or {}).get("id")
    events = play.get("playEvents", []) or []

    pinch_hits: list[tuple[int, Optional[int], Optional[int]]] = []
    for j, ev in enumerate(events):
        if (ev.get("details") or {}).get("eventType") != "offensive_substitution":
            continue
        code = (ev.get("position") or {}).get("code")
        if code is None:
            # 2002–2026 抽樣 195 場全部帶 position.code；缺值時無從分辨代打或代跑，
            # 視為非代打（不換打者），留 warning 以便發現 API 改變
            logger.warning(
                "offensive_substitution without position.code (game atBatIndex=%s, event %s)",
                play.get("atBatIndex"), ev.get("index"),
            )
            continue
        if code == _PINCH_HITTER_CODE:
            pinch_hits.append((
                j,
                (ev.get("player") or {}).get("id"),
                (ev.get("replacedPlayer") or {}).get("id"),
            ))

    batter_id = pinch_hits[0][2] if pinch_hits else (matchup.get("batter") or {}).get("id")
    pinch_at = {j: new_batter for j, new_batter, _ in pinch_hits}
    out: list[tuple[Optional[int], Optional[int]]] = []
    for j, ev in enumerate(events):
        if j in pinch_at:
            batter_id = pinch_at[j]
        pitcher_id = ((ev.get("defense") or {}).get("pitcher") or {}).get("id") or pa_pitcher_id
        out.append((pitcher_id, batter_id))
    return out


def _roster_code(players: dict, player_id: Optional[int], field: str) -> str:
    """``gameData.players["ID<id>"].<field>.code``（``pitchHand`` / ``batSide``）；缺值回空字串。"""
    player = players.get(f"ID{player_id}") or {}
    return (player.get(field) or {}).get("code") or ""


def _hand_for_pitch(
    matchup: dict, players: dict, pitcher_id: Optional[int], batter_id: Optional[int]
) -> tuple[str, str]:
    """這顆球實際的 ``(pitch_hand, bat_side)``。

    實際投打的人與 ``matchup`` 相同時沿用 ``matchup.pitchHand`` / ``batSide``：
    它是這個打席的實際值（左右開弓投手、打者每個打席各自不同）。換投或代打前的球，
    改取該球員在 ``gameData.players`` 的登錄值：
    - 投手登錄值為 "S"（左右開弓投手）或缺值時存 ""，只進合計、不進 L/R 分項。
    - 打者登錄值為 "S" 時取這顆球投球手的反邊（Savant 746572 第 56 打席：同一位
      左右開弓打者，右投換左投後 ``stand`` 由 L 變 R）；投球手為 "" 時存 ""。
    """
    matchup_pitcher = (matchup.get("pitcher") or {}).get("id")
    matchup_batter = (matchup.get("batter") or {}).get("id")

    if pitcher_id == matchup_pitcher:
        pitch_hand = (matchup.get("pitchHand") or {}).get("code", "")
    else:
        code = _roster_code(players, pitcher_id, "pitchHand")
        pitch_hand = code if code in ("L", "R") else ""

    if pitcher_id == matchup_pitcher and batter_id == matchup_batter:
        bat_side = (matchup.get("batSide") or {}).get("code", "")
    else:
        bat_side = _roster_code(players, batter_id, "batSide")
        if bat_side == "S":
            bat_side = {"L": "R", "R": "L"}.get(pitch_hand, "")
    return pitch_hand, bat_side


def _pa_context(play: dict) -> dict:
    # 這裡故意不抓 contextMetrics.catchProbability、matchup.batterHotColdZones、
    # matchup.pitcherHotColdZones。實測 245 場比賽（2002-2026，共 1.88 萬個
    # 打席）驗證過：
    #   - catchProbability / pitcherHotColdZones：一次都沒出現過，這個
    #     endpoint 根本不會回傳，是死欄位。
    #   - batterHotColdZones：不是逐打席的統計欄位，而是轉播端用的一次性
    #     熱區圖素材（好球帶切 9 宮格 + 4 個角落），MLB 只會附掛在整場
    #     比賽「最後一個打席」上，而且也只有約 87% 的機率有值。一場比賽
    #     最多只有 1 筆（常常還是 0 筆），而且每格的 value 看起來是球員的
    #     生涯/近況數字，不是這場比賽算出來的，當統計資料源沒有意義。
    count = play.get("count", {}) or {}
    context_metrics = play.get("contextMetrics", {}) or {}
    return {
        "pa_final_balls": count.get("balls"),
        "pa_final_strikes": count.get("strikes"),
        "pa_final_outs": count.get("outs"),
        "home_wp": play.get("homeTeamWinProbability"),
        "wpa": play.get("homeTeamWinProbabilityAdded"),
        "leverage_index": play.get("leverageIndex"),
        "drama_index": play.get("dramaIndex"),
        "pa_xwoba": context_metrics.get("xWoba"),
    }


def extract_pitch_logs(
    game_data: dict, player_id: int, role: str
) -> tuple[list[dict], list[dict]]:
    """Walk a live-feed JSON and return every pitch ``player_id`` actually threw or faced.

    Args:
        game_data: raw JSON from ``game/{pk}/withMetrics``.
        player_id: MLB ID to filter for.
        role: ``positions.PITCHER`` or ``positions.BATTER`` — which side of the
              pitch to match on.  Only that role: a two-way player's other role
              lives in its own ``game_logs`` row and is extracted separately.

    ``PITCHER`` 取實際投手為本人的球，``BATTER`` 取實際打者為本人的球（見
    ``_actual_participants``）；本人在一個打席沒有任何一顆球時，那個打席不會出現。
    打席結果（``is_pa_final``、``pa_event`` 等）只在打席實際的最後一球，
    那顆球屬於誰，結果就在誰的資料裡（模組 docstring：對齊 Savant）。

    Returns (pitches, nonpitch_events), both produced in the same walk.
    """
    if not game_data:
        return [], []
    plays = (
        game_data.get("liveData", {})
        .get("plays", {})
        .get("allPlays", [])
    )
    if not plays:
        return [], []
    # gameData.players["ID<id>"]：換人前那段球的投球手/打擊邊來源（見 _hand_for_pitch）
    roster = game_data.get("gameData", {}).get("players", {}) or {}
    # _actual_participants 的 (投手, 打者) 中，本人所在的位置
    own_index = {PITCHER: 0, BATTER: 1}[role]

    out: list[dict] = []
    nonpitch_out: list[dict] = []
    for play in plays:
        matchup = play.get("matchup", {})
        events = play.get("playEvents", [])
        participants = _actual_participants(play)

        # 這個打席本人完全沒有參與（沒有球、也沒有非投球事件）就整個略過
        if all(pair[own_index] != player_id for pair in participants):
            continue

        # Find the index of the LAST pitch in the PA (for wOBA attribution).
        # A play can have zero pitches (e.g. a pickoff that ends the inning
        # before any pitch is thrown) — its nonpitch events (pickoff/stepoff)
        # still need to be captured below; last_pitch_idx just never matches
        # when there are no pitches, so the isPitch branch never fires.
        pitch_indices = [i for i, e in enumerate(events) if e.get("isPitch")]
        last_pitch_idx = pitch_indices[-1] if pitch_indices else None

        result = play.get("result", {}) or {}
        event_type = result.get("eventType", "")
        event_desc = result.get("event", "")
        about = play.get("about", {}) or {}

        # Track pre-pitch strike count within this PA.
        # First pitch of every PA starts at 0-0.  For subsequent pitches the
        # pre-pitch count equals the previous pitch's post-pitch count.
        pa_pre_balls = 0
        pa_pre_strikes = 0

        for i, ev in enumerate(events):
            actual_pitcher, actual_batter = participants[i]
            is_own = participants[i][own_index] == player_id
            if ev.get("isPitch"):
                if not is_own:
                    # 換人前後不屬於本人的球：不收，但球數照實際比賽進度往前推，
                    # 本人接手後第一球的 pre_balls/pre_strikes 才是延續下來的球數
                    # （換人不會把球數歸零）
                    count = ev.get("count", {}) or {}
                    pa_pre_balls = count.get("balls", 0)
                    pa_pre_strikes = count.get("strikes", 0)
                    continue

                details = ev.get("details", {}) or {}
                pdata = ev.get("pitchData", {}) or {}
                hdata = ev.get("hitData", {}) or {}
                coords = pdata.get("coordinates", {}) or {}
                hit_coords = hdata.get("coordinates", {}) or {}
                breaks = pdata.get("breaks", {}) or {}
                count = ev.get("count", {}) or {}

                pitch_type_obj = details.get("type") or {}
                is_final = i == last_pitch_idx

                post_balls = count.get("balls", 0)
                post_strikes = count.get("strikes", 0)

                precount = ev.get("preCount")
                if precount:
                    p_pre_balls = precount.get("balls")
                    p_pre_strikes = precount.get("strikes")
                    p_pre_outs = precount.get("outs")
                else:
                    p_pre_balls = pa_pre_balls
                    p_pre_strikes = pa_pre_strikes
                    p_pre_outs = None

                sz_info = pdata.get("strikeZoneInfo", {}) or {}
                ctx = ev.get("contextMetrics", {}) or {}
                pitch_hand, bat_side = _hand_for_pitch(
                    matchup, roster, actual_pitcher, actual_batter
                )

                pitch = {
                    "game_pk": game_data.get("gamePk"),
                    # allPlays[].atBatIndex：打席邊界（stats/core/pitches.py::iter_plate_appearances）
                    "at_bat_index": play.get("atBatIndex"),
                    "inning": about.get("inning"),
                    "pitch_type": pitch_type_obj.get("code", ""),
                    "pitch_name": pitch_type_obj.get("description", ""),
                    "result_code": details.get("code", ""),
                    "result_desc": details.get("description", ""),
                    "is_strike": bool(details.get("isStrike")),
                    "is_ball": bool(details.get("isBall")),
                    "is_in_play": bool(details.get("isInPlay")),
                    "zone": pdata.get("zone"),
                    "start_speed": pdata.get("startSpeed"),
                    "end_speed": pdata.get("endSpeed"),
                    "extension": pdata.get("extension"),
                    "plate_time": pdata.get("plateTime"),
                    "strike_zone_top": pdata.get("strikeZoneTop"),
                    "strike_zone_bottom": pdata.get("strikeZoneBottom"),
                    "type_confidence": pdata.get("typeConfidence"),
                    "pfx_x": coords.get("pfxX"),
                    "pfx_z": coords.get("pfxZ"),
                    "px": coords.get("pX"),
                    "pz": coords.get("pZ"),
                    "x0": coords.get("x0"),
                    # y0 是 x0/z0 這兩個座標所在的平面（距本壘板幾呎），不是
                    # 球的第三個座標軸。2008 年起實測一律是 50，但 PITCHf/x
                    # 上線期出現過 40/45/50/55 四種，2007 年還會在賽季中途與
                    # 場中切換，所以必須逐球存、不能整組假設。缺這一欄的舊列
                    # 由 release_point._origin_plane() 退回 50——詳見
                    # constants.PITCH_TRAJECTORY_ORIGIN_Y_FT 的說明。
                    "y0": coords.get("y0"),
                    "z0": coords.get("z0"),
                    "vx0": coords.get("vX0"),
                    "vy0": coords.get("vY0"),
                    "vz0": coords.get("vZ0"),
                    "ax": coords.get("aX"),
                    "ay": coords.get("aY"),
                    "az": coords.get("aZ"),
                    "ivb": breaks.get("breakVerticalInduced"),
                    "hb": breaks.get("breakHorizontal"),
                    "spin_rate": breaks.get("spinRate"),
                    "spin_dir": breaks.get("spinDirection"),
                    "break_angle": breaks.get("breakAngle"),
                    "break_length": breaks.get("breakLength"),
                    "break_y": breaks.get("breakY"),
                    "break_vertical": breaks.get("breakVertical"),
                    "ev": hdata.get("launchSpeed"),
                    "la": hdata.get("launchAngle"),
                    "hit_distance": hdata.get("totalDistance"),
                    "trajectory": hdata.get("trajectory", ""),
                    "hit_location": hdata.get("location"),
                    "hit_coord_x": hit_coords.get("coordX"),
                    "hit_coord_y": hit_coords.get("coordY"),
                    "hardness": hdata.get("hardness", ""),
                    "balls": count.get("balls"),
                    "strikes": post_strikes,
                    "pre_balls": p_pre_balls,
                    "pre_strikes": p_pre_strikes,
                    "pre_outs": p_pre_outs,
                    "outs": count.get("outs"),
                    "batter_id": actual_batter,
                    "pitcher_id": actual_pitcher,
                    "bat_side": bat_side,
                    "pitch_hand": pitch_hand,
                    "is_pa_final": is_final,
                    "pa_event": event_type if is_final else "",
                    "pa_event_desc": event_desc if is_final else "",
                    "runners": _extract_runners(play) if is_final else None,
                    "play_id": ev.get("playId"),
                    "pitch_number": ev.get("pitchNumber"),
                    "sz_plate_x": sz_info.get("plateX"),
                    "sz_plate_y": sz_info.get("plateY"),
                    "sz_plate_z": sz_info.get("plateZ"),
                    "sz_top": sz_info.get("strikeZoneTop"),
                    "sz_bottom": sz_info.get("strikeZoneBottom"),
                    # sz_flat/sz_rounded/sz_corner_radius 這幾個「圓角好球帶
                    # 模型」欄位，MLB 從 2020 年才開始回傳，2020 年以前的比賽
                    # 一律是 null，不是抓取壞掉。
                    "sz_flat": sz_info.get("strikeZoneFlat"),
                    "sz_rounded": sz_info.get("strikeZoneRounded"),
                    "sz_corner_radius": sz_info.get("strikeZoneCornerRadiusInches"),
                    "sz_width_in": sz_info.get("widthInches"),
                    "sz_depth_in": sz_info.get("depthInches"),
                    # sz_edge_distance 從 2024 年才開始回傳，2024 年以前一律
                    # 是 null。
                    "sz_edge_distance": sz_info.get("edgeDistance"),
                    "sz_is_strike": sz_info.get("isStrike"),
                    # ctx（contextMetrics）故意只抓 homeRunBallparks。
                    # averagePitchSpeedPlayer/maxPitchSpeedPlayer/
                    # pitchSpeedPlayerRank 原本以為是「這球球速在該投手所有
                    # 球種中的百分位」，但實測 245 場比賽（2002-2026，共 7.3
                    # 萬顆投球）一次都沒出現過，確認是死欄位，已移除。
                    "hr_ballparks": ctx.get("homeRunBallparks"),
                    "hit_probability": hdata.get("hitProbability"),
                    # bat_speed/is_sword_swing 是 MLB 的 bat-tracking 資料，
                    # 2024 年才開始有（2024 年只有部分場館/部分賽程涵蓋，
                    # 2025 年起才是全面覆蓋）。沒揮棒的球（taken pitch）本來
                    # 就不會有棒速，是正常現象不是缺資料。
                    "bat_speed": hdata.get("batSpeed"),
                    "is_sword_swing": hdata.get("isSwordSwing"),
                    "defense": _condense_defense(ev.get("defense")),
                    "offense": _condense_offense(ev.get("offense")),
                }
                if is_final:
                    pitch.update(_pa_context(play))
                out.append(pitch)

                # Advance pre-pitch tracker: next pitch's pre-count =
                # this pitch's post-count.
                pa_pre_balls = post_balls
                pa_pre_strikes = post_strikes
            elif ev.get("type") in ("pickoff", "stepoff") and is_own:
                # 投手端看這個事件的 defense.pitcher（牽制的人），打者端看事件當下的打者
                nonpitch_out.append(
                    _condense_nonpitch_event(ev, play, actual_pitcher, actual_batter)
                )

    return out, nonpitch_out
