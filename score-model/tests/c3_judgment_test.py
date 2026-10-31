# -*- coding: utf-8 -*-
"""C3 判定层测试：正向 + 负向（须能打穿不变量）。运行：python c3_judgment_test.py

SM0049 强制验收：三态真实、J2 成因分列、四层不合并、未决有阻断、零映射、负测真失败。
"""

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
import sys
from pathlib import Path

from dataclasses import dataclass, field as dc_field
from typing import Any

import c3_judgment as cj

FAILS = []


def check(name, cond, note=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" —— {note}" if note else ""))
    if not cond:
        FAILS.append(name)


# ── 最小证据包替身（C3 只消费约定字段）──

@dataclass
class Rec:
    source_item: str
    src: str = "F"
    src_state: str = "VALUE"
    result: str = "retained"
    verification: str = "verified"
    scope_status: str = "in_scope"
    policy: str = "HARD_NO_LOSS"
    reason: str = ""
    target_evidence: Any = None
    omission_conditions: Any = None


@dataclass
class Ev:
    preconditions_ok: bool = True
    diagnostic_only: bool = False
    usable_as_delivery: bool = True
    assembly_complete: bool = True
    target_validation_status: str = "verified"
    target_validation_errors: list = dc_field(default_factory=list)
    records: list = dc_field(default_factory=list)
    unresolved: list = dc_field(default_factory=list)
    losses: list = dc_field(default_factory=list)
    omission_candidates: list = dc_field(default_factory=list)
    out_of_scope: list = dc_field(default_factory=list)


def base_ok():
    return Ev(records=[
        Rec("notated_onset"), Rec("notated_duration"),
        Rec("pitch_spelling"), Rec("pitch_semitone", result="retained"),
    ])


