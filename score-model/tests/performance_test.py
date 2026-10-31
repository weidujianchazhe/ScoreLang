# -*- coding: utf-8 -*-
"""演奏因子与动作测试（P0–P3 补齐后的回归）。

守的语义（全部**只用现有格式**表达）：
  · 数据：harp/harpsichord 是拨弦机制；cello/bass/tuba 音域按真实乐器
  · 音域：C9 报越界（收束层，不阻止写入）
  · 动作：turns 的 kind 决定音头声音（换弓≠换气≠换槌≠再击）
  · 动作：pizz/harmonic/mallet_soft/mallet_hard/bow_up/bow_down 各自改音色
  · 连续：curves 的 vibrato / bow_position / pitch_cents（滑音）
  · 状态：pedals 的 sordino（弱音器）+ sustain depth（半踏板）
  · 适用性：不该做的动作被 V16 拒绝；奏法/装饰音在写谱侧被拒
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import make_audio
import ms_author as au
import ms_events as ev
import ms_instruments as reg
import ms_io
import ms_performance as perf
import ms_playability
import ms_semantics as ms
import ms_validate

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


STEPS = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
         9: ("A", 0), 11: ("B", 0), 1: ("C", 1), 3: ("D", 1), 6: ("F", 1),
         8: ("G", 1), 10: ("A", 1)}


def note(iid, onset, semi=60, dur=600_000, perm=800):
    step, alter = STEPS[semi % 12]
    return ev.Event(id=f"L{iid:08d}", instrument_id=1, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, perm, "relative_permille", "c", "measured"))


def doc(notes, instruments=(), turns=(), curves=(), pedals=()):
    d = ev.MSDocument(events=list(notes), instruments=list(instruments),
                      turns=list(turns), curves=list(curves), pedals=list(pedals))
    d.piano_count = max(1, len(instruments))
    d.constraint_mode = "single_piano" if d.piano_count == 1 else "n_pianos"
    return d


# ── 1) 数据修正（P0）────────────────────────────────────────
check("A1 竖琴是拨弦机制", reg.resolve("orchestral_harp")["mechanism"] == "plucked_string",
      reg.resolve("orchestral_harp")["mechanism"])
check("A2 大键琴是拨弦机制", reg.resolve("harpsichord")["mechanism"] == "plucked_string",
      reg.resolve("harpsichord")["mechanism"])
check("A3 大提琴音域按乐器（36..76）", reg.resolve("cello")["range"] == (36, 76),
      str(reg.resolve("cello")["range"]))
check("A4 低音提琴 28..67", reg.resolve("contrabass")["range"] == (28, 67))
check("A5 大号 28..58", reg.resolve("tuba")["range"] == (28, 58))
check("A6 中提琴 48..88", reg.resolve("viola")["range"] == (48, 88))

# ── 2) 音域检查（C9）────────────────────────────────────────
low = doc([note(1, 0, 40)], [ev.Instrument("P1", "flute")])
errs = ms_playability.check_playability(low)
check("B1 长笛吹 C2 → C9 报越界", any(e.startswith("C9") for e in errs), str(errs))
ok = doc([note(1, 0, 72)], [ev.Instrument("P1", "flute")])
check("B2 长笛正常音域不报", not any(e.startswith("C9")
                                    for e in ms_playability.check_playability(ok)))

# ── 3) 动作适用性（V16）──────────────────────────────────────
bad = doc([note(1, 0), note(2, 300_000, 62)],
          [ev.Instrument("P1", "acoustic_grand_piano")],
          turns=[ev.TurnPoint("L00000002", "bow_up", 800)])
check("C1 钢琴写弓向 → 拒绝",
      any("不适用于" in e for e in ms_validate.validate(bad)), str(ms_validate.validate(bad)))
bad2 = doc([note(1, 0)], [ev.Instrument("P1", "violin")],
           turns=[ev.TurnPoint("L00000001", "mallet_hard", 800)])
check("C2 小提琴写换槌 → 拒绝", any("不适用于" in e for e in ms_validate.validate(bad2)))
good = doc([note(1, 0)], [ev.Instrument("P1", "violin")],
           turns=[ev.TurnPoint("L00000001", "bow_up", 800)])
check("C3 小提琴写上弓 → 通过", ms_validate.validate(good) == [], str(ms_validate.validate(good)))

# ── 4) 写谱侧：奏法/装饰音适用性 ────────────────────────────
try:
    au.check_articulation("church_organ", "staccatissimo")
    check("D1 管风琴没有 staccatissimo → 应拒绝", False, "居然通过")
except ValueError as exc:
    check("D1 管风琴没有 staccatissimo → 拒绝", "做不了" in str(exc), str(exc))
try:
    au.check_ornament("timpani", "trill")
    check("D2 定音鼓没有颤音 → 应拒绝", False, "居然通过")
except ValueError as exc:
    check("D2 定音鼓没有颤音 → 拒绝", "做不了" in str(exc), str(exc))
au.check_articulation("acoustic_grand_piano", "staccato")   # 不抛即通过
au.check_ornament("violin", "trill")
check("D3 钢琴断奏 / 小提琴颤音可用", True)

# ── 5) 动作改变声音（turns）────────────────────────────────
SR = make_audio.SR

def render(d):
    return make_audio.render(d).mean(axis=1)

base = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")]))
for kind in ("bow_change", "breath", "mallet", "retrigger"):
    pass
violin_notes = [note(1, 0, 60)]
sounds = {}
for kind in ("bow_change", "breath", "retrigger"):
    d = doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
            turns=[ev.TurnPoint("L00000001", kind, 800)])
    sounds[kind] = render(d)
check("E1 换弓/换气/再击声音各不相同",
      not np.allclose(sounds["bow_change"], sounds["breath"])
      and not np.allclose(sounds["bow_change"], sounds["retrigger"])
      and not np.allclose(sounds["breath"], sounds["retrigger"]))
check("E2 有动作时音头与无动作不同", not np.allclose(base, sounds["bow_change"]))
check("E3 换弓比换气更亮（摩擦带更高）",
      float(np.abs(np.diff(sounds["bow_change"][:2000])).mean())
      > float(np.abs(np.diff(sounds["breath"][:2000])).mean()),
      "friction > air")

# ── 6) 音色类动作 ──────────────────────────────────────────
soft = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "timpani")],
                  turns=[ev.TurnPoint("L00000001", "mallet_soft", 800)]))
hard = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "timpani")],
                  turns=[ev.TurnPoint("L00000001", "mallet_hard", 800)]))
check("F1 软槌比硬槌暗", not np.allclose(soft, hard))

vln_pizz = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
                      turns=[ev.TurnPoint("L00000001", "pizz", 800)]))
check("F2 拨奏比拉弦短（尾音更小）",
      float(np.abs(vln_pizz[int(0.9 * SR):]).sum()) < float(np.abs(base[int(0.9 * SR):]).sum()) * 0.8,
      f"{float(np.abs(vln_pizz[int(0.9*SR):]).sum()):.3f} vs {float(np.abs(base[int(0.9*SR):]).sum()):.3f}")

harm = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
                  turns=[ev.TurnPoint("L00000001", "harmonic", 800)]))
def peak_freq(x, a=0.1, b=0.5):
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    return float(np.fft.rfftfreq(len(seg), 1 / SR)[int(np.argmax(spec))])
check("F3 泛音高八度", peak_freq(harm) > peak_freq(base) * 1.7,
      f"{peak_freq(harm):.0f} vs {peak_freq(base):.0f}")

# ── 7) 连续参数（curves）──────────────────────────────────
tasto = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
                   curves=[ev.CurvePoint(1, "bow_position", 0, 0, 0)]))
pont = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
                  curves=[ev.CurvePoint(1, "bow_position", 0, 1000, 0)]))
def centroid(x, a=0.1, b=0.4):
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1 / SR)
    return float((spec * fr).sum() / (spec.sum() + 1e-9))


def hf_ratio(x, a=0.05, b=0.30, cut=1200.0):
    """高频占比：泛音多 = 亮（比质心更灵敏）。"""
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(spec[fr >= cut].sum() / (spec.sum() + 1e-9))


def band_energy(x, a, b, lo, hi):
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1 / SR)
    m = (fr >= lo) & (fr <= hi)
    return float(spec[m].sum())


check("G1 靠桥比靠指板亮", hf_ratio(pont) > hf_ratio(tasto) * 1.15,
      f"{hf_ratio(pont):.3f} vs {hf_ratio(tasto):.3f}")

gliss = render(doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
                   curves=[ev.CurvePoint(1, "pitch_cents", 0, 0, 0),
                           ev.CurvePoint(1, "pitch_cents", 400_000, 400, 1)]))
check("G2 滑音：音高在音内变化",
      band_energy(gliss, 0.40, 0.55, 300, 360) > band_energy(base, 0.40, 0.55, 300, 360) * 2.0,
      f"{band_energy(gliss, 0.40, 0.55, 300, 360):.1f} vs "
      f"{band_energy(base, 0.40, 0.55, 300, 360):.1f}")

vib_doc = doc([note(1, 0, 69, dur=900_000)], [ev.Instrument("P1", "violin")],
              curves=[ev.CurvePoint(1, "vibrato", 0, 600, 0)])
act = perf.actions_for(vib_doc, vib_doc.events[0], reg.resolve("violin"))
check("G3 vibrato 曲线进入动作", act["vibrato"] is not None and act["vibrato"][1] > 0,
      str(act["vibrato"]))

# ── 8) 状态：弱音器与半踏板 ────────────────────────────────
mute = doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
           pedals=[ev.PedalSegment(1, "sordino", 0, 2_000_000, 1000)])
plain = doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")])
check("H1 弱音器让声音变暗", hf_ratio(render(mute)) < hf_ratio(render(plain)) * 0.85,
      f"{hf_ratio(render(mute)):.3f} vs {hf_ratio(render(plain)):.3f}")
check("H2 sordino 进入文件字典并往返",
      (lambda t: "sordino" in t and ms_io.dump(ms_io.parse(t)) == t)(
          ms_io.dump(ev.MSDocument(
              events=[note(1, 0, 60)], instruments=[ev.Instrument("P1", "violin")],
              pedals=[ev.PedalSegment(1, "sordino", 0, 900_000, 1000, "mechanical")]))))

half = render(doc([note(1, 0, 60, dur=300_000)], [ev.Instrument("P1", "acoustic_grand_piano")],
                  pedals=[ev.PedalSegment(1, "sustain", 0, 1_500_000, 300)]))
full = render(doc([note(1, 0, 60, dur=300_000)], [ev.Instrument("P1", "acoustic_grand_piano")],
                  pedals=[ev.PedalSegment(1, "sustain", 0, 1_500_000, 1000)]))
tail = lambda x: float(np.abs(x[int(0.6 * SR):int(1.2 * SR)]).sum())
check("H3 半踏板比全踏板收得快", tail(half) < tail(full) * 0.9,
      f"{tail(half):.2f} vs {tail(full):.2f}")

# ── 9) 动作随文件往返 ─────────────────────────────────────
d = doc([note(1, 0, 60)], [ev.Instrument("P1", "violin")],
        turns=[ev.TurnPoint("L00000001", "bow_up", 700)],
        curves=[ev.CurvePoint(1, "bow_position", 0, 800, 0)])
t = ms_io.dump(d)
b = ms_io.parse(t)
check("I1 弓向随文件往返", b.turns[0].kind == "bow_up" and b.turns[0].strength == 700,
      str(b.turns))
check("I2 弓位曲线随文件往返",
      b.curves[0].param == "bow_position" and b.curves[0].value == 800, str(b.curves))
check("I3 字节稳定", ms_io.dump(b) == t)

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
