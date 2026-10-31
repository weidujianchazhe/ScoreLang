# -*- coding: utf-8 -*-
"""生成“演奏语义对照”：奏法/装饰音/转折/曲线/和声 → 实际实现。

输出：
  docs/reference/演奏语义对照.md
  docs/reference/performance_semantics.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms", "ms/_core", "perform", "render",
                                       "audio", "analyze", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms_articulation as art  # noqa: E402
import ms_ornament as orn  # noqa: E402
import ms_performance as perf  # noqa: E402

OUT = ROOT / "docs" / "reference"
OUT.mkdir(parents=True, exist_ok=True)

data = {
    "articulations": art.table(),
    "ornaments": {
        "grace_short": {"rule": "主音前 25%（从前音借时间）", "pm": orn.GRACE_SHORT_PM},
        "appoggiatura_long": {"rule": "拍上占主音 50%（从主音借）", "pm": orn.APPOGGIATURA_LONG_PM},
        "mordent": {"rule": "辅助音占 10%，需上邻音", "pm": orn.MORDENT_AUX_PM},
        "turn": {"rule": "四音各 15%，需上/下邻音", "pm": orn.TURN_EACH_PM},
        "trill": {"rule": "主音/上邻音交替，实测 10 次/秒", "hz": orn.TRILL_RATE_HZ},
    },
    "turns": {k: v for k, v in perf.TURN_TRANSIENT.items()},
    "curves": {
        "dynamics": {"audio": True, "where": "make_audio 逐样本插值"},
        "tempo": {"audio": False, "where": "分析/呈现用，音频不实现"},
        "pedal": {"audio": False, "where": "踏板另有 PedalSegment"},
        "brightness": {"audio": False, "where": "分析/呈现用"},
        "expression": {"audio": False, "where": "分析/呈现用"},
    },
    "harmony": {"audio": False, "where": "S02 分析（counterpoint/harmonic），不生成和声动作"},
}
(OUT / "performance_semantics.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

lines = ["# 演奏语义对照（实际实现）", "",
         "> 说明“某个奏法/装饰音/动作，在这套引擎里**具体怎么实现**、参数是多少、哪里不实现”。", "",
         "## 1. 奏法（articulation）", "",
         "| 名称 | 实际实现 | 效果 |", "|---|---|---|"]
for name, v in sorted(art.table().items()):
    lines.append(f"| `{name}` | gate ×{v['gate_pm']/1000:.2f}，力度 ×{v['vel_pm']/1000:.2f} | "
                 f"时值缩短到 {v['gate_pm']/10:.0f}%，力度 {'不变' if v['vel_pm']==1000 else '加大'} |")
lines += ["", "写入方式：Guide `g.note(..., articulation=\"staccato\")` 或 JSON `articulation`；",
          "MD 标签格式**暂不支持**奏法字段。", "",
          "## 2. 装饰音（ornament）", "",
          "| 名称 | 展开规则 |", "|---|---|"]
for name, v in data["ornaments"].items():
    lines.append(f"| `{name}` | {v['rule']} |")
lines += ["", "实现方式：`ms_ornament.expand()` 在写谱时**展开成具体音符**（MS 里存展开后的音）；",
          "邻音音高必须由上游给出（MS 不含调号）。", "",
          "## 3. 演奏转折（turn / action）", "",
          "| 名称 | 声音实现 |", "|---|---|"]
for name, v in data["turns"].items():
    if v is None:
        lines.append(f"| `{name}` | 无瞬态（只作结构/连奏标记） |")
    else:
        lines.append(f"| `{name}` | {v['kind']}：{v['sec']*1000:.0f}ms，"
                     f"gain {v['gain']}，band {v['band']} |")
lines += ["", "`turn` 用 Guide `g.turn(id, kind)` 或 JSON `turns`。", "",
          "## 4. 连续参数（curve）", "",
          "| 参数 | 音频实现 | 说明 |", "|---|---|---|"]
for name, v in data["curves"].items():
    lines.append(f"| `{name}` | {'✅' if v['audio'] else '❌'} | {v['where']} |")
lines += ["", "## 5. 和声", "",
          "**没有“和声动作”这种演奏实现**；和声只作为 S02 分析量",
          "（`counterpoint`、`harmonic`、段落四维），用于判定，不生成声音。", "",
          "## 6. 快速结论", "",
          "- 奏法：5 种，已实现时值/力度变化；",
          "- 装饰音：5 种，已实现展开（颤音 10Hz）；",
          "- 转折：retrigger/restrike/breath/break/key_noise 有真实瞬态；liaison 无瞬态；",
          "- 曲线：只有 dynamics 真正进音频；tempo/brightness/expression 不实现；",
          "- 和声：只分析，不演奏。"]
(OUT / "演奏语义对照.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("生成：演奏语义对照.md / performance_semantics.json")
