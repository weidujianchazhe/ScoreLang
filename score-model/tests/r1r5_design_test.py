# -*- coding: utf-8 -*-
"""R1–R5 验收（按**当前设计**重写，2026-10-19）。

旧 `r1r6_acceptance.py` 是照旧字段表链路的措辞写的清单；链路退役后，
本文件**从现有设计重新推导该验什么**，而不是把旧清单搬过来改几个字。

推导依据（每条断言都标出来源）：
  SPEC §7.7 六条不变量 · SPEC §7.1–7.6 字段语义 · 契约 §6.2 最低覆盖
  P1 结构/计算/收束分层 · P4 缺失有痕 · C-003（tempo 不属 MS）· C-004（记号不落 MS）

**不验什么**（不是 N/A，而是当前模型不主张）：
  - tie / tuplet / 奏法的"装配正确性"：MS 不含这三类，属模型边界（`已知边界.md`）。
    旧 R1-b/R1-c 验的是旧链路能否装配它们——不是当前模型的主张，故不进清单。
  - tempo 曲线：C-003 已判不属 MS。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_edit as ed
import ms_events as ev
import ms_io as mj
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi=60):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def ev0(**kw):
    d = dict(id="e1", instrument_id=1, onset_us=0, pitch=pitch(), release_us=500_000,
             release_state="given", dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured"))
    d.update(kw)
    return ev.Event(**d)


# ══ R1 表示：当前模型声称能表达哪些演奏事实（SPEC §7.1–7.6）══
d = ev.MSDocument(events=[
    ev0(id="a", onset_us=0, release_us=500_000),
    ev0(id="b", onset_us=500_000, release_us=1_000_000, pitch=pitch(64)),
])
check("R1-1 音高四元组自洽（step/alter/octave/semitone）",
      all(e.pitch.consistent() for e in d.events))
check("R1-2 时间以整数微秒表达且 release ≥ onset",
      all(isinstance(e.onset_us, int) and e.release_us >= e.onset_us for e in d.events))
check("R1-3 力度为 permille 且三伴随字段齐全",
      all(1 <= e.dynamics.permille <= 100000 and e.dynamics.scale
          and e.dynamics.calibration_ref for e in d.events))
check("R1-4 释放三态与取值一致（given⟺有值）",
      all((e.release_state == "given") == (e.release_us is not None) for e in d.events))

ped = ev.MSDocument(events=[ev0()], pedals=[ev.PedalSegment(1, "sustain", 0, 900_000, 700)])
check("R1-5 踏板段：类型合法、深度 0..1000、起止有序",
      ped.pedals[0].kind == "sustain" and 0 <= ped.pedals[0].depth_permille <= 1000
      and ped.pedals[0].end_us > ped.pedals[0].start_us)
check("R1-6 约束档与琴数自洽（single_piano ⇒ count=1）",
      ev.validate(ev.MSDocument(constraint_mode="single_piano", piano_count=1, events=[ev0()])) == []
      and any("V6" in e for e in ev.validate(
          ev.MSDocument(constraint_mode="single_piano", piano_count=2, events=[ev0()]))))

# ══ R2 身份与引用（SPEC §7.2；缺口有痕 P4）══
dup = ev.MSDocument(events=[ev0(id="x"), ev0(id="x", onset_us=600_000)])
check("R2-1 事件 id 唯一（重复 id 被拒）",
      any("重复" in e or "id" in e.lower() for e in ev.validate(dup)), str(ev.validate(dup))[:60])

retired = ev.MSDocument(events=[ev0(id="r1")], retired_ids=["r1"])
check("R2-2 作废 id 不得复用（retired_ids 与现有事件不得相交）",
      any("R2" in e or "作废" in e for e in ev.validate(retired)), str(ev.validate(retired))[:60])

check("R2-3 mechanical 下 sostenuto 不带 targets（V4）",
      any("V4" in e for e in ev.validate(
          ev.MSDocument(constraint_mode="unlimited",
                        pedals=[ev.PedalSegment(1, "sostenuto", 0, 1000, 1000, "mechanical", ["e1"])]))))

# ══ R3 关系：结构层能算、不合并（P1）══
three = ev.MSDocument(events=[ev0(id="s1"), ev0(id="s2"), ev0(id="s3")])
check("R3-1 同刻三事件结构合法且不被合并", ev.validate(three) == [] and len(three.events) == 3)
check("R3-2 结构层不判同键同刻", ev.validate(three) == [])
check("R3-3 演奏收束层能识别同键同刻",
      any("R-1" in e for e in ev.check_realization(three)))

# ══ R4 派生：时间换算与时长（SPEC §4.2；契约 §6.2.9）══
import ms_midi as mm
doc = ev.MSDocument(events=[ev0(onset_us=0, release_us=500_000)])
data, rep = mm.write_midi(doc, time_base_us=500_000)
back = mm.read_midi(data)["notes"]
check("R4-1 微秒 ↔ tick 换算可逆（500ms ↔ 480 tick @♥=120）",
      any(n["tick"] == 480 for n in back), str([n["tick"] for n in back]))
check("R4-2 时长派生 = release - onset", doc.events[0].release_us - doc.events[0].onset_us == 500_000)

# ══ R5 保真与状态（P4 缺失有痕；C-003/C-004）══
np_ev = ev0(dynamics=ev.Dynamics(ms.NOT_PROVIDED, 1000))
check("R5-1 NOT_PROVIDED 不得携带数值",
      any("V3" in e for e in ev.validate(ev.MSDocument(events=[np_ev]))))

fake = ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "midi_inverted")
check("R5-2 编辑层拒绝冒用来源（midi_inverted/measured）",
      not ed.set_dynamics(doc, "e1", 1000, src="midi_inverted").ok)

check("R5-3 写出前强制校验（非法文档不落盘）", True)   # 占位，由下面 try 覆盖
try:
    mj.dumps(ev.MSDocument(events=[ev0(onset_us=1_000_000, release_us=500_000)]))
    results.pop()          # 撤掉占位
    check("R5-3 写出前强制校验（非法文档不落盘）", False)
except ValueError:
    results.pop()          # 撤掉占位
    check("R5-3 写出前强制校验（非法文档不落盘）", True)

# ── 输出 ─────────────────────────────────────────────────────
bad = [r for r in results if not r[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
