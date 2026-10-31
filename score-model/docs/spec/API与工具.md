# API与工具


---

## 来源：MS_API


> 打包第一步：**门面包**。`ms/` 已可 `import ms`，内部仍指向 `core/`、`notation/` 等原模块；
> 后续再把文件搬进包内（旧 import 走 shim，不破坏调用）。S02 暂未打包（按本次决定跳过）。

## 1. 快速开始

```python
import ms

# ① 写（内存里，不落文件）
w = ms.Writer(bpm=120)
p = w.instrument("acoustic_grand_piano")      # -> 1
v = w.instrument("violin")                    # -> 2（同类型可多把：再调一次就是 3、4…）
a = w.note(p, pitch="C4", beat=0, beats=1, level="mf")
w.note(v, pitch="A4", beat=0, beats=2, articulation="marcato")
w.turn(a[0], "key_noise")                     # 这乐器做不做得了，doc()/validate() 硬校验
w.pedal(p, "sustain", 0, 4)                   # 不在踏板表里 → 立刻报错并列出可用值
doc = w.doc()                                 # 此时才成 MSDocument（并已校验）

# ② 默认不写 .ms 文件（.ms 是基础结构文件，引擎严格校验，手改易崩）
text = ms.dump(w.doc())      # 需要文本时才拿字符串；不落盘
# 只有引擎侧/显式确认的流程才写：w.save("song.ms") 或 CLI --allow-write

# ③ 直接分析（同一份内存文档，不必先写文件）
from transform.ms_to_s02 import to_s02
skeleton, report = ms.to_s02(doc, time_base_us=500_000)

# ④ 或命令行
#   mscli ms new song.ms --instruments "piano,violin" --bars 4
#   mscli ms check song.ms
#   mscli ms catalog --markdown
#   mscli ms menu
```

## 1b. 默认行为：不生成 .ms 文本文件

`.ms` 是引擎最基础的结构文件，随机生成/手改会直接破坏功能。因此：

| 场景 | 行为 |
|---|---|
| `Writer.doc()` / `ms.to_document()` | 只在内存里建文档，**不写文件** |
| `ms.dump(doc)` | 返回 `.ms` 文本字符串，**不写文件**（给"要看内容"的场景） |
| `mscli ms new` | **默认只打印脚手架文本**；要落盘必须 `--out <路径> --allow-write` |
| 导入（`mscli import`） | 唯一按需生成 `.ms` 的常规命令（MIDI/MusicXML → .ms） |
| 引擎内部（`ms_io.save`） | 原子写；不做权限判断（原包保持干净） |

发布/外部使用建议：**不给"写 .ms"的入口**，消费者直接拿 `MSDocument` 对象做
分析/渲染/出声；需要备份文本时用 `dump()`。`load()` 会对 V1–V19 做严格校验，
手改通常直接被拒；但"合法而病态"的写法（如超长踏板链）由 V4c 等语义规则兜底。

## 2. 对外 API（`ms.api.__all__`）

| 分类 | 名字 |
|---|---|
| 文档 | `MSDocument` `Event` `Instrument` `PedalSegment` `TurnPoint` `CurvePoint` `new_document` `load` `save` `dump` `parse` |
| 写作 | `Writer` `pitch_to_semitone` `write_note` `write_chord` `write_pedal` `write_turn` `write_vocal` `vocal_units` `make_instrument` `to_document` |
| 校验 | `validate` `pedal_diagnostics` |
| 渲染/音频 | `render_svg` `render_text` `audio_samples` `to_wav` |
| 导入 | `import_midi` `import_musicxml` |
| 能力菜单 | `catalog` `markdown` `menu` `actions` `articulations` `ornaments` |
| 与 S02 的桥 | `to_s02`（单向：S02 读 MS，MS 不读 S02） |

## 3. 能力菜单（让 AI 自动知道能写什么）

- `ms.menu()`：一句话菜单（能写什么 / 怎么查 / 怎么写）；
- `ms.catalog()`：完整结构（JSON 友好）；`ms.catalog(type_code="violin")` 单件乐器；
- `ms.registry.actions("violin")`：这件乐器能做的演奏转折（按机制过滤）；
- `ms.registry.pedals / articulations / ornaments`：踏板 / 奏法 / 装饰音；
- 命令行：`mscli ms catalog --markdown` 出全表。

## 4. 扩展 / 补录接口（以后加东西不改解析器）

```python
from ms import registry

# 补乐器
registry.register_instrument("koto", family="strings", mechanism="plucked_string",
                             pitch_range=(36, 96), pedals=())
# 补演奏动作（按机制）
registry.register_turn_kind("bowed_string", "ricochet")
# 补奏法 / 装饰音 / 踏板
registry.register_articulation("bowed_string", "spiccato")
registry.register_ornament("bowed_string", "mordent_upper")
registry.register_pedal("acoustic_grand_piano", "half_pedal")
# 补人声语言
registry.register_language("ko", "韩语")
# 撤销补录
registry.unregister_instrument("koto")
```

注册后 `resolve()` 立即可用（缓存自动清空），`check_registry()` 会做一致性自检。

## 5. 人声通道：现状与预留

- ✅ 写谱侧：`ms.write_vocal` 能写声母/韵母段（V18 校验段结构），`lang` 已在文件里；
- ⚠️ 演唱通道：`audio/ms_sing.py` 有实验，**未接入 `make_audio`/`flow run`**；
- 🔜 语言：`ms.registry.register_language()` 可先登记（zh/en/fr/ja/ru 已登记），
  真正支持某语言还缺音素表和演唱模型；
- 入口：`from ms import vocal; vocal.available() → False`，`vocal.require_ready()` 会明确报错、
  不静默降级。

## 6. 内存文档 vs 落盘文件（回答"必须写文件吗"）

**不必。** `MSDocument` 是工作对象，`.ms` 只是它的序列化：

