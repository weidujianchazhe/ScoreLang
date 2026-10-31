# -*- coding: utf-8 -*-
"""MS 结构校验（V1–V13）。模型在 `ms_model`，本模块只放规则。"""
from __future__ import annotations

import ms_semantics as ms
from ms_model import *  # noqa: F401,F403


# ── 踏板链诊断（V4c 的数据层） ─────────────────────────────────
# 背景：踏板在抬脚后 `PEDAL_REPRESS_TOL_US`(50ms) 内再踩，会被判为同一脚、声音继续按住。
# 若作者"每小节踩一次、抬脚只留 30ms"，整曲会被串成一条大踏板：每个音互相延长、
# 物理上糊成一片（实测可把 2 分钟曲子的单音拉到整曲长度）。
# 这条规则就是"防写错层"：拦下来、说清原因、给改法。
# 判错条件：链长 ≥60s **且**覆盖 ≥80% 曲长（= 整曲被串成一条大踏板）。
# 只按绝对秒数会误伤真实作品：钢琴曲连续踩 40–50s 是正常写法（实测 piece 49.4s 合法）。
PEDAL_CHAIN_MAX_US = 60_000_000      # 单链 >60s 才可能是"糊成一片"
PEDAL_CHAIN_RATIO = 0.8              # 且覆盖曲长 ≥80%


def pedal_diagnostics(doc: MSDocument) -> dict:
    """踏板链与发声总长（给 validate / info / report 共用）。

    返回：
      · chains：每件乐器的 sustain 链 [{inst,start,end,segments,ids,span_us}]
      · longest_chain_us：最长一条链
      · sounding_us：所有音"实际发声总长"之和（= 被踏板延长后的时长）
      · content_us：内容结束时间
    """
    content = content_end_us(doc)
    by_inst: dict = {}
    for p in doc.pedals:
        if p.kind != "sustain":
            continue
        by_inst.setdefault(p.instrument_id, []).append(p)

    chains = []
    for inst, segs in by_inst.items():
        segs = sorted(segs, key=lambda x: x.start_us)
        cur = None
        for p in segs:
            end = content if p.end_us is None else p.end_us
            if cur is None:
                cur = {"inst": inst, "start": p.start_us, "end": end,
                       "segments": 1, "ids": [getattr(p, "id", None)]}
            elif p.start_us <= cur["end"] + PEDAL_REPRESS_TOL_US:
                cur["end"] = max(cur["end"], end)
                cur["segments"] += 1
                cur["ids"].append(getattr(p, "id", None))
            else:
                chains.append(cur)
                cur = {"inst": inst, "start": p.start_us, "end": end,
                       "segments": 1, "ids": [getattr(p, "id", None)]}
        if cur is not None:
            chains.append(cur)

    for c in chains:
        c["span_us"] = max(0, c["end"] - c["start"])

    sounding = 0
    for e in doc.events:
        try:
            end = sustain_end_us(doc, e)
        except Exception:  # noqa: BLE001
            end = e.release_us if e.release_us is not None else e.onset_us
        sounding += max(0, end - e.onset_us)

    return {"chains": chains,
            "longest_chain_us": max([c["span_us"] for c in chains] + [0]),
            "sounding_us": sounding,
            "content_us": content}


def _fmt_sec(us: int) -> str:
    return f"{us / 1e6:.1f}s"


