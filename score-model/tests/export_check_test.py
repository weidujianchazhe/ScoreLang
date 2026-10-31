# -*- coding: utf-8 -*-
"""export_check 测试：阻断/警告/提示/门禁。"""
from __future__ import annotations

import json
import sys
import tempfile
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


CLEAN = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 1}]}
res = ms.export_check(CLEAN)
check("E1 干净任务 ok", res["ok"] and not res["blockers"], res["summary"][:60])
check("E2 单编制提示", any("单编制" in x for x in res["info"]), str(res["info"]))

OV = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 2},
                            {"pitch": "C4", "beat": 1, "beats": 1}]}
res2 = ms.export_check(OV)
check("E3 重叠是阻断", not res2["ok"]
      and any(b.get("code") == "same_pitch_overlap" for b in res2["blockers"]),
      str([b.get("code") for b in res2["blockers"]]))

PED = {"bpm": 100, "notes": [{"pitch": "C4", "beat": 0, "beats": 1}],
       "pedals": [{"inst": 1, "kind": "sustain", "start": 0, "end": 2},
                  {"inst": 1, "kind": "sustain", "start": 2, "end": 4}]}
res3 = ms.export_check(PED)
check("E4 踏板间隙是阻断", not res3["ok"]
      and any(b.get("code") == "pedal_gap" for b in res3["blockers"]),
      str([b.get("code") for b in res3["blockers"]]))

END = {"bpm": 90, "instruments": [{"type": "piano"}, {"type": "cello"}],
       "notes": [{"inst": 1, "pitch": "C4", "beat": 0, "beats": 4},
                 {"inst": 2, "pitch": "C2", "beat": 0, "beats": 4}]}
res4 = ms.export_check(END)
check("E5 收束是警告", res4["ok"]
      and any(w.get("code") == "ending_voices" for w in res4["warnings"]),
      str([w.get("code") for w in res4["warnings"]]))
res4s = ms.export_check(END, strict=True)
check("E6 strict 把警告变不通过", not res4s["ok"], res4s["summary"][:60])

BAD = {"bpm": 100, "notes": [{"pitch": "H9", "beat": 0, "beats": 1}]}
res5 = ms.export_check(BAD)
check("E7 生成失败是阻断", not res5["ok"] and res5["blockers"], res5["summary"][:60])

check("E8 summary 有结论", "阻断" in res2["summary"] and "不通过" in res2["summary"])
json.dumps(res, ensure_ascii=False)
check("E9 JSON 可序列化", True)
check("E10 API 导出", hasattr(ms, "export_check"))

with tempfile.TemporaryDirectory() as td:
    info = ms.package(CLEAN, td, check=True, bars_per_page=2, width=900)
    exts = {f.suffix.lower() for f in Path(td).rglob("*") if f.is_file()}
    check("E11 package(check=True) 通过", {".mid", ".wav", ".png", ".abc"} <= exts,
          str(exts))
    try:
        ms.package(OV, td, check=True)
        ok = False
    except ValueError:
        ok = True
    check("E12 package(check=True) 拒绝阻断", ok)

check("E13 检查结果含 findings", isinstance(res4.get("findings"), list)
      and len(res4["findings"]) >= 1)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(failed)}，失败 {len(failed)}")
if failed:
    raise SystemExit(1)
