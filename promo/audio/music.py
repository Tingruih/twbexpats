"""Lo-fi 背景配樂合成器。

全部用 numpy 從正弦波與噪音合成，不依賴任何外部音訊素材，因此沒有版權問題。
編曲刻意單薄：影片主角是畫面，配樂只負責提供時間感與溫度。
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy import signal

from promo import config

# ── 編曲 ────────────────────────────────────────────────────────
# 下行的溫暖進行，四小節一循環。每個和弦以 MIDI 音高列出。
CHORDS = [
    ("Fmaj9", [53, 57, 60, 64, 67]),   # F A C E G
    ("Em7", [52, 55, 59, 62]),         # E G B D
    ("Dm7", [50, 53, 57, 60]),         # D F A C
    ("Cmaj7", [48, 52, 55, 59]),       # C E G B
]
SWING = 0.58        # 第一個八分音符佔該拍的比例；> 0.5 即為 swing
LOWPASS_HZ = 3500   # lo-fi 的核心：砍掉高頻的空氣感
WOBBLE_HZ = 0.7     # 磁帶抖動頻率
WOBBLE_DEPTH = 0.004


def midi_to_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _env(n: int, attack: float, decay: float, sr: int) -> np.ndarray:
    """線性起音 + 指數衰減的包絡。"""
    env = np.exp(-np.arange(n) / (decay * sr))
    a = max(1, int(attack * sr))
    if a < n:
        env[:a] *= np.linspace(0.0, 1.0, a)
    return env


def _add(buf: np.ndarray, sample: np.ndarray, at: int) -> None:
    """把一個音疊加到緩衝區，自動處理尾端截斷。"""
    end = min(at + len(sample), len(buf))
    if end > at:
        buf[at:end] += sample[: end - at]


def _rhodes(freq: float, dur: float, sr: int, amp: float = 1.0) -> np.ndarray:
    """電鋼琴音色：正弦基頻 + 遞減的泛音，另加一層短促的敲擊泛音。"""
    n = int(dur * sr)
    t = np.arange(n) / sr
    tone = (
        1.00 * np.sin(2 * np.pi * freq * t)
        + 0.32 * np.sin(2 * np.pi * freq * 2 * t)
        + 0.12 * np.sin(2 * np.pi * freq * 3 * t)
        + 0.05 * np.sin(2 * np.pi * freq * 5 * t)
    )
    # Rhodes 特有的金屬敲擊聲，衰減得比琴body快得多
    bell = 0.18 * np.sin(2 * np.pi * freq * 7 * t) * np.exp(-t / 0.12)
    return amp * (tone + bell) * _env(n, 0.012, dur * 0.45, sr)


def _sub_bass(freq: float, dur: float, sr: int, amp: float = 1.0) -> np.ndarray:
    """低八度正弦，加一點軟飽和讓它在小喇叭上也聽得見。"""
    n = int(dur * sr)
    t = np.arange(n) / sr
    tone = np.sin(2 * np.pi * freq * t) + 0.15 * np.sin(2 * np.pi * freq * 2 * t)
    return amp * np.tanh(tone * 1.4) * _env(n, 0.02, dur * 0.5, sr)


def _kick(sr: int, amp: float = 1.0) -> np.ndarray:
    """60Hz 掃至 45Hz 的正弦，前端補一點點擊聲。"""
    dur = 0.32
    n = int(dur * sr)
    t = np.arange(n) / sr
    freq = 60 - 15 * (1 - np.exp(-t / 0.05))
    phase = 2 * np.pi * np.cumsum(freq) / sr
    body = np.sin(phase) * np.exp(-t / 0.09)
    click = 0.25 * np.random.default_rng(7).normal(0, 1, n) * np.exp(-t / 0.004)
    return amp * (body + click)


def _hat(sr: int, amp: float = 1.0, dur: float = 0.055) -> np.ndarray:
    """帶通白噪音的閉合 hi-hat。"""
    n = int(dur * sr)
    noise = np.random.default_rng(13).normal(0, 1, n)
    sos = signal.butter(4, [6000, 11000], btype="bandpass", fs=sr, output="sos")
    return amp * signal.sosfilt(sos, noise) * np.exp(-np.arange(n) / (0.012 * sr))


def _tape_wobble(x: np.ndarray, sr: int) -> np.ndarray:
    """以緩慢的正弦調變讀取位置，模擬磁帶轉速不穩造成的音高飄移。"""
    n = len(x)
    t = np.arange(n) / sr
    offset = WOBBLE_DEPTH * sr * np.sin(2 * np.pi * WOBBLE_HZ * t)
    idx = np.clip(np.arange(n) + offset, 0, n - 1)
    return np.interp(idx, np.arange(n), x)


def _compress(x: np.ndarray, sr: int, thresh_db: float = -30.0, ratio: float = 4.0,
              attack: float = 0.008, release: float = 0.18) -> np.ndarray:
    """軟膝壓縮器。

    壓平 kick 的瞬間峰值，讓整體 RMS 得以拉高 —— 沒有這一步，標準化後的音樂
    會安靜到在影片裡幾乎聽不見。同時這也是 lo-fi 類型典型的呼吸(pumping)感來源。
    """
    eps = 1e-9
    # 單極點包絡追蹤器，起音與釋放用不同時間常數
    a_att = np.exp(-1.0 / (attack * sr))
    a_rel = np.exp(-1.0 / (release * sr))
    rect = np.abs(x)
    env = np.empty_like(rect)
    prev = 0.0
    for i in range(len(rect)):
        coeff = a_att if rect[i] > prev else a_rel
        prev = coeff * prev + (1 - coeff) * rect[i]
        env[i] = prev

    env_db = 20 * np.log10(env + eps)
    over = np.maximum(env_db - thresh_db, 0.0)
    gain_db = -over * (1 - 1 / ratio)
    return x * (10 ** (gain_db / 20))


def synthesize(duration: float, sr: int = config.SAMPLE_RATE) -> np.ndarray:
    """合成指定長度的立體聲配樂，回傳形狀 (n, 2) 的 float32 陣列。"""
    bpm = config.MUSIC_BPM
    beat = 60.0 / bpm
    bar = beat * 4

    # 多算兩小節，讓尾端淡出不會切到音符的起音
    n = int((duration + bar * 2) * sr)
    keys = np.zeros(n, dtype=np.float64)
    bass = np.zeros(n, dtype=np.float64)
    drums = np.zeros(n, dtype=np.float64)

    n_bars = int(np.ceil((duration + bar * 2) / bar))
    for b in range(n_bars):
        bar_at = int(b * bar * sr)
        _, notes = CHORDS[b % len(CHORDS)]

        # 電鋼琴：第 1 拍完整和弦，第 3 拍只用上聲部，避免過於厚重
        for beat_idx, subset in ((0, notes), (2, notes[1:])):
            at = bar_at + int(beat_idx * beat * sr)
            for i, note in enumerate(subset):
                # 琶音式的細微參差，讓和弦不像電腦一次按下
                stagger = int(i * 0.018 * sr)
                voice = _rhodes(midi_to_hz(note), bar * 0.9, sr, amp=0.26 / len(subset) ** 0.5)
                _add(keys, voice, at + stagger)

        # Bass：根音低一個八度，落在第 1 與第 3 拍後半
        root = notes[0] - 12
        _add(bass, _sub_bass(midi_to_hz(root), beat * 1.8, sr, 0.5), bar_at)
        _add(bass, _sub_bass(midi_to_hz(root), beat * 0.8, sr, 0.28),
             bar_at + int(2.5 * beat * sr))

        # Kick：第 1、3 拍
        for beat_idx in (0, 2):
            _add(drums, _kick(sr, 0.55), bar_at + int(beat_idx * beat * sr))

        # Hi-hat：八分音符加 swing，反拍稍弱
        for beat_idx in range(4):
            base = bar_at + int(beat_idx * beat * sr)
            _add(drums, _hat(sr, 0.17), base)
            _add(drums, _hat(sr, 0.10), base + int(SWING * beat * sr))

    mix = keys + bass + drums

    # ── Lo-fi 質感處理 ──────────────────────────────────────────
    sos = signal.butter(2, LOWPASS_HZ, btype="low", fs=sr, output="sos")
    mix = signal.sosfilt(sos, mix)
    mix = _tape_wobble(mix, sr)

    # 極輕的底噪，補上類比的溫度
    rng = np.random.default_rng(29)
    hiss = rng.normal(0, 1, len(mix))
    hiss = signal.sosfilt(signal.butter(2, 8000, btype="low", fs=sr, output="sos"), hiss)
    mix += hiss * 0.0022

    mix = mix[: int(duration * sr)]

    # ── 動態與音量 ──────────────────────────────────────────────
    # 順序很重要：壓縮 → soft clip 壓平殘餘峰值 → 最後才對齊 RMS。
    # 若把 RMS 標準化排在峰值處理之前，限峰的全域衰減會再次拉低整體音量，
    # 使最終響度偏離目標數 dB。以 RMS（而非峰值）為對齊基準，是因為聽感上的
    # 響度由 RMS 決定，不該被單一 kick 峰值綁架。
    mix = _compress(mix, sr)

    mix = mix / (np.max(np.abs(mix)) or 1.0)
    mix = np.tanh(mix * 1.6) / np.tanh(1.6)   # 溫和的軟削峰，同時帶來一點類比飽和

    fade_in = int(2.0 * sr)
    fade_out = int(4.0 * sr)
    mix[:fade_in] *= np.linspace(0, 1, fade_in) ** 2
    mix[-fade_out:] *= np.linspace(1, 0, fade_out) ** 2

    rms = np.sqrt(np.mean(mix ** 2)) or 1.0
    mix = mix / rms * (10 ** (config.MUSIC_RMS_DBFS / 20))

    ceiling = 10 ** (config.MUSIC_PEAK_CEILING_DBFS / 20)
    peak = np.max(np.abs(mix))
    if peak > ceiling:
        mix *= ceiling / peak

    # 立體聲：右聲道延遲 11ms 製造寬度，但低頻保持置中
    delay = int(0.011 * sr)
    right = np.concatenate([np.zeros(delay), mix[:-delay]])
    return np.stack([mix, mix * 0.35 + right * 0.65], axis=1).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, sr: int = config.SAMPLE_RATE) -> None:
    """輸出 16-bit PCM WAV。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def build(duration: float = config.TOTAL_SECONDS, path: Path = config.OUT_AUDIO) -> Path:
    """合成配樂並寫檔，回傳檔案路徑。"""
    write_wav(path, synthesize(duration))
    return path


if __name__ == "__main__":
    out = build()
    print(f"配樂已輸出：{out}")
