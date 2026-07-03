"""Per-game pitch-log JSON payloads (lazy-loaded by the browser)."""

from pathlib import Path

from ..util.json import dumps_json


def summarize_pitch_for_display(p: dict) -> dict:
    """Thin projection of a pitch dict for use in the per-game expandable row."""
    return {
        "inning": p.get("inning"),
        "pitch_type": p.get("pitch_type", ""),
        "pitch_name": p.get("pitch_name", ""),
        "speed": p.get("start_speed"),
        "zone": p.get("zone"),
        "result": p.get("result_desc") or p.get("result_code", ""),
        "ev": p.get("ev"),
        "la": p.get("la"),
        "ivb": p.get("ivb"),
        "hb": p.get("hb"),
        "spin": p.get("spin_rate"),
        "extension": p.get("extension"),
        "pa_event": p.get("pa_event_desc") if p.get("is_pa_final") else "",
        "balls": p.get("balls"),
        "strikes": p.get("strikes"),
    }


def write_pitch_log_files(logs_by_year: dict, out_dir: Path,
                          normalized_base_url: str, mlb_id) -> None:
    """Write summarised pitch logs as external JSON and annotate each log row.

    Summarised pitch logs are lazy-loaded by the browser when a game row is
    expanded. This keeps player HTML small.  Mutates each log Obj, setting
    ``pitch_data_url`` and ``pitch_count``.
    """
    pitchlog_dir = out_dir / "data" / "pitchlogs" / str(mlb_id)
    pitchlog_url_base = f"{normalized_base_url}data/pitchlogs/{mlb_id}"
    for y_key in logs_by_year:
        for log in logs_by_year[y_key]:
            if log.pitches_json:
                pitch_display = [
                    summarize_pitch_for_display(p) for p in log.pitches_json
                ]
                if pitch_display:
                    pitchlog_dir.mkdir(parents=True, exist_ok=True)
                    pitchlog_filename = f"{log.game_id}.json"
                    (pitchlog_dir / pitchlog_filename).write_text(
                        dumps_json(pitch_display), encoding="utf-8"
                    )
                    log.pitch_data_url = f"{pitchlog_url_base}/{pitchlog_filename}"
                    log.pitch_count = len(pitch_display)
                else:
                    log.pitch_data_url = ""
                    log.pitch_count = 0
            else:
                log.pitch_data_url = ""
                log.pitch_count = 0
