# -*- coding: utf-8 -*-
"""MS（音乐模型）→ ScoreV02 投影。管理者已授权把 C2 的入口迁到新模型。本模块先做**独立实现**。

已知边界（必须随结果一起报告，不得静默）：
  1. **释放语义简化**：`release_us=None`（sustaining）在 S02 里必须给时长 →
     取"到本段结束"，并记 loss
  2. **声部是推出来的**：S02 要求同一 voice 内不得时间重叠→
     用区间着色分配 voice，并记 loss（"voice 由投影推导"）
  3. **连音/tuplet/奏法**：新模型不含这些记号 → 无从投影
  4. 时间用**冻结的 time_base** 换算成整数网格；不给 time_base 直接拒绝
  5. **演奏层**（动作/曲线/发声段）现已投影：`actions` / `curves` / `segments`
"""
from __future__ import annotations

import ms_events as ev
import ms_semantics as ms
from model_v02 import (ActionMark, CurveLane, NoteEvent, PedalMark, PitchSpell,
                       ScoreV02, VoiceSegmentV02)


def _grid(us: int, tb_us: int, guq: int) -> int:
    return int(round(us * guq / tb_us))


def _staff_of(semitone: int) -> str:
    return "treble" if semitone >= 60 else "bass"


def _pick_voice(occupancy: list, onset: int) -> tuple[int, bool]:
    """区间着色：同 onset 的音属**和弦**，可共享声部（Q6 修正）。

    occupancy[i] = (last_onset, end)；返回 (声部号, 是否新建)。
    """
    for i, (last_onset, _end) in enumerate(occupancy):
        if last_onset == onset:
            return i, False
    for i, (_last_onset, end) in enumerate(occupancy):
        if onset >= end:
            return i, False
    occupancy.append((-1, 0))
    return len(occupancy) - 1, True


