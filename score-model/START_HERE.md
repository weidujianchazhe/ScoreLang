# START HERE · 这个工程是什么 / 怎么跑（5 分钟）

> 平台技能入口：`../SKILL.md`（路由）；本页是 5 分钟总览，细节去 `docs/`。

> 给**第一次来的人或 AI**：读完这一页，够你判断「要不要用、怎么用、别动什么」。
> 往深处走：`README.md`（代码地图）→ `docs/spec/`（规范）。

---

## 1. 这是什么

一套**乐谱的数学模型 + 工具链**。核心主张：

> 谱面事实（音高/时间/力度/释放/踏板）用**绝对数值**表示；
> 记号 → 数值的换算**只在写谱层**做；
> 算不出来的就记 `NOT_PROVIDED`，**不猜**。

### 口径（先分清这三个，后面全按这个说）

| 词 | 是什么 | 有文件形态吗 |
|---|---|---|
| **MS 格式** | **MS 数学模型**：事件模型 + 语义 + 六条不变量 | **没有**，它是内存里的 `MSDocument` |
| **`.md`** | 模型的**文档写法**（标签式 / 表格式） | 有 |
| **`.py`** | 模型的**脚本写法**（`ms.Writer` / `ms.start`） | 有，产物落 `.md` |

**写谱只有这两种方式。** MS 不是文件后缀，没有「MS 文件模板」这种东西。
完整规则见 `docs/spec/写作手册.md`。

### 能做什么

| 能做 | 命令 |
|---|---|
| 校验一份谱 | `python tools/mscli.py validate x.md` |
| 导入 MusicXML / MIDI | `python tools/mscli.py import x.musicxml -o x.md` |
| 出 MIDI | `python tools/mscli.py export x.md -o x.mid --time-base 500000` |
| 出图（4 种） | `python ../tools/render_svg.py x.md -o x.svg --mode staff2` |
| 出声（三档音色） | `python ../tools/midi_to_wav.py x.mid -o x.wav` |
| 打开编辑器（浏览器） | `python tools/mscli.py serve x.md` |
| 合规产出（六步 + manifest） | `python tools/mscli.py flow run x.md --time-base 500000` |
| 跑全部测试 | `python run_all.py` |

**Python 解释器**：`python`
（系统 PATH 里的 python 可能是 3.13 且缺 numpy；所有命令在 `score-model` 目录下执行）

---

## 2. 三分钟上手

```powershell
cd score-model

# ① 看一份现成的谱
python tools/mscli.py info samples/chords_and_pedal.md

# ② 自己写一份（复制骨架，改音符）
#    见 docs/spec/写作手册.md，产物是 .md

# ③ 跑测试，确认环境没问题
python run_all.py
```

看到 `全部通过（78 套件，1218 项断言）` 就说明环境正常。

---

## 3. 目录地图

```
score-model/
├── START_HERE.md          ← 本页
├── README.md              ← 代码地图
├── docs/                  ← 文档
│   ├── spec/              ← 现行规范（写作手册、数学模型、S02）
│   ├── reference/         ← 生成物（速查卡/乐器/演奏语义）
├── ms/                    ← 门面层（api / Writer / start / 渲染 / 报告）
│   └── _core/             ← 模型内核（事件模型 / 校验 / 收束 / .md 读写）
├── perform/               ← 演奏语义（力度等级 / 奏法 / 装饰音 / 乐器表）
├── render/                ← 谱面（五线 / 简谱 / 事件谱 / ABC）
├── audio/                 ← 播放（MIDI 导出 / 合成）
├── analyze/               ← S02 投影与测量
├── importers/             ← 导入：MusicXML / MIDI / ABC
├── tools/                 ← 入口：mscli / ms_server / msflow
├── tests/                 ← 测试与验收（run_all.py 的套件）
├── samples/               ← 示例谱（.md，资产）
├── fixtures/              ← 测试用 MusicXML（含 real/ 三份真实谱）
├── tests/snapshots/       ← 渲染快照（视觉回归基线，别随手改）
└── （无 out/）            ← 产出一律写 ../inbox/（临时产出区）
```

---

## 3.5 产出放哪（**先看这条，别放错**）

| 你产出了什么 | 放哪 | 不要放哪 |
|---|---|---|
| **曲子本体**（`.md` 源） | `ScoreLang/inbox/<曲名>/<曲名>.md` | ❌ 工程区根目录 |
| **导出产物**（mid / wav / pdf / png） | `inbox/<曲名>/` | — |
| **中间产物**（试渲染、测试 MIDI） | `inbox/<曲名>/_work/` 或系统临时目录 | — |
| **分析数据** | 与曲目同目录的 `inbox/<曲名>/` | — |

> **判据：工程依赖 vs 工程产出。**
> 工程跑起来需要它 → 留工程区；作品产物 → `inbox/`（**正式产出区**）。

---

## 4. 该读哪几份

| 想知道 | 读 |
|---|---|
| 怎么写谱 | `docs/spec/写作手册.md`（只有 `.md` / `.py` 两种） |
| `.md` 的内部结构 | `docs/spec/写作手册.md` |
| 文件尾标识与四层划分 | `docs/spec/文件尾标识约定.md` |
| 数据模型长什么样 | `docs/spec/数学乐谱规范.md` |
| 转换判定的标准 | `docs/spec/边界与契约.md` |
| 为什么这么设计 | `docs/spec/第一原理.md`（P1–P5） |
| 已知限制 | `docs/spec/已知边界.md` |
| 给外部 AI 的完整提示词 | `docs/spec/给外部AI的提示词.md` |

**不要碰的**：`tests/snapshots/`（回归基线）。

---

## 5. 三条硬规矩

1. **不猜**：缺失就是缺失（`NOT_PROVIDED`），不填默认值、不静默降级。
2. **结构合法 ≠ 能弹**：同键同刻在结构上允许，只在演奏收束（`check_realization`）里报 `R-1..R-4`。

---

## 6. 成熟度（别误解）

| 能做 | 还不能做 |
|---|---|
| 单声部/多声部谱的表示、渲染、导出、回读 | 流式结构（S02 是否承担**未定**） |
| MusicXML / MIDI 导入 | 标准 ABC 导入（目前只吃工程自产方言） |
| 88 键演奏收束检查 | 复杂排版（跨行连音线、多页自动分页以外的版式） |

**规模参考**：现有曲子 588–3804 事件（3–6 分钟）；工具在 20k 事件内验证过。
