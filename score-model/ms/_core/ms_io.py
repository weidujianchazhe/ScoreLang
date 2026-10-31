# -*- coding: utf-8 -*-
"""旧档案行式读写（**只读兼容**，不再作为写作格式）。

MS 是数学模型，没有文件形态；实际写谱只有 `.md`（文档）与 `.py`（脚本）两种。
本模块保留的唯一用途：读兼容作品、跑回归、把旧档案一次转成 `.md`。
格式细节见 `docs/reference/旧档案线格式.md`（代码里不重复口径）。
"""
from __future__ import annotations

import re
from pathlib import Path

import ms_events as ev
import ms_semantics as ms

MAGIC = "ms"
FORMAT_VERSION = 1

_ID_RE = re.compile(r"L(\d{8})")
_PEDAL_ID_RE = re.compile(r"D(\d{8})")

# 字典基线（稳定顺序；实际写出时 = 基线 + 数据里出现的额外值）
BASE_DICTS = {
    "step": ["C", "D", "E", "F", "G", "A", "B"],
    "rel": ["given", "sustaining", ms.NOT_PROVIDED],
    "state": ["VALUE", ms.NOT_PROVIDED, ms.ABSENT, ms.UNDETERMINED,
              ms.UNSUPPORTED, ms.DERIVABLE_PENDING],
    "src": ["measured", "midi_inverted", "notated_inferred"],
    "scale": ["relative_permille", "velocity_steps", "continuous", "fixed_levels"],
    "exc": ["impulse", "sustained"],
    "kind": ["sustain", "sostenuto", "una_corda", "tuning", "swell", "hihat", "sordino"],
    "curve": ["dynamics", "brightness", "pitch_cents", "vibrato", "bow_position"],
    "turn": ["retrigger", "bow_change", "breath", "restrike", "mallet", "liaison", "break",
             "bow_up", "bow_down", "pizz", "arco", "harmonic",
             "mallet_soft", "mallet_hard", "inhale", "key_noise", "mute_on", "mute_off",
             "col_legno", "flutter", "key_click", "roll", "brush", "rim_shot",
             "tremolo", "mute_cup", "mute_harmon", "mute_plunger", "half_valve", "growl"],
}
FREE_DICTS = ("src", "scale", "exc")   # 值域可扩展的字典


class FormatError(ValueError):
    """.ms 解析/写出错误。"""


def _fmt_id(n: int) -> str:
    if not 0 <= n <= 99_999_999:
        raise FormatError(f"id 超出 8 位容量：{n}")
    return f"L{n:08d}"


def _is_id(s: str, prefix: str = "L") -> bool:
    """`L`+8 位（音符/发声行）或 `D`+8 位（踏板控制事件）。"""
    rx = _PEDAL_ID_RE if prefix == "D" else _ID_RE
    return bool(rx.fullmatch(s or ""))


def _pedal_from_parts(parts, dic: dict, no: int | None = None):
    """踏板控制事件行 → PedalSegment。

    两种写法：
      · 8 列：`id instrument kind start end depth scope targets`（带 id）
      · 7 列：`instrument kind start end depth scope targets`（旧写法，无 id）
    """
    pid, rest = None, list(parts)
    if len(rest) >= 8 and str(rest[0]).startswith("D"):
        pid, rest = rest[0], rest[1:]
    if len(rest) < 5:
        msg = "踏板行至少 5 列（instrument kind start end depth [scope targets]）"
        raise FormatError(f"第 {no} 行：{msg}" if no else msg)
    piano, kind_i, start, end, depth = rest[:5]
    scope = rest[5] if len(rest) > 5 else "mechanical"
    tgt = rest[6] if len(rest) > 6 else "-"
    targets = None if tgt == "-" else tuple(tgt.split(","))
    try:
        kind = dic["kind"][int(kind_i)]
    except (IndexError, ValueError):
        raise FormatError(f"第 {no} 行：踏板 kind 索引非法：{kind_i}" if no else "踏板 kind 索引非法")
    return ev.PedalSegment(int(piano), kind, int(start),
                           None if end == "-" else int(end), int(depth),
                           scope, targets, id=pid)


