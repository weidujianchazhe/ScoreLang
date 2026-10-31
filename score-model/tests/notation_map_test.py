# -*- coding: utf-8 -*-
"""记谱对照规则测试：动作 ↔ 谱面符号 ↔ 连音/延音线。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_instruments as reg
import ms_notation_map as nm
import ms_render_staff2 as r2
import ms_semantics as ms

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


STEPS = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
         9: ("A", 0), 11: ("B", 0)}


def note(i, onset, dur, semi=60):
    step, alter = STEPS[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=1, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


# ── 1) 对照表要覆盖所有动作 ─────────────────────────────
missing = [k for k in reg.ACTION_MECHS if k not in nm.MS_TO_SYMBOL]
check("N1 每个动作都有记谱对照", not missing, str(missing))
check("N2 弓法记号可用", nm.symbol_for("bow_up")[0] == "V"
      and nm.symbol_for("bow_down")[0] == "Π")
check("N3 反向可查（V → 上弓）", nm.by_symbol("V") == ["bow_up"], str(nm.by_symbol("V")))
check("N4 弱音器记号双向", nm.symbol_for("mute_on")[0] == "con sord."
      and nm.by_symbol("con sord.") == ["mute_on"])
check("N5 未登记动作返回 None 不抛", nm.symbol_for("no_such_action")[0] is None)
check("N6 连线类不画符号（靠连线表达）",
      nm.symbol_for("liaison")[0] is None and nm.symbol_for("break")[0] is None)

# ── 2) 连音/延音规则 ───────────────────────────────────
tie = nm.arcs_for([note(1, 0, 300_000), note(2, 300_000, 300_000)])
check("N7 同音相接 → 延音线", tie == [("tie", "L00000001", "L00000002")], str(tie))
slur = nm.arcs_for([note(1, 0, 300_000, 60), note(2, 300_000, 300_000, 64)],
                   [ev.TurnPoint("L00000002", "liaison", 800)])
check("N8 不同音相接 + 标了 liaison → 连音线", slur == [("slur", "L00000001", "L00000002")], str(slur))
plain = nm.arcs_for([note(1, 0, 300_000, 60), note(2, 300_000, 300_000, 64)])
check("N9 不同音相接但没标 liaison → 不画（谱面连音线是有意标的）", plain == [], str(plain))
gap = nm.arcs_for([note(1, 0, 300_000, 60), note(2, 400_000, 300_000, 60)])
check("N10 有空隙 → 不画", gap == [], str(gap))
brk = nm.arcs_for([note(1, 0, 300_000), note(2, 300_000, 300_000)],
                  [ev.TurnPoint("L00000002", "restrike", 800)])
check("N11 重新发音打断延音线", brk == [], str(brk))

# ── 3) 谱面真的画出来 ──────────────────────────────────
d = ev.MSDocument(events=[note(1, 0, 400_000, 67), note(2, 400_000, 400_000, 67)],
                  turns=[ev.TurnPoint("L00000001", "bow_up", 800)])
svg = r2.render_staff2(d)
check("N12 谱面画了动作记号", 'class="turn turn-bow_up"' in svg and ">V<" in svg)
check("N13 谱面画了延音线", 'class="tie"' in svg)

# ── 4) 踏板/曲线的记号对照 ────────────────────────────
check("N14 踏板都有记谱对照",
      all(k in nm.PEDAL_SYMBOL for k in ("sustain", "sostenuto", "una_corda",
                                         "sordino", "swell", "tuning", "hihat")),
      str(sorted(nm.PEDAL_SYMBOL)))
check("N15 曲线参数都有对照",
      all(p in nm.CURVE_SYMBOL for p in reg.CURVE_PARAMS), str(sorted(nm.CURVE_SYMBOL)))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
