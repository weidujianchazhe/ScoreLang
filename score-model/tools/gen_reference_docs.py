# -*- coding: utf-8 -*-
"""生成静态参考文档（不需要运行脚本才能读）。

产物：
  docs/reference/乐器速查.md
  docs/reference/MD写作约束.md
  docs/reference/写作前必读.md
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms", "ms/_core", "perform", "render",
                                       "audio", "analyze", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms  # noqa: E402
import ms_articulation as art  # noqa: E402
import ms_ornament as orn  # noqa: E402
import ms_performance as perf  # noqa: E402

OUT = ROOT / "docs" / "reference"
OUT.mkdir(parents=True, exist_ok=True)

inst = ms.instruments()
cat = ms.instrument_catalog()
types = cat["types"]

lines = ["# 乐器速查（静态）", "",
         "> 写谱前读这一页即可，不用运行脚本。别名用于 MD/JSON/Guide 里写乐器。", "",
         "## 常用别名（13）", "",
         "| 别名 | 类型码 | 族 | 音域 | 踏板 |", "|---|---|---|---|---|"]
for alias, info in sorted(inst.items()):
    t = info.get("type")
    d = types.get(t, {})
    rng = d.get("range")
    lines.append(f"| `{alias}` | `{t}` | {d.get('family', info.get('family', ''))} | "
                 f"{rng[0]}–{rng[1] if rng else '?'} | {', '.join(d.get('pedals') or []) or '无'} |")

lines += ["", "## 全部类型（含扩展）", "",
          "| 类型码 | 族 | 机制 | 音域 | 复音 | 踏板 | 转折 | 奏法 | 装饰音 |",
          "|---|---|---|---|---|---|---|---|---|"]
for t, d in sorted(types.items()):
    rng = d.get("range") or [None, None]
    lines.append("| `{}` | {} | {} | {}–{} | {} | {} | {} | {} | {} |".format(
        t, d.get("family", ""), d.get("mechanism", ""), rng[0], rng[1],
        d.get("poly", ""), ", ".join(d.get("pedals") or []) or "-",
        ", ".join(d.get("actions") or []) or "-",
        ", ".join(d.get("articulations") or []) or "-",
        ", ".join(d.get("ornaments") or []) or "-"))
(OUT / "乐器速查.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

md = """# MD 写作约束（静态）

> 写给 AI/人看的写作规则；解析时会校验，但**写之前**先按这里避免踩坑。

## 1. 文件骨架

```markdown
# 曲名
- BPM: 87
- Meter: 4/4

## 乐器
- 1: piano
- 2: violin

## 乐谱
```notes
[n1] 1: C5 @0+1 mf
[n2] 1: E5 @1+1
```

## 动作
- turn: n2 retrigger
- pedal: 1 sustain 0 2
- curve: 1 dynamics 0 500 8 950
```

## 2. 音符行

```
[标签] 乐器号: 音高 @起始拍+时值拍 [力度]
```

- 标签：`[A-Za-z_][A-Za-z0-9_]*`，必须唯一（转折/踏板引用它）；
- 乐器号：`1..N`，必须在“## 乐器”里声明；
- 音高：`C4 / F#5 / Bb3`，范围 **21..108**（A0–C8）；
- 起始拍/时值：拍，不是微秒；时值必须 > 0；
- 力度：`ppp…fff` 或 `0..1000` 的 permille（可省略）；
- 奏法/装饰音：写在该行行尾会与力度冲突——当前格式只支持力度；
  奏法/装饰音请用 Python DSL 或 JSON。

## 3. 动作行

| 写法 | 约束 |
|---|---|
| `- turn: 标签 种类 [强度]` | 钢琴可用 retrigger/restrike/…；同音高重击需前一个同音高音、间隔 ≥60ms |
| `- pedal: 乐器号 种类 起始拍 结束拍` | 乐器必须支持该踏板；连续踏板间隔 ≥0.25 拍 |
| `- curve: 乐器号 参数 拍 值 …（成对）` | 参数：dynamics/tempo/pedal/brightness/expression；值在范围内 |

## 4. 校验链

1. `ms_md.lint(text)` —— 写之前快速检查（返回行号+原因）；
2. `ms_md.loads_authoring(text)` —— 编译时完整校验（V1–V19）；
3. `ms.export_check(spec)` / `mscli ms export-check` —— 导出前门禁；
4. `ms.report(song)` —— 结构/演奏测量。

## 5. 常见错误

