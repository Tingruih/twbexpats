"""MLB Stats API stat-field → local column-name mappings."""

from ..util.numbers import safe_float, safe_int


def apply_yearbyyear_fields(stat_doc: dict, group_name: str, stat: dict):
    if group_name == "pitching":
        stat_doc.update(
            {
                "era": safe_float(stat.get("era")),
                "whip": safe_float(stat.get("whip")),
                "ip": safe_float(stat.get("inningsPitched")),
                "so": safe_int(stat.get("strikeOuts")),
                "wins": safe_int(stat.get("wins")),
                "losses": safe_int(stat.get("losses")),
                "bb": safe_int(stat.get("baseOnBalls")),
                "sv": safe_int(stat.get("saves")),
                "hld": safe_int(stat.get("holds")),
                "gs": safe_int(stat.get("gamesStarted")),
                "earned_runs": safe_int(stat.get("earnedRuns")),
                "pitches": safe_int(stat.get("numberOfPitches")),
                "bf": safe_int(stat.get("battersFaced")),
                "k_per_9": safe_float(stat.get("strikeoutsPer9Inn")),
                "bb_per_9": safe_float(stat.get("walksPer9Inn")),
                "h_per_9": safe_float(stat.get("hitsPer9Inn")),
                "k_bb_ratio": safe_float(stat.get("strikeoutWalkRatio")),
                "hr_per_9": safe_float(stat.get("homeRunsPer9")),
                "p_per_ip": safe_float(stat.get("pitchesPerInning")),
                "win_pct": str(stat.get("winPercentage", "")),
                "strike_pct": str(stat.get("strikePercentage", "")),
                "p_ground_outs": safe_int(stat.get("groundOuts")),
                "p_air_outs": safe_int(stat.get("airOuts")),
                "runs_allowed": safe_int(stat.get("runs")),
                "p_hits": safe_int(stat.get("hits")),
                "p_hr": safe_int(stat.get("homeRuns")),
                "p_hbp": safe_int(stat.get("hitByPitch")),
                "p_ibb": safe_int(stat.get("intentionalWalks")),
                "p_sb": safe_int(stat.get("stolenBases")),
                "p_cs": safe_int(stat.get("caughtStealing")),
                "p_gdp": safe_int(stat.get("groundIntoDoublePlay")),
                "p_doubles": safe_int(stat.get("doubles")),
                "p_triples": safe_int(stat.get("triples")),
                "p_tb": safe_int(stat.get("totalBases")),
                "p_ab": safe_int(stat.get("atBats")),
                "svo": safe_int(stat.get("saveOpportunities")),
                "outs": safe_int(stat.get("outs")),
                "cg": safe_int(stat.get("completeGames")),
                "sho": safe_int(stat.get("shutouts")),
                "strikes": safe_int(stat.get("strikes")),
                "balks": safe_int(stat.get("balks")),
                "wp": safe_int(stat.get("wildPitches")),
                "pickoffs": safe_int(stat.get("pickoffs")),
                "gf": safe_int(stat.get("gamesFinished")),
                "ir": safe_int(stat.get("inheritedRunners")),
                "irs": safe_int(stat.get("inheritedRunnersScored")),
                "p_sac_bunts": safe_int(stat.get("sacBunts")),
                "p_sac_flies": safe_int(stat.get("sacFlies")),
                "p_avg": str(stat.get("avg", "")),
                "p_obp": str(stat.get("obp", "")),
                "p_slg": str(stat.get("slg", "")),
                "p_ops": str(stat.get("ops", "")),
                "p_sb_pct": str(stat.get("stolenBasePercentage", "")),
                "p_babip": safe_float(stat.get("babip")),
                "p_go_ao": safe_float(stat.get("groundOutsToAirouts")),
                "qs": safe_int(stat.get("qualityStarts")),
            }
        )
    elif group_name == "hitting":
        stat_doc.update(
            {
                "avg": safe_float(stat.get("avg")),
                "obp": safe_float(stat.get("obp")),
                "slg": safe_float(stat.get("slg")),
                "ops": safe_float(stat.get("ops")),
                "hr": safe_int(stat.get("homeRuns")),
                "rbi": safe_int(stat.get("rbi")),
                "sb": safe_int(stat.get("stolenBases")),
                "cs": safe_int(stat.get("caughtStealing")),
                "ab": safe_int(stat.get("atBats")),
                "hits": safe_int(stat.get("hits")),
                "hit_bb": safe_int(stat.get("baseOnBalls")),
                "pa": safe_int(stat.get("plateAppearances")),
                "doubles": safe_int(stat.get("doubles")),
                "triples": safe_int(stat.get("triples")),
                "tb": safe_int(stat.get("totalBases")),
                "hbp": safe_int(stat.get("hitByPitch")),
                "gdp": safe_int(stat.get("groundIntoDoublePlay")),
                "runs": safe_int(stat.get("runs")),
                "h_so": safe_int(stat.get("strikeOuts")),
                "ibb": safe_int(stat.get("intentionalWalks")),
                "h_ground_outs": safe_int(stat.get("groundOuts")),
                "h_air_outs": safe_int(stat.get("airOuts")),
                "pitches_seen": safe_int(stat.get("numberOfPitches")),
                "lob": safe_int(stat.get("leftOnBase")),
                "sac_bunts": safe_int(stat.get("sacBunts")),
                "sac_flies": safe_int(stat.get("sacFlies")),
                "ci": safe_int(stat.get("catchersInterference")),
                "babip": safe_float(stat.get("babip")),
                "go_ao": safe_float(stat.get("groundOutsToAirouts")),
                "sb_pct": str(stat.get("stolenBasePercentage", "")),
                "cs_pct": str(stat.get("caughtStealingPercentage", "")),
                "ab_per_hr": safe_float(stat.get("atBatsPerHomeRun")),
            }
        )


def apply_advanced_fields(stat_doc: dict, group_name: str, stat: dict):
    if group_name == "hitting":
        for api_key, local_key in [
            ("reachedOnError", "roe"),
            ("walkOffs", "wo"),
            ("gidpOpp", "gidpo"),
            ("extraBaseHits", "xbh"),
        ]:
            val = safe_int(stat.get(api_key))
            if val is not None:
                stat_doc[local_key] = val
        for api_key, local_key in [
            ("babip", "babip"),
            ("pitchesPerPlateAppearance", "pitches_per_pa"),
        ]:
            val = safe_float(stat.get(api_key))
            if val is not None:
                stat_doc[local_key] = val
    elif group_name == "pitching":
        for api_key, local_key in [
            ("qualityStarts", "qs"),
            ("bequeathedRunners", "bqr"),
            ("bequeathedRunnersScored", "bqr_s"),
            ("gidpOpp", "p_gidpo"),
            ("runSupport", "run_support"),
        ]:
            val = safe_int(stat.get(api_key))
            if val is not None:
                stat_doc[local_key] = val
        for api_key, local_key in [
            ("runsScoredPer9", "rs_per_9"),
            ("babip", "p_babip"),
            ("pitchesPerPlateAppearance", "pitches_per_pa"),
        ]:
            val = safe_float(stat.get(api_key))
            if val is not None:
                stat_doc[local_key] = val
