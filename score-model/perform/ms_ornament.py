# -*- coding: utf-8 -*-
"""写谱层 · 装饰音展开表。

作用：把"人写的装饰音记号"展开成**若干具体音符**（起点/时长/音高），供写谱层写入 MS。
第一原理：本模块**不属模型、不进契约、不参与计算**；MS 里存的是展开后的音符。

实证依据（已解析正文）：
  - 短倚音：实测 `previous stolen proportion = 1` → **拍前、从前音借时间**；
    文献口径 short appoggiatura < 1/3 主音 → 默认 0.25
  - 长倚音：文献 long appoggiatura = 主音 1/2 ~ 2/3 → 默认 0.5，拍上（从主音借）
  - 颤音：实测钢琴均值 **10.1 note/s**（区间 6.4–12.1）→ 默认 10 次/秒
  - 波音 / 回音：**无实证**，按约定（辅助音各 10% / 四音各 15%）

关键约束：**邻音音高必须由调用方给出**——邻音要按调号取调内音，而 MS 不含调号，
所以取音只能在上游（谱面/导入层）完成。本模块只做"给定邻音后如何切分时间"。
"""
from __future__ import annotations

VERSION = "ornament-v1"

# 时长比例（千分比）
from semantics import (GRACE_SHORT_PM, APPOGGIATURA_LONG_PM,
                       MORDENT_AUX_PM, TURN_EACH_PM, TRILL_RATE_HZ)

SINGLE = ("grace_short", "appoggiatura_long", "mordent", "turn", "trill")


def _split(duration_us: int, parts) -> list:
    """按千分比切分时长，余数并入最后一段（保证总时长不变）。"""
    out, used = [], 0
    for pm in parts[:-1]:
        d = duration_us * pm // 1000
        out.append(d)
        used += d
    out.append(duration_us - used)
    return out


def expand(ornament: str, *, onset_us: int, duration_us: int, main_semitone: int,
           upper_semitone: int | None = None, lower_semitone: int | None = None,
           grace_semitone: int | None = None) -> list:
    """展开为音符列表 `[{"onset_us", "duration_us", "semitone", "role"}]`。

    `role` ∈ {main, grace, aux, final}，仅供呈现层标注，不属 MS 语义。
    """
    if ornament not in SINGLE:
        raise KeyError(f"未知装饰音：{ornament!r}（允许 {SINGLE}）")
    if duration_us <= 0:
        raise ValueError("主音时长必须为正")
    dur = int(duration_us)

    if ornament == "grace_short":
        gs = grace_semitone if grace_semitone is not None else main_semitone + 1
        g = max(1, dur * GRACE_SHORT_PM // 1000)
        if onset_us >= g:
            # 拍前：起点在主音之前，从前音借时间
            return [
                {"onset_us": onset_us - g, "duration_us": g, "semitone": gs,
                 "role": "grace"},
                {"onset_us": onset_us, "duration_us": dur, "semitone": main_semitone,
                 "role": "main"},
            ]
        # 前方空间不足：退化为拍上（占主音开头），并标 role=grace_onbeat 以便上游察觉
        return [
            {"onset_us": onset_us, "duration_us": g, "semitone": gs,
             "role": "grace_onbeat"},
            {"onset_us": onset_us + g, "duration_us": dur - g, "semitone": main_semitone,
             "role": "main"},
        ]

    if ornament == "appoggiatura_long":
        gs = (grace_semitone if grace_semitone is not None
              else (upper_semitone if upper_semitone is not None
                    else main_semitone + 1))
        g = max(1, dur * APPOGGIATURA_LONG_PM // 1000)
        return [
            {"onset_us": onset_us, "duration_us": g, "semitone": gs,
             "role": "grace"},
            {"onset_us": onset_us + g, "duration_us": dur - g, "semitone": main_semitone,
             "role": "main"},
        ]

    if ornament == "mordent":
        if upper_semitone is None:
            raise ValueError("mordent 需要 upper_semitone（调内上邻音，由上游提供）")
        d1, d_aux, d2 = _split(dur, [450, MORDENT_AUX_PM, 450])
        return [
            {"onset_us": onset_us, "duration_us": d1, "semitone": main_semitone, "role": "main"},
            {"onset_us": onset_us + d1, "duration_us": d_aux, "semitone": upper_semitone, "role": "aux"},
            {"onset_us": onset_us + d1 + d_aux, "duration_us": d2, "semitone": main_semitone,
             "role": "final"},
        ]

    if ornament == "turn":
        if upper_semitone is None or lower_semitone is None:
            raise ValueError("turn 需要 upper_semitone 与 lower_semitone")
        d_up, d_main, d_low, d_rest = _split(
            dur, [TURN_EACH_PM, TURN_EACH_PM, TURN_EACH_PM, 1000 - 3 * TURN_EACH_PM])
        return [
            {"onset_us": onset_us, "duration_us": d_up, "semitone": upper_semitone, "role": "aux"},
            {"onset_us": onset_us + d_up, "duration_us": d_main, "semitone": main_semitone, "role": "main"},
            {"onset_us": onset_us + d_up + d_main, "duration_us": d_low,
             "semitone": lower_semitone, "role": "aux"},
            {"onset_us": onset_us + d_up + d_main + d_low, "duration_us": d_rest,
             "semitone": main_semitone, "role": "final"},
        ]

    # trill
    if upper_semitone is None:
        raise ValueError("trill 需要 upper_semitone")
    period = 1_000_000 // TRILL_RATE_HZ          # 100_000 µs = 100ms
    out, t, i = [], onset_us, 0
    while t + period <= onset_us + dur:
        out.append({"onset_us": t, "duration_us": period,
                    "semitone": main_semitone if i % 2 == 0 else upper_semitone,
                    "role": "main" if i % 2 == 0 else "aux"})
        t += period
        i += 1
    if not out:                                   # 太短，退化为一个主音
        return [{"onset_us": onset_us, "duration_us": dur,
                 "semitone": main_semitone, "role": "main"}]
    tail = onset_us + dur - t
    if tail > 0:
        out.append({"onset_us": t, "duration_us": tail, "semitone": main_semitone, "role": "final"})
    return out


def table() -> dict:
    return {
        "version": VERSION,
        "grace_short_pm": GRACE_SHORT_PM,
        "appoggiatura_long_pm": APPOGGIATURA_LONG_PM,
        "mordent_aux_pm": MORDENT_AUX_PM,
        "turn_each_pm": TURN_EACH_PM,
        "trill_rate_hz": TRILL_RATE_HZ,
    }
