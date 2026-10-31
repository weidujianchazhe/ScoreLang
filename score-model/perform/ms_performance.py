# -*- coding: utf-8 -*-
"""演奏动作解析：把 `turns` / `curves` / `pedals` 里的动作，翻译成本音要做的调整。

**不新增格式**：动作全部用现有三个表表达——
  · `turns`  = 逐音动作（`dict turn` 可扩：弓向、拨/拉、泛音、槌硬度、吸气、机械声、弱音器、花舌…）
  · `curves` = 逐乐器连续参数（`dict curve` 可扩：颤音深度、弓位）
  · `pedals` = 持续状态（`dict kind` 可扩：`sordino` 弱音器、`tuning` 调音、`swell` 表情、`hihat`）

本模块只算"要做什么"，合成在 `make_audio`；这样动作语义可以单独测试。
"""
from __future__ import annotations

import numpy as np

# 音头那一小段额外声音：换弓=摩擦、换气=气噪、换槌=木击、再击/重拨=瞬态
from semantics import TURN_TRANSIENT

# 音高类：调音踏板按"音级"改音（竖琴）；depth 0/500/1000 = ♭ / ♮ / ♯
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _curve_value(curves, iid, param, t_us, default=None):
    pts = [(c.time_us, c.value) for c in curves if c.instrument_id == iid and c.param == param]
    if not pts:
        return default
    pts.sort()
    ts = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    if t_us <= ts[0]:
        return vs[0]
    if t_us >= ts[-1]:
        return vs[-1]
    import bisect
    i = bisect.bisect_right(ts, t_us) - 1
    if i >= len(ts) - 1:
        return vs[-1]
    span = ts[i + 1] - ts[i]
    if span <= 0:
        return vs[i]
    f = (t_us - ts[i]) / span
    return vs[i] + (vs[i + 1] - vs[i]) * f


def _pitch_class_of(event) -> str:
    return PITCH_CLASSES[event.pitch.semitone % 12]


def muted_at(doc, iid: int, t_us: int) -> bool:
    for p in doc.pedals:
        if p.instrument_id != iid or p.kind != "sordino":
            continue
        end = p.end_us if p.end_us is not None else 10 ** 18
        if p.start_us <= t_us < end:
            return True
    return False


def tuning_cents(doc, event) -> float:
    """竖琴调音踏板：按音级命中，depth 0/500/1000 → −100/0/+100 音分。"""
    pc = _pitch_class_of(event)
    cents = 0.0
    for p in doc.pedals:
        if p.kind != "tuning" or p.instrument_id != event.instrument_id:
            continue
        if p.start_us > event.onset_us or (p.end_us is not None and event.onset_us >= p.end_us):
            continue
        tgt = tuple(p.targets or ())
        if not tgt or pc in tgt or pc.replace("#", "sharp") in tgt:
            cents += (p.depth_permille - 500) / 5.0      # 0→−100, 500→0, 1000→+100
    return cents


def hihat_open(doc, iid: int, t_us: int):
    """hihat 踏板在 t 时刻的深度（‰）；没踩 = 闭合。鼓件合成用。"""
    for p in doc.pedals:
        if p.kind != "hihat" or p.instrument_id != iid:
            continue
        end = p.end_us if p.end_us is not None else 10 ** 18
        if p.start_us <= t_us < end:
            return p.depth_permille
    return 0