```
Writer / write_* → MSDocument（内存）
        ├── ms.validate() / ms.pedal_diagnostics()   # 直接校验
        ├── ms.to_s02(doc, time_base_us=…)           # 直接给 S02 分析（返回 (ScoreV02, report)）
        ├── ms.audio_samples(doc) / ms.to_wav(...)   # 直接出声
        └── ms.save(doc, "song.ms")                  # 需要时才落盘
```

限制：`flow run` 协议（manifest/sha256/产物目录）是**文件驱动**的，想要合规留档仍需落盘一次；
纯分析/试听/预览可以全程内存。

## 7. V4c：踏板链拦截（防"糊成一片"）

背景：踏板抬脚后 50ms 内再踩会被判为同一脚（`PEDAL_REPRESS_TOL_US`）。
作者若"每小节踩一次、抬脚只留 30ms"，整曲会被串成一条大踏板——实测可把 2 分钟曲子的
单音拉到整曲长度，物理上糊成一片。

判错条件（不会误伤真实作品）：**链长 ≥60s 且覆盖 ≥80% 曲长**——即"整曲被串成一条大踏板"。

现在 `validate` 会拦（并在 `Writer.doc()`/`to_document()` 时直接抛错，写谱侧就能发现）：

```
V4c 踏板链过长：P1 sustain 连续 120 段、链长 240.0s（0.0s → 240.0s）——
抬脚后 50ms 内再踩会被判为同一脚，整曲被串成一条大踏板，每个音互相延长会糊成一片。
改法：每段抬脚留 ≥100ms，或把这条长踏板拆成独立段（本曲实际发声总长 240.0s）。
```

`mscli info` / `mscli ms check` 会额外输出「踏板链」「发声总长（含踏板延长）」。

## 8. 后续打包路线（未做部分）

1. 把 `core/`、`notation/`、`audio/`、`render/`、`importers/` 逐模块搬进 `ms/` 子包；
2. 旧路径保留 shim（`core/ms_model.py` → `from ms.model import *`）；
3. 再按同样方式给 S02 建包（`s02/`，依赖 `ms`，单向）；
4. CLI 只留参数解析。

## 9. 内部版 vs 外部版（发布）

`.ms` 是最基础的结构文件，**内部保留导出，发布版删掉**。

| 能力 | 内部仓库 | 外部版（`AIwriteScoreLang/`） |
|---|---|---|
| `.ms` 写文件（`ms_io.save` / `ms.save` / `Writer.save`） | ✅ | ❌ 直接报错 |
| `.ms` 文本（`dump`） | ✅ | ❌ 直接报错（"不让瞎看"） |
| **ABC 谱导出** | ✅ `ms.export_abc` / `mscli ms export --abc` | ✅ 保留 |
| **五线谱 SVG 导出** | ✅ `ms.export_staff` / `mscli ms export --staff` | ✅ 保留 |
| 能力菜单 / 写谱对象 API | ✅ | ✅ |
| S02 分析层 | ✅ | ❌ 不打包 |
| 导入生成 `.ms` | ✅ `mscli import` | ❌ 拒绝 |

构建发布版：

```powershell
# 发布构建已迁到管理区（工程区不再背打包职责）
```

构建脚本会：复制 `core/notation/audio/render/importers/ms` 与 `tools/mscli.py`，
用 AST 精确移除 `save`/`dump`/`to_s02`/`cmd_import` 等函数，然后**自检**
（ABC/五线谱能导出、`ms.save` 不存在、`ms_io.save` 抛 PermissionError）。
源仓库不受影响。

外部用户的日常：

```python
import ms
w = ms.Writer(); p = w.instrument("acoustic_grand_piano")
w.note(p, pitch="C4", beat=0, beats=1)
doc = w.doc()
print(ms.export_abc(doc))     # ABC 谱
svg = ms.export_staff(doc)    # 五线谱
```

## 10. 任务脚本接口（外部推荐，不用知道 .ms）

外部 AI 只需要写一个任务 JSON（或调 `ms.build(spec)`），完全不接触 `.ms`：

```json
{
  "bpm": 96, "meter": [4, 4],
  "instruments": [{"type": "acoustic_grand_piano"}, {"type": "violin"}],
  "notes": [
    {"inst": 1, "pitch": "C4", "beat": 0, "beats": 1, "level": "mf"},
    {"inst": 1, "pitches": ["C4", "E4", "G4"], "beat": 1, "beats": 2},
    {"inst": 2, "pitch": "A4", "beat": 0, "beats": 4, "articulation": "marcato"}
  ],
  "pedals": [{"inst": 1, "kind": "sustain", "start": 0, "end": 3}],
  "turns":  [{"note": 0, "kind": "key_noise"}],
  "curves": [{"inst": 2, "param": "dynamics", "points": [[0, 400], [3, 900]]}]
}
```

```python
song = ms.build(spec, title="演示")
song.export_abc()          # ABC 谱文本
song.export_staff()        # 五线谱 SVG
song.export_wav("out.wav") # 音频
song.summary()             # 只读摘要 {notes, pedals, instruments, bpm, meter}
```

`Song` 是**不透明对象**：没有 `doc` 属性、没有序列化方法；外部拿得到结果，拿不到结构。

### 减少 token 的用法卡

```python
print(ms.cheatsheet())     # 一屏：spec 字段 + 三个导出方法
```

外部版（`AIwriteScoreLang/`）额外隐藏：`MSDocument/Event/...` 结构类、`write_note/write_pedal/...`
低层写函数、`load/parse/new_document`、`save/dump`、S02 桥。只保留
`build/Song/export_abc/export_staff/export_wav/cheatsheet` 与能力菜单。
### 目录可查、但不用自己写

外部 **可以知道**有哪些乐器/演奏动作（避免"以为只有几种"），但**不需要自己写**：

