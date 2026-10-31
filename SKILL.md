---
name: score-model
description: 钢琴乐谱的数学模型与工具链：用 .md 文档或 .py 脚本写 MS 乐谱模型，做校验、渲染、MIDI/WAV/PDF/MD 导出、S02 结构计算与 A 叔（卧式三角琴/Steinway 类）基线对照。Use when 用户说“写一首钢琴曲”“作曲”“写谱”“乐谱模型”“MS 模型”“.md 写谱”“S02 分析”“结构判定”“可弹性”“对照 A 叔/Animenz 基线”“渲染五线谱”“导出 MIDI/WAV/PDF”。Do NOT use for 直接写 ABC 作为主格式（ABC 仅可导入）、音频母带处理、非钢琴编制优先。
---

# ScoreLang · 技能入口

> 本页在技能包根；路径相对包根。命令示例默认在 `score-model/` 目录执行。
> 先读 `score-model/START_HERE.md`（5 分钟），再按下面流程走。
> 这里只做路由，不重复规范正文。

## 1. 先读（都不需要运行脚本）

| 文档 | 用途 |
|---|---|
| `score-model/START_HERE.md` | 5 分钟认识工程 |
| `score-model/docs/reference/速查卡.md` | 一页版：乐器/奏法/装饰音/约束 |
| `score-model/docs/reference/写作前必读.md` | 阅读顺序 |
| `score-model/docs/spec/写作手册.md` | `.md` / `.py` 两种写法、保存/加载 |
| `score-model/docs/reference/乐器速查.md` | 可选乐器、音域、踏板、奏法、装饰音 |
| `score-model/docs/reference/演奏语义对照.md` | 语义名 → 实际实现（奏法/装饰音/动作/曲线） |

## 2. 写谱：只有两种入口

### A. `.md` 文档（标签式）

```markdown
# 曲名
- BPM: 87
- Meter: 4/4

## 乐器
- 1: piano

## 乐谱
```notes
[n1] 1: C5 @0+1 mf
[n2] 1: E5 @1+1
```

## 动作
- turn: n2 retrigger
- pedal: 1 sustain 0 2
```

```python
import ms, ms_md
song = ms_md.compile_song(open("piece.md").read())
song.export_png("piece.png", bars_per_page=4)
```

### B. `.py` 脚本（DSL）

```python
g = ms.start(bpm=87, instruments=[{"type": "piano"}])
n1 = g.note(1, "C5", beat=0, beats=1, level="mf")
n2 = g.note(1, "E5", beat=1, beats=1)
g.turn(n2, "retrigger")
song = g.finish()
song.save_md("piece.md")
```

## 3. 写之前/之后的自检

```python
ms_md.lint(text)            # 行号级预检
ms_md.loads_authoring(text) # 编译 + V1–V19
ms.export_check(spec)       # 导出前门禁
ms.report(song)             # 结构/演奏测量
```

## 4. 交付：四件套

以后默认交付 **PDF + MID + MD + WAV**：

```python
song.save_delivery("out", "piece")
# 生成：
#   out/piece.md    MS 乐谱模型（源码）
#   out/piece.pdf   五线谱 PDF（矢量）
#   out/piece.mid   MIDI
#   out/piece.wav   渲染音频
```

也可单独导出：

```python
song.save_md("x.md")
song.export_pdf("x.pdf")
song.export_midi()          # bytes
song.export_wav("x.wav")
```

- 交付默认四件套；PNG 仅作预览，可选；
- ABC 只用于导入（`score-model/importers/abc2ms.py`），不作为交付格式。

## 5. S02 与基线

```bash
python tools/s02_analyze.py --dir <含 .ms 的目录>
python tools/baseline_compare.py --ms piece.ms
```

- S02 可对**半成品**计算，但整体指标（structure/ending）要等写完再定；
- 基线：`score-model/inbox/s02/animenz_baseline_v3.json`（5 首 A 叔参照）。

## 6. 边界

- **不把 ABC 当写谱主路径**；ABC 只通过 `score-model/importers/abc2ms.py` 导入；
- 模型/校验/S02 分层不要混：换算只在写谱层做，计算只吃数值。

## 7. 参考

- 模型权威：`score-model/docs/spec/数学乐谱规范.md`
- 演奏/记谱：`score-model/docs/spec/演奏与记谱.md`
- S02：`score-model/docs/spec/S02手册.md`
- 边界契约：`score-model/docs/spec/边界与契约.md`
- API/工具：`score-model/docs/spec/API与工具.md`
