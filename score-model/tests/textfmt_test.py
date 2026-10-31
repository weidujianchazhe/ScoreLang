# -*- coding: utf-8 -*-
"""文本谱格式测试：解析/规范写回/错误。"""
from __future__ import annotations

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


TXT = """# 测试
title 水镜
bpm 63
meter 3/4
inst 1 piano
inst 2 cello

P1 C4 0 1 mf
P1 E4 1 0.5
2:C5@2+1/p
E4@3+1/mf
pedal P1 sustain 0 4
curve P1 dynamics 0 500 8 950
turn 3 retrigger 900
"""
spec = ms.parse_text(TXT)
check("T1 bpm", spec["bpm"] == 63.0, str(spec["bpm"]))
check("T2 meter", spec["meter"] == [3, 4], str(spec["meter"]))
check("T3 title", spec.get("title") == "水镜", str(spec.get("title")))
check("T4 乐器数", len(spec["instruments"]) == 2, str(spec["instruments"]))
check("T5 音符数", len(spec["notes"]) == 4, str(len(spec["notes"])))
check("T6 简写解析", spec["notes"][2]["inst"] == 2 and spec["notes"][2]["level"] == "p",
      str(spec["notes"][2]))
check("T7 踏板", spec["pedals"][0]["kind"] == "sustain"
      and spec["pedals"][0]["end"] == 4.0, str(spec["pedals"]))
check("T8 曲线", spec["curves"][0]["points"][1] == [8.0, 950], str(spec["curves"]))
check("T9 转折", spec["turns"][0]["kind"] == "retrigger", str(spec["turns"]))
song = ms.build(spec)
check("T10 可 build", song.summary()["notes"] == 4, str(song.summary()))

roundtrip = ms.parse_text(ms.dump_text(spec))
check("T11 dump→parse 音数一致", len(roundtrip["notes"]) == 4,
      str(len(roundtrip["notes"])))
check("T12 dump 保 bpm/meter", roundtrip["bpm"] == 63.0
      and roundtrip["meter"] == [3, 4])
check("T13 dump 保踏板", len(roundtrip.get("pedals") or []) == 1)

for bad in ("", "bpm 120\n", "curve P1 nope 0 1"):
    try:
        ms.parse_text(bad)
        ok = False
    except ValueError:
        ok = True
    check("T14 非法文本拒绝", ok, bad[:20])

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(failed)}，失败 {len(failed)}")
if failed:
    raise SystemExit(1)
