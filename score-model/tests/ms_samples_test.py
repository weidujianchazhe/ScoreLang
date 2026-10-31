# -*- coding: utf-8 -*-
"""示例谱与端到端产物测试（排表 I-4 / I-5）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re
from pathlib import Path

import ms_audio as au
import ms_events as ev
import ms_io as mj
import ms_md
import ms_render as rd

HERE = ROOT
SAMPLES = HERE / "samples"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def load(stem):
    """样例谱是 `.md` 文档写法（写作格式）；这里验证它能被载入、校验、渲染。"""
    text = (SAMPLES / f"{stem}.md").read_text(encoding="utf-8")
    return ms_md.loads(text), text


files = sorted(SAMPLES.glob("*.md"))
check("S1 三份示例谱存在", len(files) == 3, str([f.name for f in files]))

doc, text = load("simple_melody")
check("S2 旋律 5 事件", len(doc.events) == 5, str(len(doc.events)))
check("S3 旋律校验通过", ev.validate(doc) == [], str(ev.validate(doc)))

doc2, text2 = load("chords_and_pedal")
check("S4 和弦 6 事件 / 2 踏板段",
      len(doc2.events) == 6 and len(doc2.pedals) == 2,
      f"{len(doc2.events)}/{len(doc2.pedals)}")
check("S5 踏板种类含 sustain 与 sostenuto",
      {p.kind for p in doc2.pedals} == {"sustain", "sostenuto"}, str({p.kind for p in doc2.pedals}))

doc3, text3 = load("ornaments")
check("S6 装饰音展开后 15 事件", len(doc3.events) == 15, str(len(doc3.events)))
check("S7 装饰音确实展开（15 事件来自 3 个写入音），且颤音交替出现上邻音",
      len(doc3.events) == 15 and any(e.pitch.semitone == 79 for e in doc3.events)
      and any(e.pitch.semitone == 81 for e in doc3.events),
      f"半音集合={sorted({e.pitch.semitone for e in doc3.events})}")

for name, (d, t) in {"simple_melody": (doc, text), "chords_and_pedal": (doc2, text2),
                     "ornaments": (doc3, text3)}.items():
    _a = ms_md.dumps(ms_md.loads(t))
    _b = ms_md.dumps(ms_md.loads(_a))
    check(f"S8-{name} 往返语义一致", _a == _b)
    check(f"S9-{name} 校验通过", ev.validate(d) == [], str(ev.validate(d)))

# 渲染产物：图元数应等于事件数
svg = rd.render_pianoroll(doc3)
check("S10 渲染图元数=事件数",
      len(re.findall(r'class="note"', svg)) == len(doc3.events),
      f"{len(re.findall(r'class=.note.', svg))} vs {len(doc3.events)}")

# 参数表：每个事件一条，且力度均可计算
params = au.event_parameters(doc3)
check("S11 参数条数=事件数", len(params) == len(doc3.events))
check("S12 样本力度均已提供（无 NOT_PROVIDED）",
      all(p["dynamics_state"] == "VALUE" for p in params),
      str([p["dynamics_state"] for p in params]))

# 样本文件齐备（生成脚本已退役，样本本身是资产）
check("S13 三份样本齐备",
      all((SAMPLES / f"{n}.md").exists() for n in ("simple_melody", "chords_and_pedal", "ornaments")))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
