# -*- coding: utf-8 -*-
"""可演奏性收束（按机制）：只报告，不限制 MS 写入。

规则码：
  C1 同刻音数超过机制上限
  C2 和弦跨度超过机制上限
  C3 同时发声数超过复音上限
  C4 单音乐器（吹/人声）出现时间重叠
  C5 单音持续超过气息/弓长上限
  C6 弓弦同时发声超过双音上限
C7 同键重复触发间隔不足（钢琴同键连击）
C8 弓弦换弓（转折）时间不足
C9 音域越界（低于/高于该乐器实际能发出的音）
"""
from __future__ import annotations

from collections import defaultdict

import ms_events as ev
import ms_instruments as reg


def _spec(doc, iid: int) -> dict:
    inst = ev.instrument_of(doc, iid)          # 按 id 取，不按下标
    if inst is None:
        return reg.resolve("acoustic_grand_piano")
    try:
        spec = reg.resolve(getattr(inst, "type", ""), getattr(inst, "subtype", None))
    except KeyError:
        return reg.resolve("acoustic_grand_piano")
    if getattr(inst, "constraints", None):
        spec = dict(spec)
        spec["constraints"] = {**spec["constraints"], **inst.constraints}
    return spec


def check_playability(doc) -> list[str]:
    errs: list[str] = []
    by_inst = defaultdict(list)
    for e in doc.events:
        by_inst[e.instrument_id].append(e)

    for iid, notes in sorted(by_inst.items()):
        spec = _spec(doc, iid)
        cons = spec.get("constraints", {})
        mech = spec.get("mechanism")
        name = f"P{iid}({spec.get('type_code')})"

        # C9 音域：低于/高于这件乐器能发出的音
        rng = spec.get("range")
        if rng:
            lo, hi = rng
            bad = [e for e in notes if not (lo <= e.pitch.semitone <= hi)]
            if bad:
                errs.append(f"C9 {name} 有 {len(bad)} 个音超出音域 {lo}..{hi}"
                            f"（如 {bad[0].id} = {bad[0].pitch.semitone}）")

        # C1/C2 同刻
        by_onset = defaultdict(list)
        for e in notes:
            by_onset[e.onset_us].append(e)
        for onset, group in by_onset.items():
            if len(group) > cons.get("max_simultaneous", 99):
                errs.append(f"C1 {name} 同刻 {len(group)} 音，超过 {mech} 上限 {cons['max_simultaneous']}（t={onset}µs）")
            if "max_span" in cons and len(group) > 1:
                semis = sorted(g.pitch.semitone for g in group)
                span = semis[-1] - semis[0]
                if span > cons["max_span"]:
                    # 双手机制：按最大音程缝隙拆成两簇，两簇各自不超限即视为两手分工
                    ok_split = False
                    if cons.get("hands", 1) >= 2 and len(semis) >= 2:
                        gaps = [(semis[i + 1] - semis[i], i) for i in range(len(semis) - 1)]
                        gap, idx = max(gaps)
                        left = semis[idx] - semis[0]
                        right = semis[-1] - semis[idx + 1]
                        ok_split = gap >= 12 and left <= cons["max_span"] and right <= cons["max_span"]
                    if not ok_split:
                        errs.append(f"C2 {name} 和弦跨度 {span} 半音，超过上限 {cons['max_span']}（t={onset}µs）")

        # C3 同时发声
        if "max_polyphony" in cons:
            points = []
            for e in notes:
                points.append((e.onset_us, 1))
                end = e.release_us if e.release_us is not None else e.onset_us + 1_500_000
                points.append((end, -1))
            points.sort()
            cur = peak = 0
            for _t, d in points:
                cur += d
                peak = max(peak, cur)
            if peak > cons["max_polyphony"]:
                errs.append(f"C3 {name} 同时 {peak} 音，超过 {mech} 复音上限 {cons['max_polyphony']}")

        # C4 单音机制重叠
        if cons.get("max_polyphony") == 1:
            srt = sorted(notes, key=lambda e: e.onset_us)
            for a, b in zip(srt, srt[1:]):
                a_end = a.release_us if a.release_us is not None else a.onset_us + 1_500_000
                if b.onset_us < a_end:
                    errs.append(f"C4 {name} 单音乐器出现重叠：{a.id} 与 {b.id}")
                    break

        # C5 持续过长（按音区分档：低音更长，高音更短）
        hold_key = "max_bow_s" if "max_bow_s" in cons else ("max_hold_s" if "max_hold_s" in cons else None)
        if hold_key:
            for e in notes:
                end = e.release_us if e.release_us is not None else e.onset_us + 1_500_000
                dur = (end - e.onset_us) / 1e6
                semi = e.pitch.semitone
                factor = 1.15 if semi < 60 else (0.85 if semi > 76 else 1.0)
                limit = cons[hold_key] * factor
                if dur > limit:
                    errs.append(f"C5 {name} {e.id} 持续 {dur:.1f}s，超过 {mech} 上限 "
                                f"{limit:.1f}s（{cons[hold_key]}s × 音区 {factor}）")

        # C6 弓弦双音
        if "max_double_stops" in cons:
            limit = max(1, cons["max_double_stops"])
            for onset, group in by_onset.items():
                if len(group) > limit:
                    errs.append(f"C6 {name} 弓弦同时 {len(group)} 音，超过上限 {limit}（t={onset}µs）")
    # C7/C8：转折点不是结构，而是**由相邻音符推导**的可演奏性事实
    #   · 同键连击：上一音释放到下一音触发之间的间隙不足 → 机械上来不及复位
    #   - 换弓：同弓连续两音（无间隙或间隙过小）需要反向，需给弓留时间
    turn_marks = {}
    for t in getattr(doc, "turns", []):
        turn_marks[t.event_id] = t.kind
    by_inst = {}
    for e in doc.events:
        by_inst.setdefault(e.instrument_id, []).append(e)
    for iid, evs in by_inst.items():
        evs.sort(key=lambda x: x.onset_us)
        inst = next((i for i in doc.instruments if i.id == f"P{iid}"), None)
        if inst is None:
            continue
        spec = reg.resolve(inst.type, inst.subtype)
        cons = spec["constraints"]
        mech = spec["mechanism"]
        for a, b in zip(evs, evs[1:]):
            a_rel = a.release_us if a.release_us is not None else a.onset_us
            gap_ms = (b.onset_us - a_rel) / 1000.0
            if b.id in turn_marks:
                continue          # 已显式标记转折（音头方式由演奏者给出）
            if a.pitch.semitone == b.pitch.semitone and "min_retrigger_ms" in cons:
                need = cons["min_retrigger_ms"]
                if gap_ms < need:
                    errs.append(f"C7 {inst.type} 同键 {a.pitch.semitone} 连击间隔 "
                                f"{gap_ms:.0f}ms < {need}ms（{a.id} → {b.id}）")
            if mech == "bowed_string" and "min_bow_change_ms" in cons:
                if a.pitch.semitone != b.pitch.semitone or gap_ms < cons["min_bow_change_ms"]:
                    need = cons["min_bow_change_ms"]
                    if gap_ms < need:
                        errs.append(f"C8 {inst.type} 换弓时间 {gap_ms:.0f}ms < {need}ms（{a.id} → {b.id}）")

    return errs
