"""Pitch extraction from live-feed JSON.

``extract_pitch_logs`` defines the pitch dict schema that gets cached in
``game_logs.pitches_json`` — every downstream stat module reads these keys.
"""


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


def _condense_nonpitch_event(ev: dict, play: dict) -> dict:
    details = ev.get("details", {}) or {}
    pre_count = ev.get("preCount", {}) or {}
    count = ev.get("count", {}) or {}
    about = play.get("about", {}) or {}
    matchup = play.get("matchup", {}) or {}
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
        "pitcher_id": matchup.get("pitcher", {}).get("id"),
        "batter_id": matchup.get("batter", {}).get("id"),
    }


def _pa_context(play: dict) -> dict:
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
        "catch_probability": context_metrics.get("catchProbability"),
    }


def extract_pitch_logs(
    game_data: dict, player_id: int, role: str
) -> tuple[list[dict], list[dict]]:
    """Walk a live-feed JSON and return every pitch involving ``player_id``.

    Args:
        game_data: raw JSON from ``game/{pk}/withMetrics``.
        player_id: MLB ID to filter for.
        role: ``"pitcher"`` or ``"batter"`` — which side of the matchup to
              match on.

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

    out: list[dict] = []
    nonpitch_out: list[dict] = []
    for play in plays:
        matchup = play.get("matchup", {})
        pitcher_id = matchup.get("pitcher", {}).get("id")
        batter_id = matchup.get("batter", {}).get("id")

        if role == "pitcher" and pitcher_id != player_id:
            continue
        if role == "batter" and batter_id != player_id:
            continue

        events = play.get("playEvents", [])
        # Find the index of the LAST pitch in the PA (for wOBA attribution)
        pitch_indices = [i for i, e in enumerate(events) if e.get("isPitch")]
        if not pitch_indices:
            continue
        last_pitch_idx = pitch_indices[-1]

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
            if ev.get("isPitch"):
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

                pitch = {
                    "game_pk": game_data.get("gamePk"),
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
                    "batter_id": batter_id,
                    "pitcher_id": pitcher_id,
                    "bat_side": matchup.get("batSide", {}).get("code", ""),
                    "pitch_hand": matchup.get("pitchHand", {}).get("code", ""),
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
                    "sz_flat": sz_info.get("strikeZoneFlat"),
                    "sz_rounded": sz_info.get("strikeZoneRounded"),
                    "sz_corner_radius": sz_info.get("strikeZoneCornerRadiusInches"),
                    "sz_width_in": sz_info.get("widthInches"),
                    "sz_depth_in": sz_info.get("depthInches"),
                    "sz_edge_distance": sz_info.get("edgeDistance"),
                    "sz_is_strike": sz_info.get("isStrike"),
                    "avg_pitch_speed_player": ctx.get("averagePitchSpeedPlayer"),
                    "max_pitch_speed_player": ctx.get("maxPitchSpeedPlayer"),
                    "pitch_speed_pct": ctx.get("pitchSpeedPlayerRank"),
                    "hr_ballparks": ctx.get("homeRunBallparks"),
                    "hit_probability": hdata.get("hitProbability"),
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
            elif ev.get("type") in ("pickoff", "stepoff"):
                nonpitch_out.append(_condense_nonpitch_event(ev, play))

    return out, nonpitch_out
