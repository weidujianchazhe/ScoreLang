# -*- coding: utf-8 -*-
"""C3 判定层（实现）· 依 C3_JUDGMENT_CONTRACT_DESIGN.md v2 / SM0048 裁定。

职责：消费 C2 证据包 + 冻结 ScopeVersion + KEEP_POLICY → J1/J2/未决/四层评估。
红线（SM0049 放行范围）：
  零映射——不重做字段映射、不复制转换规则、不补造缺失证据、不改契约。
  三态诚实——已证明满足 / 已证明不满足 / 证据不足，不得互相冒充。
  五不变量 A–E；四层 L-a/b/c/d 不跳层。
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

# ── 判定枚举（契约 §9.2 + 设计 v2 §2）──

J1_FULL = "FULL_EQUIVALENT"
J1_LOSSY = "LOSSY"
J1_FAILED = "FAILED"
J1_UNDETERMINED = "UNDETERMINED"

J2_DELIVER = "DELIVER"
J2_REJECT = "REJECT"

# J2 拒绝成因（设计 v2 §2.1：REJECT≠已证失败）
CAUSE_FAILURE = "failure"                 # 已证实失败
CAUSE_UNDETERMINED = "undetermined"       # 证据不足
CAUSE_POLICY = "policy"                   # 政策不允许交付（如可降级但未许可）
CAUSE_PRECONDITION = "precondition"       # 前置未满足

EXEC_COMPLETED = "completed"
EXEC_REJECTED = "rejected"
EXEC_ERROR = "error"
EXEC_UNCONFIRMED = "未确认"

# 四层
L_A = "L-a_target_validation"
L_B = "L-b_assembly_complete"
L_C = "L-c_mapping_correctness"
L_D = "L-d_overall_equivalence"

ST_PASS = "pass"
ST_FAIL = "fail"
ST_UNDET = "undetermined"
ST_NA = "not_applicable"

HARD_NO_LOSS = "HARD_NO_LOSS"
HARD_DEGRADEABLE = "HARD_DEGRADEABLE"
LOSSY_OK = "LOSSY_OK"
OMITTABLE_DERIVED = "OMITTABLE_DERIVED"


@dataclass
class UndeterminedItem:
    item: str
    reason: str
    blocks: tuple = ()          # ("J1:FULL_EQUIVALENT", "J2:DELIVER", ...)
    gap_ref: str = ""


@dataclass
class LayerAssessment:
    layer: str
    status: str                 # pass / fail / undetermined / not_applicable
    evidence: str = ""


@dataclass
class JudgmentResult:
    exec_status: str
    J1: str
    J2: str
    j2_cause: str
    policy_basis: list = dc_field(default_factory=list)
    losses: list = dc_field(default_factory=list)
    hard_violations: list = dc_field(default_factory=list)
    omitted_derived: list = dc_field(default_factory=list)
    undetermined_items: list = dc_field(default_factory=list)
    layers: list = dc_field(default_factory=list)

    def undetermined_blocked(self, tag: str) -> bool:
        return any(tag in u.blocks for u in self.undetermined_items)


# ── 零映射输入视图（只读证据包约定字段）──

def _iter_in_scope(records):
    for r in records or []:
        scope_status = getattr(r, "scope_status", "unknown")
        if scope_status == "in_scope":
            yield r


def judge(evidence: Any, exec_status: str = EXEC_COMPLETED) -> JudgmentResult:
    """判定入口：只消费证据包约定字段（设计 v2 §1/§8）。

    不重新执行映射；不从 L-a/b/c 推导 L-d。
    """
    basis: list = []
    losses: list = []
    hard_violations: list = []
    omitted: list = []
    undets: list = []
    layers: list = []

    usable = bool(getattr(evidence, "usable_as_delivery", False))
    diag = bool(getattr(evidence, "diagnostic_only", False))
    pre_ok = bool(getattr(evidence, "preconditions_ok", False))

    # ── 步 1/2：前提与 J3 ──
    if not pre_ok or diag or not usable:
        exec_status = EXEC_REJECTED if exec_status == EXEC_COMPLETED else exec_status
        basis.append(f"前提未满足/诊断产物：usable={usable} diag={diag} pre_ok={pre_ok}"
                     "——不进入交付判定")
        layers.append(LayerAssessment(L_A, ST_UNDET, "前提未满足，L-a 不计入交付证据"))
        layers.append(LayerAssessment(L_B, ST_UNDET, "前提未满足"))
        layers.append(LayerAssessment(L_C, ST_UNDET, "前提未满足"))
        layers.append(LayerAssessment(L_D, ST_FAIL, "前提未满足→J1=FAILED（J3=rejected）"))
        return JudgmentResult(
            exec_status=exec_status, J1=J1_FAILED, J2=J2_REJECT,
            j2_cause=CAUSE_PRECONDITION, policy_basis=basis,
            undetermined_items=[UndeterminedItem(
                item="preconditions", reason="前置未满足/诊断产物",
                blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"), gap_ref="C2")],
            layers=layers)

    if exec_status in (EXEC_REJECTED, EXEC_ERROR, EXEC_UNCONFIRMED):
        basis.append(f"J3={exec_status}→J1=FAILED，J2=REJECT（契约 §9.2）")
        layers.append(LayerAssessment(L_D, ST_FAIL, f"J3={exec_status}"))
        return JudgmentResult(
            exec_status=exec_status, J1=J1_FAILED, J2=J2_REJECT,
            j2_cause=CAUSE_FAILURE, policy_basis=basis, layers=layers)

    # ── L-a 目标验证（独立，不推导后层）──
    tv = getattr(evidence, "target_validation_status", "not_run")
    if tv == "verified":
        layers.append(LayerAssessment(L_A, ST_PASS, "target_validation_status=verified"))
    elif tv == "failed":
        layers.append(LayerAssessment(L_A, ST_FAIL,
                                      f"目标验证失败：{getattr(evidence, 'target_validation_errors', [])[:2]}"))
    else:
        layers.append(LayerAssessment(L_A, ST_UNDET, f"target_validation_status={tv}"))

    # ── L-b 装配完整（独立；A3 语义澄清）──
    if getattr(evidence, "assembly_complete", False):
        layers.append(LayerAssessment(L_B, ST_PASS, "assembly_complete=True"))
    else:
        # A3：布尔 False ≠ 已证装配失败。有具体失败记录才算已证；否则=证据不足
        prov_asm = [u for u in (getattr(evidence, "unresolved", []) or [])
                    if "event_assembly:" in str(u.get("item", "") if isinstance(u, dict)
                                                 else getattr(u, "item", ""))]
        if prov_asm:
            layers.append(LayerAssessment(
                L_B, ST_FAIL,
                f"已证装配失败：{[p.get('item') if isinstance(p, dict) else p.item for p in prov_asm][:3]}"))
            undets.append(UndeterminedItem(
                item="assembly_incomplete",
                reason=f"已证装配失败（{len(prov_asm)} 项记录）——阻断完整等价",
                blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"), gap_ref="L-b-proven"))
        else:
            layers.append(LayerAssessment(
                L_B, ST_UNDET,
                "assembly_complete=False 但无具体失败记录——"
                "证据只表示完整未确认（输入契约未区分已证失败/未确认）"))
            undets.append(UndeterminedItem(
                item="assembly_incomplete",
                reason="装配完整性未确认（输入契约缺口：布尔无法区分已证失败与未确认）"
                       "——证据不足，不得视为已证失败或已证完整",
                blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"), gap_ref="INPUT-CONTRACT-ASM"))

    # ── L-c 映射正确性（独立；A2：失败具体化 + 已证错误/无法验证分列）──
    recs = list(getattr(evidence, "records", []) or [])
    l_c_fail = False
    l_c_fail_detail = []
    for r in recs:
        result = getattr(r, "result", "")
        ver = getattr(r, "verification", "")
        policy = getattr(r, "policy", "") or ""
        name = getattr(r, "source_item", "?")
        reason = getattr(r, "reason", "")
        if result == "retained" and ver != "verified":
            l_c_fail = True
            # A2：区分已证映射错误 vs 无法验证
            proven_err = any(k in reason for k in
                             ("不一致", "失败", "错误", "mismatch", "不成立"))
            l_c_fail_detail.append({
                "item": name, "verification": ver, "reason": reason,
                "kind": "proven_error" if proven_err else "unverifiable"})
            undets.append(UndeterminedItem(
                item=f"map_verify:{name}",
                reason=(f"已证映射错误：{reason}" if proven_err
                        else f"映射正确性无法验证：{reason or ver}"),
                blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"),
                gap_ref="L-c-proven" if proven_err else "L-c-unverifiable"))
        # KEEP_POLICY 应用（步 3–4）
        if result == "loss" and policy == HARD_NO_LOSS:
            hard_violations.append({"item": name, "reason": reason, "policy": policy})
            basis.append(f"HARD_NO_LOSS 违规：{name}")
        elif result == "loss":
            losses.append({"item": name, "reason": reason, "policy": policy})
        elif result == "omission_candidate":
            conds = getattr(r, "omission_conditions", None) or {}
            if conds.get("declaration_valid"):
                omitted.append({"item": name, "deps": conds.get("deps"),
                                "rule_version": conds.get("rule_version")})
                basis.append(f"合法省略候选成立：{name}（终判已核登记条件）")
            else:
                undets.append(UndeterminedItem(
                    item=name,
                    reason="省略候选条件不足——不得计入合法省略",
                    blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"), gap_ref="OMIT"))
        elif result == "unresolved":
            sc = getattr(r, "scope_status", "unknown")
            if sc == "in_scope":
                undets.append(UndeterminedItem(
                    item=name, reason=reason or "未决",
                    blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"),
                    gap_ref=getattr(r, "src_state", "") or "UNRESOLVED"))
            elif sc == "unknown":
                undets.append(UndeterminedItem(
                    item=name,
                    reason="范围未确定——不得解释为范围外无义务",
                    blocks=("J1:FULL_EQUIVALENT", "J2:DELIVER"),
                    gap_ref="SCOPE-UNKNOWN"))
        elif result == "out_of_scope":
            basis.append(f"范围外：{name}（不计入范围内损失）")

    layers.append(LayerAssessment(
        L_C, ST_FAIL if l_c_fail else ST_PASS,
        (f"映射核验失败 {len(l_c_fail_detail)} 项：{l_c_fail_detail[:5]}"
         if l_c_fail_detail else "映射记录核验通过（零重映射）")))

    # 未决清单不静默消除（不变量 C）+ A1：同名合并取阻断并集，不得缩水
    # SM0055：input_unres 范围感知——范围×依赖四象限（c3_scope_rule）
    input_unres = getattr(evidence, "unresolved", []) or []
    by_name: dict = {}
    for u in undets:
        ent = by_name.setdefault(u.item, {
            "reasons": [u.reason], "blocks": set(u.blocks), "gaps": {u.gap_ref}})
        ent["blocks"] |= set(u.blocks)
        if u.reason not in ent["reasons"]:
            ent["reasons"].append(u.reason)
        ent["gaps"].add(u.gap_ref)
    rec_scope_by_name = {
        getattr(r, "source_item", None): getattr(r, "scope_status", None)
        for r in recs}
    for u in input_unres:
        if isinstance(u, dict):
            uname, ureason = u.get("item", ""), u.get("reason", "")
        else:
            uname, ureason = getattr(u, "item", ""), getattr(u, "reason", "")
        if not uname:
            continue
        rec_scope = rec_scope_by_name.get(uname)
        # 依赖证据：同名已有阻断（记录路径已认定影响结论）或原因含依赖提示
        has_dep = (uname in by_name and by_name[uname]["blocks"]) or any(
            k in ureason for k in ("影响", "依赖", "阻断"))
        block, why = input_unres_blocks(rec_scope, has_dep)
        ent = by_name.setdefault(uname, {
            "reasons": [], "blocks": set(), "gaps": set()})
        if block:
            ent["blocks"] |= {"J1:FULL_EQUIVALENT", "J2:DELIVER"}
        if ureason and ureason not in ent["reasons"]:
            ent["reasons"].append(ureason + f"（{why}）")
        ent["gaps"].add("INPUT-UNRESOLVED")
    undets = [UndeterminedItem(
        item=n,
        reason="；".join(e["reasons"]) or "未决",
        blocks=tuple(sorted(e["blocks"])),
        gap_ref="|".join(sorted(g for g in e["gaps"] if g)))
        for n, e in by_name.items()
        if e["blocks"] or e["reasons"]]

    # ── 步 7：J1（失败优先 > 未决 > 有损 > 完整等价）──
    # SM0055：仅「带阻断范围」的未决影响 J1；无阻断项仅作可追溯记录
    blocking_undets = [u for u in undets if u.blocks]
    if hard_violations:
        j1 = J1_FAILED
        basis.append("J1=FAILED：存在 HARD_NO_LOSS 明确违规（不变量 E 反证优先）")
    elif blocking_undets:
        j1 = J1_UNDETERMINED
        basis.append(f"J1=UNDETERMINED：{len(blocking_undets)} 项阻断性未决"
                     "（不变量 A/B/D）")
    elif losses:
        j1 = J1_LOSSY
        basis.append(f"J1=LOSSY：{len(losses)} 项范围内损失")
    elif any(l.status == ST_FAIL for l in layers if l.layer in (L_A, L_B, L_C)):
        # 前层失败但无硬违规：不宣称完整等价
        j1 = J1_UNDETERMINED
        basis.append("J1=UNDETERMINED：前层验证失败但无独立禁止损失证据（不变量 A）")
    else:
        j1 = J1_FULL
        basis.append("J1=FULL_EQUIVALENT：范围内必检通过且无损失/未决")

    layers.append(LayerAssessment(L_D, {
        J1_FULL: ST_PASS, J1_LOSSY: ST_PASS,
        J1_FAILED: ST_FAIL, J1_UNDETERMINED: ST_UNDET,
    }[j1], f"J1={j1}"))

    # ── 步 8：J2（独立；成因分列）──
    if j1 == J1_FAILED:
        j2, cause = J2_REJECT, CAUSE_FAILURE
    elif j1 == J1_UNDETERMINED:
        j2, cause = J2_REJECT, CAUSE_UNDETERMINED
    elif j1 == J1_LOSSY:
        # A4：政策须来自冻结 KEEP_POLICY；缺失/未知→不默认许可
        ALLOWED = {HARD_DEGRADEABLE, LOSSY_OK}
        pols = {getattr(r, "policy", "") for r in _iter_in_scope(recs)
                if getattr(r, "result", "") == "loss"}
        if pols and pols <= ALLOWED:
            j2, cause = J2_DELIVER, CAUSE_POLICY
            basis.append(f"J2=DELIVER：有损且政策许可 {pols}（附损失清单）")
        else:
            j2, cause = J2_REJECT, CAUSE_POLICY
            basis.append(f"J2=REJECT：损失政策 {pols or '{空}'} "
                         "非冻结许可政策（缺失/未知/冲突不得默认交付）")
    else:
        j2, cause = J2_DELIVER, ""
        basis.append("J2=DELIVER：完整等价")

    # 不变量 E：有反证时不得因未决降格——J1 已保证；此处再钉 J2 成因
    if hard_violations and j1 == J1_FAILED:
        cause = CAUSE_FAILURE

    return JudgmentResult(
        exec_status=exec_status, J1=j1, J2=j2, j2_cause=cause,
        policy_basis=basis, losses=losses, hard_violations=hard_violations,
        omitted_derived=omitted, undetermined_items=undets, layers=layers)

# ── 合并自 py（2026-10-22 整理） ────────────────

# -*- coding: utf-8 -*-
"""SM0055 局部规则（实现前冻结）：C3 未决项范围语义 × 依赖关系。

