# -*- coding: utf-8 -*-
"""撤销/重做栈测试（IV-1）。"""
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
import ms_edit as un

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi=60):
    return ev.Pitch("C", 0, 4, semi)


def base():
    return ev.MSDocument(events=[
        ev.Event(id="e1", instrument_id=1, onset_us=0, pitch=pitch(), release_us=500_000,
                 release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
    ])


# ── 基本 ────────────────────────────────────────────────────
st = un.UndoStack(base())
check("U1 初始深度 1、不可撤销", st.depth == 1 and not st.can_undo and not st.can_redo)
check("U2 初始 current() 合法", ev.validate(st.current()) == [])

r = ed.add_event(base(), pitch=ev.Pitch("E", 0, 4, 64), onset_us=1_000_000, release_us=1_500_000)
check("U3 编辑成功", r.ok)
check("U4 apply 成功入栈", st.apply(r) is True)
check("U5 深度 2、可撤销", st.depth == 2 and st.can_undo and not st.can_redo)

back = st.undo()
check("U6 撤销回到 1 个事件", len(back.events) == 1, str(len(back.events)))
check("U7 撤销后仍可重做", st.can_redo)
fwd = st.redo()
check("U8 重做回到 2 个事件", len(fwd.events) == 2)

# ── 边界 ────────────────────────────────────────────────────
st2 = un.UndoStack(base())
check("U9 栈底 undo 返回 None", st2.undo() is None)
check("U10 栈顶 redo 返回 None", st2.redo() is None)

# ── 新推入清空重做分支 ─────────────────────────────────────
st3 = un.UndoStack(base())
st3.apply(ed.add_event(base(), pitch=ev.Pitch("D", 0, 4, 62), onset_us=1_000_000, release_us=1_400_000))
st3.undo()
check("U11 撤销后可重做", st3.can_redo)
st3.apply(ed.add_event(st3.current(), pitch=ev.Pitch("G", 0, 4, 67),
                       onset_us=2_000_000, release_us=2_400_000))
check("U12 新推入后重做分支被清空", not st3.can_redo)

# ── 非法文档不得入栈 ──────────────────────────────────────
bad_doc = base()
bad_doc.events.append(ev.Event(id="bad", instrument_id=1, onset_us=1_000_000,
                               pitch=pitch(), release_us=900_000, release_state="given"))
try:
    un.UndoStack(bad_doc)
except ValueError:
    check("U13 非法初始文档被拒", True)
else:
    check("U13 非法初始文档被拒", False)

st4 = un.UndoStack(base())
try:
    st4.push(bad_doc)
except ValueError:
    check("U14 非法文档 push 被拒", True)
else:
    check("U14 非法文档 push 被拒", False)

# ── 快照隔离 ───────────────────────────────────────────────
st5 = un.UndoStack(base())
snap = st5.current()
snap.events.append(ev.Event(id="x", instrument_id=1, onset_us=9_000_000, pitch=pitch(),
                            release_us=9_500_000, release_state="given"))
check("U15 外部修改快照不影响栈内", len(st5.current().events) == 1, str(len(st5.current().events)))

# ── 上限与显式丢弃 ────────────────────────────────────────
st6 = un.UndoStack(base(), limit=3)
for i in range(5):
    st6.apply(ed.add_event(st6.current(), pitch=ev.Pitch("C", 0, 4, 60),
                           onset_us=(i + 1) * 1_000_000, release_us=(i + 1) * 1_000_000 + 400_000))
check("U16 深度不超过上限", st6.depth <= 3, str(st6.depth))
check("U17 超限丢弃被记录", st6.dropped >= 1, str(st6.dropped))

# ── history 摘要 ───────────────────────────────────────────
h = un.UndoStack(base())
h.apply(r)
check("U18 history 给出帧摘要", len(h.history()) == 2 and h.history()[-1]["events"] == 2,
      str(h.history()))

# ── 与编辑失败组合：不改变栈 ──────────────────────────────
st7 = un.UndoStack(base())
bad_edit = ed.update_event(base(), "e1", onset_us=9_000_000)   # release < onset
check("U19 失败编辑 apply 返回 False", st7.apply(bad_edit) is False)
check("U20 失败编辑不改变深度", st7.depth == 1, str(st7.depth))

bad = [x for x in results if not x[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