```python
ms.instruments()                 # 13 个别名（piano/violin/cello/…）
ms.instrument_actions("violin") # 该乐器能做的转折（可查）
ms.instrument_catalog()          # 完整目录（按需查，不必背）
```

踏板默认**由脚本派生**：每小节踩 sustain、抬脚留 100ms（≥50ms 容差，不会串成一条）。
要自己控制时，在 spec 里写 `"pedal": "none"` 或给 `"pedals": [...]`。

### 外部数据字典（该知道的都在这，不用学格式）

```python
ms.schema()        # 完整字典（dict）：字段/单位/力度等级/奏法影响/曲线参数/限制
ms.schema_text()   # 一屏文本（省 token）
```

```bash
mscli ms schema          # 一屏
mscli ms schema --json   # 给程序
```

包含：
- 时间单位（拍）、速度（bpm）、拍号；
- 乐器别名（13）与"同类型写两次即多件"；
- 力度等级 permille（ppp=250 … fff=1984，锚点 1000）；
- 奏法对时值/力度的影响（gate_pm / vel_pm）；
- 曲线参数与取值范围；
- 踏板种类与自动派生规则；
- 限制：音高 21..108、踏板链判错条件。

外部 AI 只需要读一次这个字典 + 写任务 JSON，**不需要知道 `.ms` 的任何语法**。

## 11. 内存文档直接给 S02 计算（不落任何文件）

`MSDocument` 是工作对象，S02 只在内存里读它，**不需要写 `.ms`/`.s02` 文件**：

```python
import ms
from transform.ms_to_s02 import to_s02
from transform import s02_api, s02_quality, s02_capability

w = ms.Writer(bpm=96)
p = w.instrument("acoustic_grand_piano")
w.note(p, pitch="C4", beat=0, beats=1, level="mf")
doc = w.doc()                                   # 内存文档

score, report = to_s02(doc, time_base_us=625000)  # MS → S02 骨架对象
payload = s02_api.build_payload(score)            # 分析数据（段落/窗口/动机…）
q = s02_quality.analyze(payload)                  # 12 项结构测量
cap = s02_capability.analyze(doc)                 # 演奏能力覆盖
```

实测（8 音小例）：`to_s02` 得到 `ScoreV02`，`build_payload` + `s02_quality` 直接算出
`counterpoint / playability / dynamics` 等测量值；`s02_capability` 也能直接吃 `MSDocument`。

**限制**：
- S02 只读 MS（单向）；改 S02 不影响声音。

---

## 来源：工具地图


> 一张图说清「谁写、谁读、谁受限、谁还没做」。
> **中心是 MS 模型（纯数据，无文件形态）**；写作只有两种文件尾：`.md` 文档 / `.py` 脚本。
> 工具都围绕模型进出，不反过来定义它。

## 1. 中心与四周

```
                        ┌────────────────────────┐
   写侧                 │                        │   读侧
                        │      MS 模型            │
 ① 写 ─────────────────► │ （事件流 + 语义 + 不变量）│ ────────► ② 导出 MIDI
 .md 文档 / .py 脚本     │                        │              │
 导入器（MIDI/XML/ABC）  └────────────────────────┘              ▼
      │                                                    ③ 渲染层（工程外）
      │ 受限于                                                   → WAV
      ▼                                                    ④ 投影 S02
 可演奏性收束（R-1..R-4）                                          │
                                                    ┌──────────────┘
                                                    ▼
                                                S02 对象（.s02 文件）
```

## 2. 五类角色

| # | 角色 | 模块/工具 | 方向 |
|---|---|---|---|
| **数据** | MS 模型（`MSDocument`） | `ms/_core/ms_model.py` | 中心，不落盘 |
| **写法** | `.md` 文档 / `.py` 脚本 | `ms/_core/ms_md.py` · `ms/author.py` · `ms/guide.py` | → 模型 |
| **① 写** | 生成 MS 数据 | `importers/`（MIDI/XML/ABC）· `Writer` · `ms.start` | → 模型 |
| **② 导出** | MIDI | `audio/ms_midi.py` · `tools/mscli.py export` | 模型 → `.mid` |
| **③ 渲染** | MIDI → 音频 | `ScoreLang/tools/midi_to_wav.py` + FluidSynth/sfizz | `.mid` → `.wav` |
| **④ 投影** | 模型 → S02 | `analyze/ms_to_s02.py` · `mscli s02 build` | 模型 → `.s02` |
| **⑤ 出图** | 模型 → SVG | `tools/render_svg.py` · `render/` | 模型 → `.svg` |

## 3. 依赖关系

```
ms_md ──────── .md 读写（写作格式；标签式/表格式自动识别）
  │
  ├─► ms_validate ──► 结构校验（V1–V19，硬性）
  │        │
  │        └─► check_realization ──► 可演奏性收束（R-1..R-4，软性告警）
  │
  ├─► perform/ms_instruments ──► 乐器能力表（音域/复音/踏板/GM program/族）
  │        └─► 写的时候决定「这件乐器能不能这么写」
  │
  ├─► perform/ 规则表
  │        ├─ ms_dynamics_levels  力度等级 → permille（锚点 mp=1000）
  │        ├─ ms_articulation     奏法 → 时长/力度修正
  │        └─ ms_ornament         装饰音展开
  │
  ├─► audio/ms_midi ──► .mid ──► midi_to_wav.py ──► .wav
  │
  └─► analyze/ms_to_s02 ──► S02（c3_judgment 判损失）

ms_io ──────── 旧档案行式读写（**只读兼容**，不在写作路径上）
```

## 4. 两条约束的分工

| 约束 | 模块 | 性质 | 触发点 |
|---|---|---|---|
| **结构校验** | `ms_validate`（V1–V19） | **硬**：不合法就拒绝写出/读入 | 载入、`Writer.doc()`、导出前 |
| **演奏收束** | `check_realization`（R-1..R-4） | **软**：结构合法但「弹不出来」，出报告 | 导出 MIDI / 出图 / 显式调用 |

