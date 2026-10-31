# -*- coding: utf-8 -*-
"""音频语义测试：踏板两档 / section 声像 / 族音色 / 人声接口 / 声调。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import ms_events as ev
import ms_semantics as ms
import make_audio as ma

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
            5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
            10: ("B", -1), 11: ("B", 1)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def evt(iid, onset=0, dur=400_000, semi=60, eid="L00000001", perm=800, scale="relative_permille"):
    return ev.Event(id=eid, instrument_id=iid, onset_us=onset, release_us=onset + dur,
                    pitch=pitch(semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, perm, scale, "c", "measured"))


def doc(inst, events, pedals=(), segments=(), channels="per_instance"):
    d = ev.MSDocument(events=list(events), pedals=list(pedals), instruments=list(inst),
                      segments=list(segments), channels=channels)
    d.piano_count = len(inst)
    return d


def one_seg(eid, tone, *, text="a", kind="nucleus"):
    return ev.VoiceSegment("B00001", 0, kind, text, tone,
                           event_id=eid, binding_id="B00001", lang="zh")


def brightness(x):
    mono = x.mean(axis=1) if x.ndim == 2 else x
    spec = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1 / ma.SR)
    return float((spec * freqs).sum() / (spec.sum() + 1e-9))


piano = [ev.Instrument("P1", "acoustic_grand_piano", "steinway_d")]

# ── 1) una_corda：频谱变暗 ────────────────────────────────
plain = ma.render(doc(piano, [evt(1)]))
dark = ma.render(doc(piano, [evt(1)], pedals=[ev.PedalSegment(1, "una_corda", 0, 900_000, 1000)]))
check("A1 una_corda 使频谱变暗", brightness(dark) < brightness(plain),
      f"{brightness(dark):.0f} < {brightness(plain):.0f}")

# ── 2) section：声像 ─────────────────────────────────────
left_inst = [ev.Instrument("P1", "violin", None, "strings_1")]
right_inst = [ev.Instrument("P1", "trombone", None, "brass")]
L = ma.render(doc(left_inst, [evt(1, semi=76)]))
R = ma.render(doc(right_inst, [evt(1, semi=48)]))
check("A2 strings_1 偏左", L[:, 0].std() > L[:, 1].std(), f"{L[:,0].std():.3f} vs {L[:,1].std():.3f}")
check("A3 brass 偏右", R[:, 1].std() > R[:, 0].std(), f"{R[:,1].std():.3f} vs {R[:,0].std():.3f}")

# ── 3) 族音色不同 ────────────────────────────────────────
piano_wave = ma.render(doc(piano, [evt(1)]))
violin = ma.render(doc([ev.Instrument("P1", "violin")], [evt(1, semi=76)]))
check("A4 钢琴与小提琴频谱不同", abs(brightness(piano_wave) - brightness(violin)) > 50,
      f"{brightness(piano_wave):.0f} vs {brightness(violin):.0f}")

# ── 4) sustentao：只延 targets ───────────────────────────
sost = ev.PedalSegment(1, "sostenuto", 0, 1_200_000, 1000, "explicit",
                       ("L00000001",))
with_sost = ma.render(doc(piano, [evt(1, dur=100_000)], pedals=[sost]))
no_sost = ma.render(doc(piano, [evt(1, dur=100_000)]))
tail = lambda x: float(np.abs(x[int(0.3 * ma.SR):]).sum())
check("A5 sostenuto 延长目标音", tail(with_sost) > tail(no_sost),
      f"{tail(with_sost):.0f} > {tail(no_sost):.0f}")

# ── 5) 人声接口：发声段进入合成 ───────────────────────────
voice = [ev.Instrument("P1", "choir_aahs")]
no_seg = ma.render(doc(voice, [evt(1, semi=72)]))
with_seg = ma.render(doc(voice, [evt(1, semi=72)],
                         segments=[one_seg("L00000001", 1)]))
check("A6 发声段进入人声合成", not np.allclose(no_seg, with_seg))

# ── 6) 段级声调影响波形 ─────────────────────────────────
t1 = ma.render(doc(voice, [evt(1, semi=72)], segments=[one_seg("L00000001", 1)]))
t2 = ma.render(doc(voice, [evt(1, semi=72)], segments=[one_seg("L00000001", 2)]))
check("A7 不同声调波形不同", not np.allclose(t1, t2))

# ── 7) 机制分支：弓弦持续 / 拨弦更短 ───────────────────
def energy_at(x, t0, t1):
    """按绝对秒数取能量（避开尾巴静音）。"""
    mono = x.mean(axis=1)
    a, b = int(t0 * ma.SR), int(t1 * ma.SR)
    return float(np.sqrt((mono[a:b] ** 2).mean()))


bowed = ma.render(doc([ev.Instrument("P1", "violin")], [evt(1, dur=1_000_000, semi=76, eid="L00000001")]))
hammer = ma.render(doc([ev.Instrument("P1", "acoustic_grand_piano")], [evt(1, dur=1_000_000, semi=60, eid="L00000001")]))
pluck = ma.render(doc([ev.Instrument("P1", "acoustic_guitar_nylon")], [evt(1, dur=1_000_000, semi=60, eid="L00000001")]))
check("A8 弓弦停留比击弦长", energy_at(bowed, 0.8, 0.98) > energy_at(hammer, 0.8, 0.98),
      f"{energy_at(bowed,0.8,0.98):.4f} vs {energy_at(hammer,0.8,0.98):.4f}")
def decay_ratio(x):
    """后段/前段能量比：越小衰减越快。"""
    return energy_at(x, 0.45, 0.95) / max(1e-9, energy_at(x, 0.05, 0.20))


check("A9 拨弦衰减比击弦快", decay_ratio(pluck) < decay_ratio(hammer),
      f"{decay_ratio(pluck):.3f} vs {decay_ratio(hammer):.3f}")

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
