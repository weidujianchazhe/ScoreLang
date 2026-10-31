# -*- coding: utf-8 -*-
"""analyze_fix 原型测试：分析→修改→复核。"""
from __future__ import annotations
import pathlib

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _p in (ROOT / "ms", ROOT / "ms" / "_core", ROOT / "perform",
           ROOT / "render", ROOT / "audio", ROOT / "analyze",
           ROOT / "importers"):
    sys.path.insert(0, str(_p))

import ms  # noqa: E402


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# A 同音重叠 + 踏板间隙 + 力度越界
spec_a = {
    "bpm": 100,
    "instruments": [{"type": "piano"}],
    "notes": [
        {"pitch": "C4", "beat": 0, "beats": 2, "permille": 1200},
        {"pitch": "C4", "beat": 1, "beats": 1},
        {"pitch": "E4", "beat": 2, "beats": 1},
    ],
    "pedals": [
        {"inst": 1, "kind": "sustain", "start": 0, "end": 2},
        {"inst": 1, "kind": "sustain", "start": 2, "end": 4},
    ],
}
res = ms.analyze_fix(spec_a)
check("A1 返回 ok", res.get("ok") is True, str(res.get("warnings")))
kinds = {f["kind"] for f in res.get("fixes", [])}
check("A2 检出同音重叠", "same_pitch_overlap" in kinds, str(kinds))
check("A3 检出踏板间隙", "pedal_gap" in kinds, str(kinds))
check("A4 检出力度越界", "dynamics_range" in kinds, str(kinds))
fixed = res["spec"]
notes = fixed["notes"]
check("A5 重叠已消除", [float(notes[0]["beats"])] <= [1.0],
      str(notes[0].get("beats")))
check("A6 力度已夹紧", int(notes[0]["permille"]) <= 1000, str(notes[0].get("permille")))
if fixed.get("pedals"):
    gap = float(fixed["pedals"][1]["start"]) - float(fixed["pedals"][0]["end"])
    check("A7 踏板间隙已留", gap >= 0.2, f"gap={gap}")
else:
    check("A7 踏板间隙已留", True, "自动踏板")
check("A8 前后指标都有", bool(res["before"].get("metrics")) and bool(res["after"].get("metrics")))
check("A9 复核标记存在", "verified" in res, str(res.get("verified")))

# B dry-run：只建议不修改
res_b = ms.analyze_fix(spec_a, apply=False)
check("B1 dry-run 有修复建议", len(res_b.get("fixes") or []) > 0)
check("B2 dry-run 不标 applied", all(not f.get("applied") for f in res_b["fixes"]))
check("B3 dry-run 不改 spec", float(res_b["spec"]["notes"][0]["beats"]) == 2.0)

# C 收束错开（意图）
spec_c = {
    "bpm": 90,
    "instruments": [{"type": "piano"}, {"type": "cello"}],
    "notes": [
        {"inst": 1, "pitch": "C4", "beat": 0, "beats": 4},
        {"inst": 2, "pitch": "C2", "beat": 0, "beats": 4},
    ],
}
res_c = ms.analyze_fix(spec_c, intent={"ending": {"stagger_voices": True}})
ck = [f for f in res_c.get("fixes", []) if f["kind"] == "ending_stagger"]
check("C1 收束错开建议", len(ck) >= 1, str(ck))
beats = [n.get("beats") for n in res_c["spec"]["notes"]]
check("C2 末音已错开", len(set(beats)) > 1, str(beats))

# D 奏法过量（intent low）
spec_d = {
    "bpm": 100,
    "instruments": [{"type": "piano"}],
    "notes": [{"pitch": "C4", "beat": i, "beats": 0.5,
               "articulation": "staccato"} for i in range(8)],
}
res_d = ms.analyze_fix(spec_d, intent={"technique": {"density": "low"}})
removed = [f for f in res_d["fixes"] if f["kind"] == "technique_density"]
check("D1 奏法过量检出", len(removed) > 0, str(len(removed)))
marked = sum(1 for n in res_d["spec"]["notes"] if n.get("articulation"))
check("D2 奏法已删到上限", marked / 8 <= 0.2, f"{marked}/8")

# E 无问题任务：不该乱改
spec_e = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 1}]}
res_e = ms.analyze_fix(spec_e)
check("E1 无问题不改", res_e.get("ok") and len(res_e.get("fixes") or []) == 0,
      str(res_e.get("fixes")))
check("E2 check_spec 复核通过", res_e.get("verified") is True, str(res_e.get("warnings")))

# F build(fix=True) / package(fix=True)：先修后出图
spec_f = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 2},
                                {"pitch": "C4", "beat": 1, "beats": 1}]}
song_f = ms.build(spec_f, fix=True)
check("F1 build(fix=True) 应用修复",
      bool((song_f.fix_report or {}).get("fixes")), str(song_f.fix_report or {}))
check("F2 修复后时值已缩短", float(song_f._spec["notes"][0]["beats"]) < 2.0,
      str(song_f._spec["notes"][0]["beats"]))
song_n = ms.build(spec_f)
check("F3 不传 fix 不改", float(song_n._spec["notes"][0]["beats"]) == 2.0
      and song_n.fix_report is None)

import tempfile as _tf
with _tf.TemporaryDirectory() as _td:
    info = ms.package(spec_f, _td, fix=True, bars_per_page=2, width=900)
    exts = set()
    for f in pathlib.Path(_td).rglob("*"):
        if f.is_file():
            exts.add(f.suffix.lower())
    check("F4 package(fix=True) 出四件", {".mid", ".wav", ".png", ".abc"} <= exts)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(failed)}，失败 {len(failed)}")
if failed:
    raise SystemExit(1)