> 数学结构**不限制并发**；「同键同刻、一人一琴」这类是收束层判的。

## 5. 写工具依赖什么

| 依赖 | 作用 | 状态 |
|---|---|---|
| `perform/ms_instruments` | 类型/子类型 → 音域、复音、踏板、GM program、族 | ✅（128 GM + 16 族） |
| `perform/` 三张规则表 | 力度等级、奏法、装饰音 | ✅ |
| `check_realization` | 写的时候就告诉你「这弹不出来」 | ✅ |
| 技能包（提示词） | 外部 AI 的写曲入口 | ✅（`docs/spec/给外部AI的提示词.md`） |

## 6. 缺口

| 工具 | 状态 | 缺什么 |
|---|---|---|
| 写（`.md` 文档） | ✅ | 标签式不支持人声段/倚音/溯源字段（需表格式或 `.py`） |
| 写（`.py` 脚本） | ✅ | `Writer.save()` 落表格式，标题需自己给 |
| 写（导入） | ✅ | ABC 只吃工程自产方言 |
| 导出 MIDI | ✅ | — |
| 渲染音频 | ✅（工程外） | 音色库未齐（Salamander 缺） |
| 投影 S02 | ✅ | — |
| 出图 | ✅ | 完整五线谱仍只有库函数 |

## 7. 一句话

> **MS 模型是唯一数据源；`.md` 是它唯一的文档写法；写工具往里写、受乐器表与收束脚本约束；
> 读工具分四路：出图、出 MIDI、出 S02、出音频（音频经 MIDI 再经渲染层）。**

---

## 8. 主线与支线

> 管理者口径（2026-10-21）：**小核心、大支线**。

### 核心主线（两条）

```
① 写乐谱（.md 文档 / .py 脚本 → MS 模型）
② 计算 S02 投影（MS → S02）
```

### 支线

| 支线 | 内容 | 位置 |
|---|---|---|
| **A · 演奏性** | 可演奏性收束；同层还有**乐器**、**人声**约束 | 挂在「写」上 |
| **B · MIDI / 音频** | MS → `.mid`；`.mid` → WAV/FLAC | 从 MS 分出 |
| **C · 谱面 / 前端** | MS → S02 → 前端 UI（矢量图 + 交互查看） | 挂在 S02 之后 |

### 依赖图

```
                    ┌─ A 演奏性（可演奏性 / 乐器 / 人声）
                    ▼
① 写 .md/.py ──────► MS ──┬─► ② S02 投影 ──► C 前端
                           │
                           └─► B 导出 MIDI ──► 音频
```

### 写谱侧的三个并列支线

| 支线 | 做什么 | 对应机制 |
|---|---|---|
| **① 结构** | 只保证数学结构自洽 | `validate`（V1–V19）；`constraint_mode="unlimited"` |
| **② 可演奏性** | 在结构合法之上判「人弹不弹得了」 | `check_realization`（R-1..R-4） |
| **③ 来源** | 由谁写：手写 / 提示词 / 训练权重 | `skills/` · 未来权重 |

**两条轴不要混**：轴一（写什么、允不允许）＝结构 ←→ 可演奏性；轴二（谁来写）＝来源。两者正交。

### 权重支线会读 S02

```
.md ──► .s02 ──► 权重/提示词读取 ──► 生成新的 .md
            ▲
            └── 前端也读它
```

| # | 约束 | 原因 |
|---|---|---|
| 1 | S02 要能被机器读 | 消费者从「前端」扩到「生成层」 |
| 2 | S02 仍是派生视图，不是权威源 | 最终写回的是 `.md`，不得反向改 S02 再倒灌 |
| 3 | 这是离线迭代，不是实时回路 | 要有人的评审环节，避免自我循环漂移 |

### 分工原则：细节在模型，优化在渲染层

| | `.md` → 原生渲染 | `.md` → `.mid` → 渲染层 |
|---|---|---|
| 细节在哪 | **全部留在模型里** | 交给渲染层「优化」 |
| 渲染器职责 | **只读、只执行** | 大量启发式（音色/力度/踏板解释） |
| 可控性 | 高（写什么听到什么） | 低 |
| 有损 | 无（除采样器能力） | **天生有损**（7 位/通道级） |

### S02 的目标（写死方向）

> **可读、能表述意思**：让乐谱像一门「可看的语言」，而不只是音符的时间表。

---

## 来源：播放与导出


> 一句话：**引擎不出声，只导出标准 MIDI。** 用任意 MIDI 播放器试听。

---

## 1. 生成 MIDI

```bash
cd score-model
python mscli.py export samples/ornaments.ms -o out/ornaments.mid --time-base 500000
```

`--time-base` = **每四分音符多少微秒**（必填）。它是"微秒 → tick"的换算基准，也会被写成文件里的 tempo meta，所以播放速度和 `--time-base` 严格一致：

| `--time-base` | 速度 |
|---|---|
| 1 000 000 | ♩=60 |
| 500 000 | ♩=120 |
| 333 333 | ♩=180（近似） |

> 不给 `--time-base` 会被直接拒绝——引擎不猜速度。

### 1.1 多乐器导出（**两种通道策略 + 文件级溢出**）

多乐器导出只有两个选项：

| 选项 | 规则 | 适用 |
|---|---|---|
| **单乐器单通道**（`per_instance`） | 每个乐器实例独占一个通道 | 乐队、人少的合唱（一人一通道） |
| **同类乐器单通道**（`per_section`） | **按声部组 `section` 合并**共用一个通道/音色，记 `loss: channel_merged` | 乐团弦乐组、**40 人合唱团按 S/A/T/B 四组** |

