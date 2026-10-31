# 代码地图（按层）

> 根目录只留**门禁入口**；业务模块按依赖层分布在五个目录。
> 结构由 `check_structure.py` 机检（进 `run_all`），乱放会红。

## 核心（core/）

| 模块 | 一句话 |
|---|---|
| `core/ms_model.py` | MS 模型：dataclass + 常量（纯数据） |
| `core/ms_validate.py` | 结构校验 V1–V13 |
| `core/ms_realization.py` | 演奏收束 R-1..R-4 |
| `core/ms_events.py` | 聚合门面（再导出 model/validate/realization） |
| `core/ms_semantics.py` | 数学结构化乐谱 · 语义核（第三步自验的最小可执行骨架） |
| `core/ms_instruments.py` | 乐器总登记表：128 GM 类型 + 16 族能力 + 子类型 |
| `ms/_core/ms_io.py` | 旧档案行式读写（**只读兼容**，见 `../reference/旧档案线格式.md`）；写作不经过它 |
| `core/model_v02.py` | SPEC v0.2 底层语义模型（实现 SEMANTIC_CONTRACT_v0.2） |

## 写谱与编辑（notation/）

| 模块 | 一句话 |
|---|---|
| `notation/ms_dynamics_levels.py` | 写谱层 · 默认力度等级表（`dyn-levels-v1`） |
| `notation/ms_articulation.py` | 写谱层 · 奏法参数表（`articulation-v1`，2026-10-19） |
| `notation/ms_ornament.py` | 写谱层 · 装饰音展开表（`ornament-v1`，2026-10-19） |
| `notation/ms_author.py` | 写谱 API（2026-10-19）：把三张表串成"写一个音"的能力 |
| `notation/ms_edit.py` | 引擎 · 编辑通道（六铁律 E1–E6） |

## 呈现（render/）

| 模块 | 一句话 |
|---|---|
| `render/ms_render.py` | 引擎呈现层 · 阶段 1：MSDocument → SVG |
| `render/ms_render_staff2.py` | 五线规范排版（排表 II-3） |
| `render/ms_render_jianpu.py` | 数字简谱渲染（排表 II-2 · 阶段2 第一优先） |
| `render/ms_score.py` | 完整五线谱渲染（2026-10-19） |

## 播放（audio/）

| 模块 | 一句话 |
|---|---|
| `audio/ms_audio.py` | 引擎 · 听觉参数（不合成音频，只出参数表） |
| `audio/ms_voice.py` | 人声接口（歌词 + 声调 → 共振峰） |
| `audio/ms_midi.py` | MIDI 导出与回读（排表 III-1 / III-2） |

## 投影与判定（transform/）

| 模块 | 一句话 |
|---|---|
| `transform/ms_to_s02.py` | MS（事件模型）→ ScoreV02 投影（迁移 M-1~M-3 的实现件 · 2026-10- |
| `transform/s02_to_ms.py` | ScoreV02 → MS（事件模型）反向转换（M-6.5 · R6 往返所需） |
| `transform/transform_events.py` | C2 新入口：`MSDocument → ScoreV02`（迁移 M-1，2026-10-19 |
| `transform/transform_types.py` | 转换层的数据类型与常量（2026-10-19 抽出） |
| `transform/c3_judgment.py` | C3 判定层（实现）· 依 C3_JUDGMENT_CONTRACT_DESIGN.md v2  |

## 门禁（根目录）

| 模块 | 一句话 |
|---|---|
| `run_all.py` | 统一测试入口（排表 I-1） |
| `check_consistency.py` | 一致性检查（排表 V-4）：文档 ↔ 实现 ↔ 测试 是否对得上 |
| `check_structure.py` | 结构门禁：防复发（根目录只放核心模块；文档进 docs；产物不进工程；无临时文件） |

## 工具（tools/）

| 模块 | 一句话 |
|---|---|
| `tools/mscli.py` | 命令行入口（排表 I-2 / I-3） |
| `tools/ms_server.py` | 本地编辑器服务（排表 IV-3）：HTML 单页 + 薄后端 |
| `tools/perf_baseline.py` | 性能基线（分级） |

## 作曲与示例（compose/）

| 模块 | 一句话 |
|---|---|
| `ScoreLang/archive/piece-sources/` | 两首作品的生成脚本（**作品来源**，非工程能力） |
| `audio/make_audio.py` | MS → WAV（本项目自带的最小钢琴合成，2026-10-19 · v2） |

## 导入（importers/）

| 模块 | 一句话 |
|---|---|
| `importers/ms_import.py` | MusicXML → MS（事件模型）导入器（2026-10-19） |
| `importers/ms_import_midi.py` | MIDI → MS（事件模型）导入器（2026-10-19） |
| `importers/abc_parse.py` | ABC 谱面解析库 —— 适配 pattern_assembler 产出的 ABC 格式 |
| `importers/abc2ms.py` | ABC → `.ms` 导入桥（ScoreLang 引擎产出物 → score-mode |

## 测试（tests/）

共 34 个；统一入口 `python run_all.py`。
