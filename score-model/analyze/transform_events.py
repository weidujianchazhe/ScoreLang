# -*- coding: utf-8 -*-
"""C2 新入口：`MSDocument → ScoreV02`（迁移 M-1，2026-10-19）。

管理者已授权把 C2 入口迁到新事件模型。本模块提供**新入口**，
`transform_core.map_fields_ms_to_s02` 保持原样（旧路径，待 M-4 退役）。

与旧入口的区别：
  - 输入是 `MSDocument`（事件模型），不是 `ScoreFields`（字段表）
  - 时间由**冻结的 `time_base_us`** 换算成网格（不猜）
  - 不逐字段生成 `MappingRecord`；改为**逐损失**记录（`ms_to_s02` 的 losses）
  - 前置检查保留：方向必须 MS→S02；`time_base_us` 必填

返回的仍是 `TransformEvidence`，字段含义不变：
  - `records`：每个损失一条 `MappingRecord`（result=UNRESOLVED / LOSSY）
  - `losses`：原始损失清单
  - `target_obj`：投影得到的 `ScoreV02`
  - `assembly_complete`：无损失且投影成功才为 True
"""
from __future__ import annotations

import ms_events as ev
import ms_to_s02 as conv
import ms_to_s02  # noqa: F401  （保持可读的模块别名）
from transform_types import (
    DIRECTION_MS_TO_S02, LOSS, NO_MECHANISM, SCOPE_IN, TV_FAILED, TV_NOT_RUN, TV_VERIFIED,
    DirectionDecl, MappingRecord, ScopeVersion, TransformEvidence,
)


def check_events_preconditions(doc: "ev.MSDocument", decl: DirectionDecl,
                               scope: ScopeVersion, time_base_us: int | None) -> tuple:
    """新入口的前置检查：方向 / 作用域方向 / 时间基准。"""
    problems = []
    if decl.direction != DIRECTION_MS_TO_S02:
        problems.append(f"D-4 方向 {decl.direction} 不受本入口支持（仅 {DIRECTION_MS_TO_S02}）")
    if scope.direction != DIRECTION_MS_TO_S02:
        problems.append("D-4 ScopeVersion.direction 与入口方向不一致")
    if not scope.includes:
        problems.append("D-5 范围为空（includes 为空）")
    if not time_base_us or time_base_us <= 0:
        problems.append("D-6 未给出 time_base_us——微秒无法换算为网格（不得猜）")
    errs = ev.validate(doc)
    if errs:
        problems.append("D-7 源文档不合法：" + "；".join(errs))
    return (not problems), problems


def map_events_ms_to_s02(doc: "ev.MSDocument", decl: DirectionDecl, scope: ScopeVersion,
                         *, time_base_us: int | None = None,
                         grid_units_per_quarter: int = 480,
                         key_fifths: int = 0, time_beats: int = 4,
                         time_beat_type: int = 4) -> TransformEvidence:
    ok, detail = check_events_preconditions(doc, decl, scope, time_base_us)
    evidence = TransformEvidence(
        decl=decl, scope=scope,
        preconditions_ok=ok, preconditions_detail=list(detail),
        diagnostic_only=not ok,
        evidence_class="normal" if ok else "diagnostic",
        usable_as_delivery=False,
    )
    if not ok:
        evidence.target_validation_status = TV_NOT_RUN
        return evidence

    try:
        score, losses = conv.to_s02(
            doc, time_base_us=time_base_us, grid_units_per_quarter=grid_units_per_quarter,
            key_fifths=key_fifths, time_beats=time_beats, time_beat_type=time_beat_type)
    except ValueError as e:
        evidence.target_validation_status = TV_FAILED
        evidence.target_validation_errors = [str(e)]
        evidence.losses.append({"item": "projection", "reason": str(e)})
        return evidence

    evidence.target_obj = score
    errs = score.validate()
    evidence.target_validation_errors = list(errs)
    evidence.target_validation_status = TV_VERIFIED if not errs else TV_FAILED

    for loss in losses:
        record = MappingRecord(
            source_item=loss["item"], src="F", src_state="",
            result=LOSS, verification=NO_MECHANISM,
            scope_status=SCOPE_IN,
            basis="MS→S02 投影", basis_valid=True,
            reason=loss["reason"], detail=loss)
        evidence.records.append(record)
        evidence.losses.append(loss)

    # `assembly_complete` 只看"装配是否做完"（目标产出且通过校验），
    # **不**把损失算进来——损失由 `losses` 驱动 C3 的 J1=LOSSY，二者是不同维度。
    evidence.assembly_complete = (evidence.target_obj is not None) and (not errs)
    # `usable_as_delivery` 是**前置门禁**（前置通过且非诊断），不是"允许交付"：
    # 旧入口同样是 `ok and not diagnostic_only`。是否交付由 C3 的 J2 判。
    evidence.usable_as_delivery = ok and not evidence.diagnostic_only
    return evidence
