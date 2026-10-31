# -*- coding: utf-8 -*-
"""S02 规则层权重（**阈值只许出现在这里**）。

死算层（`s02_probe` / `s02_harmony`）不读本文件；只有分段/标签/诊断这些"判断"才用。
权重可整体替换：`load()` 先取内置默认，再用 TOML 覆盖（`tomllib`，标准库）。
"""
from __future__ import annotations

from pathlib import Path

DEFAULTS = {
    "segment": {
        "min_section_bars": 4,      # 一段至少几小节
        "split_ratio": 0.06,        # 切一刀至少要降低多少比例的段内方差（越大越少切）
        "phrase_long_note_bars": 2,  # 长音阈值：时值 ≥ 2 小节的音起句读
        "min_phrase_bars": 2,      # 一短语至少几小节（避免句读碎成一片）
    },
    "label": {
        "density_high": 8.0,       # 每小节音数
        "density_low": 3.0,
        "tension_high": 0.45,      # 纵向张力 0..1
        "tension_low": 0.15,
        "centroid_high": 72,       # MIDI 均值
        "centroid_low": 55,
    },
    "diagnose": {
        "flat_density_range": 1.5,   # 全曲密度极差小于此 → "线条平"
        "high_repeat_ratio": 0.5,    # 重复窗口占比高于此 → "靠重复撑"
        "low_repeat_ratio": 0.05,    # 低于此 → "缺乏呼应"
    },
    "fingering": {
        "span_limit": 12,            # 同刻跨度上限（半音）：12 = 八度
        "hard_limit": 16,            # 超过此跨度基本够不到（十度）
        "jump_limit": 19,            # 相邻两组音之间允许的手位移动（半音；八度+五度）
    },
    "perturb": {
        "accent_z": 1.5,             # 力度偏移：至少高出本节均值 1.5 个标准差
        "accent_abs": 200,           # 且绝对值高出 200‰（避免小样本噪声）
        "register_jump": 19,         # 音区突变：比该声部附近中位 ≥ 19 半音（八度+五度）
        "density_slope": 0.5,        # 密度突变：相对上一节变化 ≥ 50%
        "tension_per_event": 0.10,   # L3→L4：每段扰动最多把紧张度抬高多少（按扰动比例饱和）
    },
    "quality": {
        # 2026-10-27 按 557 首参照曲目分布校准（全部连续化，避免饱和）
        "structure_cv_lo": 0.30,     # 段落长度 CV：≤0.30 满分
        "structure_cv_hi": 1.20,     # CV ≥1.20 记 0
        "return_scale": 0.30,        # 首末段四维距离：0.30 记 0
        "phrasing_min_bars": 4.0,    # 平均句长（小节）
        "phrasing_max_bars": 24.0,
        "register_scale": 10.0,      # 音区重心 std / 10 → 0..1
        "variety_low": 0.15,         # 密度 CV 低于此判平
        "variety_scale": 0.5,        # CV / 0.5 → 0..1
        "counterpoint_center": 0.5,  # 反向占比理想中心
        "counterpoint_scale": 0.30,  # 偏离 0.30 记 0
        "harmonic_center": 0.045,    # 调外音比例理想中心
        "harmonic_scale": 0.09,
        "ending_offset": 0.05,       # 末段密度回落（+0.05 容差）
        "ending_scale": 0.25,
        "dynamics_scale": 0.6,       # 力度差 / 0.6
        "arc_sd_scale": 0.06,        # 张力 std / 0.06
        "arc_edge": 0.25,            # 峰值在两端时的分
        "voice_stagger_min": 0.01,   # 同时结束判 0
        "voice_stagger_lo": 0.02,    # 错落评分区间
        "voice_stagger_hi": 0.35,
        "voice_fade_scale": 2.0,
        "voice_w_stagger": 0.5,
        "voice_w_fade": 0.3,
        "voice_w_hold": 0.2,
    },
    "score": {
        # 连续维度 = sigmoid((原始值 − center) / scale)
        "tension_center": 0.35,      # 纵向+跳进+调外的合成原始值
        "tension_scale": 0.15,
        "drive_center": 6.0,         # 密度（每小节音数）
        "drive_scale": 3.0,
        "space_center": 6.0,         # 留白：密度反向，center 是"中等密度"
        "space_scale": 3.0,
        "bright_center": 64.0,       # 音区重心（MIDI）
        "bright_scale": 10.0,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None) -> dict:
    """内置默认 + 可选 TOML 覆盖。"""
    data = {k: dict(v) for k, v in DEFAULTS.items()}
    if path:
        p = Path(path)
        if p.exists():
            try:
                import tomllib
                with p.open("rb") as fh:
                    data = _merge(data, tomllib.load(fh))
            except Exception:
                pass
    return data


def dump_template(path) -> Path:
    """写一份带注释的默认权重文件（给人改）。"""
    p = Path(path)
    lines = ["# S02 规则层权重（阈值只允许出现在这里）", ""]
    for section, kv in DEFAULTS.items():
        lines.append(f"[{section}]")
        for k, v in kv.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
