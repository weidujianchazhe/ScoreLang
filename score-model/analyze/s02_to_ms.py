# -*- coding: utf-8 -*-
"""ScoreV02 → MS（事件模型）反向转换（M-6.5 · R6 往返所需）。

只覆盖 S02 真有承载的部分（`s02-1.1`）：
  - 音符：网格 → 微秒（需 `time_base_us`，不猜）；拼写 → Pitch；力度 → Dynamics
  - 释放：`release_state` 三态回填（sustaining → `release_us=None`）
  - 踏板：start/stop 记号 → 段（深度回填）

**不转换（记入 gaps，不伪造）**：
  - tie / tuplet / 奏法：S02 有对象但 MS 不含，反向时无从对应
  - `words`：文本袋，无语义映射
"""
from __future__ import annotations

import ms_events as ev
import ms_semantics as ms
from model_v02 import ScoreV02


def _us(grid: int, tb_us: int, guq: int) -> int:
    return int(round(grid * tb_us / guq))


def from_s02(score: "ScoreV02", *, time_base_us: int, guq: int | None = None) -> tuple:
    if time_base_us <= 0:
        raise ValueError("必须给出正的 time_base_us（不猜时间基准）")
    guq = guq or score.grid_units_per_quarter
    gaps: list = []
    events: list = []
    for n in score.notes:
        on = _us(n.onset, time_base_us, guq)
        if n.release_state == "sustaining":
            rel = None
        else:
            rel = _us(n.onset + n.duration, time_base_us, guq)
            if rel <= on:
                rel = on + 1
        p = n.pitch
        events.append(ev.Event(
            id=n.id, instrument_id=getattr(n, "instrument_id", 1), onset_us=on,
            pitch=ev.Pitch(p.step, p.alter, p.octave, p.semitone),
            release_us=rel,
            release_state=(n.release_state if n.release_state in
                           ("given", "sustaining", "NOT_PROVIDED") else "given"),
            dynamics=(ev.Dynamics(ms.VALUE, n.dynamics_permille, "relative_permille", "s02", None)
                      if getattr(n, "dynamics_permille", None) is not None
                      else ev.Dynamics(ms.NOT_PROVIDED)),
            is_grace=n.is_grace,
        ))

    pedals: list = []
    open_ped: dict = {}
    for m in sorted(score.pedal_marks, key=lambda x: x.onset):
        if m.action_notated == "start":
            open_ped[(m.pedal_type, getattr(m, "target_scope", None) is not None)] = m
        elif m.action_notated == "stop":
            for key in list(open_ped):
                if key[0] == m.pedal_type:
                    st = open_ped.pop(key)
                    pedals.append(ev.PedalSegment(
                        instrument_id=1, kind=st.pedal_type,
                        start_us=_us(st.onset, time_base_us, guq),
                        end_us=_us(m.onset, time_base_us, guq),
                        depth_permille=(st.depth_permille if st.depth_permille is not None else 1000)))
                    break
    for (kind, _has_scope), st in open_ped.items():
        pedals.append(ev.PedalSegment(
            instrument_id=1, kind=kind,
            start_us=_us(st.onset, time_base_us, guq), end_us=None,
            depth_permille=(st.depth_permille if st.depth_permille is not None else 1000)))
        gaps.append({"code": "pedal_unclosed", "severity": "warn",
                     "detail": f"{kind} 踏板只有 start 没有 stop，反向为未闭合段"})

    if score.tie_groups:
        gaps.append({"code": "tie_not_in_ms", "severity": "info",
                     "detail": f"{len(score.tie_groups)} 个 tie 组在 MS 中无对应表示（模型边界）"})
    if score.tuplets:
        gaps.append({"code": "tuplet_not_in_ms", "severity": "info",
                     "detail": f"{len(score.tuplets)} 个 tuplet 在 MS 中无对应表示（模型边界）"})

    n_inst = max([getattr(n, "instrument_id", 1) for n in score.notes] + [1])
    doc = ev.MSDocument(piano_count=n_inst,
                        constraint_mode="single_piano" if n_inst == 1 else "n_pianos",
                        events=events, pedals=pedals, gaps=gaps,
                        instruments=[ev.Instrument(i.get("id", f"P{k+1}"),
                                                   i.get("type", "acoustic_grand_piano"),
                                                   i.get("subtype"), i.get("section"))
                                     for k, i in enumerate(score.instruments)])
    if getattr(score, "lyrics", None):
        gaps.append({"code": "s02_lyrics_dropped", "severity": "info",
                     "detail": f"S02 里的 {len(score.lyrics)} 条歌词没有对端结构（人声只在 MS 侧用 vocal 段）"})
    errs = ev.validate(doc)
    if errs:
        raise ValueError("反向转换结果未通过 MS 校验：" + "；".join(errs[:5]))
    return doc, gaps
