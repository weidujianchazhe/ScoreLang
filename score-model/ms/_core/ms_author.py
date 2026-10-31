# -*- coding: utf-8 -*-
"""写谱 API：把乐器/奏法/力度表串成写一个音的能力。"""
from __future__ import annotations

import ms_articulation as art
import ms_dynamics_levels as dl
import ms_events as ev
import ms_ornament as orn
import ms_semantics as ms
import pinyin as pf

# 应用顺序：先展开装饰音，再对每个音应用奏法
# 理由：奏法作用于"每个音符的发音方式"，装饰音先把一个音符变成多个音符。
ORDER = "ornament_then_articulation"


def _resolve_dynamics(level: str | None, permille: int | None,
                      calibration_ref: str | None) -> "ev.Dynamics":
    if level is not None and permille is not None:
        raise ValueError("level 与 permille 只能给一个")
    if level is not None:
        pm = dl.level_to_permille(level)
        return ev.Dynamics(ms.VALUE, pm, "relative_permille",
                           calibration_ref or dl.LEVELS_VERSION, "notated_inferred")
    if permille is not None:
        if not (ev.DYNAMICS_MIN <= permille <= ev.DYNAMICS_MAX):
            raise ValueError(f"permille 越界：{permille}")
        return ev.Dynamics(ms.VALUE, permille, "relative_permille",
                           calibration_ref or "manual", None)
    return ev.Dynamics(ms.NOT_PROVIDED)


def _next_ids(count: int, used: set, prefix: str = "w", width: int | None = None) -> list:
    out, n = [], 1
    while len(out) < count:
        cand = f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"
        n += 1
        if cand in used:
            continue
        out.append(cand)
    return out


def _next_bind(used: set) -> str:
    """分配一个未用的绑定号（`B` + 5 位）。"""
    n = 1
    while True:
        cand = f"B{n:05d}"
        if cand not in used:
            return cand
        n += 1


def _mk_pitch(semitone: int, spelling=None) -> "ev.Pitch":
    if spelling is not None:
        step, alter, octave = spelling
        return ev.Pitch(step, alter, octave, semitone)
    # 未知拼写时用升号形式（仅作为占位；调用方应尽量给 spelling）
    base = {0: "C", 1: "C", 2: "D", 3: "D", 4: "E", 5: "F",
            6: "F", 7: "G", 8: "G", 9: "A", 10: "A", 11: "B"}[semitone % 12]
    alter = 1 if semitone % 12 in (1, 3, 6, 8, 10) else 0
    octave = semitone // 12 - 1
    return ev.Pitch(base, alter, octave, semitone)


def write_note(*, onset_us: int, duration_us: int, semitone: int,
               spelling=None, instrument_id: int = 1,
               level: str | None = None, permille: int | None = None,
               articulation: str | None = None,
               ornament: str | None = None,
               instrument_type: str | None = None,
               upper_semitone: int | None = None,
               lower_semitone: int | None = None,
               grace_semitone: int | None = None,
               calibration_ref: str | None = None,
               used_ids: set | None = None,
               warnings: list | None = None) -> list:
    """写一个音，返回 `list[Event]`（装饰音会返回多个）。

    `warnings` 若给出，会把"退化/近似"写入其中（欠账④：grace 退化为拍上必须可见）。
    `instrument_type` 若给出，会检查这个乐器**做不做得了**该奏法/装饰音（不做就拒绝）。
    """
    if duration_us <= 0:
        raise ValueError("duration_us 必须为正")
    if instrument_type and articulation:
        check_articulation(instrument_type, articulation)
    if instrument_type and ornament:
        check_ornament(instrument_type, ornament)

    dyn = _resolve_dynamics(level, permille, calibration_ref)

    # ① 装饰音展开（在"写下的时长"上展开）
    if ornament:
        grace_upper = grace_semitone if grace_semitone is not None else semitone + 1
        specs = orn.expand(
            ornament, onset_us=onset_us, duration_us=duration_us,
            main_semitone=semitone,
            upper_semitone=upper_semitone if upper_semitone is not None else grace_upper,
            lower_semitone=lower_semitone,
            grace_semitone=grace_semitone,
        )
    else:
        specs = [{"onset_us": onset_us, "duration_us": duration_us,
                  "semitone": semitone, "role": "main"}]

    # 欠账④：短倚音因前方无空间退化为"拍上"时，必须显式上报
    if warnings is not None:
        for spec in specs:
            if spec.get("role") == "grace_onbeat":
                warnings.append({
                    "code": "grace_onbeat",
                    "where": f"onset_us={onset_us}",
                    "detail": "短倚音前方空间不足，已退化为拍上（占用主音开头）",
                    "severity": "warn",
                })

    # ② 奏法（逐音应用）
    events = []
    used = set(used_ids or ())
    ids = _next_ids(len(specs), used)
    for spec, eid in zip(specs, ids):
        d = spec["duration_us"]
        pm = dyn.permille
        if articulation:
            d = art.apply_duration(d, articulation)
            pm = art.apply_dynamics(pm, articulation)
            d = max(1, d)
        dyn_final = dyn if not articulation else ev.Dynamics(
            dyn.state, pm, dyn.scale, dyn.calibration_ref, dyn.src)
        if dyn_final.state == ms.VALUE and dyn_final.permille is None:
            raise ValueError("状态错误：VALUE 状态却无 permille")
        events.append(ev.Event(
            id=eid, instrument_id=instrument_id,
            onset_us=int(spec["onset_us"]),
            pitch=_mk_pitch(spec["semitone"],
                            spelling if spec["role"] == "main" else None),
            release_us=int(spec["onset_us"]) + int(d),
            release_state="given",
            dynamics=dyn_final,
        ))
    return events


