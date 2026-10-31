# -*- coding: utf-8 -*-
"""转换层的数据类型与常量（2026-10-19 抽出）。

从 `transform_core.py` 抽出：旧字段表入口已退役，但这些**类型本身**仍被
新入口 `transform_events.py` 与 C3 判定使用，所以保留并独立成模块。

不含任何映射逻辑——映射在新入口里，用事件模型。
"""
from __future__ import annotations

import dataclasses as dc
from dataclasses import dataclass, field

DIRECTION_MS_TO_S02 = "MS→S02"
DIRECTION_S02_TO_MS = "S02→MS"

# 粗粒度来源（F=原始记谱事实 / I=演奏解释 / D=派生）
SRC_F, SRC_I, SRC_D = "F", "I", "D"

RETAINED = "retained"
LOSS = "loss"
OMISSION_CANDIDATE = "omission_candidate"
UNRESOLVED = "unresolved"
OUT_OF_SCOPE = "out_of_scope"

SCOPE_IN = "in_scope"
SCOPE_OUT = "out_of_scope"
SCOPE_UNKNOWN = "unknown"

VERIFIED = "verified"
UNVERIFIED = "unverified"
NO_MECHANISM = "no_mechanism"

TV_VERIFIED = "verified"
TV_FAILED = "failed"
TV_NOT_RUN = "not_run"


@dataclass
class DirectionDecl:
    direction: str
    input_model: str
    output_model: str
    scope_version: str
    notes: str = ""


@dataclass
class ScopeItem:
    item: str
    semantic_id: str
    keep_policy: str
    notes: str = ""


@dataclass(frozen=True)
class ScopeVersion:
    version: str
    direction: str
    includes: tuple
    excludes: tuple = ()
    normalization_rules: tuple = ()
    change_log: tuple = ()

    def policy_of(self, item: str) -> str:
        for it in self.includes:
            if isinstance(it, ScopeItem) and it.item == item:
                return it.keep_policy
        return ""


@dataclass
class MappingRecord:
    """一条映射记录（C3 消费）。"""
    source_item: str
    src: str
    src_state: str
    result: str
    verification: str
    scope_status: str = SCOPE_UNKNOWN
    target: str = ""
    basis: str = ""
    basis_refs: tuple = ()
    basis_integrity: bool = False
    rule_correct: bool = False
    basis_valid: bool = False
    policy: str = ""
    reason: str = ""
    target_evidence: object = None
    omission_conditions: object = None
    detail: object = None


@dataclass
class TransformEvidence:
    decl: DirectionDecl
    scope: ScopeVersion
    preconditions_ok: bool
    preconditions_detail: list
    diagnostic_only: bool = False
    assembly_complete: bool = True
    evidence_class: str = "normal"
    usable_as_delivery: bool = False
    records: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    losses: list = field(default_factory=list)
    omission_candidates: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    target_obj: object = None
    target_validation_status: str = TV_NOT_RUN
    target_validation_errors: list = field(default_factory=list)
