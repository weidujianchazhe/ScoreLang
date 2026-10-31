# -*- coding: utf-8 -*-
"""乐器动作与因子：调音/踩镲/表情/鼓件/滚奏/花舌/变调夹/逐音微差。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import make_audio
import ms_events as ev
import ms_instruments as reg
import ms_performance as perf
import ms_semantics as ms
import ms_validate

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


STEPS = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
         9: ("A", 0), 11: ("B", 0), 1: ("C", 1), 3: ("D", 1), 6: ("F", 1),
         8: ("G", 1), 10: ("A", 1)}


def note(i, onset, dur, semi, inst=1, perm=800):
    step, alter = STEPS[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=inst, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, perm, "relative_permille", "c", "measured"))


def doc(events, instruments, pedals=(), turns=(), curves=()):
    d = ev.MSDocument(events=list(events), instruments=list(instruments),
                      pedals=list(pedals), turns=list(turns), curves=list(curves))
    d.piano_count = max(1, len(instruments))
    d.constraint_mode = "single_piano" if d.piano_count == 1 else "n_pianos"
    return d


SR = make_audio.SR

def render(d):
    return make_audio.render(d).mean(axis=1)


def peak_freq(x, a=0.05, b=0.35):
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    return float(np.fft.rfftfreq(len(seg), 1 / SR)[int(np.argmax(spec))])


def hf_ratio(x, a=0.02, b=0.25, cut=2000.0):
    seg = x[int(a * SR):int(b * SR)]
    spec = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(spec[fr >= cut].sum() / (spec.sum() + 1e-9))


# ── 1) 竖琴调音踏板：改音高 ───────────────────────────────
harp = [ev.Instrument("P1", "orchestral_harp")]
base = render(doc([note(1, 0, 900_000, 60)], harp))
flat = render(doc([note(1, 0, 900_000, 60)], harp,
                  pedals=[ev.PedalSegment(1, "tuning", 0, 2_000_000, 0, "explicit", ("C",))]))
sharp = render(doc([note(1, 0, 900_000, 60)], harp,
                   pedals=[ev.PedalSegment(1, "tuning", 0, 2_000_000, 1000, "explicit", ("C",))]))
check("T1 调音踏板降半音（C→B，−100 音分）",
      peak_freq(flat) < peak_freq(base) * 0.97, f"{peak_freq(flat):.0f} vs {peak_freq(base):.0f}")
check("T2 调音踏板升半音（C→C#，+100 音分）",
      peak_freq(sharp) > peak_freq(base) * 1.03, f"{peak_freq(sharp):.0f} vs {peak_freq(base):.0f}")
check("T3 只影响对应音级（G 不受 C 踏板影响）",
      abs(peak_freq(render(doc([note(1, 0, 900_000, 67)], harp,
                               pedals=[ev.PedalSegment(1, "tuning", 0, 2_000_000, 0,
                                                       "explicit", ("C",))])))
          - peak_freq(render(doc([note(1, 0, 900_000, 67)], harp)))) < peak_freq(base) * 0.02)

# ── 2) 踩镲：踏板开合改变长度 ─────────────────────────────
kit = [ev.Instrument("P1", "kit_standard", None, "percussion")]
closed = render(doc([note(1, 0, 400_000, 42)], kit))
opened = render(doc([note(1, 0, 400_000, 42)], kit,
                    pedals=[ev.PedalSegment(1, "hihat", 0, 900_000, 1000)]))
tail = lambda x: float(np.abs(x[int(0.25 * SR):int(0.45 * SR)]).sum())
check("T4 开镲比闭镲长", tail(opened) > tail(closed) * 1.3,
      f"{tail(opened):.3f} vs {tail(closed):.3f}")

# ── 3) 表情踏板：变响也变亮 ───────────────────────────────
organ = [ev.Instrument("P1", "church_organ")]
sw_low = render(doc([note(1, 0, 900_000, 60)], organ,
                    pedals=[ev.PedalSegment(1, "swell", 0, 900_000, 200)]))
sw_high = render(doc([note(1, 0, 900_000, 60)], organ,
                     pedals=[ev.PedalSegment(1, "swell", 0, 900_000, 1000)]))
check("T5 表情踏板深 → 更亮", hf_ratio(sw_high) > hf_ratio(sw_low) * 1.05,
      f"{hf_ratio(sw_high):.3f} vs {hf_ratio(sw_low):.3f}")

# ── 4) 鼓件映射：键号是鼓件，不是音高 ─────────────────────
kick = render(doc([note(1, 0, 400_000, 36)], kit))
crash = render(doc([note(1, 0, 400_000, 49)], kit))
check("T6 底鼓与吊镲音色差很多", hf_ratio(crash) > hf_ratio(kick) * 2,
      f"{hf_ratio(crash):.3f} vs {hf_ratio(kick):.3f}")
check("T7 鼓件在表里都有名字",
      all(reg.DRUM_MAP[k][0] for k in (35, 36, 38, 42, 49, 51)),
      str([reg.DRUM_MAP[k][0] for k in (35, 36, 38, 42, 49, 51)]))

# ── 5) 滚奏 / 花舌：振幅调制 ─────────────────────────────
tim = [ev.Instrument("P1", "timpani", None, "percussion")]
plain = render(doc([note(1, 0, 800_000, 48)], tim))
rolled = render(doc([note(1, 0, 800_000, 48)], tim,
                    turns=[ev.TurnPoint("L00000001", "roll", 800)]))


def envelope_var(x, a=0.1, b=0.6):
    """调制指数：包络去掉整体衰减趋势后的起伏（滚奏/花舌用）。"""
    seg = np.abs(x[int(a * SR):int(b * SR)])
    k = 400
    env = np.convolve(seg, np.ones(k) / k, mode="valid")
    trend = np.convolve(env, np.ones(6 * k) / (6 * k), mode="same")
    return float(np.std(env - trend) / (np.mean(trend) + 1e-9))


check("T8 滚奏有振幅起伏", envelope_var(rolled) > envelope_var(plain) * 1.5,
      f"{envelope_var(rolled):.3f} vs {envelope_var(plain):.3f}")

flute = [ev.Instrument("P1", "flute")]
f_plain = render(doc([note(1, 0, 900_000, 72)], flute))
f_flut = render(doc([note(1, 0, 900_000, 72)], flute,
                    turns=[ev.TurnPoint("L00000001", "flutter", 800)]))
check("T9 花舌与平吹不同", envelope_var(f_flut) > envelope_var(f_plain) * 1.3,
      f"{envelope_var(f_flut):.3f} vs {envelope_var(f_plain):.3f}")

# ── 6) 变调夹（capo）────────────────────────────────────
g0 = [ev.Instrument("P1", "acoustic_guitar_steel")]
g2 = [ev.Instrument("P1", "acoustic_guitar_steel", None, None, {"capo": 2})]
p0 = peak_freq(render(doc([note(1, 0, 900_000, 64)], g0)))
p2 = peak_freq(render(doc([note(1, 0, 900_000, 64)], g2)))
check("T10 变调夹 +2 品 → 高两个半音", p2 > p0 * 1.08, f"{p2:.0f} vs {p0:.0f}")

# ── 7) 逐音微差：同一音重复不完全一样 ───────────────────
d1 = doc([note(1, 0, 400_000, 60)], [ev.Instrument("P1", "acoustic_grand_piano")])
d2 = doc([note(2, 0, 400_000, 60)], [ev.Instrument("P1", "acoustic_grand_piano")])
check("T11 逐音微差（同一音不同 id 波形不同）",
      not np.allclose(render(d1), render(d2)))

# ── 8) 弓长：长音略亮 ──────────────────────────────────
vln = [ev.Instrument("P1", "violin")]
short = render(doc([note(1, 0, 200_000, 72)], vln))
longn = render(doc([note(1, 0, 2_000_000, 72)], vln))
check("T12 长音比短音亮（弓速）", hf_ratio(longn, 0.05, 0.18) > hf_ratio(short, 0.05, 0.18) * 1.03,
      f"{hf_ratio(longn, 0.05, 0.18):.3f} vs {hf_ratio(short, 0.05, 0.18):.3f}")

# ── 9) 弦乐震音 / 吉他闷音 / 铜管弱音器种类 / 半阀咆哮 ──
vln_plain = render(doc([note(1, 0, 800_000, 72)], vln))
vln_trem = render(doc([note(1, 0, 800_000, 72)], vln,
                      turns=[ev.TurnPoint("L00000001", "tremolo", 800)]))
check("T13 弦乐震音有振幅起伏", envelope_var(vln_trem) > envelope_var(vln_plain) * 1.4,
      f"{envelope_var(vln_trem):.3f} vs {envelope_var(vln_plain):.3f}")

gtr = [ev.Instrument("P1", "acoustic_guitar_steel")]
gtr_plain = render(doc([note(1, 0, 800_000, 64)], gtr))
gtr_mute = render(doc([note(1, 0, 800_000, 64)], gtr,
                      turns=[ev.TurnPoint("L00000001", "mute_on", 800)]))
check("T14 吉他闷音更短更暗",
      float(np.abs(gtr_mute[int(0.5 * SR):]).sum()) < float(np.abs(gtr_plain[int(0.5 * SR):]).sum()) * 0.8
      and hf_ratio(gtr_mute) < hf_ratio(gtr_plain) * 0.8,
      f"尾音 {float(np.abs(gtr_mute[int(0.5*SR):]).sum()):.2f} vs "
      f"{float(np.abs(gtr_plain[int(0.5*SR):]).sum()):.2f}")

tr = [ev.Instrument("P1", "trumpet")]
tr_straight = render(doc([note(1, 0, 700_000, 67)], tr,
                         turns=[ev.TurnPoint("L00000001", "mute_on", 800)]))
tr_harmon = render(doc([note(1, 0, 700_000, 67)], tr,
                       turns=[ev.TurnPoint("L00000001", "mute_harmon", 800)]))
check("T15 哈蒙弱音器比直筒更暗", hf_ratio(tr_harmon) < hf_ratio(tr_straight) * 0.9,
      f"{hf_ratio(tr_harmon):.3f} vs {hf_ratio(tr_straight):.3f}")

tr_half = render(doc([note(1, 0, 700_000, 67)], tr,
                     turns=[ev.TurnPoint("L00000001", "half_valve", 800)]))
tr_open = render(doc([note(1, 0, 700_000, 67)], tr))
check("T16 半阀音高略低", peak_freq(tr_half) < peak_freq(tr_open) * 0.995,
      f"{peak_freq(tr_half):.1f} vs {peak_freq(tr_open):.1f}")

tr_growl = render(doc([note(1, 0, 700_000, 67)], tr,
                      turns=[ev.TurnPoint("L00000001", "growl", 800)]))
check("T17 咆哮有起伏", envelope_var(tr_growl) > envelope_var(tr_open) * 1.3,
      f"{envelope_var(tr_growl):.3f} vs {envelope_var(tr_open):.3f}")

_kinds = {"tremolo": vln, "mute_cup": tr, "mute_harmon": tr, "mute_plunger": tr,
          "half_valve": tr, "growl": tr, "mute_on": tr}
check("T18 新动作都能通过校验（弦乐震音给弓弦、弱音器给铜管）",
      all(not ms_validate.validate(doc([note(1, 0, 500_000, 67)], insts,
                                       turns=[ev.TurnPoint("L00000001", k, 800)]))
          for k, insts in _kinds.items()),
      str({k: ms_validate.validate(doc([note(1, 0, 500_000, 67)], v,
                                        turns=[ev.TurnPoint("L00000001", k, 800)]))
           for k, v in _kinds.items()}))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
