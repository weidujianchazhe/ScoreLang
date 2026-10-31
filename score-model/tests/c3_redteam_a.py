# -*- coding: utf-8 -*-
"""C3 验收阻断项红队（C3-A1…A4）：先证明旧实现可被击穿。运行：python c3_redteam_a.py

修复前应见 FAIL；修复后同判据全 PASS。每测独立构造输入。
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


def clean_records():
    return [Rec("notated_onset"), Rec("notated_duration"),
            Rec("pitch_spelling"), Rec("pitch_semitone")]


def main():
    print("=== C3-A 红队：修复前应 FAIL ===")

    # ══ A1 同名未决合并不得缩小阻断范围 ══
    # 缩水场景：unknown 范围记录只块 FULL；输入同名未决要求 FULL+DELIVER
    ev1 = Ev(records=clean_records() + [
        Rec("tempo_notated", result="unresolved", policy="",
            scope_status="unknown", reason="范围未确定"),
    ])
    ev1.unresolved = [{"item": "tempo_notated",
                       "reason": "输入未决——应阻断 FULL+DELIVER"}]
    r1 = cj.judge(ev1)
    blocks1 = set()
    for u in r1.undetermined_items:
        if u.item == "tempo_notated":
            blocks1 |= set(u.blocks)
    check("A1-1 同名未决阻断范围=并集（unknown 记录+输入→须含 DELIVER）",
          "J1:FULL_EQUIVALENT" in blocks1 and "J2:DELIVER" in blocks1,
          f"blocks1={blocks1}")
    # 顺序无关：仅输入 vs 记录+输入，DELIVER 不得丢失
    ev2 = Ev(records=clean_records())
    ev2.unresolved = [{"item": "tempo_notated", "reason": "输入未决"}]
    r2 = cj.judge(ev2)
    blocks2 = set()
    for u in r2.undetermined_items:
        if u.item == "tempo_notated":
            blocks2 |= set(u.blocks)
    check("A1-2 仅输入未决亦阻断 FULL+DELIVER",
          {"J1:FULL_EQUIVALENT", "J2:DELIVER"} <= blocks2,
          f"blocks2={blocks2}")
    ev3 = Ev(records=clean_records() + [
        Rec("tempo_notated", result="unresolved", policy="HARD_NO_LOSS",
            reason="R"),
    ])
    ev3.unresolved = [{"item": "tempo_notated", "reason": "I"}]
    r3 = cj.judge(ev3)
    merged = set()
    for u in r3.undetermined_items:
        if u.item == "tempo_notated":
            merged |= set(u.blocks)
    check("A1-3 记录(in_scope)+输入同名→并集完整",
          {"J1:FULL_EQUIVALENT", "J2:DELIVER"} <= merged,
          f"merged={merged}")

    # ══ A2 L-c 映射验证失败须具体化，且不判完整等价 ══
    ev = Ev(records=clean_records() + [
        Rec("x_map", result="retained", verification="unverified",
            reason="写后核验失败——已证映射错误"),
    ])
    r = cj.judge(ev)
    check("A2-1 L-c 明确失败→不得 FULL",
          r.J1 != cj.J1_FULL, f"J1={r.J1}")
    lc = next((l for l in r.layers if l.layer == cj.L_C), None)
    detail_ok = lc and ("x_map" in lc.evidence or "x_map" in str(r.undetermined_items)
                        or "x_map" in str(r.policy_basis))
    check("A2-2 失败记录标识/原因可审计（非笼统摘要）",
          bool(detail_ok), f"evidence={getattr(lc, 'evidence', '')[:60]}")
    # 无法验证 vs 已证错误 须可区分
    ev_u = Ev(records=clean_records() + [
        Rec("y_map", result="retained", verification="unverified",
            reason="no_post_check_mechanism"),
    ])
    r_u = cj.judge(ev_u)
    ev_e = Ev(records=clean_records() + [
        Rec("z_map", result="retained", verification="unverified",
            reason="源值与目标值不一致——已证错误"),
    ])
    r_e = cj.judge(ev_e)
    check("A2-3 已证映射错误 vs 无法验证 可区分",
          r_e.J1 != r_u.J1 or
          str(r_e.layers) != str(r_u.layers) or
          str(r_e.undetermined_items) != str(r_u.undetermined_items)
          or any("不一致" in u.reason for u in r_e.undetermined_items)
          and any("no_post_check" in u.reason or "无法" in u.reason
                  or "核验" in u.reason for u in r_u.undetermined_items),
          f"J1e={r_e.J1} J1u={r_u.J1}")

    # ══ A3 assembly_complete=False 语义 ══
    # 3a：有具体装配失败证据（skipped/duplicate 在 unresolved）→ 可记已证 L-b 失败
    ev_prov = Ev(assembly_complete=False, records=clean_records())
    ev_prov.unresolved = [{"item": "event_assembly:skipped:n1",
                           "reason": "缺拼写跳过——已证实装配失败"}]
    r_p = cj.judge(ev_prov)
    check("A3-1 有具体装配失败证据→L-b 可为 fail（可解释）",
          any(l.layer == cj.L_B and l.status in (cj.ST_FAIL, cj.ST_UNDET)
              for l in r_p.layers),
          str([(l.layer, l.status) for l in r_p.layers if l.layer == cj.L_B]))
    # 3b：仅布尔 False、无细节→必须是「证据不足」而非「已证失败」
    ev_bool = Ev(assembly_complete=False, records=clean_records())
    r_b = cj.judge(ev_bool)
    lb = next((l for l in r_b.layers if l.layer == cj.L_B), None)
    check("A3-2 仅布尔 False→L-b=undetermined（非已证 fail）+缺口登记",
          r_b.J1 != cj.J1_FULL
          and lb is not None and lb.status == cj.ST_UNDET
          and any("输入契约" in u.reason or "尚未确认" in u.reason
                  or "证据不足" in u.reason or "无法区分" in u.reason
                  for u in r_b.undetermined_items),
          f"J1={r_b.J1} L-b={lb.status if lb else None} "
          f"undets={[u.reason[:40] for u in r_b.undetermined_items]}")

    # ══ A4 有损交付政策：缺/未知政策不得默认许可 ══
    ev = Ev(records=clean_records() + [
        Rec("loss1", result="loss", policy="", reason="政策缺失"),
    ])
    r = cj.judge(ev)
    check("A4-1 政策缺失→不得 LOSSY+DELIVER",
          not (r.J1 == cj.J1_LOSSY and r.J2 == cj.J2_DELIVER),
          f"{r.J1}/{r.J2}")
    ev = Ev(records=clean_records() + [
        Rec("loss2", result="loss", policy="UNKNOWN_POLICY", reason="未知政策"),
    ])
    r = cj.judge(ev)
    check("A4-2 未知政策→不得 DELIVER",
          r.J2 != cj.J2_DELIVER, f"{r.J1}/{r.J2}")
    ev = Ev(records=clean_records() + [
        Rec("loss3", result="loss", policy="HARD_DEGRADEABLE", reason="可降级"),
    ])
    r = cj.judge(ev)
    check("A4-3 明确可降级政策→允许 LOSSY+DELIVER（对照）",
          r.J1 == cj.J1_LOSSY and r.J2 == cj.J2_DELIVER, f"{r.J1}/{r.J2}")

    # ══ 测试独立性：N-5 原语义（独立构造）══
    ev = Ev(records=clean_records() + [
        Rec("tuplet_ratio", result="unresolved", policy="HARD_NO_LOSS",
            reason="缺口"),
    ])
    r = cj.judge(ev)
    check("A5-1 独立构造：UNDETERMINED→J2=REJECT/undetermined",
          r.J1 == cj.J1_UNDETERMINED and r.J2 == cj.J2_REJECT
          and r.j2_cause == cj.CAUSE_UNDETERMINED,
          f"{r.J1}/{r.J2}/{r.j2_cause}")

    print("—— 红队结果 ——")
    if FAILS:
        print(f"RED {len(FAILS)}: {FAILS}")
        sys.exit(1)
    print("C3-A 红队全绿（修复后）")


if __name__ == "__main__":
    main()