def _segment_from_parts(parts, no: int | None = None):
    """发声段行 → VoiceSegment。两种形态：

      · 事件流（11 列）：`event_id vocal index kind text binding tone turn lang start end`
      · 旧 `vocal` 块（7/8 列）：`event_id index kind text binding tone turn [lang]`
    """
    rest = list(parts)
    if len(rest) >= 2 and rest[1] == "vocal":
        rest = [rest[0]] + rest[2:]
    if len(rest) >= 9:                      # 带时间
        eid, idx, kind, text, bid, tone, turn, lang, st, en = rest[:10]
        start = 0 if st == "-" else int(st)
        end = 0 if en == "-" else int(en)
    elif len(rest) == 8:                    # 旧：带 lang，无时间
        eid, idx, kind, text, bid, tone, turn, lang = rest
        start = end = 0
    elif len(rest) == 7:                    # 旧：无 lang，无时间
        eid, idx, kind, text, bid, tone, turn = rest
        lang, start, end = "-", 0, 0
    else:
        msg = ("发声段行应为 11 列（event_id vocal index kind text binding tone turn lang start end）"
               "或旧写法 7/8 列")
        raise FormatError(f"第 {no} 行：{msg}" if no else msg)
    return ev.VoiceSegment(bid, int(idx), kind, text, int(tone),
                           onset_us=start, release_us=end, turn=int(turn),
                           event_id=eid, binding_id=bid,
                           lang=None if lang == "-" else lang)


# ── 写出 ─────────────────────────────────────────────────────

def _dict_for(values, base):
    out = list(base)
    for v in sorted({v for v in values if v is not None} - set(out)):
        out.append(v)
    return out


def _build_dicts(doc) -> dict[str, list[str]]:
    steps, rels, states, srcs, scales, excs, kinds = [], [], [], [], [], [], []
    curves = []
    turns = []
    for e in doc.events:
        steps.append(e.pitch.step)
        rels.append(e.release_state)
        states.append(e.dynamics.state)
        srcs.append(e.dynamics.src)
        scales.append(e.dynamics.scale)
        excs.append(e.excitation_type)
    for p in doc.pedals:
        kinds.append(p.kind)
    for c in doc.curves:
        curves.append(c.param)
    for t in doc.turns:
        turns.append(t.kind)
    return {
        "step": _dict_for(steps, BASE_DICTS["step"]),
        "rel": _dict_for(rels, BASE_DICTS["rel"]),
        "state": _dict_for(states, BASE_DICTS["state"]),
        "src": _dict_for(srcs, BASE_DICTS["src"]),
        "scale": _dict_for(scales, BASE_DICTS["scale"]),
        "exc": _dict_for(excs, BASE_DICTS["exc"]),
        "kind": _dict_for(kinds, BASE_DICTS["kind"]),
        "curve": _dict_for(curves, BASE_DICTS["curve"]) if curves else [],
        "turn": _dict_for(turns, BASE_DICTS["turn"]) if turns else [],
    }


def _assign_ids(doc) -> tuple[list, dict, list]:
    """按 (onset, semitone, id) 排序事件，保留合法 8 位 id，其余分配新号。"""
    evs = sorted(doc.events, key=lambda e: (e.onset_us, e.pitch.semitone, e.id))
    used = {int(e.id[1:]) for e in evs if _is_id(e.id)}
    nxt = max(used) + 1 if used else 1
    mapping, seen, rows = {}, set(), []
    for e in evs:
        if _is_id(e.id) and e.id not in seen:
            new = e.id
        else:
            new = _fmt_id(nxt)
            nxt += 1
        seen.add(new)
        mapping[e.id] = new
        rows.append((new, e))
    retired = []
    for rid in doc.retired_ids:
        if _is_id(rid):
            retired.append(rid)
        elif rid in mapping:
            retired.append(mapping[rid])
    retired = sorted(set(retired) - seen)
    return rows, mapping, retired


