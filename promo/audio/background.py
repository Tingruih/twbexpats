"""Prepare the provided background track for the promo video's final mix."""
from __future__ import annotations

import subprocess
from pathlib import Path

from promo import config


def build(
    duration: float = config.TOTAL_SECONDS,
    source: Path = config.SOURCE_MUSIC,
    path: Path = config.OUT_AUDIO,
) -> Path:
    """Trim, level, and fade the source track into a video-length PCM WAV."""
    if duration <= 0:
        raise ValueError("配樂長度必須大於 0 秒")
    if not source.is_file():
        raise FileNotFoundError(f"找不到背景音樂：{source}")

    path.parent.mkdir(parents=True, exist_ok=True)

    fade_in = min(config.MUSIC_FADE_IN_SECONDS, duration / 2)
    fade_out = min(config.MUSIC_FADE_OUT_SECONDS, duration / 2)
    fade_out_at = max(0.0, duration - fade_out)
    filters = ",".join([
        (
            f"loudnorm=I={config.MUSIC_LOUDNESS_LUFS}:"
            f"TP={config.MUSIC_TRUE_PEAK_DBFS}:LRA=11"
        ),
        f"afade=t=in:st=0:d={fade_in:.3f}",
        f"afade=t=out:st={fade_out_at:.3f}:d={fade_out:.3f}",
    ])

    # Loop defensively so a future, shorter replacement track cannot cut the
    # video short. The current source is already longer than the promo.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-stream_loop", "-1",
        "-i", str(source),
        "-t", f"{duration:.6f}",
        "-af", filters,
        "-ar", str(config.SAMPLE_RATE),
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    return path


if __name__ == "__main__":
    out = build()
    print(f"配樂已輸出：{out}")