- 乐器号没声明 → 编译报错；
- 音高越界（C0/C9）→ `UNSUPPORTED_PITCH_RANGE`；
- 踏板不被乐器支持（小提琴 sustain）→ V14；
- 连续踏板间隔太小 → 被合并/校验失败；
- 标签重复 → 转折引用错位。
"""
(OUT / "MD写作约束.md").write_text(md, encoding="utf-8")

index = """# 写作前必读（工程区）

按顺序读，**都不需要运行脚本**：

1. [写作入口](../spec/写作入口.md) —— 只有两种写法：`.md` 文档 / `.py` 脚本；
2. [MD 文档格式](../spec/MD文档格式.md) —— 标签式与表格式语法；
3. [乐器速查](乐器速查.md) —— 可选乐器/音域/踏板/奏法/装饰音；
4. [MD 写作约束](MD写作约束.md) —— 写之前必须遵守的规则与常见错误；
5. [作曲流程](作曲流程.md) —— 怎么写、怎么存、怎么导出；
6. 写完：`ms_md.lint(text)` → `ms_md.loads_authoring` → `ms.export_check` → `ms.report`。
"""
(OUT / "写作前必读.md").write_text(index, encoding="utf-8")
print("生成：", [p.name for p in OUT.glob("*.md")])


# ── 速查卡 / README / 源哈希 ──────────────────────────────
quick = ["# 速查卡（写谱前先读这一页）", "",
         "> 程序执行以 Python 注册表为准；这页是生成的阅读视图。", "",
         "## 乐器（常用别名）", ""]
for alias, info in sorted(inst.items()):
    d = types.get(info.get("type"), {})
    quick.append(f"- `{alias}` → `{info.get('type')}`（{d.get('family','')}）")
quick += ["", "## 奏法（PY/JSON：`articulation=`）", ""]
for name, v in sorted(art.table().items()):
    quick.append(f"- `{name}`：时值 ×{v['gate_pm']/1000:.2f}，力度 ×{v['vel_pm']/1000:.2f}")
quick += ["", "## 装饰音（PY/JSON：`ornament=`，可配 `upper/lower/grace`）", ""]
quick += ["- `grace_short`：前 25%；`appoggiatura_long`：拍上 50%；",
          "- `mordent`：主 45/上邻 10/主 45；`turn`：上 15/主 15/下 15/主 55；",
          "- `trill`：主/上邻 10Hz 交替；默认上邻 = 主音 +1 半音。"]
quick += ["", "## 转折（`g.turn(id, kind)`）", ""]
quick += [f"- `{k}`" for k in perf.TURN_TRANSIENT if k]
quick += ["", "## 曲线", "",
          "- 音频只实现 `dynamics`；`tempo/pedal/brightness/expression` 只作分析/呈现。",
          "", "## 约束", "",
          "- 音高 21–108；乐器号先声明；踏板间隔 ≥0.25 拍；",
          "- 标签 `[n1]` 唯一；力度 0–1000 或 ppp…fff。", "",
          "## 文件", "",
          "- `.md` 作者文档；`.py` DSL；`.ms` 机器格式；`.json` 任务。"]
(OUT / "速查卡.md").write_text("\n".join(quick) + "\n", encoding="utf-8")

readme = """# 参考文档（生成物）

- 权威数据在 Python 注册表：`perform/ms_instruments.py`、`ms_articulation.py`、
  `ms_ornament.py`、`ms_performance.py`；
- 本目录的 MD 是由 `tools/gen_reference_docs.py` 生成的**阅读视图**；
- 改注册表后重跑生成器；`tools/check_reference_docs.py` 检查是否漂移。

文件：
- `速查卡.md`（一页版）
- `乐器速查.md`（全量）
- `演奏语义对照.md`
- `装饰音数学写法.md`
- `MD写作约束.md`
"""
(OUT / "README.md").write_text(readme, encoding="utf-8")

srcs = [ROOT / "perform" / n for n in
        ("ms_instruments.py", "ms_articulation.py", "ms_ornament.py", "ms_performance.py")]
meta = {"sources": {str(s.relative_to(ROOT)).replace("\\", "/"):
                    hashlib.sha256(s.read_bytes()).hexdigest()
                    for s in srcs if s.exists()},
        "files": sorted(p.name for p in OUT.glob("*.md"))}
(OUT / "_meta.json").write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=1),
                                encoding="utf-8")
print("速查卡/README/_meta 已生成")
