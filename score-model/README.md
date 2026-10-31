# ScoreLang · score-model 项目地图

> 一页看清：**谁是权威、谁在服役、工具有哪些、从哪开始读**。

---

## 1. 先读这三份

> 第一次来先看 **`START_HERE.md`**。下面三份是规范原文，在 `docs/spec/`。

| 文档 | 作用 |
|---|---|
| `docs/spec/数学乐谱规范.md` | **MS 的权威定义**（事件模型：时间/力度/释放/踏板/键/约束档） |
| `docs/spec/边界与契约.md` | 转换契约（比较基准、最低覆盖、时间基准、比较维度） |
| `docs/spec/第一原理.md` | P1–P5：结构允许≠计算需要≠写谱许可、计算只吃数值、换算在写谱侧、缺失有痕、结构/收束分层 |

工程文档：`docs/spec`（现行规范）· `docs/reference`（生成的速查/语义）·

## 2. 代码分层

```
ms/_core/   ms_model.py         dataclass + 常量（Pitch/Dynamics/PedalSegment/Event/Instrument/Lyric/MSDocument）
            ms_validate.py      结构校验 V1–V13
            ms_realization.py   演奏收束 R-1..R-4
            ms_events.py        聚合门面（再导出上面三者）
            ms_md.py            .md 读写（标签式 / 表格式，自动识别）——写作格式
            ms_io.py            旧档案行式读写（只读兼容，不作写作格式）
            ms_instruments.py   乐器登记表（GM 128 + 族 + 民乐目录 + 因子 + 收束）
            ms_semantics.py     五态等基础语义
            model_v02.py        S02 结构定义（唯一实现，架构定位未定）
写谱层      ms_dynamics_levels.py   力度等级 → 千分比
            ms_articulation.py     奏法 → 时长/力度修正
            ms_ornament.py         装饰音展开
            ms_author.py           组合三表：写一个音 → 事件列表
编辑        ms_edit.py             单步 + 批量 + 撤销/重做
呈现        ms_render.py           渲染参数 + 事件谱 / 简化五线 / 文本
            ms_render_staff2.py    五线规范（大谱表/加线/连杠/小节线/多行）
            ms_render_jianpu.py    数字简谱（三模式）
            ms_score.py            完整五线谱（谱号/调号/拍号/临时记号/分页/署名）
播放        ms_audio.py            命令流后端（含 Null backend）
            ms_midi.py             MIDI 导出（Program Change/多文件/鼓组/歌词）+ 回读
            make_audio.py          自研合成 → WAV（机制分支 + 逐件音色）
            ms_voice.py            人声接口（歌词 + 声调 + 多语言）
导入        ms_import.py           MusicXML / .mxl → MS
            ms_import_midi.py      MIDI → MS
            abc_parse.py           ABC 解析（仅限工程自产方言）
            abc2ms.py              ABC → .md
投影        ms_to_s02.py           MSDocument → ScoreV02（逐条记损失）
            s02_to_ms.py           ScoreV02 → MSDocument（反向，R6 用）
            transform_events.py    C2 入口
            transform_types.py     转换层类型与常量
判定        c3_judgment.py         C3：J1/J2 判定 + 作用域规则
收束        ms_playability.py      按机制的可演奏性检查 C1–C6
工具        tools/mscli.py         validate / info / export / import / serve
            tools/ms_server.py     编辑器薄后端（单页在 server_ui.html）
            run_all.py · check_consistency.py · check_structure.py
作曲        （通用作曲脚本规划中；两首旧作脚本在管理区 archive/piece-sources/）
```

## 3. 状态标记

| 状态 | 文件 |
|---|---|
| **权威** | `ms_model.py` · `ms_validate.py` · `ms_io.py` · `ms_instruments.py` |
| **现役** | 上表其余 |
| **冻结** | `c3_judgment.py` · `model_v02.py`（除已授权变更外不改） |
| **已退役** | `legacy/` 链路已移入 `ScoreLang/archive/score-model-legacy/` |

## 4. 工具清单（按用途）

