# -*- coding: utf-8 -*-
"""中文人声合成：VocalPlan → 波形。

  · 浊音：谐波叠加，按 F1/F2/F3 高斯包络加权
  · 清音：带通噪声（爆破=短促、摩擦=持续、塞擦=先爆后摩）
  · 鼻音/边音：低共振峰浊音
  · 声调：TONE_CONTOURS 调制 f0；V3 拖腔：整段连续，不重复声母
  · 气声：噪声走同一组共振峰
"""
from __future__ import annotations

import numpy as np

SR = 44100

# 声母部位的共振峰 locus（协同发音起点）
try:
    import phoneme_factors as _pf
except Exception:
    _pf = None

LOCUS_F2 = {"bilabial": 800, "labiodental": 1200, "alveolar": 1800,
            "retroflex": 1900, "palatal": 2200, "velar": 2000}
NOISE_CENTER = {"bilabial": 900, "labiodental": 4000, "alveolar": 6000,
                "retroflex": 3500, "palatal": 4500, "velar": 1800}
NASAL_FORMANTS = {"bilabial": (250, 1000, 2200), "alveolar": (250, 1500, 2500),
                  "velar": (250, 2000, 2600)}


def _semitones_to_hz(semi: float) -> float:
    return 440.0 * 2 ** ((semi - 69) / 12)


def _formant_gain(freq, formants, bw=110.0):
    g = np.zeros_like(freq, dtype=np.float64)
    for f in formants:
        g += np.exp(-0.5 * ((freq - f) / bw) ** 2)
    return g


def _harmonic_vowel(n, f0_curve, formants, sr, phase0=0.0):
    t = np.arange(n) / sr
    phase = 2 * np.pi * np.cumsum(f0_curve) / sr + phase0
    out = np.zeros(n, dtype=np.float64)
    h = 1
    while h <= 40:
        f = float(np.mean(f0_curve)) * h
        if f > sr / 2.2:
            break
        g = float(_formant_gain(np.array([f]), formants)[0])
        out += (g / h) * np.sin(phase * h)
        h += 1
    return out


def _band_noise(n, center, bw, sr, rng):
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    mask = np.exp(-0.5 * ((freqs - center) / bw) ** 2)
    return np.fft.irfft(X * mask, n=n)


def _tone_curve(tone: int, n: int) -> np.ndarray:
    from pinyin import TONE_CONTOURS
    pts = TONE_CONTOURS.get(tone, TONE_CONTOURS[1])
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    return np.interp(np.linspace(0, 1, n), xs, ys)


def _f0_curve(base_hz: float, tone: int, n: int, vibrato, sr) -> np.ndarray:
    f0 = np.full(n, base_hz, dtype=np.float64)
    f0 *= 2 ** ((_tone_curve(tone, n) - 0.6) * 4 / 12)     # ±2 半音
    if vibrato[0] > 0:
        t = np.arange(n) / sr
        f0 *= 2 ** ((vibrato[1] / 100.0) * np.sin(2 * np.pi * vibrato[0] * t) / 12)
    return f0


def _initial_wave(seg, n, sr, rng) -> np.ndarray:
    """声母段：爆破=闭音+爆破+送气；摩擦=持续噪声；塞擦=爆破+衰减噪声；鼻/边=低共振峰浊音。"""
    if seg.manner == "plosive":
        out = np.zeros(n)
        close = int(n * 0.45)
        burst = max(1, int(0.008 * sr))
        center = NOISE_CENTER.get(seg.place, 3000)
        noise = _band_noise(min(burst, n - close), center, center * 0.7, sr, rng)
        out[close:close + len(noise)] += 1.0 * noise
        if seg.aspirated:
            rest = n - close - len(noise)
            if rest > 0:
                asp = _band_noise(rest, center * 0.8, center * 0.8, sr, rng)
                out[close + len(noise):] += 0.35 * asp * np.linspace(1, 0.2, rest)
        return out
    if seg.manner == "affricate":
        burst = max(1, int(0.012 * sr))
        center = NOISE_CENTER.get(seg.place, 3500)
        noise = _band_noise(n, center, center * 0.6, sr, rng)
        env = np.exp(-np.linspace(0, 3.5, n))
        env[:min(burst, n)] = 1.0
        return 0.8 * noise * env
    if seg.manner in ("fricative",):
        center = NOISE_CENTER.get(seg.place, 4000)
        return 0.7 * _band_noise(n, center, center * 0.55, sr, rng) * np.linspace(0.8, 1.0, n)
    if seg.manner in ("nasal", "lateral"):
        fmt = NASAL_FORMANTS.get(seg.place, (250, 1200, 2400))
        f0 = np.full(n, 180.0)
        wav = _harmonic_vowel(n, f0, fmt, sr)
        return 0.35 * wav * np.linspace(0.7, 1.0, n)
    if seg.manner == "approximant":
        fmt = NASAL_FORMANTS.get(seg.place, (300, 1300, 2400))
        f0 = np.full(n, 190.0)
        return 0.4 * _harmonic_vowel(n, f0, fmt, sr)
    return np.zeros(n)