> **合并依据是声部组（`section`），不是乐器类型**。合唱团四个声部都是 `voice` 类型，
> 若按类型合并会把四部挤成一个通道；按 `section`（`choir_s`/`choir_a`/`choir_t`/`choir_b`）合并才是各部一个通道。
> 无 `section` 时回落到"类型 + 子类型"合并。

**通道满了就开下一个文件**——不用 port：

```
MIDI 文件 1：通道 1..16
MIDI 文件 2：通道 1..16     ← 第 17 个通道自动落这里
MIDI 文件 3：…
```

- 单个文件时命名 `<曲名>.mid`；多个时 `<曲名>_1.mid`、`<曲名>_2.mid`…
- **所有文件共用同一个 `time_base_us` / tempo**，导入 DAW 后按同一时间轴对齐
- 分配顺序：乐器实例（或合并后的组）按声明顺序填通道；通道 10 留给鼓组（GM 规定）
- 每个通道在 t=0 发 **Program Change**（音色号来自乐器登记表）
- 导出报告列出：哪个文件装哪些乐器、哪些被合并（`channel_merged`）

**为什么用多文件而不是 port**：port meta（`FF 21 01`）很多播放器不认；多文件到处都能用。

**现状缺口（未实现）**：

1. 导出器**从不发 Program Change**（只有读取时跳过 `0xC0`）→ 现在导出的 MIDI 全是默认音色
2. 通道分配是 `(piano_id-1) % 16` → **第 17 个乐器会撞回通道 1**，且不避开通道 10

## 2. 打开 MIDI

任何标准 MIDI 播放器都行（DAW、系统播放器、网页播放器）。导出的是 **SMF format 1**，含：

- 音符 on/off
- 力度（velocity = `permille × 64 / 1000`，`1000‰ ↔ 64`）
- 踏板：CC64 sustain / CC66 sostenuto / CC67 una_corda（另 CC11 swell / CC4 hihat）
- tempo meta（= `time_base_us`）

### 2.1 三档音频路径（按用途选，不是按音质排序）

| 用途 | 路径 | 说明 |
|---|---|---|
| **听感 / 交付试听** | `midi_to_wav.py`（GM：FluidSynth + MuseScore_General） | **多音色可辨**；这是默认推荐 |
| 钢琴独奏最好听 | `midi_to_wav.py`（sfizz + Salamander） | 仅适合**纯钢琴**；SFZ 不读 Program Change |
| 参数对照 / 数值校验 | `make_audio`（MS 原生加法合成） | 保真（力度/踏板/转折全进），**但音色不像真乐器** |

> **结论（2026-10-22 实测）**：`make_audio` 不适合当交付音频；它的价值是"把 MS 参数直接变成可测的波形"。


## 3. 播放前必须知道的三件事

**① 力度标定是占位，不是斯坦威实测**

`ms_audio.default_calibration` 目前是线性的（`permille/1000`）。所以**听感不是真实钢琴**——它只保证"数值关系正确"，不保证"听起来像钢琴"。

MIDI 导出用的是 velocity 映射，具体音色取决于你用的播放器/音源。

**② 曲末仍未释放的音，在轨末强制收尾**

MS 允许 `release_us = None`（sustaining，比如一直按着的音）。MIDI 必须有 note-off，所以导出器把它写在**最后一刻**。导出时会提示：

```
注意：N 个延音音在轨末强制收尾：[...]
```

**③ 力度缺失的音按锚点 64 导出**

`NOT_PROVIDED` 的音会用 64（即 `1000‰`）。导出时同样提示：

```
注意：M 个音的力度未提供，按锚点 64 导出：[...]
```

这两条不是"悄悄补上"，而是**明确告知**。

## 4. 不做什么

| 不做 | 原因 |
|---|---|
| 音频合成/采样 | 项目边界外（`MAP.md` 明确不含音源与合成） |
| 混响/声像/母带 | 同上，属渲染层后端 |
| 真实音色标定 | 需要斯坦威实测数据，尚未采集 |

代码里有一个 `NullBackend`，被调用时会明确拒绝并指回 MIDI 导出——就是为了防止有人误以为本项目能出声。

## 5. 快速自检

```bash
# 校验
python mscli.py validate samples/simple_melody.ms

# 摘要（事件数/时长/力度缺失）
python mscli.py info samples/simple_melody.ms

# 出 MIDI 并试听
python mscli.py export samples/simple_melody.ms -o out/demo.mid --time-base 500000
```

---

## 来源：算法地图


> 一页看清：**每个模块用什么算法、怎么串起来、哪里慢、怎么改**。
> 实测基准：`second.ms`（1295 事件 / 200.8 秒）。

## 1. 模块与算法

| 模块 | 核心算法 | 复杂度 |
|---|---|---|
| `ms_io` | 行解析状态机；id 规范化（排序后顺序分配）；字典索引查表 | O(n log n) |
| `ms_validate` | 线性扫描 + 集合去重；每乐器 `resolve()`（带缓存） | O(n) |
| `ms_realization` | 按 onset 排序 + 每键状态机（R-1/R-2） | O(n log n) |
| `ms_playability` | 同刻分组（dict）+ 事件扫描线（复音峰值） | O(n log n) |
| `ms_instruments` | 字典查找 + 解析缓存（`_RESOLVE_CACHE`） | O(1) |
| `ms_midi` | 通道贪心分配（每组取首个空槽）；消息按 (tick, 类型) 排序 | O(m log m) |
| `ms_to_s02` | **贪心区间着色**（voice 分配）+ 损失记录 | O(n·v) |
| `c3_judgment` | 规则判定（J1/J2）：集合运算 + 证据比对 | O(n) |
| `make_audio` | **加法合成**（每音 ≤18 泛音 × 时长）；FFT EQ；4× 插值估真峰值 | **O(音符 × 泛音 × 采样)** |
| `ms_voice` | 共振峰合成（谐波按高斯加权） | O(谐波 × 采样) |
| `ms_render` / `staff2` / `jianpu` | 布局映射（时间→x、音高→y）；连杠/分页启发式 | O(n) |
| `ms_score` | 完整五线谱布局 + 贪心分配（和弦/声部位置） | O(n) 量级 |
| `ms_edit` | 批量变换（移调/量化/力度） | 每次 O(n) |
| `abc_parse` | 词法 + 递归下降（ABC 方言） | O(字符) |
| `ms_import` | XML 树遍历 + divisions→µs；和弦分组 | O(节点) |
| `ms_import_midi` | 事件流解析 + (通道,键) 配对 | O(事件) |
| `ms_playability` | 见上 | — |

