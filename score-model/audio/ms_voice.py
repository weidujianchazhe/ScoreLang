# -*- coding: utf-8 -*-
"""人声接口（歌声合成的接入点）。见模块顶部契约。

现状：**没有真正的歌声合成器**，但接口先定死，避免以后"人唱"变成外挂。

契约
----
`mix_syllable(note_wave, f0, t, *, text, tone, amp, sr) -> np.ndarray`
  · 输入：该音的合成波形（float32，长度 len(t)）、基频 f0、时间轴 t、歌词文本、声调、幅度
  · 输出：与输入等长的波形（人声成分已混入）
  · 要求：**不改变音高语义**——音高由 `f0` 决定；`tone` 只影响共振峰/音高微弯

声调：0=未标 1=阴平 2=阳平 3=上声 4=去声 5=轻声。

未来的真实合成器（VOCALOID / Synthesizer V / DiffSinger）只需替换本文件实现，
`make_audio` 与 `.ms` 格式都不用动。
"""
from __future__ import annotations

import numpy as np

LANGS = ("zh", "en", "fr", "ja", "ru")

VOWELS = {
    "a": (800, 1200, 2500),
    "e": (500, 1800, 2500),
    "i": (300, 2300, 3000),
    "o": (500, 900, 2400),
    "u": (320, 800, 2300),
}

_FINALS = ("iang", "uang", "iong", "ang", "eng", "ing", "ong", "ai", "ei", "ao", "ou",
           "an", "en", "in", "un", "ia", "ie", "iu", "ua", "uo", "ui", "a", "o", "e", "i", "u")


def vowel_of(text: str) -> str:
    t = (text or "").strip().lower()
    for f in _FINALS:
        if t.endswith(f):
            for v in "aoeiu":
                if v in f:
                    return v
    return "a"


def tone_shift(tone: int) -> tuple[float, float]:
    """声调 → (共振峰缩放, 音高微弯半音)。"""
    return {
        1: (1.00, 0.00),
        2: (1.02, +0.20),
        3: (0.98, -0.25),
        4: (1.04, -0.30),
        5: (0.99, 0.00),
    }.get(tone or 0, (1.00, 0.00))


def _formant_gain(freq: np.ndarray, formants) -> np.ndarray:
    g = np.zeros_like(freq)
    for center, bw in formants:
        g += np.exp(-((freq - center) ** 2) / (2.0 * bw ** 2))
    return g


def mix_syllable(wave: np.ndarray, f0: float, t: np.ndarray, *, text: str,
                 tone: int, amp: float, sr: int) -> np.ndarray:
    """把元音共振峰混到音符波形上（占位实现，界面已定）。"""
    v = vowel_of(text)
    scale, bend = tone_shift(tone)
    formants = [(c * scale, bw) for c, bw in
                ((VOWELS[v][0], 90.0), (VOWELS[v][1], 110.0), (VOWELS[v][2], 160.0))]

    f0_use = f0 * (2 ** (bend / 12))
    vocal = np.zeros_like(t)
    nyq = sr / 2.1
    for h in range(1, 40):
        fh = f0_use * h
        if fh >= nyq:
            break
        weight = float(_formant_gain(np.array([fh]), formants)[0])
        if weight < 0.02:
            continue
        vocal += (weight * 0.5 / h) * np.sin(2 * np.pi * fh * t)

    env = np.minimum(1.0, t / 0.03) * np.exp(-t / 1.2)
    vocal = vocal * env * amp
    return (wave * 0.75 + vocal.astype(np.float32) * 0.5).astype(np.float32)


def phonemes(lang: str, text: str) -> list[str]:
    """语言 → 音素（占位）。真实实现接各语言 G2P；当前只做长度一致的占位。"""
    if lang not in LANGS:
        raise ValueError(f"未预留的语言：{lang!r}（已预留 {LANGS}）")
    return [f"{lang}:{ch}" for ch in (text or "")]