def _render(syl, f0_base, n, sr, vibrato, rng) -> np.ndarray:
    out = np.zeros(n, dtype=np.float64)
    segs = syl.segments or []
    total = sum(s.dur_us for s in segs) or 1
    pos = 0
    prev_place = None
    for seg in segs:
        m = max(1, int(round(n * seg.dur_us / total)))
        m = min(m, n - pos)
        if m <= 0:
            break
        tone = int(getattr(seg, "tone", 0) or 0) or syl.surface_tone   # 段级声调优先
        if seg.kind == "initial" and not seg.voiced:
            out[pos:pos + m] += _initial_wave(seg, m, sr, rng)
            prev_place = seg.place
        else:
            formants = seg.formants
            if seg.kind == "nucleus" and prev_place in LOCUS_F2:
                # 协同发音：前 18% 从 locus 滑到目标 F2
                gl = max(1, int(m * 0.18))
                locus = (formants[0], LOCUS_F2[prev_place], formants[2])
                f0 = _f0_curve(f0_base, tone, m, vibrato, sr)
                wav = np.zeros(m)
                part = _harmonic_vowel(gl, f0[:gl], locus, sr)
                rest = _harmonic_vowel(m - gl, f0[gl:], formants, sr, phase0=gl * 0.01)
                wav[:gl] = part
                wav[gl:] = rest
            else:
                f0 = _f0_curve(f0_base, tone, m, vibrato, sr)
                wav = _harmonic_vowel(m, f0, formants or (500, 1500, 2500), sr, phase0=pos * 0.01)
            if syl.breathiness > 0:
                noise = _band_noise(m, (formants or (500, 1500, 2500))[1], 900, sr, rng)
                wav = wav + syl.breathiness * 0.22 * noise
            env = np.ones(m)
            k = max(1, int(0.012 * sr))
            env[:k] = np.linspace(0, 1, k)
            env[-k:] = np.linspace(1, 0, min(k, m))
            out[pos:pos + m] += wav * env
            prev_place = None
        pos += m
        if pos >= n:
            break
    k = max(1, int(0.01 * sr))
    out[:k] *= np.linspace(0, 1, k)
    out[-k:] *= np.linspace(1, 0, k)
    return out.astype(np.float32)


TURN_FADE_S = {"restrike": 0.003, "breath": 0.008, "break": 0.008}
INHALE_MAX_S = 0.12          # 气口最长（更长的间隙不填满，留白也是演奏）


def _raise_cos(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones(max(n, 0))
    return 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)


def _inhale(n: int, sr: int, rng) -> np.ndarray:
    """换气：低通噪声（吸气声），两端渐入渐出。"""
    if n <= 0:
        return np.zeros(0)
    noise = _band_noise(n, 1200, 1400, sr, rng)
    noise = noise / (float(np.abs(noise).max()) or 1.0)
    return 0.12 * noise * _raise_cos(n) * np.linspace(0.6, 1.0, n)


def _glottal(n: int, sr: int, rng) -> np.ndarray:
    """重起音：低频声门脉冲（短促）+ 少量噪声 + 快速衰减。"""
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / sr
    pulse = np.sin(2 * np.pi * 180.0 * t) * np.exp(-t * 55.0)
    noise = _band_noise(n, 900, 1200, sr, rng)
    noise = noise / (float(np.abs(noise).max()) or 1.0)
    return 0.30 * (0.75 * pulse + 0.45 * noise) * np.exp(-np.linspace(0, 5, n))


