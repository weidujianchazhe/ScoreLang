# -*- coding: utf-8 -*-
"""ABC → 任务 JSON（spec）：把技能产出的 ABC 直接交给引擎出声 / 出图。

技能（`skills/`）写 ABC 双行谱，引擎吃任务 JSON —— 本桥是两者唯一的衔接点。
只做机械搬运：小节拍位、力度名、和弦展开、每小节换踏板；**不做音乐判断**。

用法：cd score-model && python importers/abc_spec.py <输入.abc> <输出.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms/_core", "perform", "analyze",
                                        "render", "audio", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import abc_parse                                    # noqa: E402

SHARP = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
         6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}
LEVELS = {"ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"}


def name_of(midi: int) -> str:
    step, alter = SHARP[midi % 12]
    return f"{step}{'#' if alter else ''}{midi // 12 - 1}"


def to_spec(abc_path: str) -> dict:
    data = abc_parse.parse_abc(abc_path)
    meter, bpm = data["meter"], data["bpm"]
    bars = data["bars"]
    if not bars:
        raise SystemExit("ABC 里没有可解析的声部")

    notes: list[dict] = []
    for voice_bars in bars.values():
        for bi, bar in enumerate(voice_bars):
            base = bi * meter
            for tok in bar:
                if tok["kind"] == "rest" or not tok["keys"]:
                    continue
                dur = max(0.05, float(tok["dur"]))
                lvl = tok.get("dyn") or "mf"
                if lvl not in LEVELS:
                    lvl = "mf"
                for k in tok["keys"]:
                    notes.append({"inst": 1, "pitch": name_of(int(k)),
                                  "beat": round(base + float(tok["off"]), 4),
                                  "beats": round(dur, 4), "level": lvl})

    # 踏板：跟着和声换。4/4 及以上半小节一换，其余整小节一换（与 abc2ms 同规则）
    n_bars = max(len(v) for v in bars.values())
    pedals: list[dict] = []
    for bi in range(n_bars):
        b0 = bi * meter
        if meter >= 4:
            pedals.append({"inst": 1, "kind": "sustain", "start": b0, "end": b0 + meter / 2})
            pedals.append({"inst": 1, "kind": "sustain",
                           "start": b0 + meter / 2, "end": b0 + meter})
        else:
            pedals.append({"inst": 1, "kind": "sustain", "start": b0, "end": b0 + meter})

    notes.sort(key=lambda n: (n["beat"], n["pitch"]))
    return {"bpm": round(float(bpm), 2), "meter": [meter, 4],
            "title": data["header"].get("T", "未命名"),
            "instruments": [{"type": "piano"}],
            "notes": notes, "pedals": pedals}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法：python importers/abc_spec.py <输入.abc> <输出.json>")
        raise SystemExit(2)
    spec = to_spec(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出：{len(spec['notes'])} 音符 / {len(spec['pedals'])} 踏板段 / "
          f"{spec['bpm']}bpm {spec['meter'][0]}/{spec['meter'][1]}")