def _cons_str(c) -> str:
    if not c:
        return "-"
    return ",".join(f"{k}={v}" for k, v in sorted(c.items()))


def _parse_cons(tok: str):
    if not tok or tok == "-":
        return None
    out = {}
    for part in tok.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        try:
            out[k.strip()] = int(v)
        except ValueError:
            out[k.strip()] = v.strip()
    return out or None


def _instrument_rows(doc) -> list:
    if doc.instruments:
        return [(i.id, i.type, i.subtype, i.section, _cons_str(getattr(i, "constraints", None)))
                for i in doc.instruments]
    return [("P1", "acoustic_grand_piano", None, None, "-")]


def _index(dic: dict, name: str, value) -> str:
    if value is None:
        return "-"
    table = dic[name]
    if value not in table:
        raise FormatError(f"值 {value!r} 不在字典 {name} 中")
    return str(table.index(value))


def dump(doc) -> str:
    """把 MSDocument 写成 `.ms` 文本（确定性：同数据两次字节一致）。"""
    errs = ev.validate(doc)
    if errs:
        raise FormatError("文档不合法，拒绝写出：" + "；".join(errs[:3]))

    dic = _build_dicts(doc)
    rows, mapping, retired = _assign_ids(doc)
    inst = _instrument_rows(doc)
    inst_index = {row[0]: n + 1 for n, row in enumerate(inst)}

    out = [f"{MAGIC} {FORMAT_VERSION}",
           f"channels {doc.channels}",
           f"piano_count {doc.piano_count}",
           f"constraint_mode {doc.constraint_mode}"]
    if getattr(doc, "trailing_silence_us", 0):
        out.append(f"trailing_silence_us {doc.trailing_silence_us}")
    out += ["",
            f"instruments {len(inst)}"]
    for iid, typ, sub, sec, cons in inst:
        out.append(" ".join([iid, typ, sub or "-", sec or "-", cons]))

    out.append("")
    for name in ("step", "rel", "state", "src", "scale", "exc", "kind"):
        out.append("dict " + name + " " + " ".join(dic[name]))
    if dic.get("curve"):
        out.append("dict curve " + " ".join(dic["curve"]))
    if dic.get("turn"):
        out.append("dict turn " + " ".join(dic["turn"]))

    # ── 事件流：音符 + 踏板控制事件，同一条时间线，按时间排序 ──
    #   · 同刻时踏板在前（它是状态，作用在那一刻起的音上）
    #   · 踏板行 8 列（带 id）或 7 列（旧写法无 id），与 16 列音符行靠列数区分
    timeline = []
    for new_id, e in rows:
        rel = _index(dic, "rel", e.release_state)
        p = e.pitch
        perm = "-" if e.dynamics.permille is None else str(e.dynamics.permille)
        # 音符只写**起始时间**；停止由独立的「止音事件」给出（见下面的 off 行）
        cols = [
            new_id,
            str(e.instrument_id),
            str(e.onset_us),
            str(p.semitone),
            perm,
            "1" if e.is_grace else "0",
            rel,
            _index(dic, "state", e.dynamics.state),
            _index(dic, "src", e.dynamics.src),
            _index(dic, "exc", e.excitation_type),
            _index(dic, "step", p.step),
            str(p.alter),
            str(p.octave),
            _index(dic, "scale", e.dynamics.scale),
            "-" if e.dynamics.calibration_ref is None else e.dynamics.calibration_ref,
        ]
        timeline.append((int(e.onset_us), 1, new_id, " ".join(cols)))
        # 止音事件：`<event_id> off <time_us> [kind] [ramp_us]`
        #   · kind 省略（`-`）= 按该乐器的机制查默认
        #   · ramp 是"止音缓冲"：从这一刻起衰减到无声的过程长度，不是硬切
        if e.release_us is not None and getattr(e, "release_state", "given") == "given":
            kind = getattr(e, "off_kind", None) or "-"
            ramp = int(getattr(e, "off_ramp_us", 0) or 0)
            timeline.append((int(e.release_us), 3, f"{new_id}#off",
                             f"{new_id} off {int(e.release_us)} {kind} "
                             f"{ramp if ramp else '-'}"))

    for p in doc.pedals:
        end = "-" if p.end_us is None else str(p.end_us)
        tgt = "-"
        if p.targets:
            tgt = ",".join(p.targets)
        cols = [str(p.instrument_id), _index(dic, "kind", p.kind), str(p.start_us),
                end, str(p.depth_permille), p.scope, tgt]
        pid = getattr(p, "id", None)
        if pid:
            cols.insert(0, pid)
        timeline.append((int(p.start_us), 0, pid or "~", " ".join(cols)))

    # 发声段也是事件流里的一行（带自己的起止时间）：
    #   `<event_id> vocal <index> <kind> <text> <binding> <tone> <turn> <lang> <start_us> <end_us>`
    onset_of = {e.id: int(e.onset_us) for e in doc.events}
    for x in sorted(getattr(doc, "segments", []),
                    key=lambda v: (v.event_id or v.structure_id, int(v.index))):
        eid = mapping.get(x.event_id, x.event_id) or "-"
        st = int(getattr(x, "onset_us", 0) or 0)
        en = int(getattr(x, "release_us", 0) or 0)
        cols = [eid, "vocal", str(x.index), x.kind, x.text,
                x.binding_id or x.structure_id, str(x.tone), str(x.turn),
                getattr(x, "lang", None) or "-", str(st), str(en)]
        timeline.append((onset_of.get(eid, st or 0), 2, f"{eid}#{int(x.index):03d}",
                         " ".join(cols)))

    timeline.sort(key=lambda x: (x[0], x[1], x[2]))
    out += ["", f"events {len(timeline)}"]
    for _on, _rank, _id, line in timeline:
        out.append(line)

    curves = sorted(doc.curves, key=lambda c: (c.instrument_id, c.param, c.time_us))
    if curves:
        out += ["", f"curves {len(curves)}"]
        for c in curves:
            out.append(" ".join([str(c.instrument_id), _index(dic, "curve", c.param),
                                 str(c.time_us), str(c.value), str(c.ramp)]))

    turns = sorted(doc.turns, key=lambda t: t.event_id)
    if turns:
        out += ["", f"turns {len(turns)}"]
        for t in turns:
            tid = mapping.get(t.event_id)
            if tid is None:
                raise FormatError(f"转折挂靠的事件不存在：{t.event_id}")
            out.append(" ".join([tid, _index(dic, "turn", t.kind), str(t.strength)]))

    out += ["", f"retired {len(retired)}"] + retired

    out += ["", f"gaps {len(doc.gaps)}"]
    for g in doc.gaps:
        code = g.get("code", "gap")
        sev = g.get("severity", "info")
        detail = str(g.get("detail", "")).replace("\n", " ")
        out.append(f"{code} {sev} {detail}".rstrip())

    return "\n".join(out) + "\n"