def sing(plan, doc, *, sr: int = SR, tail_s: float = 0.3) -> np.ndarray:
    """把 VocalPlan 渲染成整段人声（**按音**逐个摆位）。

    每个 `plan.syllables` 元素 = 一个音：自己的起点/时长/音高。
    转折（`turn_kind`）决定音头怎么处理，`overlap_us` 决定与前一音叠多少。
    """
    import ms_events as ev

    total = ev.total_end_us(doc) / 1e6 + tail_s
    n = int(total * sr)
    buf = np.zeros(n, dtype=np.float32)
    events = {e.id: e for e in doc.events}
    for syl in plan.syllables:
        e = events.get(syl.event_ids[0]) if syl.event_ids else None
        if e is None:
            continue
        hz = _semitones_to_hz(e.pitch.semitone)
        m = max(256, int(syl.dur_us / 1e6 * sr))
        kind = getattr(syl, "turn_kind", None)
        strength = int(getattr(syl, "turn_strength", 0) or 0)
        overlap = max(0, int(getattr(syl, "overlap_us", 0) or 0))
        gap = max(0, int(getattr(syl, "gap_us", 0) or 0))
        wav = _render(syl, hz, m, sr, (5.5, 6.0),
                      np.random.default_rng(abs(hash((syl.char, syl.row_id))) & 0xFFFF))
        ov = int(overlap / 1e6 * sr)          # 重叠量（样本）
        # 音头：连音按 xfade 渐入（与前一音真正叠在一起），其余按转折给极短渐入
        fade_n = min(ov, len(wav)) if kind == "liaison" else int(TURN_FADE_S.get(kind, 0.004) * sr)
        k = min(len(wav), max(1, fade_n))
        wav[:k] *= _raise_cos(k)
        i0 = max(0, int(syl.onset_us / 1e6 * sr) - (ov if kind == "liaison" else 0))
        if kind == "breath" and gap > 0:
            g = min(int(gap / 1e6 * sr), int(INHALE_MAX_S * sr))
            j = max(0, i0 - g)
            inh = _inhale(i0 - j, sr, np.random.default_rng(abs(hash(("inhale", syl.row_id))) & 0xFFFF))
            buf[j:j + len(inh)] += inh.astype(np.float32)
        elif kind == "restrike":
            gl = _glottal(max(1, int(0.006 * sr)), sr,
                          np.random.default_rng(abs(hash(("glottal", syl.row_id))) & 0xFFFF))
            gl = gl * (0.5 + 0.5 * min(1000, strength) / 1000.0)
            seg_end = min(n, i0 + len(gl))
            buf[i0:seg_end] += gl[:seg_end - i0].astype(np.float32)
        i1 = min(n, i0 + len(wav))
        buf[i0:i1] += wav[: i1 - i0]
    peak = float(np.abs(buf).max())
    if peak > 1e-9:
        buf *= 0.85 / peak
    return buf


def sing_with_transitions(plan, doc, *, sr=SR, tail_s=0.4):
    """按段渲染 + 转折重叠（读 ocal_transition.build_transitions）。"""
    import sys as _s
    from pathlib import Path as _P
    _root = _P(__file__).resolve().parent.parent
    for _d in (_root / "transform", _root / "notation"):
        if str(_d) not in _s.path:
            _s.path.insert(0, str(_d))
    import ms_events as ev
    import vocal_plan as vp
    import vocal_transition as vt

    trs = vt.build_transitions(plan, doc)
    by = {}
    for t in trs:
        by.setdefault(t["syl"], []).append(t)
    total = ev.total_end_us(doc) / 1e6 + tail_s
    n = int(total * sr)
    buf = np.zeros(n, dtype=np.float32)
    evs = {e.id: e for e in doc.events}
    for syl in plan.syllables:
        e = evs.get(syl.event_ids[0]) if syl.event_ids else None
        if e is None:
            continue
        hz = _semitones_to_hz(e.pitch.semitone)
        for t, seg in zip(by.get(syl.char, []), syl.segments):
            dur = max(50_000, t["end_us"] - t["start_us"])
            one = vp.SyllablePlan(char=syl.char, pinyin=syl.pinyin,
                                  lexical_tone=syl.lexical_tone, surface_tone=syl.surface_tone,
                                  word_id=syl.word_id, event_ids=syl.event_ids,
                                  onset_us=0, dur_us=dur, segments=[seg],
                                  breathiness=syl.breathiness)
            w = _render(one, hz, max(256, int(dur / 1e6 * sr)), sr, (5.5, 6.0),
                        np.random.default_rng(abs(hash((syl.char, t["i"]))) & 0xFFFF))
            i0 = max(0, int(t["start_us"] / 1e6 * sr))
            i1 = min(n, i0 + len(w))
            buf[i0:i1] += w[: i1 - i0]
    peak = float(np.abs(buf).max())
    return (buf / peak * 0.9).astype(np.float32) if peak > 1e-9 else buf
