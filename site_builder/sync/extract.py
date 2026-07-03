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


def extract_pitch_logs(
    game_data: dict, player_id: int, role: str
) -> list[dict]:
    """Walk a live-feed JSON and return every pitch involving ``player_id``.

    Args:
        game_data: raw JSON from ``game/{pk}/feed/live``.
        player_id: MLB ID to filter for.
        role: ``"pitcher"`` or ``"batter"`` — which side of the matchup to
              match on.

    Returns a list of pitch dicts in chronological order.
    """
    if not game_data:
        return []
    plays = (
        game_data.get("liveData", {})
        .get("plays", {})
        .get("allPlays", [])
    )
    if not plays:
        return []

    out: list[dict] = []
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
            if not ev.get("isPitch"):
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

            out.append({
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
                "pre_balls": pa_pre_balls,
                "pre_strikes": pa_pre_strikes,
                "outs": count.get("outs"),
                "batter_id": batter_id,
                "pitcher_id": pitcher_id,
                "bat_side": matchup.get("batSide", {}).get("code", ""),
                "pitch_hand": matchup.get("pitchHand", {}).get("code", ""),
                "is_pa_final": is_final,
                "pa_event": event_type if is_final else "",
                "pa_event_desc": event_desc if is_final else "",
                "runners": _extract_runners(play) if is_final else None,
            })

            # Advance pre-pitch tracker: next pitch's pre-count =
            # this pitch's post-count.
            pa_pre_balls = post_balls
            pa_pre_strikes = post_strikes

    return out