def validate(doc: MSDocument) -> list[str]:
    errs: list[str] = []

    if doc.constraint_mode not in CONSTRAINT_MODES:
        errs.append(f"V6 constraint_mode 非法：{doc.constraint_mode}")
    if doc.constraint_mode == "single_piano" and doc.piano_count != 1:
        errs.append("V6 single_piano 要求 piano_count = 1")
    if doc.constraint_mode == "n_pianos" and doc.piano_count < 2:
        errs.append("V6 n_pianos 要求 piano_count ≥ 2")
    if doc.constraint_mode == "unlimited":
        for p in doc.pedals:
            if p.scope != "explicit":
                errs.append(f"V6 unlimited 下踏板必须 explicit（{p.kind}@{p.start_us}）")

    seen_ids = set()
    retired = list(getattr(doc, "retired_ids", ()))
    if len(retired) != len(set(retired)):
        errs.append("V7 retired_ids 重复（作废簿记必须唯一）")
    overlap = {e.id for e in doc.events} & set(retired)
    if overlap:
        errs.append(f"V7 作废 id 被复用：{sorted(overlap)}（E4：id 永不复用）")

    if doc.channels not in CHANNEL_MODES:
        errs.append(f"V8 channels 非法：{doc.channels!r}（只允许 {CHANNEL_MODES}）")
    inst_ids = [getattr(i, "id", None) for i in doc.instruments]
    if len(set(inst_ids)) != len(inst_ids):
        errs.append("V8 乐器实例号重复")
    for i in doc.instruments:
        if not getattr(i, "id", None) or not getattr(i, "type", None):
            errs.append(f"V8 乐器实例缺 id 或 type：{i!r}")
    if doc.instruments:
        n = len(doc.instruments)
        for e in doc.events:
            if isinstance(e.instrument_id, int) and e.instrument_id > n:
                errs.append(f"V8 {e.id} instrument_id={e.instrument_id} 超出乐器实例数 {n}")
        for p in doc.pedals:
            if isinstance(p.instrument_id, int) and p.instrument_id > n:
                errs.append(f"V8 踏板 instrument_id={p.instrument_id} 超出乐器实例数 {n}")

    declared = declared_instrument_ids(doc)
    for e in doc.events:
        if isinstance(e.instrument_id, int) and e.instrument_id not in declared:
            errs.append(f"V8b {e.id} 指向未声明的乐器 P{e.instrument_id}")
    for p in doc.pedals:
        if isinstance(p.instrument_id, int) and p.instrument_id not in declared:
            errs.append(f"V8b 踏板指向未声明的乐器 P{p.instrument_id}"
                        f"（本曲声明：{sorted('P%d' % i for i in declared) or '无'}）")

    event_ids = {e.id for e in doc.events}

    for p in doc.pedals:
        if p.targets:
            for tid in p.targets:
                if tid == "global":
                    continue
                if tid not in event_ids:
                    errs.append(f"V10 踏板 targets 引用的事件不存在：{tid!r}（{p.kind}@{p.start_us}）")

    _CONS_RANGE = {"max_simultaneous": (1, 10), "max_span": (0, 48),
                   "max_polyphony": (1, 24), "max_hold_s": (1, 60),
                   "strings": (1, 24), "max_double_stops": (0, 4), "hands": (1, 2),
                   "max_bow_s": (1, 30), "capo": (0, 12)}
    for inst in doc.instruments:
        cons = getattr(inst, "constraints", None)
        if not cons:
            continue
        for k, v in cons.items():
            if k not in _CONS_RANGE:
                errs.append(f"V13 未知收束键：{k!r}（允许 {sorted(_CONS_RANGE)}）")
                continue
            lo, hi = _CONS_RANGE[k]
            if not isinstance(v, int) or not (lo <= v <= hi):
                errs.append(f"V13 收束值越界：{k}={v!r}（应在 {lo}..{hi}）")

    if doc.instruments:
        import ms_instruments as _reg
        used = {getattr(e, "instrument_id", None) for e in doc.events}
        used |= {getattr(p, "instrument_id", None) for p in doc.pedals}
        for idx, inst in enumerate(doc.instruments, 1):
            if idx not in used:
                continue
            try:
                spec = _reg.resolve(getattr(inst, "type", ""), getattr(inst, "subtype", None))
            except KeyError as exc:
                errs.append(f"V12 乐器类型无法解析：{exc}")
                continue
            if spec.get("reserved"):
                errs.append(f"V12 预留乐器（无音域/采样）被引用：P{idx} {getattr(inst, 'type', '?')}，"
                            f"先补参数或换可用乐器")

    for g in doc.gaps:
        if not isinstance(g, dict):
            errs.append(f"V11 gap 必须是对象：{g!r}")
            continue
        if not g.get("code"):
            errs.append(f"V11 gap 缺 code：{g!r}")
        extra = set(g) - {"code", "where", "detail", "severity"}
        if extra:
            errs.append(f"V11 gap 含未知字段：{sorted(extra)}")
        if g.get("severity") is not None and g["severity"] not in ("info", "warn", "error"):
            errs.append(f"V11 gap severity 非法：{g['severity']!r}")

    for e in doc.events:
        if e.id in seen_ids:
            errs.append(f"E4 事件 id 重复：{e.id}")
        seen_ids.add(e.id)

        if not isinstance(e.instrument_id, int) or e.instrument_id < 1:
            errs.append(f"V5 {e.id} instrument_id 缺失或非法：{e.instrument_id!r}")
        elif e.instrument_id > doc.piano_count:
            errs.append(f"V5 {e.id} instrument_id={e.instrument_id} 超出 piano_count={doc.piano_count}")
        # 88 键是**默认模型边界**（SPEC §2.2）：允许更宽音域需显式开关（尚未实现）
        if not (KEY_MIN <= e.pitch.semitone <= KEY_MAX):
            errs.append(f"V5 {e.id} {ERR_PITCH_RANGE}：semitone={e.pitch.semitone} 不在 {KEY_MIN}..{KEY_MAX}")
        if not e.pitch.consistent():
            errs.append(f"V5 {e.id} 拼写与半音不一致：{e.pitch}")

        if e.release_state not in RELEASE_STATES:
            errs.append(f"V1 {e.id} release_state 非法：{e.release_state}")
        if (e.release_state == "given") != (e.release_us is not None):
            errs.append(f"V1 {e.id} release_state={e.release_state} 与 release_us={e.release_us} 不一致"
                        f"（given 必须有止音事件，其余不应有）")

        if e.release_us is not None:
            if e.release_us < e.onset_us:
                errs.append(f"V2 {e.id} release_us({e.release_us}) < onset_us({e.onset_us})")
            elif e.release_us == e.onset_us and not e.is_grace:
                errs.append(f"V2 {e.id} 零时长仅 is_grace 允许")
            import ms_instruments as _reg_off
            kind = getattr(e, "off_kind", None)
            if kind is not None and kind not in _reg_off.OFF_KINDS:
                errs.append(f"V2 {e.id} 止音方式非法：{kind!r}（允许 {_reg_off.OFF_KINDS}）")
            ramp = int(getattr(e, "off_ramp_us", 0) or 0)
            if ramp < 0 or ramp > 2_000_000:
                errs.append(f"V2 {e.id} 止音缓冲越界：{ramp}µs（0..2s）")

        d = e.dynamics
        if d.state not in (ms.VALUE, ms.NOT_PROVIDED):
            errs.append(f"V3 {e.id} dynamics.state 非法：{d.state}")
        elif d.state == ms.VALUE:
            if d.permille is None or not (DYNAMICS_MIN <= d.permille <= DYNAMICS_MAX):
                errs.append(f"V3 {e.id} dynamics.permille 非法：{d.permille!r}")
            if d.scale not in DYNAMICS_SCALES:
                errs.append(f"V3 {e.id} dynamics.scale 非法：{d.scale!r}")
            if not d.calibration_ref:
                errs.append(f"V3 {e.id} dynamics.calibration_ref 缺失")
            # src 可为 None：表示"直接给定的数值，无推导过程"（推导来源在渲染/写谱层）
            if d.src is not None and d.src not in DYNAMICS_SRCS:
                errs.append(f"V3 {e.id} dynamics.src 非法：{d.src!r}")
        elif d.permille is not None:
            errs.append(f"V3 {e.id} NOT_PROVIDED 时 permille 必须为 None（不得填 1000）")

        if e.excitation_type not in EXCITATION_TYPES:
            errs.append(f"V5 {e.id} excitation_type 非法：{e.excitation_type}")

    seen_pedal_ids = set()
    event_inst = {e.id: e.instrument_id for e in doc.events}
    for p in doc.pedals:
        if p.kind not in PEDAL_KINDS:
            errs.append(f"V4 踏板 kind 非法：{p.kind}")
        if p.scope not in PEDAL_SCOPES:
            errs.append(f"V4 踏板 scope 非法：{p.scope}")
        pid = getattr(p, "id", None)
        if pid:
            if not (len(pid) == 9 and pid[0] == "D" and pid[1:].isdigit()):
                errs.append(f"V4 踏板 id 必须是 D+8 位：{pid!r}")
            if pid in seen_pedal_ids:
                errs.append(f"V4 踏板 id 重复：{pid}")
            seen_pedal_ids.add(pid)
        if p.targets:
            for t in p.targets:
                if t == "global":
                    continue
                inst = event_inst.get(t)
                if inst is None:
                    errs.append(f"V4 踏板 targets 指向不存在的音：{t}（{pid or p.kind}@{p.start_us}）")
                elif inst != p.instrument_id:
                    errs.append(f"V4 踏板 targets 跨乐器：{t} 属 P{inst}，"
                                f"踏板属 P{p.instrument_id}——一个踏板只管一台乐器")
        if not (DEPTH_MIN <= p.depth_permille <= DEPTH_MAX):
            errs.append(f"V4 踏板 depth 越界：{p.depth_permille}")
        if p.kind == "tuning" and p.depth_permille not in (0, 500, 1000):
            errs.append(f"V6 调音踏板只有三档（0/500/1000）：{p.depth_permille}")
        if p.end_us is not None and p.end_us <= p.start_us:
            errs.append(f"V4 踏板 end_us({p.end_us}) ≤ start_us({p.start_us})")
        if p.scope == "mechanical" and p.targets is not None:
            errs.append("V4 mechanical 不得带 targets")
        if p.scope == "explicit" and not p.targets:
            errs.append("V4 explicit 必须带 targets")

    diag = pedal_diagnostics(doc)
    for c in diag["chains"]:
        content = max(1, diag["content_us"])
        if (c["span_us"] > PEDAL_CHAIN_MAX_US
                and c["span_us"] >= PEDAL_CHAIN_RATIO * content):
            errs.append(
                f"V4c 踏板链过长：P{c['inst']} sustain 连续 {c['segments']} 段、"
                f"链长 {_fmt_sec(c['span_us'])}"
                f"（{_fmt_sec(c['start'])} → {_fmt_sec(c['end'])}）——"
                f"抬脚后 {PEDAL_REPRESS_TOL_US // 1000}ms 内再踩会被判为同一脚，"
                f"整曲被串成一条大踏板，每个音互相延长会糊成一片。"
                f"改法：每段抬脚留 ≥100ms，或把这条长踏板拆成独立段"
                f"（本曲实际发声总长 {_fmt_sec(diag['sounding_us'])}）。")

    # P1：unlimited 解除机构绑定约束 → 踏板重叠合法（仍可计算）
    tracks: dict = {}
    for p in doc.pedals:
        tracks.setdefault((p.instrument_id, p.kind), []).append(p)
    for (pid, kind), segs in tracks.items():
        if doc.constraint_mode not in ("single_piano", "n_pianos"):
            continue
        segs = sorted(segs, key=lambda s: s.start_us)
        for a, b in zip(segs, segs[1:]):
            if a.end_us is None or b.start_us < a.end_us:
                errs.append(f"V4 同轨重叠：piano={pid} {kind} @{a.start_us}/{a.end_us} 与 @{b.start_us}")

    # 注：**不再**在结构层判"同键同 onset"。
    # 数学结构上两个同键同刻的事件是存在的（只是落到一架琴时不可能被击两次）；
    # 该判据属于**演奏收束**（realization），见 `check_realization()`。
    # 依据：P1「结构允许 ≠ 计算需要 ≠ 写谱许可」——结构不替演奏层做决定。

    try:
        import ms_instruments as _reg
        by_id = {i.id: i for i in doc.instruments}
        for p in doc.pedals:
            inst = by_id.get(f"P{p.instrument_id}")
            if inst is None:
                continue
            spec = _reg.resolve(inst.type, inst.subtype)
            allowed = spec.get("pedals") or ()
            if p.kind not in allowed:
                errs.append(f"V14 踏板不被乐器支持：{inst.type} 没有 {p.kind!r}（有 {list(allowed)}）")
    except KeyError:
        pass   # 乐器类型未知时由 V8 报

    _CURVE_RANGE = {"dynamics": (0, 1000), "brightness": (0, 1000), "pitch_cents": (-2400, 2400)}
    try:
        import ms_instruments as _reg_cp
        _CURVE_RANGE = dict(_reg_cp.CURVE_PARAMS)
    except Exception:
        pass
    _seen: dict = {}
    for c in sorted(doc.curves, key=lambda x: (x.instrument_id, x.param, x.time_us)):
        if c.param not in _CURVE_RANGE:
            errs.append(f"V15 未知曲线参数：{c.param!r}")
            continue
        lo, hi = _CURVE_RANGE[c.param]
        if not (lo <= c.value <= hi):
            errs.append(f"V15 曲线值越界：{c.param}={c.value}（应在 {lo}..{hi}）")
        if c.ramp not in (0, 1):
            errs.append(f"V15 曲线 ramp 只能是 0/1：{c.ramp}")
        key = (c.instrument_id, c.param)
        prev = _seen.get(key)
        if prev is None:
            if c.ramp != 0:
                errs.append(f"V15 {c.param} 首点必须是阶跃（ramp=0，作为起点）")
        else:
            if c.time_us <= prev:
                errs.append(f"V15 {c.param} 的曲线点必须严格递增：{prev} → {c.time_us}")
        _seen[key] = c.time_us

    TURN_KINDS = ("retrigger", "bow_change", "breath", "restrike", "mallet",
                  "liaison", "break")
    ACTION_MECHS = {}
    try:
        import ms_instruments as _reg_act
        TURN_KINDS = tuple(_reg_act.TURN_KINDS)
        ACTION_MECHS = dict(_reg_act.ACTION_MECHS)
    except Exception:
        pass
    ev_ids = {e.id for e in doc.events}
    try:
        import ms_instruments as _reg2
        mech_of = {}
        for i in doc.instruments:
            mech_of[i.id] = _reg2.resolve(i.type, i.subtype)["mechanism"]
        ev_inst = {e.id: e.instrument_id for e in doc.events}
    except Exception:
        mech_of, ev_inst = {}, {}
    for t in doc.turns:
        if t.event_id not in ev_ids:
            errs.append(f"V16 转折点挂靠的事件不存在：{t.event_id}")
        if t.kind not in TURN_KINDS:
            errs.append(f"V16 未知转折类型：{t.kind!r}")
        if not (0 <= t.strength <= 1000):
            errs.append(f"V16 转折强度越界：{t.strength}（应在 0..1000）")
        iid = ev_inst.get(t.event_id)
        mech = mech_of.get(f"P{iid}") if iid else None
        allow = ACTION_MECHS.get(t.kind)
        if mech and allow is not None and mech not in allow:
            errs.append(f"V16 动作 {t.kind} 不适用于 {mech}（{t.event_id}）")

    try:
        import ms_instruments as _reg3
        for t in doc.turns:
            if t.event_id not in ev_ids or t.kind not in (
                    "retrigger", "bow_change", "breath", "restrike", "mallet"):
                continue
            cur = next((e for e in doc.events if e.id == t.event_id), None)
            if cur is None:
                continue
            inst = next((i for i in doc.instruments if f"P{cur.instrument_id}" == i.id), None)
            if inst is None:
                continue
            cons = _reg3.resolve(inst.type, inst.subtype)["constraints"]
            prev = [e for e in doc.events
                    if e.instrument_id == cur.instrument_id and e.id != cur.id
                    and e.onset_us < cur.onset_us]
            if not prev:
                errs.append(f"V16 {t.kind} 转折没有前一个音（{t.event_id}），无法成立")
                continue
            p0 = max(prev, key=lambda e: e.onset_us)
            p_rel = p0.release_us if p0.release_us is not None else p0.onset_us
            gap_ms = (cur.onset_us - p_rel) / 1000.0
            _NEED = {"retrigger": ("min_retrigger_ms", 20),
                     "bow_change": ("min_bow_change_ms", 60),
                     "breath": ("min_breath_ms", 80),
                     "restrike": ("min_restrike_ms", 25),
                     "mallet": ("min_mallet_ms", 60)}
            key, default = _NEED[t.kind]
            need = cons.get(key, default)
            if t.kind == "retrigger" and p0.pitch.semitone != cur.pitch.semitone:
                errs.append(f"V16 retrigger 转折要求同音高：{p0.pitch.semitone} ≠ {cur.pitch.semitone}")
            if gap_ms < need:
                errs.append(f"V16 {t.kind} 转折时间不可行：间隙 {gap_ms:.0f}ms < {need}ms")
    except KeyError:
        pass

    tsu = getattr(doc, "trailing_silence_us", 0) or 0
    if tsu < 0:
        errs.append(f"V17 trailing_silence_us 不能为负：{tsu}")

    _KINDS = ("initial", "medial", "nucleus", "coda")
    last = {}
    for x in sorted(getattr(doc, "segments", []),
                    key=lambda v: ((v.event_id or v.structure_id), v.index)):
        if x.kind not in _KINDS:
            errs.append(f"V18 未知段类型：{x.kind!r}")
        if not (0 <= x.tone <= 5):
            errs.append(f"V18 段声调越界：{x.tone}")
        if x.release_us and x.onset_us and x.release_us <= x.onset_us:
            errs.append(f"V18 段时长非正：{x.structure_id}#{x.index}")
        key = x.event_id or x.structure_id
        prev = last.get(key)
        if prev is not None and x.index != prev + 1:
            errs.append(f"V18 段索引不连续：{key} {prev}→{x.index}")
        last[key] = x.index


    return errs

