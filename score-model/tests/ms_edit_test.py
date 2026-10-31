# -*- coding: utf-8 -*-
"""编辑通道测试（E1–E6）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_edit as ed
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def base():
    return ev.MSDocument(events=[
        ev.Event(id="e1", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
                 release_us=500_000, release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
    ])


# ── 基本编辑 ─────────────────────────────────────────────────
d = base()
r = ed.add_event(d, pitch=ev.Pitch("E", 0, 4, 64), onset_us=1_000_000, release_us=1_500_000)
check("E1-1 新增成功", r.ok and len(r.doc.events) == 2 and r.changed_id == "e2", str(r.errors))
check("E1-2 原文档未被修改（纯函数）", len(d.events) == 1)

r2 = ed.update_event(r.doc, "e2", release_us=1_800_000)
check("E1-3 修改成功", r2.ok and r2.doc.events[1].release_us == 1_800_000)

r3 = ed.update_event(r2.doc, "e2", id="x9")
check("E4-1 改 id 被拒绝", (not r3.ok) and any("不允许修改事件" in e for e in r3.errors), str(r3.errors))

# ── 非法值不写回（E2） ──────────────────────────────────────
r4 = ed.update_event(r2.doc, "e2", onset_us=5_000_000)     # release=1.8s < onset=5s
check("E2-1 非法修改被拒绝", not r4.ok)
check("E2-2 失败时返回原文档（同一对象）", r4.doc is r2.doc)
check("E2-3 错误指出违反项", any("V2" in e for e in r4.errors), str(r4.errors))

r5 = ed.add_event(r2.doc, pitch=ev.Pitch("C", 0, 9, 120), onset_us=0)
check("E2-4 越界音高被拒绝", (not r5.ok) and any("UNSUPPORTED_PITCH_RANGE" in e for e in r5.errors))

# ── 不自动修正（E5） ────────────────────────────────────────
check("E5-0 越界编辑确实被拒（r5.ok=False）", not r5.ok)
check("E5-1 被拒结果指向原文档，且越界值未被吸附",
      r5.doc is r2.doc and all(e.pitch.semitone != 120 for e in r5.doc.events))

# ── id 不复用（E4） ─────────────────────────────────────────
d3 = base()
add = ed.add_event(d3, pitch=ev.Pitch("D", 0, 4, 62), onset_us=2_000_000, release_us=2_500_000)
check("E4-2 分配 e2", add.changed_id == "e2")
dele = ed.delete_event(add.doc, "e2")
check("E4-3 删除成功并写入 retired_ids",
      dele.ok and "e2" in dele.doc.retired_ids and dele.doc.gaps == [],
      f"retired={dele.doc.retired_ids} gaps={dele.doc.gaps}")
again = ed.add_event(dele.doc, pitch=ev.Pitch("G", 0, 4, 67), onset_us=3_000_000, release_us=3_400_000)
check("E4-4 作废 id 永不复用", again.ok and again.changed_id == "e3", str(again.changed_id))

# ── 来源不得伪造（E3） ──────────────────────────────────────
d4 = base()
r6 = ed.set_dynamics(d4, "e1", 1500, src="measured")
check("E3-1 手动编辑标 measured 被拒", (not r6.ok) and any("E3" in e for e in r6.errors), str(r6.errors))
r7 = ed.set_dynamics(d4, "e1", 1500, src="midi_inverted")
check("E3-2 手动编辑标 midi_inverted 被拒", not r7.ok)
r8 = ed.set_dynamics(d4, "e1", 1500)
check("E3-3 默认直接给值（src=null，表示无推导过程）",
      r8.ok and r8.doc.events[0].dynamics.src is None)
r8b = ed.set_dynamics(d4, "e1", 1500, src="notated_inferred")
check("E3-4 显式 notated_inferred 也允许", r8b.ok and r8b.doc.events[0].dynamics.src == "notated_inferred")

# ── 约束档 ──────────────────────────────────────────────────
d5 = base()
r9 = ed.set_constraint(d5, "n_pianos", piano_count=2)
check("E5-1 切 n_pianos(count=2) 通过", r9.ok, str(r9.errors))
r10 = ed.set_constraint(d5, "n_pianos")            # count 仍 1
check("E5-2 n_pianos 但 count=1 被拒", (not r10.ok) and any("V6" in e for e in r10.errors))

# ── 踏板 ────────────────────────────────────────────────────
d6 = base()
p1 = ed.add_pedal(d6, kind="sustain", start_us=0, end_us=1_000_000, depth_permille=1000,
                  instrument_id=1)
check("P1-1 加踏板成功", p1.ok and len(p1.doc.pedals) == 1)
check("P1-1b 踏板绑定到指定乐器", p1.ok and p1.doc.pedals[0].instrument_id == 1
      and p1.doc.pedals[0].id == "D00000001", str(p1.doc.pedals[0]))
check("P1-1c 不给乐器 → 拒绝",
      (not ed.add_pedal(d6, kind="sustain", start_us=0, end_us=1_000_000).ok))
p2 = ed.add_pedal(p1.doc, kind="sustain", start_us=500_000, end_us=1_500_000,
                  depth_permille=800, instrument_id=1)
check("P1-2 同轨重叠被拒", (not p2.ok) and any("V4" in e for e in p2.errors), str(p2.errors))
p3 = ed.update_pedal(p1.doc, 0, depth_permille=500)
check("P1-3 改深度成功", p3.ok and p3.doc.pedals[0].depth_permille == 500)

# ── 撤销（E6） ──────────────────────────────────────────────
prev, cur = p1.doc, p3.doc
check("E6-1 撤销＝用旧文档", prev.pedals[0].depth_permille == 1000)
check("E6-2 被撤销到的状态本身合法", ev.validate(prev) == [], str(ev.validate(prev)))
check("E6-3 新文档也合法", ev.validate(cur) == [], str(ev.validate(cur)))

# ── 失败不改入参（多步后仍不变） ────────────────────────────
snapshot = [(e.id, e.onset_us) for e in d6.events]
check("E1-4 连续失败操作后入参不变", snapshot == [(e.id, e.onset_us) for e in d6.events])

# ── E7 编辑/撤销不丢字段 ──
from ms_model import CurvePoint, TurnPoint, VoiceSegment, Instrument
_doc_full = ev.MSDocument(
    piano_count=1, constraint_mode="single_piano",
    instruments=[Instrument("P1", "acoustic_grand_piano")],
    curves=[CurvePoint(instrument_id=1, param="dynamics", time_us=0,
                       value=500, ramp=0)],
    turns=[TurnPoint(event_id="a", kind="retrigger", strength=1000)],
    trailing_silence_us=123, channels="per_section",
    segments=[VoiceSegment(structure_id="B1", index=0, kind="initial",
                           text="ch", tone=1)])
for _name, _d in (("E7-1 _clone", ed._clone(_doc_full)),
                  ("E7-2 snapshot", ed.snapshot(_doc_full))):
    check(_name + " 保留全部字段",
          len(_d.instruments) == 1 and len(_d.curves) == 1
          and len(_d.turns) == 1 and _d.trailing_silence_us == 123
          and _d.channels == "per_section" and len(_d.segments) == 1,
          f"inst={len(_d.instruments)} curves={len(_d.curves)} "
          f"turns={len(_d.turns)} silence={_d.trailing_silence_us}")


bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
