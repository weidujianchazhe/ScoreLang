# -*- coding: utf-8 -*-
"""数学结构化乐谱 · 语义核（第三步自验的最小可执行骨架）。

实现 数学乐谱规范.md §4–5 的语义机制——**不是完整乐谱模型**：
- 五态缺省语义：未提供 / 明确不存在 / 无法确定 / 当前不支持 / 可推导但未计算
- F/I/D 来源属性：粒度=字段值级；混合来源=带来源标记的独立记录
- 三分：值（含合法空结果）/ 状态（五态）/ 错误（计算失败走错误通道）
- 验证纪律：非法组合拒绝且**不静默纠正**；序列化无损；未定输入不参与计算、不编造
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field as dc_field

# ── 五态（缺省语义）；VALUE 不是缺省态，是"有值" ──
NOT_PROVIDED = "NOT_PROVIDED"          # 未提供
ABSENT = "ABSENT"                      # 明确不存在
UNDETERMINED = "UNDETERMINED"          # 无法确定
UNSUPPORTED = "UNSUPPORTED"            # 当前不支持
DERIVABLE_PENDING = "DERIVABLE_PENDING"  # 可推导但未计算
VALUE = "VALUE"                        # 有值（含合法空结果）

FIVE_STATES = (NOT_PROVIDED, ABSENT, UNDETERMINED, UNSUPPORTED, DERIVABLE_PENDING)
ALL_STATES = FIVE_STATES + (VALUE,)

SRC_F, SRC_I, SRC_D = "F", "I", "D"

# 字段×状态适用表（SPEC §5.2）：D 禁用 ABSENT 表示缺省（合法空结果=VALUE）
ALLOWED = {
    SRC_F: {VALUE, NOT_PROVIDED, ABSENT, UNDETERMINED, UNSUPPORTED},
    SRC_I: {VALUE, NOT_PROVIDED, ABSENT, UNDETERMINED, UNSUPPORTED},
    SRC_D: {VALUE, NOT_PROVIDED, UNDETERMINED, UNSUPPORTED, DERIVABLE_PENDING},
}

EVIDENCE_REQUIRED = {ABSENT, UNDETERMINED, UNSUPPORTED}
COMPUTE_FAILED = "COMPUTE_FAILED"      # 错误通道标记（不是状态）


@dataclass
class Field:
    name: str
    src: str                      # F | I | D
    state: str
    value: object = None          # 仅 state=VALUE 承载；0/[]/"" 是合法值，None=无载荷
    evidence: str = ""            # ABSENT/UNDETERMINED/UNSUPPORTED 必填
    rule_version: str = ""        # D 类 VALUE 必填（规则版本可识别）
    deps: tuple = ()              # D 类输入依赖标识


@dataclass
class ScoreSem:
    fields: dict = dc_field(default_factory=dict)   # name -> Field
    errors: list = dc_field(default_factory=list)   # 错误通道（计算失败等）

    def add(self, f: Field):
        self.fields[f.name] = f
        return self


def validate(score: ScoreSem) -> list:
    """语义校验：返回错误列表。**不修改输入**（禁静默纠正）。"""
    errs = []
    for name, f in score.fields.items():
        if f.src not in (SRC_F, SRC_I, SRC_D):
            errs.append(f"{name}: 非法来源属性 {f.src}")
            continue
        if f.state not in ALL_STATES:
            errs.append(f"{name}: 非法状态 {f.state}")
            continue
        if f.state not in ALLOWED[f.src]:
            errs.append(f"{name}: 来源 {f.src} 禁用状态 {f.state}（非法字段×状态组合，不纠正）")
        if f.state == VALUE:
            if f.value is None:
                errs.append(f"{name}: VALUE 必须带载荷（缺失≠真实值；禁止 None 冒充零值/空集）")
            if f.src == SRC_D and not f.rule_version:
                errs.append(f"{name}: D 类 VALUE 必须带规则版本 rule_version")
        else:
            if f.value is not None:
                errs.append(f"{name}: 状态 {f.state} 不得携带载荷（值与状态不得混）")
        if f.state in EVIDENCE_REQUIRED and not f.evidence:
            errs.append(f"{name}: 状态 {f.state} 须附依据/缘由（evidence）")
    return errs


def derive_d(name: str, inputs: dict, rule_version: str, fn):
    """D 类派生：未定输入不编造；计算失败入错误通道，不伪装为无法确定/输入不足。

    inputs: {依赖名: Field}
    返回 (Field, err|None)
    """
    deps = tuple(sorted(inputs))
    missing = [k for k, f in inputs.items() if f.state != VALUE]
    if missing:
        return (Field(name=name, src=SRC_D, state=UNDETERMINED,
                      evidence=f"缺少必要依赖：{missing}", rule_version=rule_version,
                      deps=deps), None)
    try:
        out = fn({k: f.value for k, f in inputs.items()})
    except Exception as e:  # noqa: BLE001 —— 失败必须可见
        err = {"kind": COMPUTE_FAILED, "field": name,
               "reason": f"{type(e).__name__}: {e}", "deps": deps}
        # 计算失败 ≠ 输入不足：状态保持「可推导未计算」，错误单独记录
        return (Field(name=name, src=SRC_D, state=DERIVABLE_PENDING,
                      evidence="计算失败（详见错误通道）", rule_version=rule_version,
                      deps=deps), err)
    if out is None:
        raise ValueError("派生函数返回 None=未定义；空结果请用空集合等显式值")
    return (Field(name=name, src=SRC_D, state=VALUE, value=out,
                  rule_version=rule_version, deps=deps), None)


def dumps(score: ScoreSem) -> str:
    return json.dumps({
        "fields": {n: {"name": f.name, "src": f.src, "state": f.state,
                       "value": f.value, "evidence": f.evidence,
                       "rule_version": f.rule_version, "deps": list(f.deps)}
                   for n, f in score.fields.items()},
        "errors": list(score.errors)},
        ensure_ascii=False)


def loads(text: str) -> ScoreSem:
    d = json.loads(text)
    sc = ScoreSem(errors=list(d.get("errors", [])))
    for n, fd in d["fields"].items():
        sc.fields[n] = Field(name=fd["name"], src=fd["src"], state=fd["state"],
                             value=fd["value"], evidence=fd["evidence"],
                             rule_version=fd["rule_version"], deps=tuple(fd["deps"]))
    return sc


def clone(score: ScoreSem) -> ScoreSem:
    return copy.deepcopy(score)


def same(a: ScoreSem, b: ScoreSem) -> bool:
    return dumps(a) == dumps(b)
