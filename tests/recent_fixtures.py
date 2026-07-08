"""共用 pitch dict fixture — 欄位齊全的 Tier 1 MLB 球，測試以 overrides 客製。"""


def make_pitch(**overrides) -> dict:
    base = dict(
        game_pk=776911, inning=1,
        pitch_type="FF", pitch_name="Four-Seam Fastball",
        result_code="C", result_desc="Called Strike",
        is_strike=True, is_ball=False, is_in_play=False,
        zone=5, start_speed=95.0, end_speed=87.0, extension=6.5,
        plate_time=0.40, type_confidence=0.95,
        strike_zone_top=3.4, strike_zone_bottom=1.6,
        pfx_x=-6.0, pfx_z=14.0, px=0.0, pz=2.5,
        x0=-1.5, z0=5.8, vx0=2.0, vy0=-135.0, vz0=-5.0,
        ax=-8.0, ay=25.0, az=-15.0,
        ivb=15.0, hb=8.0, spin_rate=2300, spin_dir=210.0,
        break_angle=None, break_length=None, break_y=None, break_vertical=None,
        ev=None, la=None, hit_distance=None, trajectory="", hit_location=None,
        hit_coord_x=None, hit_coord_y=None, hardness="",
        balls=0, strikes=1, pre_balls=0, pre_strikes=0, pre_outs=0, outs=0,
        batter_id=592885, pitcher_id=678906, bat_side="R", pitch_hand="R",
        is_pa_final=False, pa_event="", pa_event_desc="", runners=None,
        play_id="b339cea8-e12d-340f-adbc-a655fb63aaed", pitch_number=1,
    )
    base.update(overrides)
    return base


def make_untracked_pitch(**overrides) -> dict:
    """Tier 3（AA/A+）球：無追蹤欄位，只有結果。"""
    p = make_pitch(
        pitch_type="", pitch_name="", zone=None, start_speed=None,
        end_speed=None, extension=None, px=None, pz=None,
        x0=None, z0=None, vx0=None, vy0=None, vz0=None,
        ax=None, ay=None, az=None, ivb=None, hb=None,
        spin_rate=None, spin_dir=None,
        play_id="07821736-0016-0013-000c-f08cd117d70a",
    )
    p.update(overrides)
    return p
