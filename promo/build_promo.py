"""宣傳影片建置入口。

    python -m promo.build_promo             # 1080p 完整建置
    python -m promo.build_promo --4k        # 4K 版本（底片升到 8K，耗時約 2.5 倍）
    python -m promo.build_promo --reuse     # 沿用既有底片，只重跑合成（調節奏時用）

流程：擷取底片 → 渲染字卡與說明條 → 依分鏡組裝時間軸 → 合成配樂 → 編碼 mp4。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from promo import config


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="建置 TwbExpats 宣傳影片")
    ap.add_argument("--4k", dest="four_k", action="store_true",
                    help="輸出 3840×2160（底片同步升到 7680×4320 以維持縮放無損）")
    ap.add_argument("--reuse", action="store_true",
                    help="沿用既有底片，只重跑合成（調節奏時用）")
    return ap.parse_args()


# 設定檔必須在其他模組取用解析度常數之前決定
_ARGS = _parse_args() if __name__ == "__main__" else None
if _ARGS and _ARGS.four_k:
    config.set_profile("4k")

from promo import storyboard as sb                        # noqa: E402
from promo.audio import music                             # noqa: E402
from promo.capture import browser, scenes                 # noqa: E402
from promo.compose import camera, cards, lower_third, timeline   # noqa: E402
from promo.compose.timeline import CardSegment, ShotSegment      # noqa: E402


def _secs_to_frames(seconds: float) -> int:
    return max(1, int(round(seconds * config.FPS)))


def capture_plates(reuse: bool) -> dict:
    """擷取（或沿用）全片所需底片。"""
    flip_frames = _secs_to_frames(sb.SORT_ANIM_DUR)
    expand_frames = _secs_to_frames(sb.EXPAND_ANIM_DUR)
    # 影片段落全程都在播放，需要與段落等長的逐格畫面
    video_frames = _secs_to_frames(sb.D_PITCH_VIDEO)

    if reuse and scenes.MANIFEST.exists():
        print("→ 沿用既有底片")
        return _load_manifest()

    print("→ 擷取網站底片")
    t0 = time.time()
    plates = scenes.capture_all(flip_frames, expand_frames, video_frames)
    print(f"   完成，耗時 {time.time() - t0:.0f}s")
    return plates


def _load_manifest() -> dict:
    """從 manifest 重建 Plate/Sequence 物件，跳過瀏覽器。"""
    import json

    data = json.loads(scenes.MANIFEST.read_text(encoding="utf-8"))
    out: dict = {}
    for name, meta in data.items():
        boxes = {k: tuple(v) for k, v in meta["boxes"].items()}
        w, h = meta["size"]
        if meta["type"] == "Sequence":
            paths = sorted((config.PLATE_DIR / name).glob("*.png"))
            out[name] = scenes.Sequence(
                name, paths, w, h, boxes, origin_y=meta.get("origin_y", 0)
            )
        else:
            out[name] = scenes.Plate(name, config.PLATE_DIR / f"{name}.png", w, h, boxes)
    return out


def render_overlays() -> tuple[dict[str, cards.CardClip], list]:
    """渲染所有字卡與說明條。"""
    print("→ 渲染字卡與說明條")
    t0 = time.time()
    logo = cards.load_logo()
    card_dir = config.WORK_DIR / "cards"

    with browser.card_page() as page:
        clips = {
            "intro": cards.render_card(
                page, cards.intro_html(logo, sb.INTRO_TITLE, sb.INTRO_SUBTITLE),
                _secs_to_frames(sb.D_INTRO), card_dir, "intro"),
            "outro": cards.render_card(
                page, cards.outro_html(logo, sb.OUTRO_URL, sb.OUTRO_TAGLINE),
                _secs_to_frames(sb.D_OUTRO), card_dir, "outro"),
        }
        captions = lower_third.render(page, sb.ALL_CAPTIONS, config.WORK_DIR / "captions")

    print(f"   完成，耗時 {time.time() - t0:.0f}s")
    return clips, captions


def _plate_box(seq, key: str) -> tuple[int, int, int, int]:
    """把 viewport 序列上的區域換算成長底片座標 —— 游標軌跡是在長底片上跑的。"""
    x, y, w, h = seq.boxes[key]
    return (x, y + seq.origin_y, w, h)


def build_segments(plates: dict, clips: dict, captions: list) -> list:
    """依分鏡組裝所有段落。

    全片只有四處轉場。三次分頁切換（進階數據 / 比賽紀錄 / 數據圖表）刻意**不**轉場：
    游標按下按鈕後，鏡頭停在同一個鏡位，只把底片換成另一個分頁的底片。
    """
    by_text = {(c.caption.main, c.caption.at): c for c in captions}

    def pick(group) -> list:
        return [by_text[(c.main, c.at)] for c in group]

    home_shot = sb.shot_home(plates["home"], camera)
    sort_shot = sb.shot_home_sort(plates["home_flip"], camera, home_shot.current)
    click_shot = sb.shot_home_click(plates["home_flip"], camera, sort_shot.current)
    profile_shot = sb.shot_profile_reveal(plates["profile"], camera)
    profile_tab_shot = sb.shot_profile_tab(plates["profile"], camera, profile_shot.current)
    expand_shot = sb.shot_expand(plates["gamelog_expand"], camera)
    pitchlog_shot = sb.shot_pitchlog(
        plates["gamelog_expanded"], camera, expand_shot.current, plates["pitch_video"]
    )

    return [
        CardSegment("intro", clips["intro"].paths),
        ShotSegment("home", home_shot, pick(sb.CAPTIONS_HOME),
                    transition_in=sb.T_HOME),
        # 排序切換緊接首頁瀏覽，中間不轉場 —— 這是同一個畫面的延續
        ShotSegment("home_sort", sort_shot, pick(sb.CAPTIONS_HOME_SORT),
                    cursor_track=sb.sort_cursor(plates["home_flip"].boxes["btn_recent"])),
        # 推近鄧愷威的卡片並點擊，緊接首頁排序，中間不轉場 —— 仍是同一個畫面的延續
        ShotSegment("home_click", click_shot, [],
                    cursor_track=sb.feature_click_cursor(plates["home_flip"].boxes["card_feature"])),
        ShotSegment("profile", profile_shot, pick(sb.CAPTIONS_PROFILE),
                    transition_in=sb.T_PROFILE),
        # 鏡頭退回分頁列，游標按下「進階數據」
        ShotSegment("profile_tab", profile_tab_shot, [],
                    cursor_track=sb.tab_cursor(
                        plates["profile"].boxes["tab_advanced"], sb.TAB_ADVANCED_AT)),
        # 分頁切換：鏡位不變，只換底片。段末游標按下「比賽紀錄」
        ShotSegment("advanced", sb.shot_advanced(plates["advanced"], camera),
                    pick(sb.CAPTIONS_ADVANCED),
                    cursor_track=sb.tab_cursor(
                        plates["advanced"].boxes["tab_gamelogs"], sb.TAB_GAMELOGS_AT,
                        offset=(1350, 1050), bow=-0.16)),
        ShotSegment("gamelogs_intro",
                    sb.shot_gamelogs_intro(
                        plates["gamelog_collapsed"], plates["gamelog_expand"], camera),
                    []),
        ShotSegment("expand", expand_shot, pick(sb.CAPTIONS_EXPAND),
                    cursor_track=sb.expand_cursor(plates["gamelog_expand"].boxes["arrow"])),
        ShotSegment("pitchlog", pitchlog_shot, pick(sb.CAPTIONS_PITCHLOG),
                    cursor_track=sb.pitch_video_cursor(
                        _plate_box(plates["pitch_video"], "video_btn"))),
        # 點擊後畫面換到影片底片，但鏡位不變 —— 中間不轉場才看得出是同一次操作。
        # 段末游標按下彈窗右上角的 ×
        ShotSegment("pitch_video", sb.shot_pitch_video(plates["pitch_video"], camera),
                    pick(sb.CAPTIONS_PITCH_VIDEO),
                    cursor_track=sb.close_video_cursor(
                        plates["pitch_video"].boxes["video_close"])),
        # 彈窗關掉（底片換回沒有彈窗的逐球表），快速上滑回分頁列並按下「數據圖表」
        ShotSegment("plot_tab",
                    sb.shot_plot_tab(plates["gamelog_expanded"], camera, plates["pitch_video"]),
                    [],
                    cursor_track=sb.tab_cursor(
                        plates["gamelog_expanded"].boxes["tab_plot"], sb.TAB_PLOT_AT,
                        offset=(-1200, 1100), bow=0.20, hold_after=0.15)),
        # 賽季走勢圖，游標按一下「數據」下拉
        ShotSegment("plot_trend", sb.shot_plot_trend(plates["plot"], camera),
                    pick(sb.CAPTIONS_PLOT_TREND),
                    cursor_track=sb.trend_stat_cursor(plates["plot"].boxes["trend_stat"])),
        # 換好數據的底片，用一次短交叉溶接接上 —— 看起來就是圖表重畫了
        ShotSegment("plot", sb.shot_plot(plates["plot_alt"], camera),
                    pick(sb.CAPTIONS_PLOT), transition_in=sb.T_TREND_SWAP),
        CardSegment("outro", clips["outro"].paths, transition_in=sb.T_OUTRO),
    ]


def encode(frame_dir: Path, audio: Path, out: Path, n_frames: int) -> None:
    """把幀序列與配樂編碼成 mp4。"""
    print("→ 編碼影片")
    out.parent.mkdir(parents=True, exist_ok=True)
    # 4K 的像素密度讓壓縮瑕疵不易察覺，稍微放寬 CRF 並改用較快的 preset，
    # 否則檔案會膨脹到數百 MB、編碼時間也翻倍。
    is_4k = config.PROFILE == "4k"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(config.FPS),
        "-i", str(frame_dir / "f%05d.png"),
        "-i", str(audio),
        "-c:v", "libx264",
        "-preset", "medium" if is_4k else "slow",
        "-crf", "20" if is_4k else "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    args = _ARGS or _parse_args()

    config.ensure_dirs()
    started = time.time()
    print(f"→ 設定檔 {config.PROFILE}："
          f"輸出 {config.WIDTH}×{config.HEIGHT}，底片 {config.PLATE_W}×{config.PLATE_H}")

    plates = capture_plates(args.reuse)
    clips, captions = render_overlays()
    segments = build_segments(plates, clips, captions)

    expected = timeline.total_frames(segments)
    print(f"→ 合成 {expected} 幀（{expected / config.FPS:.1f} 秒）")

    last = [0.0]

    def progress(done: int, total: int) -> None:
        pct = done / total
        if pct - last[0] >= 0.05 or done == total:
            last[0] = pct
            sys.stdout.write(f"\r   {done}/{total} 幀 ({pct * 100:.0f}%)")
            sys.stdout.flush()
            if done == total:
                sys.stdout.write("\n")

    t0 = time.time()
    n = timeline.render(segments, config.FRAME_DIR, progress=progress)
    print(f"   完成，耗時 {time.time() - t0:.0f}s")

    print("→ 合成配樂")
    music.build(duration=n / config.FPS)

    encode(config.FRAME_DIR, config.OUT_AUDIO, config.OUT_VIDEO, n)

    size_mb = config.OUT_VIDEO.stat().st_size / 1e6
    print(
        f"\n完成：{config.OUT_VIDEO}\n"
        f"  {config.WIDTH}×{config.HEIGHT} · {config.FPS}fps · "
        f"{n / config.FPS:.1f}s · {size_mb:.1f} MB\n"
        f"  總耗時 {time.time() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