def main():
    # ══ 正向：干净证据 → 完整等价+交付 ══
    r = cj.judge(base_ok())
    check("P-1 干净证据→FULL+DELIVER",
          r.J1 == cj.J1_FULL and r.J2 == cj.J2_DELIVER,
          f"{r.J1}/{r.J2}")
    check("P-2 四层评估齐全",
          {l.layer for l in r.layers} >= {cj.L_A, cj.L_B, cj.L_C, cj.L_D})

    # ══ 1. G1 已证禁止损失 → 不得完整等价 ══
    ev = base_ok()
    ev.records.append(Rec("tuplet_ratio", result="loss", policy="HARD_NO_LOSS",
                          reason="已证实未保留"))
    ev.losses.append({"item": "tuplet_ratio"})
    r = cj.judge(ev)
    check("N-1 G1 已证禁止损失→FAILED（禁 FULL）",
          r.J1 == cj.J1_FAILED and r.J1 != cj.J1_FULL
          and r.J2 == cj.J2_REJECT and r.j2_cause == cj.CAUSE_FAILURE,
          f"{r.J1}/{r.J2}/{r.j2_cause}")
    check("N-1b hard_violations 非空",
          len(r.hard_violations) >= 1, str(r.hard_violations[:1]))

    # ══ 2. G1 仅能力缺口（未决）→ UNDETERMINED，非 FAILED 非通过 ══
    ev = base_ok()
    ev.records.append(Rec("tuplet_ratio", result="unresolved",
                          policy="HARD_NO_LOSS",
                          reason="装配未实现（能力缺口）"))
    ev.unresolved.append({"item": "tuplet_ratio", "reason": "装配未实现"})
    r = cj.judge(ev)
    check("N-2 G1 仅缺口→UNDETERMINED（非 FAILED 非 FULL）",
          r.J1 == cj.J1_UNDETERMINED
          and r.J1 != cj.J1_FAILED and r.J1 != cj.J1_FULL,
          f"{r.J1}")
    check("N-2b J2=REJECT 且成因=undetermined（非 failure）",
          r.J2 == cj.J2_REJECT and r.j2_cause == cj.CAUSE_UNDETERMINED,
          r.j2_cause)

    # ══ 3. 未决项不得被静默消除（不变量 C）——独立构造 ══
    ev3 = base_ok()
    ev3.records.append(Rec("tuplet_ratio", result="unresolved",
                           policy="HARD_NO_LOSS", reason="装配未实现（能力缺口）"))
    ev3.unresolved.append({"item": "tuplet_ratio", "reason": "装配未实现"})
    r3a = cj.judge(ev3)
    check("N-3 未决项在结果中可追溯（独立输入）",
          any(u.item == "tuplet_ratio" for u in r3a.undetermined_items),
          str([u.item for u in r3a.undetermined_items]))
    # 尝试从结果中删掉未决再宣称 FULL——判定层每次必须重算，不得持久化删除
    r3b = cj.judge(ev3)
    check("N-3b 重判未决仍在（删不掉）",
          any(u.item == "tuplet_ratio" for u in r3b.undetermined_items)
          and r3b.J1 == cj.J1_UNDETERMINED,
          f"{r3b.J1}")

    # ══ 4. 未决阻断范围正确：范围外未决不污染范围结论 ══
    ev = base_ok()
    ev.records.append(Rec("tempo_curve", result="out_of_scope", policy="LOSSY_OK",
                          scope_status="out_of_scope", reason="范围外"))
    r = cj.judge(ev)
    check("N-4 范围外项不阻断 FULL（不全局污染）",
          r.J1 == cj.J1_FULL, f"{r.J1}")
    # 范围外 unresolved 也不阻断
    ev = base_ok()
    ev.records.append(Rec("micro_offset", result="unresolved", policy="LOSSY_OK",
                          scope_status="out_of_scope", reason="范围外未决"))
    r = cj.judge(ev)
    check("N-4b 范围外未决不阻断 FULL",
          r.J1 == cj.J1_FULL, f"{r.J1}")
    # 范围未确定必须阻断
    ev = base_ok()
    ev.records.append(Rec("tempo_notated", result="unresolved", policy="",
                          scope_status="unknown", reason="范围未确定"))
    r = cj.judge(ev)
    check("N-4c 范围未确定→UNDETERMINED（禁当范围外）",
          r.J1 == cj.J1_UNDETERMINED, r.J1)

    # ══ 5. J1 未决 → J2 不得接受为已证明等价（独立构造）══
    ev5 = base_ok()
    ev5.records.append(Rec("tuplet_ratio", result="unresolved",
                           policy="HARD_NO_LOSS", reason="缺口"))
    r5 = cj.judge(ev5)
    check("N-5 UNDETERMINED→J2≠DELIVER（独立输入）",
          r5.J1 == cj.J1_UNDETERMINED
          and r5.J2 != cj.J2_DELIVER and r5.J2 == cj.J2_REJECT
          and r5.j2_cause == cj.CAUSE_UNDETERMINED,
          f"{r5.J1}/{r5.J2}/{r5.j2_cause}")

    # ══ 6. 前层通过、后层失败 → 不得跳过后层 ══
    ev = base_ok()
    ev.target_validation_status = "verified"   # L-a 过
    ev.records.append(Rec("x", result="loss", policy="HARD_NO_LOSS",
                          reason="映射层失败"))
    r = cj.judge(ev)
    la = next(l for l in r.layers if l.layer == cj.L_A)
    ld = next(l for l in r.layers if l.layer == cj.L_D)
    check("N-6 L-a 过但 L-d 失败（不跳层）",
          la.status == cj.ST_PASS and ld.status == cj.ST_FAIL
          and r.J1 == cj.J1_FAILED,
          f"L-a={la.status} L-d={ld.status} J1={r.J1}")

    # ══ 7. 缺必要输入证据 → 不得默认成功 ══
    ev = Ev(usable_as_delivery=False, preconditions_ok=False, diagnostic_only=True)
    r = cj.judge(ev)
    check("N-7 前置失败/诊断→FAILED+REJECT（非默认成功）",
          r.J1 == cj.J1_FAILED and r.J2 == cj.J2_REJECT
          and r.j2_cause == cj.CAUSE_PRECONDITION,
          f"{r.J1}/{r.J2}/{r.j2_cause}")
    # J3 未确认
    r = cj.judge(base_ok(), exec_status=cj.EXEC_UNCONFIRMED)
    check("N-7b J3=未确认→FAILED+REJECT",
          r.J1 == cj.J1_FAILED and r.J2 == cj.J2_REJECT,
          f"{r.J1}/{r.J2}")

    # ══ 8. 反证 + 未决并存 → 失败优先（不变量 E）══
    ev = base_ok()
    ev.records.append(Rec("tuplet_ratio", result="loss", policy="HARD_NO_LOSS",
                          reason="已证损失"))
    ev.records.append(Rec("simultaneous_set", result="unresolved", policy="OMITTABLE_DERIVED",
                          reason="候选条件不足"))
    r = cj.judge(ev)
    check("N-8 反证+未决→FAILED 优先且未决保留",
          r.J1 == cj.J1_FAILED
          and any(u.item == "simultaneous_set" for u in r.undetermined_items)
          and len(r.hard_violations) >= 1,
          f"{r.J1} undets={[u.item for u in r.undetermined_items]}")

    # ══ 9. 三态不得互冒：UNDETERMINED ≠ FAILED ≠ FULL ══
    ev = base_ok()
    ev.records.append(Rec("tuplet_ratio", result="unresolved", policy="HARD_NO_LOSS",
                          reason="缺口"))
    r_und = cj.judge(ev)
    ev2 = base_ok()
    ev2.records.append(Rec("tuplet_ratio", result="loss", policy="HARD_NO_LOSS",
                           reason="已证损失"))
    r_fail = cj.judge(ev2)
    r_full = cj.judge(base_ok())
    check("N-9 三态可区分",
          r_und.J1 == cj.J1_UNDETERMINED
          and r_fail.J1 == cj.J1_FAILED
          and r_full.J1 == cj.J1_FULL
          and len({r_und.J1, r_fail.J1, r_full.J1}) == 3,
          f"{r_und.J1}/{r_fail.J1}/{r_full.J1}")

    # ══ 10. 零映射：判定层无映射产物 ══
    src = open(ROOT / "analyze/c3_judgment.py", encoding="utf-8").read()
    check("N-10 判定层不含映射执行（零映射）",
          "map_fields" not in src and "_FIELD_MAP_SPEC" not in src
          and "_assemble_s02" not in src,
          "无 C2 映射符号")

    # ══ 11. 合法省略 ≠ 损失 ══
    ev = base_ok()
    ev.records.append(Rec("sustained_spans", result="omission_candidate",
                          policy="OMITTABLE_DERIVED",
                          omission_conditions={"declaration_valid": True,
                                               "deps": ["notated_onset"],
                                               "rule_version": "susp-v1"}))
    r = cj.judge(ev)
    check("N-11 合法省略候选→不计入损失且可 FULL",
          r.J1 == cj.J1_FULL and len(r.losses) == 0
          and any(o["item"] == "sustained_spans" for o in r.omitted_derived),
          f"{r.J1} losses={r.losses}")

    # ══ 12. 有损+政策允许 → LOSSY+DELIVER 附清单 ══
    ev = base_ok()
    ev.records.append(Rec("tempo_curve", result="loss", policy="LOSSY_OK",
                          reason="范围外损失类"))
    r = cj.judge(ev)
    check("N-12 有损可交付→LOSSY+DELIVER+清单",
          r.J1 == cj.J1_LOSSY and r.J2 == cj.J2_DELIVER
          and len(r.losses) >= 1,
          f"{r.J1}/{r.J2}")

    print("—— 结果 ——")
    if FAILS:
        print(f"FAIL {len(FAILS)}: {FAILS}")
        sys.exit(1)
    print("C3 判定测试全过（正向+负向打穿不变量）")


if __name__ == "__main__":
    main()
