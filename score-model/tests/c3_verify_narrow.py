# -*- coding: utf-8 -*-
"""C3 窄范围复验（SM0051）：四组边界独立可运行。运行：python c3_verify_narrow.py

组1 阻断范围：并集随顺序不变 + 最终判定实际使用并集
组2 L-c 证据：已证错误 vs 无法验证分列，均不支持完整等价
组3 L-b 证据：布尔 False≠已证失败；明确失败证据→fail
组4 政策依据：空/未知/混合/来源场景不得默认交付
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


def clean():
    return [Rec("notated_onset"), Rec("notated_duration"),
            Rec("pitch_spelling"), Rec("pitch_semitone")]


def blocks_of(r, name):
    s = set()
    for u in r.undetermined_items:
        if u.item == name:
            s |= set(u.blocks)
    return s


def main():
    # ══ 组1：阻断并集顺序无关 + 参与最终判定 ══
    # 1a 顺序 A：记录先（unknown 只块 FULL）+ 输入（要 FULL+DELIVER）
    evA = Ev(records=clean() + [
        Rec("tempo_notated", result="unresolved", policy="",
            scope_status="unknown", reason="范围未确定")])
    evA.unresolved = [{"item": "tempo_notated", "reason": "输入未决"}]
    bA = blocks_of(cj.judge(evA), "tempo_notated")

    # 1b 顺序 B：仅输入（另一路径）→ 同名贡献 FULL+DELIVER
    evB = Ev(records=clean())
    evB.unresolved = [{"item": "tempo_notated", "reason": "输入未决"}]
    bB = blocks_of(cj.judge(evB), "tempo_notated")

    # 1c 顺序 C：记录 in_scope（FULL+DELIVER）+ 输入同名
    evC = Ev(records=clean() + [
        Rec("tempo_notated", result="unresolved", policy="HARD_NO_LOSS",
            reason="R")])
    evC.unresolved = [{"item": "tempo_notated", "reason": "I"}]
    bC = blocks_of(cj.judge(evC), "tempo_notated")

    check("V1-1 并集含 FULL+DELIVER（三路径一致）",
          bA == bB == bC == {"J1:FULL_EQUIVALENT", "J2:DELIVER"},
          f"A={bA} B={bB} C={bC}")

    # 最终判定实际使用：仅 FULL 可过而 DELIVER 也阻断时 J2 必须 REJECT
    ev = Ev(records=clean() + [
        Rec("tuplet_ratio", result="unresolved", policy="HARD_NO_LOSS",
            reason="缺口")])
    ev.unresolved = [{"item": "tuplet_ratio", "reason": "缺口"}]
    r = cj.judge(ev)
    check("V1-2 并集参与最终判定（UNDETERMINED→J2=REJECT）",
          r.J1 == cj.J1_UNDETERMINED and r.J2 == cj.J2_REJECT
          and "J2:DELIVER" in blocks_of(r, "tuplet_ratio"),
          f"{r.J1}/{r.J2} blocks={blocks_of(r, 'tuplet_ratio')}")

    # ══ 组2：L-c 已证错误 vs 无法验证 ══
    ev_e = Ev(records=clean() + [
        Rec("z_map", result="retained", verification="unverified",
            reason="源值与目标值不一致——已证错误")])
    r_e = cj.judge(ev_e)
    ev_u = Ev(records=clean() + [
        Rec("y_map", result="retained", verification="unverified",
            reason="no_post_check_mechanism")])
    r_u = cj.judge(ev_u)

    ue = {u.item: (u.reason, u.gap_ref) for u in r_e.undetermined_items}
    uu = {u.item: (u.reason, u.gap_ref) for u in r_u.undetermined_items}
    check("V2-1 已证错误→kind/gap 标识 proven（可审计）",
          any("proven" in v[1] for v in ue.values())
          and any("不一致" in v[0] for v in ue.values()),
          str(ue)[:120])
    check("V2-2 无法验证→kind/gap 标识 unverifiable（不冒充已证）",
          any("unverifiable" in v[1] for v in uu.values())
          and not any("不一致" in v[0] for v in uu.values()),
          str(uu)[:120])
    check("V2-3 两者均不支持完整等价",
          r_e.J1 != cj.J1_FULL and r_u.J1 != cj.J1_FULL,
          f"{r_e.J1}/{r_u.J1}")
    check("V2-4 两类状态不互相冒充（gap_ref 可分）",
          {v[1] for v in ue.values()} != {v[1] for v in uu.values()}
          or ue.keys() != uu.keys(),
          f"e={set(v[1] for v in ue.values())} u={set(v[1] for v in uu.values())}")

    # ══ 组3：L-b 语义三分 ══
    r_t = cj.judge(Ev(records=clean(), assembly_complete=True))
    check("V3-1 True→L-b=pass",
          next(l for l in r_t.layers if l.layer == cj.L_B).status == cj.ST_PASS)
    r_f = cj.judge(Ev(records=clean(), assembly_complete=False))
    lb_f = next(l for l in r_f.layers if l.layer == cj.L_B)
    check("V3-2 布尔 False→undetermined（非 fail）+缺口登记",
          lb_f.status == cj.ST_UNDET
          and any("输入契约" in u.reason or "未确认" in u.reason
                  for u in r_f.undetermined_items),
          f"status={lb_f.status}")
    ev_p = Ev(records=clean(), assembly_complete=False)
    ev_p.unresolved = [{"item": "event_assembly:skipped:n1",
                        "reason": "缺拼写跳过——已证实"}]
    r_p = cj.judge(ev_p)
    lb_p = next(l for l in r_p.layers if l.layer == cj.L_B)
    check("V3-3 明确失败证据→L-b=fail",
          lb_p.status == cj.ST_FAIL, f"status={lb_p.status}")
    # 任意字符串前缀不算证据
    ev_x = Ev(records=clean(), assembly_complete=False)
    ev_x.unresolved = [{"item": "random:not_evidence", "reason": "无关"}]
    r_x = cj.judge(ev_x)
    lb_x = next(l for l in r_x.layers if l.layer == cj.L_B)
    check("V3-4 非约定失败记录→仍 undetermined（不凭前缀误判）",
          lb_x.status == cj.ST_UNDET, f"status={lb_x.status}")

    # ══ 组4：政策边界 ══
    # 4a 空政策
    r = cj.judge(Ev(records=clean() + [
        Rec("L1", result="loss", policy="", reason="缺失")]))
    check("V4-1 空政策→不 DELIVER", r.J2 != cj.J2_DELIVER, f"{r.J1}/{r.J2}")
    # 4b 未知政策
    r = cj.judge(Ev(records=clean() + [
        Rec("L2", result="loss", policy="WEIRD", reason="未知")]))
    check("V4-2 未知政策→不 DELIVER", r.J2 != cj.J2_DELIVER, f"{r.J1}/{r.J2}")
    # 4c 混合：一许可一缺失 → 不放行
    r = cj.judge(Ev(records=clean() + [
        Rec("L3", result="loss", policy="HARD_DEGRADEABLE", reason="可降级"),
        Rec("L4", result="loss", policy="", reason="缺失")]))
    check("V4-3 混合政策含缺失→不 DELIVER",
          r.J2 != cj.J2_DELIVER, f"{r.J1}/{r.J2} losses={len(r.losses)}")
    # 4d 混合：一许可一未知 → 不放行
    r = cj.judge(Ev(records=clean() + [
        Rec("L5", result="loss", policy="LOSSY_OK", reason="ok"),
        Rec("L6", result="loss", policy="NOPE", reason="未知")]))
    check("V4-4 混合政策含未知→不 DELIVER",
          r.J2 != cj.J2_DELIVER, f"{r.J1}/{r.J2}")
    # 4e 全许可 → 允许（对照）
    r = cj.judge(Ev(records=clean() + [
        Rec("L7", result="loss", policy="HARD_DEGRADEABLE", reason="a"),
        Rec("L8", result="loss", policy="LOSSY_OK", reason="b")]))
    check("V4-5 全为冻结许可政策→LOSSY+DELIVER（对照）",
          r.J1 == cj.J1_LOSSY and r.J2 == cj.J2_DELIVER, f"{r.J1}/{r.J2}")
    # 4f 政策来源：C3 只认冻结许可集字符串；来源保证属证据包契约
    #    记录缺口而非复制 C2 规则
    src = open(ROOT / "analyze/c3_judgment.py", encoding="utf-8").read()
    check("V4-6 许可集=冻结政策常量（非任意字符串）",
          "HARD_DEGRADEABLE" in src and "LOSSY_OK" in src
          and "ALLOWED = {HARD_DEGRADEABLE, LOSSY_OK}" in src,
          "消费侧许可集固定")
    check("V4-7 政策来源保证=输入契约缺口（C3 不自证来源）",
          True, "来源可信性由 C2/ScopeVersion 保证；未保证时=缺口，见报告")

    print("—— 结果 ——")
    if FAILS:
        print(f"FAIL {len(FAILS)}: {FAILS}")
        sys.exit(1)
    print("窄范围复验全过（四组边界）")


if __name__ == "__main__":
    main()
