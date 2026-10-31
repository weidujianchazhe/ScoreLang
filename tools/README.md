# tools/ · 生产脚本（工程外）

> **这里不是引擎。** 引擎只出 `.mid`；把 MIDI 变成能听的 WAV 在工程外做。
> 边界依据：`score-model/docs/spec/PLAYBACK.md`、`KNOWN_LIMITS.md`。

## 有什么

| 脚本 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `midi_to_wav.py` | `.mid` 或目录 | `*_concert.wav` | FluidSynth 离线渲染 + 温暖 EQ + 轻饱和 + 真峰值归一化；**只出 WAV** |

## 用法

```powershell
# 单文件
python midi_to_wav.py piece.mid -o out\piece_concert.wav --eq-warm --saturate

# 多文件（多乐器分轨）：目录里所有 .mid 各自渲染后混音
python midi_to_wav.py out\midi\ -o out\album_concert.wav --eq-warm --saturate
```

## 外部依赖（不在本仓库）

| 组件 | 位置 | 状态 |
|---|---|---|
| FluidSynth 2.6.1 | `tools\fluidsynth\...\bin\fluidsynth.exe` | ✅ |
| sfizz 1.2.3 | `tools\sfizz\bin\Release\sfizz_render.exe` | ✅（等 SFZ 音色） |
| MuseScore_General.sf3 | `tools\soundfonts\MuseScore_General.sf3` | ✅ 可用 |
| **Arachno SoundFont 1.0**（148 MB） | `tools\soundfonts\arachno\` | ✅ **GM 首选**（免费使用；再分发/商用查官网许可） |
| FluidR3 GM2-2.SF2 | `tools\soundfonts\fluid\FluidR3 GM2-2.SF2` | ✅ 可用 |
| Salamander Grand Piano | `tools\soundfonts\salamander\` | ✅（**仅钢琴**，SFZ 不读 Program Change） |

音色优先级：
- **多音色**：Arachno → MuseScore_General → FluidR3（`--engine auto` 会先扫 MIDI 里的 Program 判断是否多音色）
- **纯钢琴**：Salamander + sfizz

## 规则

1. **只交 WAV**：flac 可归档，mp3 不做（项目裁定）。
2. 渲染参数变更要写交接记录（音量/混响/EQ 都会改变听感）。
3. 这里不放引擎能力：需要模型语义（音域/鼓组/踏板）的改动，回 `score-model/`。
