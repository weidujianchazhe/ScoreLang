# -*- coding: utf-8 -*-
"""音频后端适配层测试（III-3）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_audio as au
import ms_audio as ab
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def doc():
    return ev.MSDocument(events=[
        ev.Event(id="a", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
                 release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
        ev.Event(id="b", instrument_id=1, onset_us=600_000, pitch=pitch(64), release_us=None,
                 release_state="sustaining", dynamics=ev.Dynamics(ms.NOT_PROVIDED)),
    ], pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)])


# ── 后端注册 ────────────────────────────────────────────────
check("B1 可用后端含 commands 与 null", ab.available() == ["commands", "null"], str(ab.available()))
try:
    ab.get_backend("synth")
except KeyError:
    check("B2 未知后端拒绝", True)
else:
    check("B2 未知后端拒绝", False)

# ── CommandBackend ─────────────────────────────────────────
out = ab.get_backend("commands").render(doc())
check("B3 后端名标注", out["backend"] == "commands")
check("B4 两个 note_on", out["note_on_count"] == 2, str(out["note_on_count"]))
ops = [c["op"] for c in out["commands"]]
check("B5 含 note_on/note_off/sustain_until_end",
      "note_off" in ops and "sustain_until_end" in ops, str(ops))
check("B6 含踏板命令", "pedal" in ops, str(ops))

on = [c for c in out["commands"] if c["op"] == "note_on"]
check("B7 中性力度振幅=1.0", abs(on[0]["amplitude"] - 1.0) < 1e-12, str(on[0]["amplitude"]))
check("B8 NOT_PROVIDED 留痕（state 保留、幅度按中性）",
      on[1]["dynamics_state"] == ms.NOT_PROVIDED and abs(on[1]["amplitude"] - 1.0) < 1e-12,
      str(on[1]))
check("B9 含频率", abs(on[0]["freq_hz"] - 261.626) < 0.01, str(on[0]["freq_hz"]))

ped = [c for c in out["commands"] if c["op"] == "pedal"][0]
check("B10 踏板深度归一", abs(ped["depth"] - 1.0) < 1e-12 and ped["kind"] == "sustain", str(ped))

# ── 非法标定被 ms_audio 拦住 ──────────────────────────────
def bad_cal(x):
    return 0.5


try:
    ab.get_backend("commands").render(doc(), bad_cal)
except ValueError as e:
    check("B11 非法标定 → 拒绝", "f(1000)" in str(e) or "单调" in str(e), str(e))
else:
    check("B11 非法标定 → 拒绝", False)

# ── NullBackend 明确拒绝并指路 ─────────────────────────────
try:
    ab.get_backend("null").render(doc())
except RuntimeError as e:
    check("B12 NullBackend 拒绝并指引 MIDI 导出", "MIDI" in str(e), str(e)[:60])
else:
    check("B12 NullBackend 拒绝并指引 MIDI 导出", False)

# ── 命令按时间排序，note_off 优先于同刻 note_on ────────────
times = [c["at_us"] for c in out["commands"]]
check("B13 命令按时间非降序", times == sorted(times), str(times))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