def write_chord(*, onset_us: int, duration_us: int, semitones: list,
                instrument_id: int = 1, level: str | None = None, permille: int | None = None,
                articulation: str | None = None,
                calibration_ref: str | None = None,
                used_ids: set | None = None) -> list:
    """写一个和弦（同起点、同时长、同力度）。"""
    out, used = [], set(used_ids or ())
    for semi in semitones:
        evs = write_note(onset_us=onset_us, duration_us=duration_us, semitone=semi,
                         instrument_id=instrument_id, level=level, permille=permille,
                         articulation=articulation, calibration_ref=calibration_ref,
                         used_ids=used)
        out.extend(evs)
        used.update(e.id for e in evs)
    return out


def make_instrument(instrument_id: str, type_code: str, subtype: str | None = None,
                    section: str | None = None,
                    constraints: dict | None = None) -> "ev.Instrument":
    """声明一件乐器（类型码查 `ms_instruments`；约束可选）。"""
    return ev.Instrument(id=instrument_id, type=type_code, subtype=subtype,
                         section=section, constraints=constraints)


def check_articulation(type_code: str, articulation: str) -> None:
    """这个乐器做不做得了这个奏法（写谱侧把关，不进文件）。"""
    import ms_instruments as _reg
    mech = _reg.resolve(type_code).get("mechanism")
    ok = _reg.ARTICULATIONS_BY_MECH.get(mech, ())
    if articulation not in ok:
        raise ValueError(f"{type_code}（{mech}）做不了奏法 {articulation!r}；可用：{ok}")


def check_ornament(type_code: str, ornament: str) -> None:
    """这个乐器做不做得了这个装饰音。"""
    import ms_instruments as _reg
    mech = _reg.resolve(type_code).get("mechanism")
    ok = _reg.ORNAMENTS_BY_MECH.get(mech, ())
    if ornament not in ok:
        raise ValueError(f"{type_code}（{mech}）做不了装饰音 {ornament!r}；可用：{ok}")


def write_pedal(piano_id: int, kind: str, start_us: int, end_us: int | None,
                depth_permille: int = 1000, scope: str = "mechanical",
                targets: tuple | None = None,
                used_ids: set | None = None,
                pedal_id: str | None = None) -> "ev.PedalSegment":
    """写一段踏板控制事件（**带 id、带乐器**，和音符一样可寻址）。kind: sustain / sostenuto / una_corda。

    作用于哪些音由**时间**决定：踏板按下时仍在响的音、以及按下之后起的音，
    直到抬起为止（同一乐器内）。
    """
    pid = pedal_id
    if pid is None:
        used = set(used_ids or ())
        pid = _next_ids(1, used, prefix="D", width=8)[0]
    return ev.PedalSegment(instrument_id=piano_id, kind=kind, start_us=int(start_us),
                           end_us=None if end_us is None else int(end_us),
                           depth_permille=int(depth_permille), scope=scope,
                           targets=targets, id=pid)


def write_turn(event_id: str, kind: str, strength: int = 1000) -> "ev.TurnPoint":
    """标记一个演奏转折（同键再击 / 换弓 / 换气 / 重复拨弦 / 换槌）。"""
    return ev.TurnPoint(event_id=event_id, kind=kind, strength=strength)