范围状态决定事项是否属于当前目标；依赖关系决定是否影响当前结论。
二者不混同；无默认语义（缺失/未知不视为范围外）。
"""

# 未决项处理规则（仅作用于 input_unres 进入阻断的路径）
RULE_TEXT = """
| 范围状态 | 依赖证据 | 处理 |
|---|---|---|
| 处理范围内 | 影响当前结论 | 按原契约阻断相应结论 |
| 范围外 | 不影响当前结论 | **不得**仅因未决状态阻断当前结论 |
| 范围外 | 有证据表明影响当前结论 | 仍须处理该依赖，不得直接忽略 |
| 缺失/未知/不可信 | — | **不得**默认视为范围外并解除阻断 |
| 合并 | — | 不得丢失其他项目的阻断范围、原因或依赖信息 |
"""

SCOPE_IN = "in_scope"
SCOPE_OUT = "out_of_scope"
SCOPE_UNKNOWN = "unknown"


def input_unres_blocks(rec_scope: str | None, has_dependency_evidence: bool) -> tuple:
    """返回 (是否阻断 FULL/DELIVER, 依据说明)。

    rec_scope：同名 records 的 scope_status；None=缺失（不可信→不解除阻断）。
    has_dependency_evidence：有证据表明影响当前结论（真实依赖）。
    """
    if rec_scope is None:
        return True, "范围状态缺失——不得默认范围外"
    if rec_scope == SCOPE_OUT:
        if has_dependency_evidence:
            return True, "范围外但有真实依赖证据——仍阻断"
        return False, "范围外且无依赖证据——不因未决状态阻断"
    # in_scope / unknown / 其他不可信值
    return True, f"范围={rec_scope}——按原契约阻断"