dumps = dump


# ── 读入 ─────────────────────────────────────────────────────

def parse(text: str):
    lines = text.splitlines()
    if not lines:
        raise FormatError("空文件")

    def die(msg, no=None):
        raise FormatError(f"第 {no} 行：{msg}" if no else msg)

    state, i = "header", 0
    version = channels = None
    piano_count, constraint_mode = 1, "single_piano"
    trailing_silence_us = 0
    inst: list[tuple[str, str, str | None]] = []
    dic: dict[str, list[str]] = {}
    events, pedals, retired, gaps, curves, turns, segments = [], [], [], [], [], [], []
    note_offs = []
    expect = 0

    while i < len(lines):
        raw = lines[i]
        no = i + 1
        line = raw.strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        parts = line.split()
        head = parts[0]

        if state == "header":
            if head == MAGIC:
                if len(parts) < 2 or not parts[1].isdigit():
                    die("缺少格式版本", no)
                version = int(parts[1])
                if version != FORMAT_VERSION:
                    die(f"不支持的格式版本：{version}", no)
            elif head == "channels":
                channels = parts[1] if len(parts) > 1 else die("channels 缺值", no)
            elif head == "piano_count":
                piano_count = int(parts[1])
            elif head == "constraint_mode":
                constraint_mode = parts[1]
            elif head == "trailing_silence_us":
                trailing_silence_us = int(parts[1])
            elif head == "instruments":
                expect = int(parts[1])
                state = "instruments"
            elif head == "dict":
                if len(parts) < 3:
                    die("dict 行缺内容", no)
                dic[parts[1]] = parts[2:]
            else:
                die(f"未知的头部行：{head}", no)
        elif state == "instruments":
            if len(parts) < 2:
                die("乐器行缺字段", no)
            sub = parts[2] if len(parts) > 2 and parts[2] != "-" else None
            sec = parts[3] if len(parts) > 3 and parts[3] != "-" else None
            cons = _parse_cons(parts[4]) if len(parts) > 4 else None
            inst.append((parts[0], parts[1], sub, sec, cons))
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "body":
            if head == "events":
                expect = int(parts[1])
                state = "events" if expect else "body"
            elif head == "pedals":
                expect = int(parts[1])
                state = "pedals" if expect else "body"
            elif head == "lyrics":
                # 歌词块已移除；`lyrics 0`（空块）仍容忍，方便读旧文件
                if int(parts[1]):
                    die("lyrics 区块已移除：人声改用 vocal 段行（见 docs/reference/旧档案线格式.md §3.3d）", no)
                state = "body"
            elif head == "curves":
                expect = int(parts[1])
                state = "curves" if expect else "body"
            elif head == "vocal":
                # 旧块：只有 8 列的段行还能读（改写为事件流里的 vocal 行）
                expect = int(parts[1])
                state = "vocal" if expect else "body"
            elif head == "turns":
                expect = int(parts[1])
                state = "turns" if expect else "body"
            elif head == "retired":
                expect = int(parts[1])
                state = "retired" if expect else "body"
            elif head == "gaps":
                expect = int(parts[1])
                state = "gaps" if expect else "body"
            elif head == "dict":
                dic[parts[1]] = parts[2:]
            else:
                die(f"未知区块：{head}", no)
        elif state == "events":
            if len(parts) >= 2 and parts[1] == "vocal":
                # 发声段也是事件流里的一行（带自己的起止时间）
                segments.append(_segment_from_parts(parts, no))
            elif len(parts) in (3, 4, 5) and parts[1] == "off":
                # 止音事件：`<event_id> off <time_us> [kind] [ramp_us]`
                kind = parts[3] if len(parts) > 3 else "-"
                ramp = parts[4] if len(parts) > 4 else "-"
                note_offs.append((parts[0], int(parts[2]),
                                  None if kind in ("-", "") else kind,
                                  0 if ramp in ("-", "") else int(ramp)))
            elif len(parts) in (7, 8) and (len(parts) == 7 or parts[0].startswith("D")):
                # 事件流里的踏板控制事件（7 列无 id / 8 列带 id）
                pedals.append(_pedal_from_parts(parts, dic, no))
            elif len(parts) not in (15, 16):
                die("事件行应为 15 列（音符，含起始时间）/ 16 列（旧：含释放）/ "
                    "7–8 列（踏板控制事件）/ 11 列（发声段）/ 3 列（止音事件 off）", no)
            else:
                legacy = len(parts) == 16
                if legacy:
                    (eid, piano, onset, rel_us, semi, perm, grace,
                     rel_i, st_i, src_i, exc_i, step_i, alter, octave, scale_i, cal) = parts
                else:
                    (eid, piano, onset, semi, perm, grace,
                     rel_i, st_i, src_i, exc_i, step_i, alter, octave, scale_i, cal) = parts
                    rel_us = "-"
                if not _is_id(eid):
                    die(f"id 必须是 L+8 位数字：{eid}", no)
                try:
                    pitch = ev.Pitch(dic["step"][int(step_i)], int(alter), int(octave), int(semi))
                    dyn = ev.Dynamics(
                        state=dic["state"][int(st_i)],
                        permille=None if perm == "-" else int(perm),
                        scale=dic["scale"][int(scale_i)] if scale_i != "-" else None,
                        calibration_ref=None if cal == "-" else cal,
                        src=dic["src"][int(src_i)] if src_i != "-" else None,
                    )
                    events.append(ev.Event(
                        id=eid, instrument_id=int(piano), onset_us=int(onset), pitch=pitch,
                        excitation_type=dic["exc"][int(exc_i)],
                        release_us=None if rel_us == "-" else int(rel_us),
                        release_state=dic["rel"][int(rel_i)],
                        dynamics=dyn, is_grace=grace == "1"))
                except (IndexError, KeyError, ValueError) as exc:
                    die(f"事件行无法解析：{exc}", no)
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "pedals":
            # 旧文件：独立的 pedals 区块（仍然读得进，写回时并入事件流）
            pedals.append(_pedal_from_parts(parts, dic, no))
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "curves":
            if len(parts) != 5:
                die("曲线行应为 5 列（inst param time value ramp）", no)
            iid, param_i, t_us, val, ramp = parts
            curves.append(ev.CurvePoint(int(iid), dic["curve"][int(param_i)],
                                        int(t_us), int(val), int(ramp)))
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "turns":
            if len(parts) != 3:
                die("转折行应为 3 列（event_id kind strength）", no)
            turns.append(ev.TurnPoint(parts[0], dic["turn"][int(parts[1])], int(parts[2])))
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "vocal":
            # 旧块：只认 8/7 列的段行（发声行已移除）
            segments.append(_segment_from_parts(parts, no))
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "retired":
            retired.append(parts[0])
            expect -= 1
            if expect == 0:
                state = "body"
        elif state == "gaps":
            if len(parts) < 2:
                die("gap 行至少 2 列", no)
            code, sev = parts[0], parts[1]
            detail = line.split(None, 2)[2] if len(parts) > 2 else ""
            gaps.append({"code": code, "severity": sev, "detail": detail})
            expect -= 1
            if expect == 0:
                state = "body"
        i += 1

    if state not in ("body",):
        raise FormatError(f"文件在 {state} 区块中途结束（还应读 {expect} 行）")
    if version is None:
        raise FormatError("缺少 ms 魔数行")
    if channels is None:
        raise FormatError("缺少 channels 行")
    for need in ("step", "rel", "state", "src", "scale", "exc", "kind"):
        if need not in dic:
            raise FormatError(f"缺少字典：{need}")

    # 止音事件 → 回填到对应音的 release_us（音符行只写起始时间）
    if note_offs:
        from dataclasses import replace as _replace
        by_id = {e.id: n for n, e in enumerate(events)}
        seen_off = set()
        for eid, t, kind, ramp in note_offs:
            if eid in seen_off:
                raise FormatError(f"{eid} 有重复的止音事件")
            seen_off.add(eid)
            idx = by_id.get(eid)
            if idx is None:
                raise FormatError(f"止音事件指向不存在的音：{eid}")
            cur = events[idx]
            if cur.release_us is not None:
                raise FormatError(f"{eid} 既有内联释放时间又有止音事件：二选一")
            events[idx] = _replace(cur, release_us=t, off_kind=kind, off_ramp_us=ramp)

    doc = ev.MSDocument(
        piano_count=piano_count, constraint_mode=constraint_mode,
        trailing_silence_us=trailing_silence_us,
        events=events, pedals=pedals, gaps=gaps, retired_ids=retired,
        curves=curves, turns=turns, segments=segments,
        channels=channels,
        instruments=[ev.Instrument(i, t, sub, sec, cons) for i, t, sub, sec, cons in inst],
    )
    errs = ev.validate(doc)
    if errs:
        raise FormatError("读入的文档不合法：" + "；".join(errs[:3]))
    return doc


