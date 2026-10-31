# -*- coding: utf-8 -*-
"""止音（release）测试：音符只写起始时间，停止是独立事件，且总有缓冲。

守的语义：
  · 音符行不带释放时间；停止由 `<id> off <time> [kind] [ramp]` 给出
  · 止音方式/缓冲按**乐器机制**取默认（钢琴制音 70ms、弓弦离弦 45ms、吹奏收气 130ms…）
  · 不是"到点硬切"：渲染在 release 之后按 ramp 衰减
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
import ms_events as ev
import ms_instruments as reg
import ms_io
import ms_semantics as ms
import ms_validate

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


STEPS = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
         9: ("A", 0), 11: ("B", 0)}


def note(i, inst, onset, dur, semi=60, **kw):
    step, alter = STEPS[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=inst, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"),
                    **kw)


# ── 1) 机制默认：不同乐器止音方式不同，但都有缓冲 ─────────
check("A1 钢琴：制音器 70ms",
      reg.resolve("acoustic_grand_piano")["off"] == {"kind": "damper", "ramp_ms": 70},
      str(reg.resolve("acoustic_grand_piano")["off"]))
check("A2 弓弦：离弦 45ms",
      reg.resolve("violin")["off"]["kind"] == "bow_lift"
      and reg.resolve("violin")["off"]["ramp_ms"] == 45,
      str(reg.resolve("violin")["off"]))
check("A3 吹奏：收气（气簧 100ms / 唇簧 130ms，都比弦类长）",
      reg.resolve("flute")["off"] == {"kind": "breath_stop", "ramp_ms": 100}
      and reg.resolve("trumpet")["off"]["ramp_ms"] == 130,
      str(reg.resolve("flute")["off"]) + " / " + str(reg.resolve("trumpet")["off"]))
check("A4 拨弦：手停 60ms", reg.resolve("acoustic_guitar_steel")["off"]["kind"] == "pick_stop")
check("A5 所有机制都有止音默认（没有「到点就没」的乐器）",
      all(v["ramp_ms"] > 0 for v in reg.OFF_DEFAULTS.values()), str(reg.OFF_DEFAULTS))

# ── 2) 文件：音符只有起始时间，止音是独立一行 ──────────────
doc = ev.MSDocument(events=[note(1, 1, 0, 500_000)], instruments=[
    ev.Instrument("P1", "acoustic_grand_piano", "steinway_d")])
text = ms_io.dump(doc)
note_line = next(l for l in text.splitlines() if l.startswith("L00000001 "))
off_line = next(l for l in text.splitlines() if " off " in l)
check("B1 音符行 15 列（无释放列）", len(note_line.split()) == 15, note_line)
check("B2 止音单独一行（id off 时间 kind ramp）",
      off_line.split()[0] == "L00000001" and off_line.split()[1] == "off"
      and off_line.split()[2] == "500000" and len(off_line.split()) == 5, off_line)
check("B3 未写 kind/ramp 时留空（按乐器默认）",
      off_line.split()[3:] == ["-", "-"], off_line)

back = ms_io.parse(text)
check("B4 往返：释放时间由止音事件回填", back.events[0].release_us == 500_000)
check("B5 往返字节一致", ms_io.dump(back) == text)

# ── 3) 显式止音方式/缓冲 ──────────────────────────────────
doc2 = ev.MSDocument(events=[note(1, 1, 0, 400_000, off_kind="mallet_damp", off_ramp_us=120_000)],
                     instruments=[ev.Instrument("P1", "acoustic_grand_piano", "steinway_d")])
t2 = ms_io.dump(doc2)
o2 = next(l for l in t2.splitlines() if " off " in l)
check("B6 显式 kind/ramp 写进文件", o2.split()[3:] == ["mallet_damp", "120000"], o2)
b2 = ms_io.parse(t2)
check("B7 往返保留 kind/ramp",
      b2.events[0].off_kind == "mallet_damp" and b2.events[0].off_ramp_us == 120_000,
      str((b2.events[0].off_kind, b2.events[0].off_ramp_us)))

# ── 4) 校验 ─────────────────────────────────────────────
bad_kind = ev.MSDocument(events=[note(1, 1, 0, 400_000, off_kind="explode")],
                         instruments=[ev.Instrument("P1", "acoustic_grand_piano")])
check("B8 非法止音方式 → 拒绝",
      any("止音方式非法" in e for e in ms_validate.validate(bad_kind)),
      str(ms_validate.validate(bad_kind)))
bad_ramp = ev.MSDocument(events=[note(1, 1, 0, 400_000, off_ramp_us=-5)],
                         instruments=[ev.Instrument("P1", "acoustic_grand_piano")])
check("B9 负缓冲 → 拒绝",
      any("止音缓冲越界" in e for e in ms_validate.validate(bad_ramp)),
      str(ms_validate.validate(bad_ramp)))

# ── 5) 渲染：release 之后按 ramp 衰减，不是硬切 ────────────
SR = make_audio.SR

def render(ramp_us):
    d = ev.MSDocument(events=[note(1, 1, 0, 500_000, off_ramp_us=ramp_us)],
                      instruments=[ev.Instrument("P1", "acoustic_grand_piano", "steinway_d")])
    return make_audio.render(d).mean(axis=1)

def rms(x, a, b):
    seg = x[int(a * SR):int(b * SR)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0

short = render(10_000)      # 10ms 缓冲：几乎立刻停
long = render(300_000)      # 300ms 缓冲：停得慢
check("C1 缓冲不同 → release 之后能量不同",
      rms(long, 0.55, 0.75) > rms(short, 0.55, 0.75) * 3,
      f"{rms(long, 0.55, 0.75):.4f} vs {rms(short, 0.55, 0.75):.4f}")
check("C2 短缓冲：release 后 100ms 基本安静",
      rms(short, 0.62, 0.72) < rms(short, 0.30, 0.45) * 0.05,
      f"{rms(short, 0.62, 0.72):.5f} vs {rms(short, 0.30, 0.45):.4f}")
check("C3 长缓冲：release 后 100ms 仍有明显余音",
      rms(long, 0.60, 0.70) > rms(long, 0.30, 0.45) * 0.05,
      f"{rms(long, 0.60, 0.70):.4f} vs {rms(long, 0.30, 0.45):.4f}")

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
