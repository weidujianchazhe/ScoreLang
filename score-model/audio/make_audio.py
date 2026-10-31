"""MS → WAV（原生合成器）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "render", "audio",
                                        "transform", "tests", "tools", "importers"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

from pathlib import Path

import numpy as np

import ms_events as ev
import ms_instruments as reg
import ms_performance as perf

SR = 44100
ATTACK = 0.006
FADE_OUT = 0.080

# 持续型机制：起音后保持，松手才衰减（弓弦/吹奏/人声）
SUSTAINED_MECH = {"bowed_string", "lip_reed", "single_reed", "air_jet", "vocal_fold"}
# 各机制的衰减缩放（相对族 tau）
DECAY_SCALE = {"hammered_string": 1.0, "plucked_string": 0.75, "struck_body": 0.55,
               "bowed_string": 1.0, "lip_reed": 1.0, "single_reed": 1.0,
               "air_jet": 1.0, "vocal_fold": 1.0, "electronic": 1.0, "noise": 1.0}
# 力度标尺（语义表 §6.6）
SCALES = ("relative_permille", "velocity_steps", "continuous", "fixed_levels")

# 族 → 合成参数（roll=泛音衰减指数；tau=衰减常数；att=起音；bright=亮度档；noise=气声）
FAMILY = {
    "piano":      dict(roll=1.05, tau=1.15, att=0.006, bright=(4, 12), detune=1.5),
    "mallet":     dict(roll=1.40, tau=0.55, att=0.002, bright=(6, 14), detune=0.0),
    "organ":      dict(roll=1.00, tau=8.00, att=0.010, bright=(8, 16), detune=0.0),
    "guitar":     dict(roll=1.10, tau=0.85, att=0.004, bright=(4, 12), detune=1.0),
    "bass":       dict(roll=1.15, tau=0.90, att=0.005, bright=(3, 9),  detune=1.0),
    "strings":    dict(roll=1.30, tau=4.00, att=0.050, bright=(3, 9),  detune=2.5, noise=0.010),
    "ensemble":   dict(roll=1.30, tau=4.50, att=0.060, bright=(3, 9),  detune=3.0, noise=0.008),
    "voice":      dict(roll=1.35, tau=3.00, att=0.040, bright=(2, 6),  detune=0.0, noise=0.006),
    "brass":      dict(roll=1.20, tau=3.00, att=0.030, bright=(5, 14), detune=0.8, noise=0.004),
    "reed":       dict(roll=1.25, tau=3.20, att=0.040, bright=(4, 12), detune=0.5, noise=0.012),
    "pipe":       dict(roll=1.25, tau=3.00, att=0.045, bright=(4, 11), detune=0.5, noise=0.020),
    "synth":      dict(roll=1.00, tau=3.00, att=0.010, bright=(8, 18), detune=0.0),
    "ethnic":     dict(roll=1.10, tau=1.00, att=0.004, bright=(4, 12), detune=1.5),
    "percussion": dict(roll=1.50, tau=0.45, att=0.001, bright=(6, 16), detune=0.0, noise=0.30),
    "sfx":        dict(roll=1.50, tau=0.80, att=0.002, bright=(6, 16), detune=0.0, noise=0.60),
}

# 子类型微调（缺省用族参数）
SUBTYPE = {
    "steinway_d": dict(roll=1.02, bright=(4, 13)),
    "yamaha_c7":  dict(roll=1.08, bright=(5, 14)),
    "digital":    dict(roll=0.95, tau=2.0, bright=(6, 16), detune=0.0),
    "nylon":      dict(roll=1.25, tau=0.70),
    "steel":      dict(roll=1.10, tau=0.90),
    "electric_clean": dict(roll=1.00, tau=2.50, detune=0.0),
    "solo":       dict(detune=0.5, att=0.055),
    "ensemble":   dict(detune=3.5, att=0.070),
}

# section → (pan -1..1, gain)
SECTION = {
    "keyboard": (0.0, 1.00), "strings_1": (-0.35, 0.90), "strings_2": (0.35, 0.90),
    "choir_s": (-0.20, 0.85), "choir_a": (-0.05, 0.85), "choir_t": (0.10, 0.85),
    "choir_b": (0.25, 0.85), "brass": (0.40, 0.80), "woodwinds": (-0.40, 0.85),
    "percussion": (0.0, 0.95), "vocals": (0.0, 1.00),
}


def _freq(semitone: int) -> float:
    return 440.0 * (2 ** ((semitone - 69) / 12))


def _spec_of(doc, iid: int) -> dict:
    """乐器完整能力表（动作解析要用 timbre / pedal_factors / 本曲覆盖的 constraints）。"""
    inst = ev.instrument_of(doc, iid)
    if inst is None:
        return reg.resolve("acoustic_grand_piano")
    spec = reg.resolve(getattr(inst, "type", "acoustic_grand_piano"),
                       getattr(inst, "subtype", None))
    cons = getattr(inst, "constraints", None)
    if cons:
        spec = dict(spec)
        spec["constraints"] = dict(spec.get("constraints") or {})
        spec["constraints"].update(cons)
    return spec


def _profile(doc, iid: int) -> dict:
    inst = ev.instrument_of(doc, iid)          # 按 id 取（P8 就是 P8，不是第 8 项）
    spec = reg.resolve(getattr(inst, "type", "acoustic_grand_piano"),
                       getattr(inst, "subtype", None)) if inst else reg.resolve("acoustic_grand_piano")
    prof = dict(spec.get("timbre") or FAMILY.get(spec["family"], FAMILY["piano"]))
    prof.update(SUBTYPE.get(getattr(inst, "subtype", None) or "", {}))
    prof["category"] = spec["category"]
    prof["mechanism"] = spec.get("mechanism", "hammered_string")
    prof["off"] = dict(spec.get("off") or {"kind": "damper", "ramp_ms": 70})
    prof["section"] = getattr(inst, "section", None) or ("keyboard" if spec["family"] == "piano" else spec["family"])
    return prof


def _sample(low: int, high: int) -> int:
    return int(np.random.randint(low, high + 1))


def _drum_noise(t: np.ndarray, amp: float, drum: dict, sr: int) -> np.ndarray:
    """鼓件（镲/踩镲/沙锤）用噪声 + 指数包络，不用谐波。"""
    rng = np.random.default_rng(11)
    x = rng.standard_normal(len(t)).astype(np.float32)
    # 亮度：高亮 = 少平滑；一阶低通系数
    a = float(np.clip(0.02 + drum["bright"] / 14.0, 0.05, 1.0))
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        y[i] = acc
    env = np.exp(-t / max(0.01, drum["tau"] / 3.0))
    return (y * env * (0.5 + 0.5 * amp)).astype(np.float32)


def _note_wave(f: float, t: np.ndarray, amp: float, prof: dict, una_corda: bool,
               mech: str = "hammered_string") -> np.ndarray:
    p = lambda k: prof.get(k)
    roll, tau, att = p("roll"), p("tau"), p("attack")
    tau = tau * DECAY_SCALE.get(mech, 1.0)
    # 音区决定衰减：低音长、高音短（三角琴最容易被忽略的一条物理事实）。
    # 没有这一条，整台琴听起来就是"每个音一样长的电子键盘"。
    rd = p("reg_decay")
    if rd:
        tau = float(np.clip(tau * (261.63 / max(f, 20.0)) ** float(rd),
                            tau * 0.15, tau * 8.0))
    # 弦刚度 → 泛音非整数倍（stretched octaves）
    inh = float(p("inharm") or 0.0)
    B = min(1.2e-3, inh * (1.0 + f / 700.0)) if inh else 0.0
    vib_rate, vib_depth = p("vib_rate") or 0.0, p("vib_depth") or 0.0
    b_lo, b_hi = p("bright")
    bright = b_lo + (b_hi - b_lo) * min(1.0, amp / 1.2)
    if una_corda:
        bright *= float(prof.get("una_corda_darken", 0.55))
    det = [1.0]
    if p("detune"):
        det.append(2 ** (p("detune") / 1200))
    # 逐泛音（实测比 (H,T) 矩阵快：sin/exp 是主要开销，矩阵反而多吃内存带宽）
    max_h = int(min(18, bright + 2, np.floor(12000 / f), np.floor((SR / 2.1) / f)))
    if max_h < 1:
        return np.zeros_like(t)
    sig = np.zeros_like(t, dtype=np.float32)
    t32 = t
    attack_env = np.minimum(1.0, t32 / att)          # 起音包络只算一次
    omega = 2 * np.pi * f * t32                       # 基频相位，泛音按倍数复用
    vib_env = None
    if vib_depth and vib_rate:
        vib_env = 1.0 + (vib_depth / 100.0) * np.sin(2 * np.pi * vib_rate * t32)
    for mult in range(1, max_h + 1):
        env = np.exp(-t32 / (tau / (1 + 0.42 * (mult - 1)))) * attack_env
        if vib_env is not None:
            env *= vib_env
        base = (0.5 * mult ** -roll) * env
        if prof.get("noise") and mult <= 3:
            base = base + prof["noise"] * 0.05 * np.random.randn(len(t32)).astype(np.float32)
        st = (1.0 + B * mult * mult) ** 0.5 if B else 1.0
        for k, d in enumerate(det):
            if f * mult * d * st > SR / 2.1:
                continue
            sig += (base * np.sin(omega * (mult * d * st) + k * 0.7)).astype(np.float32)
    # 毡槌击弦的闷响：几十毫秒的低频瞬态。加的是"木与毡"，不是"电子起音"。
    hg = float(p("hammer") or 0.0)
    if hg:
        n_hit = int(min(len(t32), 0.035 * SR))
        if n_hit > 8:
            kern = np.exp(-np.arange(48, dtype=np.float32) / 16.0)
            kern /= kern.sum()
            # 固定种子：同一个音每次渲染的槌噪完全相同（可复现）
            rng = np.random.RandomState(int(round(f * 100)) & 0x7FFFFFFF)
            hit = np.convolve(rng.randn(n_hit).astype(np.float32), kern, "same")
            hit /= (np.max(np.abs(hit)) or 1.0)
            hit *= hg * (0.55 + 0.9 * min(1.0, amp / 1.0)) * np.exp(-t32[:n_hit] / 0.012)
            sig[:n_hit] += hit.astype(np.float32)
    return sig


def _amp_of(e, mech: str = "hammered_string") -> float:
    """力度标尺 → 幅度；机制决定曲线形状（combine 契约）。"""
    d = e.dynamics
    if d.permille is None:
        return 1.0
    x = min(1.4, d.permille / 1000.0)
    scale = getattr(d, "scale", None) or "relative_permille"
    if scale == "continuous":
        return x
    if scale == "velocity_steps":
        return round(x * 8) / 8
    if scale == "fixed_levels":
        return 1.0
    # 机制曲线：弓弦/吹奏线性（弓压×弓速/气压），拨弦略降，击弦/击体偏超线性
    if mech in ("bowed_string", "lip_reed", "single_reed", "air_jet", "vocal_fold"):
        return x
    if mech == "plucked_string":
        return x ** 0.9
    if mech == "struck_body":
        return x ** 1.2
    return x ** 1.1


def _pedal_state(doc):
    """返回按**乐器**取用的踏板函数：sustain/sostenuto/una_corda/swell。

    踏板是 per-instrument 的持续控制，不是全局区间：P1 的踏板不作用于 P8。
    """
    sustains = [p for p in doc.pedals if p.kind == "sustain"]
    unacorda = [p for p in doc.pedals if p.kind == "una_corda"]
    sost = [p for p in doc.pedals if p.kind == "sostenuto"]

    def _hit(p, inst, onset, eid):
        if p.instrument_id != inst:
            return False
        if p.targets and "global" not in p.targets and eid not in p.targets:
            return False
        return p.start_us <= onset and (p.end_us is None or onset < p.end_us)

    def sustain_end(inst, onset, rel, eid=None):
        best = rel
        for p in sustains:
            if _hit(p, inst, onset, eid):
                best = max(best, p.end_us if p.end_us is not None else onset + 2_000_000)
        return best

    def is_una(inst, onset):
        for p in unacorda:
            if _hit(p, inst, onset, None):
                return True
        return False

    def sost_end(inst, onset, eid):
        best = None
        for pp in sost:
            if not pp.targets or eid not in pp.targets:
                continue
            if _hit(pp, inst, onset, eid):
                end = pp.end_us if pp.end_us is not None else onset + 2_000_000
                best = end if best is None else max(best, end)
        return best

    # 被 sostenuto 抓住的音（按乐器分组，避免串乐器）
    sost_targets = {}
    for p in sost:
        if p.targets:
            sost_targets.setdefault(p.instrument_id, set()).update(
                t for t in p.targets if t != "global")

    # 表情踏板（管风琴 swell）：按 onset 所在区间给增益 0.3..1.0
    swells = [p for p in doc.pedals if p.kind == "swell"]

    def swell_gain(inst, onset):
        for p in swells:
            if _hit(p, inst, onset, None):
                return 0.3 + 0.7 * (p.depth_permille / 1000.0)
        return 1.0

    return sustain_end, is_una, sost_targets, sost_end, swell_gain


def render(doc: "ev.MSDocument", *, tail: float = 0.8) -> np.ndarray:
    # 严格对齐：长度 = 内容结尾 + **显式**结尾留白；tail 只用于收尾淡出
    end_us = ev.total_end_us(doc) if hasattr(ev, "total_end_us") else max(
        [e.release_us or e.onset_us for e in doc.events] + [0])
    n = int((end_us / 1e6 + tail) * SR)
    buf = np.zeros((n, 2), dtype=np.float32)
    sustain_end, is_una, sost_targets, sost_end, swell_gain = _pedal_state(doc)

    # 动态曲线：乐器 → (时间点数组, 增益数组)；MS 只存点，插值在这里做
    dyn_curves = {}
    for c in doc.curves:
        if c.param != "dynamics":
            continue
        ts, vs = dyn_curves.setdefault(c.instrument_id, ([], []))
        ts.append(c.time_us / 1e6)
        vs.append(c.value / 1000.0)
    for k in list(dyn_curves):
        ts, vs = dyn_curves[k]
        pairs = sorted(zip(ts, vs))
        dyn_curves[k] = (np.array([p[0] for p in pairs], dtype=np.float32),
                         np.array([p[1] for p in pairs], dtype=np.float32))

    turn_marks = {t.event_id: t for t in getattr(doc, "turns", [])}

    # 人声：有发声段（vocal）的 vocal_fold 乐器交给 ms_sing（共振峰合成），不走加法合成。
    vocal_ids = set()
    try:
        import ms_instruments as _reg
        for inst in getattr(doc, "instruments", []):
            try:
                if _reg.resolve(inst.type, inst.subtype).get("mechanism") == "vocal_fold":
                    vocal_ids.add(int(inst.id.lstrip("P")) if inst.id.startswith("P") else 1)
            except KeyError:
                pass
    except Exception:
        pass
    lyr_ids = set()
    vocal_plan_obj = None
    try:
        import vocal_plan as _vp
        vocal_plan_obj = _vp.build_plan(doc)
        lyr_ids |= {eid for syl in vocal_plan_obj.syllables for eid in syl.event_ids}
    except Exception:
        vocal_plan_obj = None
    vocal_events = {e.id for e in doc.events
                    if e.instrument_id in vocal_ids and e.id in lyr_ids}

    for e in doc.events:
        if e.id in vocal_events:
            continue
        prof = _profile(doc, e.instrument_id)
        mech = prof.get("mechanism", "hammered_string")
        try:
            act = perf.actions_for(doc, e, _spec_of(doc, e.instrument_id))
        except Exception:
            act = {"bright_scale": 1.0, "attack_scale": 1.0, "mech_override": None,
                   "harmonic": False, "decay_scale": 1.0, "vibrato": None,
                   "pitch_ramp": None, "pre": [], "transient": None,
                   "muted": False, "half_pedal": 1.0, "strength": 0.0}
        on = e.onset_us / 1e6
        if e.release_us is not None:
            rel_us = e.release_us
        elif e.id in sost_targets.get(e.instrument_id, ()):
            rel_us = e.onset_us + 1_500_000
        else:
            rel_us = e.onset_us + 1_500_000
        se = sost_end(e.instrument_id, e.onset_us, e.id)
        if se is not None:
            rel_us = max(rel_us, se)
        if e.id not in sost_targets.get(e.instrument_id, ()):
            rel_us = max(rel_us, ev.sustain_end_us(doc, e))
        # 延音踏板把音按住时，**松开踏板才是真正的收尾**：在踏板抬起处落制音器。
        pedal_held = rel_us > (e.release_us if e.release_us is not None else e.onset_us)
        i0 = int(on * SR)
        # 尾音：冲量 1.25s（保长鸣音尾），持续型 1.4s
        tail_extra = 1.4 if mech in SUSTAINED_MECH else 1.25
        i1 = min(n, int((rel_us / 1e6 + tail_extra) * SR))
        if i1 <= i0 + 64:
            continue
        t = np.arange(i1 - i0, dtype=np.float32) / SR
        mech = prof.get("mechanism", "hammered_string")
        amp = _amp_of(e, mech) * swell_gain(e.instrument_id, e.onset_us)
        if getattr(e, "is_grace", False):
            i1 = min(i1, i0 + int(0.09 * SR))
            t = np.arange(i1 - i0, dtype=np.float32) / SR
            amp *= 0.8
        # 演奏动作改音色：亮度乘子、起音、拨/拉、泛音、颤音
        prof = dict(prof)
        if act.get("muted"):
            prof["roll"] = float(prof.get("roll", 1.0)) * 1.25     # 弱音器：泛音滚降更快
            prof["tau"] = float(prof.get("tau", 1.0)) * 0.85       # 也收得短些
        if act.get("bright_scale", 1.0) != 1.0:
            lo, hi = prof["bright"]
            s = float(act["bright_scale"])
            prof["bright"] = (max(1.0, lo * s), max(1.5, hi * s))
        if act.get("attack_scale", 1.0) != 1.0:
            prof["attack"] = max(0.001, float(prof["attack"]) * float(act["attack_scale"]))
        if act.get("decay_scale", 1.0) != 1.0:
            prof["tau"] = float(prof["tau"]) * float(act["decay_scale"])
        if act.get("vibrato"):
            prof["vib_rate"], prof["vib_depth"] = act["vibrato"]
        if act.get("mech_override"):
            mech = act["mech_override"]
        # 音高：泛音 ×2 / capo 整音 / 调音踏板与逐音微差按音分
        semis = e.pitch.semitone + int(act.get("pitch_semitone") or 0)
        freq = _freq(semis) * (2.0 if act.get("harmonic") else 1.0)
        jit = act.get("jitter") or {}
        cents = float(act.get("pitch_cents") or 0) + float(jit.get("cents") or 0)
        if cents:
            freq *= 2 ** (cents / 1200.0)
        if jit.get("attack"):
            prof["attack"] = max(0.001, float(prof["attack"]) * float(jit["attack"]))
        drum = act.get("drum")
        wave = None
        if drum:
            prof["tau"] = drum["tau"]
            prof["bright"] = (drum["bright"], drum["bright"] * 1.8)
            prof["noise"] = drum["noise"]
            if drum["synth"] == "noise":
                wave = _drum_noise(t, amp, drum, SR)
        if wave is None:
            wave = _note_wave(freq, t, amp, prof,
                              is_una(e.instrument_id, e.onset_us), mech)
        if act.get("am"):
            rate, depth = act["am"]
            wave = wave * (1.0 + depth * np.sin(2 * np.pi * rate * t)).astype(np.float32)
        if act.get("pitch_ramp"):
            c0, c1 = act["pitch_ramp"]
            wave = perf.apply_pitch_ramp(wave, c0, c1, SR)

        if (getattr(e, "excitation_type", "impulse") == "sustained"
                or mech in SUSTAINED_MECH):
            hold = min(len(wave), max(1, int((rel_us / 1e6 - on + 0.12) * SR)))
            if hold > 1:
                wave[:hold] = np.clip(wave[:hold] / np.maximum(np.exp(-t[:hold] / 0.9), 1e-6), -1, 1)

        a = max(1, int(ATTACK * SR))
        wave[:a] *= np.linspace(0, 1, a, dtype=np.float32)
        # 止音：不是硬切——从 release（或被踏板按住后的抬起时刻）起，按该乐器的
        # 止音方式衰减到无声。ramp 缺省取乐器机制的默认（`ms_instruments.OFF_DEFAULTS`）。
        ramp_us = int(getattr(e, "off_ramp_us", 0) or 0)
        if ramp_us <= 0:
            ramp_us = int(float(prof.get("off", {}).get("ramp_ms", 70)) * 1000)
        hold_s = (rel_us - e.onset_us) / 1e6
        if hold_s < t[-1]:
            m = t > hold_s
            tau = max(0.002, ramp_us / 1e6 / 3.0)      # 3τ ≈ 衰减到 -20dB
            # 半踏板：踩得浅 = 制音器没完全抬起，收得更快
            hp = float(act.get("half_pedal", 1.0))
            if pedal_held and hp < 1.0:
                tau = tau * max(0.05, hp ** 2)
            wave[m] *= np.exp(-(t[m] - hold_s) / tau)
        # 半踏板：按住期间也不是全共振——按深度额外衰减（全踏板 hp=1 不受影响）
        hp = float(act.get("half_pedal", 1.0))
        if pedal_held and hp < 1.0:
            rel_t = (e.release_us - e.onset_us) / 1e6
            m2 = t > rel_t
            if m2.any():
                wave[m2] *= np.exp(-(t[m2] - rel_t) / (0.25 + 1.2 * hp))
        r = max(1, int(FADE_OUT * SR))
        if len(wave) > r:
            wave[-r:] *= np.linspace(1, 0, r, dtype=np.float32)

        pan, gain = SECTION.get(prof["section"], (0.0, 1.0))
        left = float(np.sqrt((1 - pan) / 2))
        right = float(np.sqrt((1 + pan) / 2))
        # 动态曲线（渐强/渐弱）：渲染层负责插值；MS 只给起点与转折点
        pts = dyn_curves.get(e.instrument_id)
        if pts:
            tt = np.arange(len(wave), dtype=np.float32) / SR + on
            wave = (wave * np.interp(tt, pts[0], pts[1]).astype(np.float32))
        # 音头动作：换弓=摩擦、换气=气噪、换槌=木击、再击/重拨=瞬态（turns 的 kind 不同，声音不同）
        tr = act.get("transient")
        if tr:
            nz = perf.transient_noise(tr, float(act.get("strength") or 0.0) + 0.15, SR)
            n_t = min(len(wave), len(nz))
            if n_t > 1:
                wave[:n_t] += nz[:n_t]
        # 吸气：音前一小段气声（吹奏/人声）
        if act.get("turn") == "inhale" or any(p[0] == "inhale" for p in act.get("pre") or ()):
            nz = perf.transient_noise({"sec": 0.12, "gain": 0.05, "band": 0.10}, 0.6, SR)
            a0 = max(0, i0 - len(nz))
            if a0 < i0:
                buf[a0:i0, 0] += nz[: i0 - a0] * 0.5
                buf[a0:i0, 1] += nz[: i0 - a0] * 0.5
        sig = (wave * (amp ** 0.35) * 0.16 * gain).astype(np.float32)
        buf[i0:i1, 0] += sig * left
        buf[i0:i1, 1] += sig * right

    # 人声轨：共振峰合成，按 Section 声像混入
    if vocal_events:
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _root = _Path(__file__).resolve().parent.parent
            for _d in (_root / "transform", _root / "notation"):
                if str(_d) not in _sys.path:
                    _sys.path.insert(0, str(_d))
        except Exception:
            pass
        try:
            import ms_sing as _msing
            if vocal_plan_obj is None:
                import vocal_plan as _vp
                vocal_plan_obj = _vp.build_plan(doc)
            _v = _msing.sing(vocal_plan_obj, doc)
            m = min(len(_v), n)
            buf[:m, 0] += _v[:m]
            buf[:m, 1] += _v[:m]
        except Exception as _exc:
            pass

    fo = min(n, int(1.0 * SR))
    if fo:
        buf[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
    peak = float(np.max(np.abs(buf))) or 1.0
    return (buf / peak * 0.89).astype(np.float32)


def write_wav(samples: np.ndarray, path: str | Path) -> None:
    import wave
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