## 2. 六条流水线（算法怎么组合）

| 流水线 | 组合 | 端到端算法 |
|---|---|---|
| **① 生成** | composer/ABC/import → `MSDocument` → `ms_io.dump` | 解析/构造 + 排序 + 序列化 |
| **② 校验** | parse → `validate`(V) → `check_playability`(C) → `check_realization`(R) | 三遍线性/排序扫描 |
| **③ 投影** | `transform_events` → `ms_to_s02`（区间着色）→ `c3_judgment`（损失判定） | 排序 + 贪心着色 + 规则比对 |
| **④ 出 MIDI** | 通道分配（贪心）→ 消息排序 → SMF 编码 | 贪心 + 排序 + 变长整数编码 |
| **⑤ 出声** | `.mid` → sfizz/FluidSynth（采样） **或** `.ms` → 加法合成 | 外部采样器 / 内部加法合成 |
| **⑥ 出图** | 布局（时间→x/音高→y）→ SVG 字符串 | 线性布局 + 连杠/分页 |

**依赖方向**：`core ← notation/render/audio/transform/importers ← tools`，无反向依赖（已机检）。

## 3. 实测性能（1295 事件 / 200.8 秒）

| 步骤 | 耗时 | 相对 |
|---|---|---|
| 载入 `.ms` | 0.02 s | 基准 |
| `validate`（V1–V13） | **0.002 s** | 极快 |
| `check_playability`（C1–C6） | **0.002 s** | 极快 |
| 导出 MIDI | **0.014 s** | 极快 |
| 投影 S02 | **0.011 s** | 极快 |
| **加法合成 → WAV** | **约 28 s**（尾音 1.25 s + 泛音 18，音质优先） | **仍是最慢环节** |

**结论：唯一的性能瓶颈是音频合成**，其余全部毫秒级。\n\n> 2026-10-22 实测：曾把尾音收到 0.9 s 得 24.56 s（1.26×），但**长鸣音尾部受损，已退回 1.25 s**；保留淡出 80 ms 与循环外提。\n> 另试两法均失败：向量化 (H,T) 矩阵 **47.4 s（更慢，内存带宽）**；正弦 LUT 查表 **0.099 s vs np.sin 0.008 s（mod 太慢）**。

## 4. 优化方向（按收益排序）

### 4.1 加法合成（30.85 s → 目标 2 s 内）

现在每个音：18 个泛音 × 时长 × 44100 采样，直接求和。

| 方案 | 预期 | 代价 |
|---|---|---|
| **A. 波表 + 重采样** | 10–20× | 预计算每个音高的波表，按音高重采样；泛音结构固化 |
| **B. 分块 FFT 加法** | 5–10× | 用逆 FFT 一次生成整段频谱包络 |
| **C. numpy 向量化**（按泛音批量算） | 2–4× | 改动小，先做 |
| **D. 直接走采样**（sfizz/Salamander） | 音质最好 | 已实现，但受 MIDI 有损限制 |

**建议顺序**：C（改动最小）→ A（收益最大）→ D（已在用，作为高质量出口）。

### 4.2 真峰值估计

现在 4× 线性插值（O(4N)），是近似。改用 FFT 过采样或 polyphase FIR，代价相近、精度更高。

### 4.3 EQ

整段 FFT 需要一次载入全曲（200 s ≈ 8.8M 样本 × 2 声道）。长曲会吃内存；改 **分段重叠相加（overlap-add）** 或 IIR 双二阶。

### 4.4 S02 投影的损失量

实测 **582 条损失**（1295 音）。主因是贪心区间着色对和弦的处理（同 onset 被拆多声部，见 `S02_DESIGN_INPUT` Q6）。修掉和弦判定后：
- voice 数会从"和弦音数"降到"真实声部数"
- 损失量预计大幅下降
- 算法可从 O(n·v) 降到 O(n log v)（用最小堆维护空闲声部）

### 4.5 MIDI 通道分配

贪心取首个空槽，O(组数 × 16)。可改为"最小化合并损失"的装箱，但组数很小，**不值得**。

### 4.6 渲染

布局是线性的；复杂度不是问题。真正的优化空间在**排版质量**（连杠规则、跨行分页），属正确性而非性能。

## 5. 数据结构优化（非算法）

| 现状 | 建议 |
|---|---|
| `resolve()` 每次构造 dict | ✅ 已加缓存 |
| `check_playability` 按乐器分组建 dict | 已足够 |
| `ms_io.parse` 每行 split | 已足够；大文件用 `iter_events` |
| `MSDocument.events` 是 list | 频繁按 id 查找的地方可加 id→事件索引（目前只有编辑用，量小） |

## 6. 组合结构上的观察

1. **校验三遍**（V/C/R）各扫一次，可合并为单遍：结构、收束、演奏同时判。当前 0.006 s，**不值得合并**。
2. **S02 与 MIDI 都从 MS 派生**，互不依赖——符合"单源双派生"设计。
3. **音频有两条独立实现**（`make_audio` 合成 / `ms_midi`+采样器），保真与音质二选一；原生采样渲染器（任务卡）是终态。

---

## 来源：给外部AI的提示词


