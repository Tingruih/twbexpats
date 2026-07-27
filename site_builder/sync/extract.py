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
        pa_pitcher_id = matchup.get("pitcher", {}).get("id")
        batter_id = matchup.get("batter", {}).get("id")

        events = play.get("playEvents", [])

        if role == "batter" and batter_id != player_id:
            # matchup.batter 只記錄「這個打席最後是誰打完的」，如果 player_id
            # 是中途被換下場的那個人（例如打到一半受傷、被代打換掉），
            # matchup.batter 記的會是後來上場的代打者，不是 player_id——
            # 這種情況下如果直接用 matchup.batter 判斷「這個 play 跟
            # player_id 有沒有關係」就會整個 play 被跳過，連他被換下場
            # 之前自己打到的那幾球都會漏抓。
            # 所以這裡除了比對最終打者，也要檢查 player_id 是否出現在這個
            # play 任何一個「Offensive Substitution」事件的 replacedPlayer
            # （被換下場的人）欄位裡；只有兩者都對不上，才代表 player_id
            # 真的完全沒打這個打席，可以整個 play 跳過。
            was_replaced_mid_pa = any(
                (e.get("replacedPlayer") or {}).get("id") == player_id
                and (e.get("details") or {}).get("eventType")
                == "offensive_substitution"
                for e in events
            )
            if not was_replaced_mid_pa:
                continue
        if role == "pitcher":
            # matchup.pitcher 是整個 play（打席）層級的欄位，記的是「這個
            # 打席結束時是誰在投」，如果打席中途換投手（例如雨延、傷退），
            # 換投手之前投的那幾球其實是另一個投手投的，用 matchup.pitcher
            # 判斷會整批算錯到後來接手的投手頭上。
            # 好在投手這邊 MLB 每一球都會附上 defense.pitcher.id（這球實際
            # 是誰投的），所以真正的過濾在下面逐球迴圈裡用 event_pitcher_id
            # 做，這裡的整個 play 篩選只是先確認 player_id 有沒有在這個
            # play 裡投過至少一球（不管是打席結束時的投手，還是中途換上/
            # 換下的投手），完全沒有的話才整個 play 跳過。
            involves_player = pa_pitcher_id == player_id or any(
                (e.get("defense") or {}).get("pitcher", {}).get("id") == player_id
                for e in events
                if e.get("isPitch")
            )
            if not involves_player:
                continue
        # Find the index of the LAST pitch in the PA (for wOBA attribution).
        # A play can have zero pitches (e.g. a pickoff that ends the inning
        # before any pitch is thrown) — don't skip the whole play in that
        # case, since its nonpitch events (pickoff/stepoff) still need to be
        # captured below; last_pitch_idx just never matches when there are
        # no pitches, so the isPitch branch below simply never fires.
        pitch_indices = [i for i, e in enumerate(events) if e.get("isPitch")]
        last_pitch_idx = pitch_indices[-1] if pitch_indices else None

        # 打者這邊跟投手不一樣：MLB 的每一球（pitch event）本身完全不會
        # 附上「這球當時是誰在打」的欄位（投手那邊有 defense.pitcher.id
        # 可以逐球核對，打者這邊沒有對應的東西），所以沒辦法像投手那樣
        # 逐球判斷球員身分，只能靠這個 play 裡「Offensive Substitution」
        # 這個換人事件出現的位置（index），去切割「這球是換人前打的、
        # 還是換人後打的」。
        #
        # 換人中途發生時，球數（好壞球數）是直接延續下去的（不會重新從
        # 0-0 開始算），這代表換上場跟換下場的兩個打者，其實共用同一個
        # 打席、同一組逐球紀錄，只是中間有一刀切開誰是「這球的打者」。
        #
        # 情況一（batter_takeover_idx）：player_id 是中途「換上場」代打
        # 的那個人（例如代打傷退球員）。換人事件之前的那幾球，是投給原本
        # 那個打者的，不算 player_id 的球，要排除掉。
        #
        # 情況二（batter_handoff_idx）：跟情況一相反，player_id 是中途
        # 「被換下場」的那個原始打者（例如打到一半受傷被代打換掉）。換人
        # 事件之後的那幾球，是投給後來代打者的，一樣不算 player_id 的球，
        # 也要排除掉——而且這個打席最後的結果（三振/安打/出局等）也正確地
        # 不會算在 player_id 頭上，因為那些球根本沒被收進他的逐球清單裡。
        #
        # 正常情況（打席全程都是同一個打者，沒有中途換人）下，這兩個變數
        # 都維持 None，下面逐球迴圈完全不受影響，行為跟修正前一樣。
        batter_takeover_idx = None
        batter_handoff_idx = None
        if role == "batter":
            for j, e in enumerate(events):
                d = e.get("details") or {}
                if d.get("eventType") != "offensive_substitution":
                    continue
                if (e.get("player") or {}).get("id") == player_id:
                    batter_takeover_idx = j
                elif (e.get("replacedPlayer") or {}).get("id") == player_id:
                    batter_handoff_idx = j

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
                # 這球實際上是誰投的：優先用這球自己的 defense.pitcher.id
                # （中途換投手時，每球都各自標記真正的投手），只有舊資料
                # 缺這個欄位時才退回用整個打席層級的 pa_pitcher_id 頂替，
                # 這樣沒有中途換投手的一般情況行為完全不變。
                event_pitcher_id = (
                    (ev.get("defense") or {}).get("pitcher", {}).get("id")
                    or pa_pitcher_id
                )

                if role == "pitcher" and event_pitcher_id != player_id:
                    # 這球不是 player_id 投的（中途換投手，這球是另一個
                    # 投手投的）——不收進 player_id 的逐球清單，但球數
                    # 追蹤（pa_pre_balls/pa_pre_strikes）還是要照實際比賽
                    # 進度往前推進，這樣下一顆真正屬於 player_id 的球，
                    # pre_balls/pre_strikes 才會是正確的「這球投出前」球數。
                    count = ev.get("count", {}) or {}
                    pa_pre_balls = count.get("balls", 0)
                    pa_pre_strikes = count.get("strikes", 0)
                    continue

                if batter_takeover_idx is not None and i < batter_takeover_idx:
                    # player_id 是中途「換上場」代打的人：換人事件之前的
                    # 這幾球是投給原本那個打者的，不是 player_id 看到的球，
                    # 排除掉；球數追蹤一樣要照實際比賽進度往前推進，讓
                    # player_id 真正接手後的第一球能正確帶著「換人當下」
                    # 延續下來的好壞球數（不是從 0-0 重新算）。
                    count = ev.get("count", {}) or {}
                    pa_pre_balls = count.get("balls", 0)
                    pa_pre_strikes = count.get("strikes", 0)
                    continue

                if batter_handoff_idx is not None and i > batter_handoff_idx:
                    # 跟上面相反：player_id 是中途「被換下場」的原始打者，
                    # 換人事件之後的這幾球是投給後來代打者的，不算
                    # player_id 看到的球，排除掉。因為這些球本來就發生在
                    # player_id 離場之後，這裡的球數追蹤更新其實不會再被
                    # 用到（player_id 在這個打席不會再有球了），單純是
                    # 跟上面兩個分支保持一致的寫法。
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
                    "pitcher_id": event_pitcher_id,
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
            elif ev.get("type") in ("pickoff", "stepoff"):
                nonpitch_out.append(_condense_nonpitch_event(ev, play))

    return out, nonpitch_out
