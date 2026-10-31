# -*- coding: utf-8 -*-
"""diagnose 测试：位置/原因/建议，且不改 spec。"""
from __future__ import annotations

import json
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


# 1) 同音重叠 + 踏板间隙
spec = {
    "bpm": 100,
    "notes": [
        {"pitch": "C4", "beat": 0, "beats": 2},
        {"pitch": "C4", "beat": 1, "beats": 1},
        {"pitch": "E4", "beat": 3, "beats": 1},
    ],
    "pedals": [
        {"inst": 1, "kind": "sustain", "start": 0, "end": 2},
        {"inst": 1, "kind": "sustain", "start": 2, "end": 4},
    ],
}
res = ms.diagnose(spec)
codes = {f["code"] for f in res["findings"]}
check("D1 ok 且有 findings", res.get("ok") and len(res["findings"]) > 0, res.get("summary"))
check("D2 同音重叠定位", "same_pitch_overlap" in codes, str(codes))
check("D3 踏板间隙定位", "pedal_gap" in codes, str(codes))
ov = next(f for f in res["findings"] if f["code"] == "same_pitch_overlap")
check("D4 位置含 bar/beat", "bar" in ov["where"] and "beat" in ov["where"],
      str(ov["where"]))
check("D5 有原因与建议", bool(ov.get("why")) and bool(ov.get("suggestion")))
check("D6 summary 含原因/建议", "原因" in res["summary"] and "建议" in res["summary"])

# 2) 收束：多编制同时结束
spec2 = {
    "bpm": 90,
    "instruments": [{"type": "piano"}, {"type": "cello"}],
    "notes": [{"inst": 1, "pitch": "C4", "beat": 0, "beats": 4},
              {"inst": 2, "pitch": "C2", "beat": 0, "beats": 4}],
}
res2 = ms.diagnose(spec2)
check("D7 收束问题定位", any(f["code"] == "ending_voices" for f in res2["findings"]),
      str([f["code"] for f in res2["findings"]]))

# 3) 结构偏差
spec3 = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 1}]}
res3 = ms.diagnose(spec3, intent={"structure": {"section_bars": [4, 4]}})
check("D8 结构偏差定位", any(f["code"] == "structure_bars" for f in res3["findings"]),
      str([f["code"] for f in res3["findings"]]))

# 4) 奏法过量
spec4 = {"bpm": 100, "notes": [
    {"pitch": "C4", "beat": i, "beats": 0.5, "articulation": "staccato"}
    for i in range(6)]}
res4 = ms.diagnose(spec4, intent={"technique": {"density": "low"}})
check("D9 奏法过量定位", any(f["code"] == "technique_density" for f in res4["findings"]),
      str([f["code"] for f in res4["findings"]]))

# 5) 干净任务：不乱报
spec5 = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 1}]}
res5 = ms.diagnose(spec5)
check("D10 干净任务无 findings", res5["findings"] == [], str(res5["findings"]))
check("D11 干净任务 summary 有提示", "未发现" in res5["summary"], res5["summary"])

# 6) 不改 spec、JSON 可序列化、严重度排序
before = json.dumps(spec, sort_keys=True)
res6 = ms.diagnose(spec)
check("D12 不改 spec", json.dumps(spec, sort_keys=True) == before)
json.dumps(res6, ensure_ascii=False)
check("D13 JSON 可序列化", True)
order = [{"high": 0, "medium": 1, "low": 2}[f["severity"]] for f in res6["findings"]]
check("D14 严重度排序", order == sorted(order), str(order))

# 7) Song 输入
song = ms.build(spec2)
res7 = ms.diagnose(song)
check("D15 支持 Song 输入", res7.get("ok"), res7.get("summary")[:60])

# 8) report 文本含定位；每条 finding 带复核命令
rep8 = ms.report(spec2)
check("D16 report 含诊断", "diagnosis" in rep8
      and len(rep8["diagnosis"]["findings"]) >= 1, str(list(rep8))[:80])
txt8 = ms.report_text(rep8)
check("D17 report 文本含位置", "bar=" in txt8 and "建议" in txt8, txt8[:120])
check("D18 每条 finding 带复核",
      all("verify" in f for f in res7["findings"]), str(res7["findings"][:1]))

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(failed)}，失败 {len(failed)}")
if failed:
    raise SystemExit(1)