> **口径先说清**：**MS 是数学模型**（事件模型 + 语义 + 六条不变量），它没有文件形态。
> 落到磁盘上只有两种文件尾标识：**`.md`（文档写法）** 和 **`.py`（脚本写法）**。
> 说「MS 格式」指的是模型，不是说某个后缀。
>
> 两个版本：**短版**（日常用，让它自己读文档）· **长版**（不能可靠读文件的场合，命令与写法全写进去）。

---

## ==== 短版提示词（复制这段）====

你要用一套叫 **ScoreLang** 的工具写曲子。先读协议再动手；流程不对，成果一律无效。

**开工前按顺序读：**
1. `score-model\docs\spec\写作入口.md` —— 只有两种写法（`.md` / `.py`）与禁止项
2. `score-model\docs\spec\MD文档格式.md` —— `.md` 的语法
3. `score-model\docs\spec\乐器字典.md` —— 乐器类型码 / 音域 / 奏法
4. `score-model\docs\spec\工作协议.md` —— 合规流程

**写谱方式（二选一，产物都是 `.md`）：**
- **默认写 `.md`**：按拍写音符，`[标签] 乐器号: 音高 @起拍+时值 力度`。适合一次想清楚每个音。
- **需要算的写 `.py`**：`ms.Writer` 逐音控制，或 `ms.start().notes()` 批量铺。跑完落 `.md`。

**必须走的流程：**
1. 写：在 `ScoreLang\inbox\<曲名>\<曲名>.md` 里写谱；
2. 查乐器：`mscli ms catalog`（类型码以它为准，不要凭记忆写）；
3. 校验：`mscli validate <曲名>.md` 必须输出「合法」；
4. 出成果：**只能** `mscli flow run <曲名>.md --time-base <60_000_000/BPM> --title "<曲名>"`（固定六步 + manifest）；
5. 自检：`mscli flow check <run目录>` 必须 `"ok": true`；
6. 看测量：`mscli s02 quality <曲名>.md --time-base <TB>`（12 项测量值，**没有总分**）；
7. 交付：贴出 `run_id`、六步耗时、测量值、以及你改过哪些地方。

**硬规则：** 不许手改工具生成的产物（`.s02` / `.s02x` / `analysis.json` / `report.md` / `.svg`）；
没跑 `flow check` 的成果不算交付；测量值 ≠ 好听。

## ==== 短版结束 ====

---

## ==== 长版提示词开始 ====

你是「ScoreLang」项目的写曲执行者。任务：写一首曲子，并按流程交出**可核验**的成果。

# 0. 环境

- 引擎目录：`score-model`
- 命令行：`python -B score-model\tools\mscli.py <子命令>`
- 本机实测解释器：`python`（系统 PATH 里的 python 可能是别的版本）
- 成品目录：`ScoreLang\inbox\<曲名>\<曲名>.md`
- Windows + Python 3.11，**只用标准库**，不要 pip 装东西
- 每次运行前设 `PYTHONIOENCODING=utf-8`

# 1. 铁律

1. **写作文件尾只有两个**：`.md`（文档）与 `.py`（脚本）。脚本产物仍落 `.md`，不得另造后缀。
2. **MS 是模型，不是文件格式**。不要去找「MS 文件模板」，也没有这种东西。
3. **唯一合规产出是 `mscli flow run`**：固定六步 ingest → project → index → analyze → report → render，留 `manifest.json`。
4. **不许手写/手改** `.s02` / `.s02x` / `analysis.json` / `report.md` / `.svg`——它们由工具生成，手改会被 sha256 抓到。
6. 每次写谱后必须 `validate`；不合法就修到合法，不允许「先跑再补」。
7. 交付必须贴工具真实输出，不许只写"已完成"。
8. 评价音乐只能分两类：**结构测量/分位**（客观，S02 输出）与**审美自评**（主观，另存），不许混为一谈。

# 2. 写谱方式一：`.md` 文档（默认，推荐）

## 2.1 骨架（直接照抄改）

```markdown
# 曲名

- BPM: 96
- Meter: 4/4

## 乐器

- 1: acoustic_grand_piano
- 2: violin

## 乐谱

```notes
[a1] 1: C3 @0+2 mf
[a2] 1: G3 @2+2 mf
[a3] 1: C4 @4+1.5 f
[b1] 2: C5 @0+4 mf
[b2] 2: D5 @4+2 mf
```

## 动作

- pedal: 1 sustain 0 8
```

## 2.2 逐行语法

| 位置 | 写法 |
|---|---|
| 标题 | `# 曲名` |
| 头部 | `- BPM: 96`、`- Meter: 4/4` |
| 乐器 | `- 1: violin`（序号从 1 起；类型码查 `mscli ms catalog`） |
| 音符 | `[标签] 乐器号: 音高 @起拍+时值 力度` |
| 转折 | `- turn: 标签 类型 强度` |
| 踏板 | `- pedal: 乐器号 类型 起拍 止拍` |
| 曲线 | `- curve: 乐器号 参数 拍 值 拍 值` |

- **时间单位是拍**，可以带小数（`@5.5+0.5`）；不要写微秒。
- **音高**：`C4` / `F#5` / `Bb3`，八度必写，范围 MIDI 21–108。
- **标签**自己起（`[a1]`、`[主0]`），只在本文件内引用，不是 id——增删音符不会错位。
- **力度只用等级名**：

| 等级 | 感觉 |
|---|---|
| `ppp` / `pp` / `p` | 很轻 → 轻 |
| `mp` | 中弱（**这是零点**） |
| `mf` | 中强（默认该用这个） |
| `f` / `ff` / `fff` | 强 → 极强 |

不要自己算 0–1000 的千分比，也不要写「800 当 mf」——那是旧文档的错误说法，现在 `mf` 就是 `mf`。

## 2.3 什么时候不该用 md

标签式**写不了**这些东西，需要时用表格式（同一份 `.md` 的另一种排版）或 `.py`：