| 想做 | 用什么 |
|---|---|
| 校验一份谱 | `python tools/mscli.py validate x.md` |
| 看摘要 | `python tools/mscli.py info x.md` |
| 出 MIDI | `python tools/mscli.py export x.md -o out.mid --time-base 500000` |
| **出声（直接出 wav）** | `python tools/mscli.py audio x.md -o out.wav` |
| 导入 MusicXML/MIDI | `python tools/mscli.py import x.musicxml -o x.md` |
| 导入 ABC（工程方言） | `python importers/abc2ms.py x.abc x.md` |
| 出图（4 种） | `python tools/render_svg.py x.md -o out.svg --mode pianoroll\|staff\|staff2\|jianpu` |
| 出完整五线谱图 | `ms_score.render_score(...)` + 截图 |
| 出声（三档音色） | `python ../tools/midi_to_wav.py x.mid -o out.wav`（auto：Salamander → sf3 → FluidR3） |
| 出 LilyPond 谱 | `python ../tools/abc2ly.py x.abc x.ly`（需另装 LilyPond 才能编译） |
| 跑全部测试 | `python run_all.py` |
| 查一致性 / 结构 | `python check_consistency.py` / `python check_structure.py` |

> **写谱只有两种方式**：写 `x.md`（文档）或写 `x.py`（脚本，产物落 `x.md`）。
> 细则见 `docs/spec/写作手册.md`。

### 4b. S02 分析 / 改曲闭环

| 想做 | 用什么 |
|---|---|
| **批量跑一批 / 周期积累** | `mscli flow batch <目录> --tag 2026-11-week1`（默认扫 `*.md`） |
| **结构测量（不给分）** | `mscli s02 quality x.s02`（12 项测量值，无总分） |
| **与参照集比较（分位）** | `mscli s02 compare x.md --batch ref-classical` |
| **演奏能力覆盖（会不会用）** | `mscli s02 capability x.md --hints`；`mscli s02 instruments` |
| 建骨架 + 索引 | `mscli s02 build x.md --time-base 500000 -o x.s02`；`mscli s02 index x.s02` |
| 出报告 / 分析图 | `mscli s02 report x.s02 --index x.s02x`；`mscli s02 render x.s02` |
| 难度 / 扰动 / 维度 | `mscli s02 fingers` / `perturb` / `score --target "drive=0.9"` |
| **改前改后对比** | `mscli s02 diff old.s02 new.s02 -o diff.md` |
| 补丁预演（不改 MS） | `mscli s02 patch x.s02 fix.json`（默认 dry-run） |
| 权重校准 + 积累 | `mscli s02 refs --add ref.md` / `mscli s02 refs --calibrate` |
| **品味评分 / 训练 / 预测** | `mscli taste rate` / `taste train` / `taste predict` |
| 性能基线 | `mscli s02 bench x.md --time-base 500000` |

> **产出必须走 `flow run`**：固定六步、写 manifest、登记数据集、可被 `flow check` 校验。

## 5. ABC 工具的限制

- 只接受**工程自产方言**：需 `V:1 clef=...` / `[V:1]`；八度约定非标准（小写=八度 5、大写=八度 4）。
- 无 `V:` 的普通 ABC 会报"小节线处拍位不齐"——是方言不匹配，不是 bug。

## 6. 外部工具（不在本目录）

| 路径 | 内容 |
|---|---|
| `tools\fluidsynth\` | FluidSynth 2.6.1 |
| `tools\sfizz\` | sfizz 1.2.3（SFZ 渲染） |
| `tools\soundfonts\` | Salamander V3（394MB）· MuseScore_General.sf3 · FluidR3 GM2 |
| `tools\kmc\` | KMC（已弃用） |

## 7. 目录

| 目录 | 内容 |
|---|---|
| `samples/` | 三份示例谱（`.md`，资产） |
| `fixtures/` | MusicXML/MIDI 测试素材（含 `real/`） |
| `references/` | **参照曲目库**（`manifest.toml` + 曲目 + 校准权重版本） |
| `tests/snapshots/` | 渲染快照（视觉回归基线，不要随手改） |
| （无 `out/`） | 产出写 `../inbox/`；临时文件用系统 `%TEMP%` |

## 8. 可搬迁（换目录 / 换机器）

- 所有模块用 `Path(__file__)` 推导根目录；`run_all.py` / `check_structure.py` 也如此；
- **代码里不许出现写死的绝对路径**——`check_structure.py` 第 11 条门禁会拦住；
- 依赖只有 Python 3.11 标准库（不需要 pip 装东西）；
- 已验证：把整个 `score-model/` 复制到任意目录，`python run_all.py` 仍 **67 套件 / 1005 断言全绿**；
- 工作区级工具（`../tools/render_svg.py`、`abc2ly.py`）用相邻目录约定；
  `midi_to_wav.py` 的第三方工具/音色库可用环境变量 `MIDI_TO_WAV_TOOLS` 指定；
- 外部依赖（fluidsynth/音色库）本来就不在本目录，属于可选项。

> `../inbox/` 里的一次性生成脚本已改为"向上找工作区根目录"，但个别脚本本身与当前