loads = parse


def save(doc, path) -> Path:
    """原子写：先写临时文件再替换，读者永远看不到半截文件。"""
    import os
    import tempfile

    p = Path(path)
    text = dump(doc)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return p


_LOAD_CACHE: dict = {}


def load(path):
    """按 (mtime, size) 缓存解析结果：两条派生链共享同一份文档。"""
    p = Path(path)
    st = p.stat()
    key = (str(p.resolve()), int(st.st_mtime_ns), st.st_size)
    hit = _LOAD_CACHE.get(key)
    if hit is not None:
        return hit
    doc = parse(p.read_text(encoding="utf-8"))
    _LOAD_CACHE.clear()
    _LOAD_CACHE[key] = doc
    return doc


def fingerprint(doc) -> str:
    """内容指纹：派生文件可据此判断是否过期。"""
    import hashlib

    return hashlib.sha256(dump(doc).encode("utf-8")).hexdigest()[:16]


def iter_events(path):
    """流式读事件：只把事件行逐条产出，不整份建模（大文件用）。"""
    dic: dict[str, list[str]] = {}
    inst_count = 0
    in_events, remaining = False, 0
    for no, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("dict "):
            parts = line.split()
            dic[parts[1]] = parts[2:]
            continue
        if line.startswith("events "):
            remaining = int(line.split()[1])
            in_events = remaining > 0
            continue
        if not in_events:
            continue
        parts = line.split()
        remaining -= 1                    # 事件流的每一行都要计入（音符/踏板/止音/发声段）
        if remaining == 0:
            in_events = False
        if len(parts) in (7, 8) and (len(parts) == 7 or parts[0].startswith("D")):
            continue                      # 踏板事件：流式读只出音
        if len(parts) >= 2 and parts[1] == "off":
            continue                      # 止音事件：流式读只出音
        if len(parts) >= 2 and parts[1] == "vocal":
            continue                      # 发声段：流式读只出音
        legacy = len(parts) == 16
        if len(parts) not in (15, 16):
            raise FormatError(f"第 {no} 行：事件行应为 15 列（音符）或 16 列（旧格式）")
        if legacy:
            (eid, piano, onset, rel_us, semi, perm, grace,
             rel_i, st_i, src_i, exc_i, step_i, alter, octave, scale_i, cal) = parts
        else:
            (eid, piano, onset, semi, perm, grace,
             rel_i, st_i, src_i, exc_i, step_i, alter, octave, scale_i, cal) = parts
            rel_us = "-"
        yield ev.Event(
            id=eid, instrument_id=int(piano), onset_us=int(onset),
            pitch=ev.Pitch(dic["step"][int(step_i)], int(alter), int(octave), int(semi)),
            excitation_type=dic["exc"][int(exc_i)],
            release_us=None if rel_us == "-" else int(rel_us),
            release_state=dic["rel"][int(rel_i)],
            dynamics=ev.Dynamics(
                state=dic["state"][int(st_i)],
                permille=None if perm == "-" else int(perm),
                scale=dic["scale"][int(scale_i)] if scale_i != "-" else None,
                calibration_ref=None if cal == "-" else cal,
                src=dic["src"][int(src_i)] if src_i != "-" else None),
            is_grace=grace == "1")