def to_s02(doc: "ev.MSDocument", *, time_base_us: int, grid_units_per_quarter: int = 480,
           key_fifths: int = 0, time_beats: int = 4, time_beat_type: int = 4,
           title: str = "") -> tuple:
    """返回 `(ScoreV02, losses)`。losses 是逐条可核的损失记录。"""
    if time_base_us <= 0:
        raise ValueError("必须给出正的 time_base_us（微秒/四分音符）——不猜时间基准")

    end_us = 0
    for e in doc.events:
        end_us = max(end_us, e.release_us if e.release_us is not None else e.onset_us)

    losses = []
    score = ScoreV02(title=title, grid_units_per_quarter=grid_units_per_quarter,
                     key_fifths=key_fifths, time_beats=time_beats, time_beat_type=time_beat_type)
    # 乐器表随 S02 走（前端/权重需要知道"谁在响"）
    score.constraint_mode = getattr(doc, "constraint_mode", "single_piano")
    score.instruments = [
        {"id": i.id, "type": i.type, "subtype": i.subtype, "section": i.section}
        for i in doc.instruments
    ]

    # 每个事件之后、同一乐器的下一个音头（未释放音按它截断）
    _sorted_ev = sorted(doc.events, key=lambda x: (x.onset_us, x.pitch.semitone))
    _next_on, _seen = {}, {}
    for e in reversed(_sorted_ev):
        _next_on[e.id] = _seen.get(e.instrument_id)
        _seen[e.instrument_id] = e.onset_us

    # ── 按谱表分组做 voice 分配 ──
    occupancy = {"treble": [], "bass": []}
    voice_names = {"treble": "RH", "bass": "LH"}
    used: dict = {}          # (staff, semitone, onset_grid) → 已占用，防量化碰撞
    for e in sorted(doc.events, key=lambda x: (x.onset_us, x.pitch.semitone)):
        staff = _staff_of(e.pitch.semitone)
        onset = _grid(e.onset_us, time_base_us, grid_units_per_quarter)
        # 量化后若与他音同键同格：**结构上合法**（两个事件），不在这里挪动。
        # 是否"弹不出来"由 ms_events.check_realization() 在演奏收束时判定。
        if e.release_us is None:
            # 未释放：取同乐器下一个音头作上界（没有则 1 拍），并记 loss
            nxt = _next_on.get(e.id)
            tail_us = (nxt if (nxt is not None and nxt > e.onset_us)
                       else e.onset_us + time_base_us)
            dur = _grid(tail_us, time_base_us, grid_units_per_quarter) - onset
            losses.append({"item": f"sustaining_tail:{e.id}",
                           "reason": "sustained 音无 release，按同乐器下一音头/1 拍截断"})
        else:
            dur = _grid(e.release_us, time_base_us, grid_units_per_quarter) - onset
        if dur <= 0:
            if e.is_grace:
                dur = 0
            else:
                losses.append({"item": f"zero_duration:{e.id}",
                               "reason": "换算后时值为 0（量化所致）——按最小 1 网格保留"})
                dur = 1
        vi, created = _pick_voice(occupancy[staff], onset)
        _last_on, last_end = occupancy[staff][vi]
        occupancy[staff][vi] = (onset, max(last_end, onset + dur))
        voice = f"{voice_names[staff]}{vi + 1}" if vi else voice_names[staff]
        if created and vi > 0:
            losses.append({"item": f"voice_created:{e.id}",
                           "reason": f"与同谱表其他事件时间重叠，投影时分配为 {voice}（S02 单声部不得重叠）"})

        score.notes.append(NoteEvent(
            id=e.id, onset=onset, duration=dur, voice=voice, staff=staff,
            measure=onset // (grid_units_per_quarter * max(1, time_beats)),
            pitch=PitchSpell(e.pitch.step, e.pitch.alter, e.pitch.octave),
            is_grace=e.is_grace,
            # s02-1.1 三槽：力度（None=未提供）、释放三态
            dynamics_permille=(e.dynamics.permille
                               if e.dynamics.state == ms.VALUE else None),
            release_state=(e.release_state
                           if e.release_state in ("given", "sustaining", "NOT_PROVIDED")
                           else "given"),
            instrument_id=e.instrument_id,
        ))
        # 力度不再记 loss：有槽可放；「未提供」本身由 None 表达

    # ── 踏板：段 → start/stop 记号 ──
    for pi, p in enumerate(doc.pedals):
        onset = _grid(p.start_us, time_base_us, grid_units_per_quarter)
        mid = f"ped{pi}_{p.kind}_start"
        scope = None
        if p.kind == "sostenuto":
            # sost-hold-v1：踩下瞬间仍在发声的音（按 id 映射，避免同 onset 排序错配）
            ev_by_id = {e.id: e for e in doc.events}
            scope = [n.id for n in score.notes
                     if (e := ev_by_id.get(n.id)) is not None
                     and e.onset_us <= p.start_us
                     and (e.release_us is None or e.release_us > p.start_us)]
        score.pedal_marks.append(PedalMark(
            id=mid, pedal_type=p.kind, action_notated="start", onset=onset,
            measure=onset // (grid_units_per_quarter * max(1, time_beats)),
            target_scope=scope, source="composed",
            depth_permille=p.depth_permille))
        if p.end_us is not None:
            score.pedal_marks.append(PedalMark(
                id=f"ped{pi}_{p.kind}_stop", pedal_type=p.kind, action_notated="stop",
                onset=_grid(p.end_us, time_base_us, grid_units_per_quarter),
                measure=0, source="composed",
                depth_permille=p.depth_permille))
        # 深度已有槽（s02-1.1），不再记 loss

    # ── 演奏动作（MS turns → S02 actions）──
    for ti, t in enumerate(sorted(getattr(doc, "turns", []), key=lambda x: (x.event_id, x.kind))):
        score.actions.append(ActionMark(id=f"A{ti + 1:08d}", kind=t.kind,
                                        target_id=t.event_id, strength=t.strength))

    # ── 连续参数（MS curves → S02 curves）──
    for c in getattr(doc, "curves", []):
        score.curves.append(CurveLane(instrument_id=c.instrument_id, param=c.param,
                                      time_us=c.time_us, value=c.value, ramp=c.ramp))

    # ── 人声发声段（MS vocal 行 → S02 segments）──
    for s in getattr(doc, "segments", []):
        score.segments.append(VoiceSegmentV02(
            event_id=s.event_id, index=s.index, kind=s.kind, text=s.text,
            binding_id=s.binding_id or s.structure_id, tone=s.tone, turn=s.turn,
            lang=getattr(s, "lang", None),
            onset_us=int(getattr(s, "onset_us", 0) or 0),
            end_us=int(getattr(s, "release_us", 0) or 0)))

    # 注：MS 本身不含 tuplet/tie/奏法记号——那是**模型边界**（见 已知边界.md），
    # 不是本次转换的损失。若记在这里，会把「MS 没有的东西」算成「S02 转换丢了」，属归因错误。

    errs = score.validate()
    if errs:
        raise ValueError("投影结果未通过 ScoreV02 校验：" + "；".join(errs))

    return score, losses