def vocal_units(pinyin_text: str, tone: int = 1) -> list:
    """拼音 → 段序列 `[(kind, text, tone)]`（写谱侧便利函数，**不入文件**）。

    段才是文件里的单位：`chang` → `[("initial","ch",2), ("nucleus","a",2), ("coda","ng",2)]`
    """
    import pinyin as _py
    syl = _py.parse("", pinyin_text, tone)
    return [(s.kind, s.text, int(tone)) for s in syl.segments]


def write_vocal(*, units: list, onset_us: int, duration_us: int, semitone: int,
                binding: str | None = None, turn: int = 0,
                instrument_id: int = 1, lang: str | None = "zh",
                level: str | None = None, permille: int | None = None,
                calibration_ref: str | None = None,
                used_ids: set | None = None,
                used_bindings: set | None = None) -> tuple:
    """写**一个音**（一个事件）及其**段**，返回 `(events, segments)`。

    `units` = `[(kind, text, tone)]`：一段 = 一个声母或一个韵母，
      · `chang` → `[("initial","ch",2), ("nucleus","a",2), ("coda","ng",2)]`
    段的**起止时间**按发音规则（`phoneme_factors.spread_durations`）从这个音里切出来，
    **写进文件**——收束层不再自己推。
    同一个音的所有段共享一个 `binding`（`B`+5 位）；拖腔的第二个音用同一 `binding` 再写一次。
    `turn=1` 表示这个音前**重新起音**。
    """
    if not (0 <= int(turn) <= 1):
        raise ValueError("turn 只能是 0 / 1")
    if not units:
        raise ValueError("units 不能为空（一个音至少一个段）")
    if lang:
        import lang as _lang_mod
        _lang_mod.require_ready(lang)
    if int(duration_us) <= 0:
        raise ValueError("duration_us 必须为正")
    kinds = ("initial", "medial", "nucleus", "coda")
    for i, u in enumerate(units):
        if u[0] not in kinds:
            raise ValueError(f"units[{i}] 段类型非法：{u[0]!r}（{kinds}）")
        if not u[1]:
            raise ValueError(f"units[{i}] 段文本为空")
        t = int(u[2]) if len(u) > 2 else 0
        if not (0 <= t <= 5):
            raise ValueError(f"units[{i}] 声调越界：{t}（0–5）")

    used = set(used_ids or ())
    eid = _next_ids(1, used, prefix="L", width=8)[0]
    used.add(eid)
    binds = set(used_bindings or ())
    bid = binding or _next_bind(binds)
    binds.add(bid)
    if used_bindings is not None:
        used_bindings.add(bid)

    start = int(onset_us)
    event = ev.Event(id=eid, instrument_id=instrument_id, onset_us=start,
                     pitch=_mk_pitch(int(semitone)),
                     release_us=start + int(duration_us),
                     release_state="given",
                     dynamics=_resolve_dynamics(level, permille, calibration_ref))
    spans = pf.spread_durations([u[0] for u in units], int(duration_us))
    segs, cursor = [], start
    for i, (u, span) in enumerate(zip(units, spans)):
        kind, text = u[0], u[1]
        tone = int(u[2]) if len(u) > 2 else 0
        segs.append(ev.VoiceSegment(
            structure_id=bid, index=i, kind=kind, text=text, tone=tone,
            onset_us=cursor, release_us=cursor + int(span),
            turn=(int(turn) if i == 0 else 0),
            event_id=eid, binding_id=bid, lang=lang))
        cursor += int(span)
    return [event], segs


def to_document(events: list, piano_count: int | None = None,
                constraint_mode: str | None = None, *,
                instruments: list | None = None,
                pedals: list | None = None,
                turns: list | None = None,
                segments: list | None = None,
                channels: str = "per_instance") -> "ev.MSDocument":
    """把写出的音符合成文档，并**立即校验**（写谱 API 不得产出非法文档）。

    支持：乐器表 / 踏板 / 转折 / 发声段（写在事件流里）/ 通道策略。
    """
    insts = list(instruments or [])
    if piano_count is None:
        piano_count = len(insts) if insts else 1
    if constraint_mode is None:
        constraint_mode = "single_piano" if piano_count == 1 else "n_pianos"
    doc = ev.MSDocument(piano_count=piano_count, constraint_mode=constraint_mode,
                        events=list(events),
                        instruments=insts,
                        pedals=list(pedals or []),
                        turns=list(turns or []),
                        segments=list(segments or []),
                        channels=channels)
    errs = ev.validate(doc)
    if errs:
        raise ValueError("写谱结果不合法：" + "；".join(errs))
    return doc