def actions_for(doc, event, spec: dict | None = None) -> dict:
    """本音要做的动作（纯数据，不合成）。"""
    spec = spec or {}
    iid = event.instrument_id
    turns = {t.event_id: t for t in getattr(doc, "turns", [])}
    t = turns.get(event.id)
    kind = t.kind if t is not None else None
    strength = (t.strength / 1000.0) if t is not None else 0.0

    act = {
        "turn": kind,
        "strength": strength,
        "bright_scale": 1.0,
        "attack_scale": 1.0,
        "mech_override": None,
        "harmonic": False,
        "decay_scale": 1.0,
        "vibrato": None,
        "pitch_ramp": None,
        "pitch_cents": 0.0,          # 固定偏移（调音踏板 / capo）
        "pitch_semitone": 0,         # capo/泛音之外的整音移调
        "am": None,                  # (rate_hz, depth) 花舌/滚奏
        "pre": [],
        "transient": TURN_TRANSIENT.get(kind) if kind else None,
        "muted": muted_at(doc, iid, event.onset_us),
        "half_pedal": 1.0,
        "drum": None,
        "jitter": None,
    }

    # ── 逐音动作 ──
    if kind == "pizz":
        act["mech_override"] = "plucked_string"
        act["decay_scale"] = 0.45
    elif kind == "arco":
        act["mech_override"] = "bowed_string"
    elif kind == "harmonic":
        act["harmonic"] = True
        act["bright_scale"] = 0.35
    elif kind == "bow_up":
        act["attack_scale"] = 0.94
    elif kind == "bow_down":
        act["attack_scale"] = 1.06
    elif kind == "mallet_soft":
        act["bright_scale"] = 0.70
    elif kind == "mallet_hard":
        act["bright_scale"] = 1.35
    elif kind == "col_legno":
        act["bright_scale"] = 1.25
        act["decay_scale"] = 0.25
    elif kind == "flutter":
        act["am"] = (11.0, 0.45)
    elif kind == "roll":
        act["am"] = (22.0, 0.55)
    elif kind == "brush":
        act["bright_scale"] = 0.65
    elif kind == "rim_shot":
        act["bright_scale"] = 1.4
        act["decay_scale"] = 0.4
    elif kind == "tremolo":
        act["am"] = (14.0, 0.55)        # 弦乐震音：快速碎弓
    elif kind == "mute_cup":
        act["bright_scale"] = 0.55      # 杯形弱音器：更闷
    elif kind == "mute_harmon":
        act["bright_scale"] = 0.35      # 哈蒙弱音器：鼻音、最暗
        act["decay_scale"] = 0.9
    elif kind == "mute_plunger":
        act["bright_scale"] = 0.6
        act["am"] = (5.0, 0.25)         # 弱音碗：开合带来的轻微起伏
    elif kind == "half_valve":
        act["bright_scale"] = 0.8
        act["attack_scale"] = 0.85
        act["pitch_cents"] += -15.0     # 半阀会略偏低
    elif kind == "growl":
        act["am"] = (32.0, 0.40)        # 咆哮：粗糙的快速起伏
        act["bright_scale"] = 1.15

    # 逐音标了弱音器（含吉他闷音 palm mute）：这一音就按"装着弱音器"发
    mech = spec.get("mechanism")
    if kind in ("mute_on", "mute_cup", "mute_harmon", "mute_plunger"):
        act["muted"] = True
        if mech == "plucked_string":     # 闷音：压弦，短而闷
            act["decay_scale"] = 0.45
            act["bright_scale"] *= 0.6

    # ── 连续参数（curves）──
    curves = getattr(doc, "curves", [])
    bow = _curve_value(curves, iid, "bow_position", event.onset_us)
    if bow is not None:
        act["bright_scale"] *= 0.45 + 1.20 * (bow / 1000.0)
    bright = _curve_value(curves, iid, "brightness", event.onset_us)
    if bright is not None:
        act["bright_scale"] *= 0.6 + 0.8 * (bright / 1000.0)
    vib = _curve_value(curves, iid, "vibrato", event.onset_us)
    if vib:
        act["vibrato"] = (spec.get("timbre", {}).get("vib_rate") or 5.0, vib / 10.0)
    pc = _curve_value(curves, iid, "pitch_cents", event.onset_us)
    end_us = event.release_us if event.release_us is not None else event.onset_us + 500_000
    pc_end = _curve_value(curves, iid, "pitch_cents", end_us)
    if pc is not None and pc_end is not None and abs(pc_end - pc) > 20:
        act["pitch_ramp"] = (pc, pc_end)

    # ── 持续状态 ──
    if act["muted"]:
        act["bright_scale"] *= 0.45
    # 表情踏板：踩得深 = 更响更亮
    for p in getattr(doc, "pedals", []):
        if p.kind == "swell" and p.instrument_id == iid:
            end = p.end_us if p.end_us is not None else 10 ** 18
            if p.start_us <= event.onset_us < end:
                d = p.depth_permille / 1000.0
                act["bright_scale"] *= 0.75 + 0.5 * d
    # 调音踏板（竖琴）：按音级改音分
    act["pitch_cents"] += tuning_cents(doc, event)
    # 变调夹（吉他）：整音移调
    capo = (spec.get("constraints") or {}).get("capo") or 0
    if capo:
        act["pitch_semitone"] += int(capo)
    # 半踏板：depth 越浅，制音越接近盖上
    for p in getattr(doc, "pedals", []):
        if p.kind != "sustain" or p.instrument_id != iid:
            continue
        if p.start_us <= event.onset_us and (p.end_us is None or event.onset_us < p.end_us):
            res = float(spec.get("pedal_factors", {}).get("sustain_resonance", 1.0) or 1.0)
            act["half_pedal"] = min(1.0, (p.depth_permille / 1000.0) * res)

    # 弓长：长音要拉得更久 → 弓速快、略亮；短音反之（教科书事实，不是玄学）
    if spec.get("mechanism") == "bowed_string" and event.release_us is not None:
        dur_s = max(0.05, (event.release_us - event.onset_us) / 1e6)
        act["bright_scale"] *= 1.0 + 0.18 * min(1.0, dur_s / 2.0)
        if dur_s < 0.25:
            act["bright_scale"] *= 0.9

    # 鼓件：键号不是音高，是哪一件鼓
    if spec.get("drum_kit") or spec.get("family") == "percussion":
        import ms_instruments as _reg
        drum = _reg.DRUM_MAP.get(event.pitch.semitone)
        if drum:
            name, synth, tau, bright, noise = drum
            if name.startswith("hihat"):
                depth = hihat_open(doc, iid, event.onset_us)
                tau = 0.07 + 0.5 * (depth / 1000.0)
                synth = "noise"
            act["drum"] = dict(name=name, synth=synth, tau=tau, bright=bright, noise=noise,
                               hihat=depth if name.startswith("hihat") else None)

    # 逐音微差（同一音重复不会完全一样）：按 id 稳定，不引入随机不稳定
    import zlib
    h = zlib.crc32(event.id.encode("utf-8")) % 1000     # 不能用 hash()：每个进程随机化
    act["jitter"] = dict(cents=(h % 9) - 4, attack=0.94 + 0.12 * ((h // 9) % 5) / 4.0)
    return act


def apply_pitch_ramp(wave: np.ndarray, cents0: float, cents1: float, sr: int) -> np.ndarray:
    """把一段波按"音分从 cents0 弯到 cents1"重采样（滑音/滑指）。"""
    n = len(wave)
    if n < 2:
        return wave
    ratios = 2 ** (np.linspace(cents0, cents1, n) / 1200.0)
    idx = np.cumsum(ratios) - ratios[0]
    idx = np.clip(idx, 0, n - 1)
    return np.interp(idx, np.arange(n), wave).astype(np.float32)


def transient_noise(kind_spec: dict, strength: float, sr: int) -> np.ndarray:
    if not kind_spec:
        return np.zeros(0, dtype=np.float32)
    n = max(1, int(kind_spec["sec"] * sr))
    rng = np.random.default_rng(7)
    x = rng.standard_normal(n).astype(np.float32)
    a = float(np.clip(kind_spec["band"], 0.02, 1.0))
    y = np.empty_like(x)
    acc = 0.0
    for i in range(n):
        acc += a * (x[i] - acc)
        y[i] = acc
    env = np.linspace(1, 0, n, dtype=np.float32) ** 1.6
    return (y * env * kind_spec["gain"] * max(0.15, strength)).astype(np.float32)