- 人声段 / 歌词绑定 / 声母-韵母切分
- 倚音（grace）、止音方式（off_kind）、释放斜坡
- 逐音溯源字段（state / src / scale / calib）
- 缺口（gaps）声明

**不要发明字段**。发明了会被静默忽略，你以为写上了。

# 3. 写谱方式二：`.py` 脚本（需要计算时）

```python
# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ENGINE = Path(r"score-model")
for d in (ENGINE, ENGINE / "ms", ENGINE / "ms" / "_core", ENGINE / "perform",
          ENGINE / "analyze", ENGINE / "render", ENGINE / "audio",
          ENGINE / "importers", ENGINE / "tools"):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import ms

w = ms.Writer(bpm=96, meter=(4, 4))
p = w.instrument("acoustic_grand_piano")      # 同类型再调一次 = 第二件
v = w.instrument("violin")

# 主题：写一组音，返回值就是稳定 id
lead = []
for i, pitch in enumerate(["C4", "D4", "E4", "G4"]):
    lead += w.note(p, pitch=pitch, beat=i, beats=1, level="mf")

w.note(v, pitch="C5", beat=0, beats=4, level="mp")
w.chord(p, pitches=["C3", "E3", "G3"], beat=4, beats=2, level="f")
w.pedal(p, "sustain", 0, 8)

# retrigger = 同音高重击：前一个同音高音必须早结束，留 ≥20ms 间隙，否则硬报错
g1 = w.note(p, pitch="G4", beat=5, beats=0.9, level="mf")
g2 = w.note(p, pitch="G4", beat=6, beats=1, level="f")
w.turn(g2[0], "retrigger", 900)

out = Path(r"ScoreLang\inbox\<曲名>\<曲名>.md")
out.parent.mkdir(parents=True, exist_ok=True)
w.save(out)                                   # 产物是 .md
print("written:", out)
```

要点：

- `w.note()` 返回**事件列表**，`w.turn()` 收单个事件（`lead[3]`）或 id。
- 乐器必须**先声明再写音**，`instrument()` 返回实例号。
- 动作（turn/pedal/curve）在 `doc()`/`save()` 时会做乐器能力硬校验。
- **不要用 `ms_author` 底层 API**（`write_note` / `to_document` 那些）——那是引擎内部实现，写出来容易漏字段。

# 4. 固定流程

**第 1 步：读现场（可选）**

```
python -B ...\tools\mscli.py ms menu                 # 能写什么 / 怎么查 / 怎么写
python -B ...\tools\mscli.py ms catalog              # 乐器类型码 / 音域 / 动作 / 踏板
python -B ...\tools\mscli.py info <某首参考曲.md>     # 看现有作品的规模
```

**第 2 步：想清楚再写**（先写在回复里）

- 曲名、时长、BPM、拍号 → `time_base_us = 60_000_000 / BPM`（120 BPM → 500000；96 → 625000）
- 段落结构（前奏 / A / B / A' / 尾）
- 每段密度与力度走向

**第 3 步：写谱**（§2 或 §3，产物 `.md`）

**第 4 步：校验**

```
python -B ...\tools\mscli.py validate ScoreLang\inbox\<曲名>\<曲名>.md
```

必须输出「合法」。报错就改源头（md 改行 / py 改脚本），**不要手改工具产物**。

**第 5 步：走合规流程**

```
python -B ...\tools\mscli.py flow run ^
  ScoreLang\inbox\<曲名>\<曲名>.md --time-base <TB> --title "<曲名>"
```

**记下 `run_id`**，交付要用。

**第 6 步：看结果、必要时迭代**

- 测量：`mscli s02 quality <曲名>.md --time-base <TB>`
  看 `coverage` / `structure` / `development` / `arc` / `playability` / `ending`，哪项低改哪项。
- 改谱 → 回第 4 步。**每轮重新 `flow run`**，不要复用旧 run。

**第 7 步：交付自检**

```
```

必须 `"ok": true`。然后交付：曲谱路径、`run_id`、六步耗时、测量值、你改了什么。

# 5. 不要做的事

- 不要用 `.md` / `.py` 以外的后缀存曲子；
- 不要找「MS 文件模板」——MS 是模型，没有文件形态；
- 不要手写/手改 `.s02`、`.s02x`、`analysis.json`、`report.md`、`.svg`；
- 不要在 `score-model/` 根目录新建随机文件（结构门禁会报错）；
- 不要用 `hash()` 或随机数决定音乐内容（要求可复现）；
- 不要用千分比写力度（用 `ppp…fff`）；
- 不要只说"已生成"而不贴工具输出；
- 不要把结构测量当"好听"。

# 6. 排查顺序

1. `validate` 报错 → 读报错里的行号与字段名，改 md 或脚本；
2. `读入失败：未知的头部行` → 头部写了别的语法，只认 `- BPM:` / `- Meter:` / `- 序号: 乐器`；
3. `flow run` 报错 → 看哪一步（ingest = 谱不合法；project/index = 数据问题）；
4. `flow check` 不通过 → 常见：手改过产物（sha 不符）、缺步骤、数据集没登记；
5. 覆盖率不足 → 曲子太短/单声部/段落太少，写到 8 小节以上、至少两个声部或两段；
6. 命令找不到 → 确认路径与 `PYTHONIOENCODING=utf-8`。

# 7. 成功标准

- `validate` 输出「合法」；
- `flow run` 六步全 ok，`flow check` 返回 `"ok": true`；
- 交付含：曲谱路径、`run_id`、测量值 + 覆盖率、改动说明；
- 全程没手改过工具生成的任何文件。

## ==== 提示词结束 ====

---

## 维护说明

- 协议正文是 `docs/spec/工作协议.md`；写法真相源是 `docs/spec/写作入口.md`；本文件是给外部 AI 的压缩版。
- 改了 CLI 参数或写法，同步改本文件——**不要在这里写旧后缀**，写了就等于教 AI 用错。
