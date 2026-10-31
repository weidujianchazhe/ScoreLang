# -*- coding: utf-8 -*-
"""MS 模型的 Markdown 文档格式（内部工程区）。

目标：把 MSDocument 完整地写成**人可读、AI 可写**的 Markdown；
不替代 .ms 线格式（`.ms` 仍保留），只是内部工程区的新默认文档格式。

格式（v0，待确认）：

    # MS 乐谱模型 · 水镜
    ---
    ms: 1
    channels: per_instance
    piano_count: 1
    constraint_mode: single_piano
    trailing_silence_us: 0
    bpm: 63        # 呈现参数，不属 MS
    meter: 4/4     # 呈现参数，不属 MS
    ---

    ## 乐器
    | id | type | subtype | section |
    |---|---|---|---|
    | P1 | acoustic_grand_piano | - | - |

    ## 音符
    | id | inst | onset_us | release_us | pitch | permille | state | src | exc | grace | off | ramp |
    |---|---|---|---|---|---|---|---|---|---|---|---|
    | w1 | 1 | 0 | 500000 | C4 | 800 | VALUE | composed | impulse | 0 | - | 0 |

    ## 踏板
    | id | inst | kind | start_us | end_us | depth | scope | targets |

    ## 转折 / 曲线 / 人声段 / 缺口
    - event=w1 kind=retrigger strength=800
"""
from __future__ import annotations

import ms_model as ev
import ms_semantics as ms
import ms_validate as _validate

NONE = "-"


def _tok(v) -> str:
    if v is None or v == "":
        return NONE
    return str(v)


def _num(v):
    return None if v is None or v == NONE else int(v)


def _pitch(text: str):
    """C4 / C#4 / Bb3 → Pitch（拼写与半音一致）。"""
    _PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    s = text.strip()
    letter = s[0].upper()
    if letter not in _PC:
        raise ValueError(f"非法音名：{text!r}")
    i, alter = 1, 0
    while i < len(s) and s[i] in "#b♯♭":
        alter += 1 if s[i] in "#♯" else -1
        i += 1
    octave = int(s[i:]) if s[i:] else 4
    semi = 12 * (octave + 1) + _PC[letter] + alter
    if not (ev.KEY_MIN <= semi <= ev.KEY_MAX):
        raise ValueError(f"{ev.ERR_PITCH_RANGE}：{text!r}")
    return ev.Pitch(letter, alter, octave, semi)


def dumps(doc) -> str:
    """MSDocument → Markdown 文本。"""
    out = ["# MS 乐谱模型" + (f" · {getattr(doc, 'title', '')}" if getattr(doc, "title", "") else ""),
           "", "---",
           f"ms: {getattr(doc, 'schema_version', '1')}",
           f"channels: {doc.channels}",
           f"piano_count: {doc.piano_count}",
           f"constraint_mode: {doc.constraint_mode}",
           f"trailing_silence_us: {getattr(doc, 'trailing_silence_us', 0)}",
           "bpm: -", "meter: -", "---", ""]

    out += ["## 乐器",
            "| id | type | subtype | section |",
            "|---|---|---|---|"]
    for ins in (doc.instruments or [ev.Instrument("P1", "acoustic_grand_piano")]):
        out.append("| " + " | ".join([_tok(ins.id), _tok(ins.type),
                                      _tok(ins.subtype), _tok(ins.section)]) + " |")
    out.append("")

    out += ["## 音符",
            "| id | inst | onset_us | release_us | pitch | permille | state | src | scale | calib | exc | grace | off | ramp |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in sorted(doc.events, key=lambda x: (x.onset_us, x.id)):
        p = e.pitch
        pitch = f"{p.step}{'#' * max(0, p.alter)}{'b' * max(0, -p.alter)}{p.octave}"
        out.append("| " + " | ".join([
            _tok(e.id), str(e.instrument_id), str(e.onset_us),
            _tok(e.release_us), pitch,
            _tok(e.dynamics.permille), _tok(e.dynamics.state),
            _tok(e.dynamics.src), _tok(e.dynamics.scale),
            _tok(e.dynamics.calibration_ref), _tok(e.excitation_type),
            "1" if e.is_grace else "0",
            _tok(e.off_kind), str(getattr(e, "off_ramp_us", 0)),
        ]) + " |")
    out.append("")

    out += ["## 踏板",
            "| id | inst | kind | start_us | end_us | depth | scope | targets |",
            "|---|---|---|---|---|---|---|---|"]
    for p in doc.pedals:
        out.append("| " + " | ".join([
            _tok(getattr(p, "id", None)), str(p.instrument_id), p.kind,
            str(p.start_us), _tok(p.end_us), str(p.depth_permille),
            p.scope, _tok(",".join(p.targets) if p.targets else None),
        ]) + " |")
    out.append("")

    out += ["## 转折"]
    for t in doc.turns:
        out.append(f"- event={t.event_id} kind={t.kind} strength={t.strength}"
                   + (f" seg={t.seg_index}" if t.seg_index is not None else ""))
    out += ["", "## 曲线"]
    for c in doc.curves:
        out.append(f"- inst={c.instrument_id} param={c.param} time_us={c.time_us} "
                   f"value={c.value} ramp={c.ramp}")
    out += ["", "## 人声段"]
    for s in doc.segments:
        out.append(f"- event={_tok(s.event_id)} index={s.index} kind={s.kind} "
                   f"text={s.text} tone={s.tone} binding={_tok(s.binding_id or s.structure_id)} "
                   f"turn={s.turn} lang={_tok(s.lang)} onset_us={s.onset_us} "
                   f"release_us={s.release_us}")
    out += ["", "## 缺口"]
    for g in doc.gaps:
        if isinstance(g, dict):
            out.append(f"- code={_tok(g.get('code'))} severity={_tok(g.get('severity'))} "
                       f"detail={_tok(g.get('detail'))}")
    out.append("")
    return "\n".join(out)


def _kv(line: str) -> dict:
    body = line.lstrip("-").strip()
    out = {}
    for part in body.split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def _rows(lines, header_count):
    rows = []
    started = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not started:
                started = True
                continue
            if all(c and set(c) <= set("-: ") for c in cells):
                continue
            if len(cells) >= header_count:
                rows.append(cells)
    return rows


def loads(text: str) -> "ev.MSDocument":  # noqa: F811
    """Markdown → MSDocument（加载即校验）。"""
    lines = text.splitlines()
    # front matter
    meta = {}
    i = 0
    while i < len(lines) and not lines[i].strip().startswith("---"):
        i += 1
    if i < len(lines):
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("---"):
            if ":" in lines[i]:
                k, v = lines[i].split(":", 1)
                meta[k.strip()] = v.strip()
            i += 1
    title = ""
    if lines and (lines[0].startswith("# MS 乐谱模型") or lines[0].startswith("# MS 文档")):
        title = lines[0].split("·", 1)[1].strip() if "·" in lines[0] else ""

    def section(name):
        start = None
        for idx, ln in enumerate(lines):
            if ln.strip() == "## " + name:
                start = idx + 1
                break
        if start is None:
            return []
        out = []
        for ln in lines[start:]:
            if ln.strip().startswith("## "):
                break
            out.append(ln)
        return out

    instruments = []
    for cells in _rows(section("乐器"), 4):
        iid, typ, sub, sec = cells[:4]
        instruments.append(ev.Instrument(
            iid, typ, None if sub == NONE else sub,
            None if sec == NONE else sec))
    events = []
    for cells in _rows(section("音符"), 14):
        (eid, inst, onset, release, pitch, perm, state, src, scale,
         calib, exc, grace, off, ramp) = cells[:14]
        events.append(ev.Event(
            id=eid, instrument_id=int(inst), onset_us=int(onset),
            release_us=_num(release), pitch=_pitch(pitch),
            release_state="given" if release != NONE else "sustaining",
            dynamics=ev.Dynamics(
                state if state != NONE else ms.NOT_PROVIDED,
                _num(perm), None if scale == NONE else scale,
                None if calib == NONE else calib,
                None if src == NONE else src),
            excitation_type=exc if exc != NONE else "impulse",
            is_grace=(grace == "1"),
            off_kind=None if off == NONE else off,
            off_ramp_us=int(ramp) if ramp not in ("", NONE) else 0,
        ))
    pedals = []
    for cells in _rows(section("踏板"), 8):
        pid, inst, kind, start, end, depth, scope, tgt = cells[:8]
        targets = None
        if tgt != NONE:
            targets = tuple(tgt.split(","))
        pedals.append(ev.PedalSegment(
            instrument_id=int(inst), kind=kind, start_us=int(start),
            end_us=_num(end), depth_permille=int(depth), scope=scope,
            targets=targets, id=None if pid == NONE else pid))
    turns = []
    for ln in section("转折"):
        if not ln.strip().startswith("-"):
            continue
        kv = _kv(ln)
        turns.append(ev.TurnPoint(event_id=kv.get("event", ""),
                                  kind=kv.get("kind", "retrigger"),
                                  strength=int(kv.get("strength", 1000)),
                                  seg_index=int(kv["seg"]) if "seg" in kv else None))
    curves = []
    for ln in section("曲线"):
        if not ln.strip().startswith("-"):
            continue
        kv = _kv(ln)
        curves.append(ev.CurvePoint(instrument_id=int(kv.get("inst", 1)),
                                    param=kv.get("param", "dynamics"),
                                    time_us=int(kv.get("time_us", 0)),
                                    value=int(kv.get("value", 0)),
                                    ramp=int(kv.get("ramp", 0))))
    segments = []
    for ln in section("人声段"):
        if not ln.strip().startswith("-"):
            continue
        kv = _kv(ln)
        segments.append(ev.VoiceSegment(
            structure_id=kv.get("binding", "B00001"), index=int(kv.get("index", 0)),
            kind=kv.get("kind", "nucleus"), text=kv.get("text", ""),
            tone=int(kv.get("tone", 0)), onset_us=int(kv.get("onset_us", 0)),
            release_us=int(kv.get("release_us", 0)),
            turn=int(kv.get("turn", 0)), event_id=kv.get("event", ""),
            binding_id=kv.get("binding", "B00001"),
            lang=None if kv.get("lang") == NONE else kv.get("lang")))
    gaps = []
    for ln in section("缺口"):
        if not ln.strip().startswith("-"):
            continue
        kv = _kv(ln)
        gaps.append({"code": kv.get("code"), "severity": kv.get("severity"),
                     "detail": None if kv.get("detail") == NONE else kv.get("detail")})

    doc = ev.MSDocument(
        piano_count=int(meta.get("piano_count", 1) or 1),
        constraint_mode=meta.get("constraint_mode", "single_piano"),
        events=events, pedals=pedals,
        gaps=gaps, retired_ids=[], channels=meta.get("channels", "per_instance"),
        instruments=instruments, curves=curves, turns=turns,
        trailing_silence_us=int(meta.get("trailing_silence_us", 0) or 0),
        segments=segments)
    errs = _validate.validate(doc)
    if errs:
        raise ValueError("MD 文档不合法：" + "；".join(errs[:5]))
    return doc


def save(doc, path) -> str:
    from pathlib import Path as _P
    p = _P(path)
    p.write_text(dumps(doc), encoding="utf-8")
    return str(p)


def load(path):
    from pathlib import Path as _P
    return loads(_P(path).read_text(encoding="utf-8"))


__all__ = ["dumps", "dumps_authoring", "loads", "loads_authoring",
           "lint",
           "compile_song", "analyze_authoring", "save", "load"]


# ── 标签式作者格式（[n1]）→ 编译成 MSDocument ─────────────────
import re as _re

# 力度等级**只认写谱层的统一表**（perform/ms_dynamics_levels.py，锚点 1000‰ ≡ vel 64）。
# 这里不得再私下维护一份数值表：两份表一旦漂移，md 写出来的谱整体偏轻，
# 且 ff 与 fff 会落到同一个值。
import ms_dynamics_levels as _dl

_LEVEL_PM = _dl.PERMILLE
_NOTE_RE = _re.compile(
    r"^\[(?P<tag>[A-Za-z_][\w]*)\]\s*(?P<inst>\d+)\s*:\s*"
    r"(?P<pitch>[A-Ga-g][#b♯♭]*\d+)\s*@\s*(?P<beat>[0-9.]+)\s*\+\s*"
    r"(?P<beats>[0-9.]+)(?:\s+(?P<level>[a-z]+))?$")


def _pitch_str(p) -> str:
    return (p.step + "#" * max(0, p.alter) + "b" * max(0, -p.alter)
            + str(p.octave))


def loads_authoring(text: str) -> "ev.MSDocument":
    """AI 写的标签式 MD → MS（自动分配 L00000001 稳定 id）。"""
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    bpm, meter = 120.0, (4, 4)
    insts = []
    notes = []          # (tag, inst, pitch, beat, beats, level)
    actions = []        # ("turn", tag, kind, strength) / ("pedal", inst, kind, s, e)
    in_notes = False
    for raw in lines:
        line = raw.strip()
        low = line.lower()
        if low.startswith("- bpm:"):
            bpm = float(line.split(":", 1)[1])
        elif low.startswith("- meter:"):
            a, b = line.split(":", 1)[1].strip().split("/")
            meter = (int(a), int(b))
        elif low.startswith("- note:") or low.startswith("## 乐谱"):
            in_notes = line.startswith("```")
        elif line.startswith("```"):
            in_notes = not in_notes
        elif in_notes:
            m = _NOTE_RE.match(line)
            if m:
                notes.append((m.group("tag"), int(m.group("inst")),
                              m.group("pitch"), float(m.group("beat")),
                              float(m.group("beats")), m.group("level")))
        elif low.startswith("- turn:"):
            body = line.split(":", 1)[1].strip().split()
            actions.append(("turn", body[0], body[1],
                            int(body[2]) if len(body) > 2 else 1000))
        elif low.startswith("- pedal:"):
            body = line.split(":", 1)[1].strip().split()
            actions.append(("pedal", int(body[0]), body[1],
                            float(body[2]), float(body[3])))
        elif low.startswith("- curve:"):
            body = line.split(":", 1)[1].strip().split()
            nums = [float(x) for x in body[2:]]
            pts = [(nums[k], int(nums[k + 1])) for k in range(0, len(nums) - 1, 2)]
            actions.append(("curve", int(body[0]), body[1], pts))
        elif line.startswith("- ") and ":" in line and not low.startswith("- bpm"):
            body = line[2:].strip()
            head, typ = body.split(":", 1)
            head = head.strip().lstrip("Pp")
            if head.isdigit():
                insts.append((int(head), typ.strip()))

    if not insts:
        insts = [(1, "piano")]
    try:
        from ms.task import resolve_instrument as _ri
        insts = [(i, _ri(t)) for i, t in insts]
    except Exception:  # noqa: BLE001 —— 已是类型码时保持原样
        pass
    upb = 60_000_000 / bpm
    events, segs, mapping, turns = [], [], {}, []
    for i, (tag, iid, pitch, beat, beats, level) in enumerate(notes, 1):
        eid = f"L{i:08d}"
        mapping[tag] = eid
        onset = int(round(beat * upb))
        release = int(round((beat + beats) * upb))
        events.append(ev.Event(
            id=eid, instrument_id=iid, onset_us=onset, release_us=release,
            pitch=_pitch(pitch),
            dynamics=ev.Dynamics(
                "VALUE" if level else ms.NOT_PROVIDED,
                _LEVEL_PM.get(level, 800) if level else None,
                "relative_permille" if level else None,
                "md_compiled" if level else None, "composed")))
    for act in actions:
        if act[0] == "turn" and act[1] in mapping:
            turns.append(ev.TurnPoint(event_id=mapping[act[1]],
                                      kind=act[2], strength=act[3]))
    pedals = []
    for act in actions:
        if act[0] == "pedal":
            start = int(round(act[3] * upb))
            end = int(round(act[4] * upb))
            pedals.append(ev.PedalSegment(
                instrument_id=act[1], kind=act[2], start_us=start,
                end_us=end, depth_permille=1000))
    pedals = ev.assign_pedal_ids(pedals)
    curves = []
    for act in actions:
        if act[0] == "curve":
            curves = [ev.CurvePoint(instrument_id=act[1], param=act[2],
                                    time_us=int(round(b * upb)), value=v,
                                    ramp=0 if idx == 0 else 1)
                      for idx, (b, v) in enumerate(act[3])]
    doc = ev.MSDocument(
        piano_count=max(1, len(insts)), constraint_mode=("single_piano" if len(insts) == 1 else "n_pianos"),
        instruments=[ev.Instrument(f"P{i}", t) for i, t in insts],
        events=events, pedals=pedals, turns=turns, curves=curves)
    errs = _validate.validate(doc)
    if errs:
        raise ValueError("标签式 MD 编译失败：" + "；".join(errs[:5]))
    return doc


def dumps_authoring(doc, *, bpm: float = 120.0, meter=(4, 4)) -> str:
    """MSDocument → 标签式作者 MD（可再编译回来）。"""
    upb = 60_000_000 / bpm
    tags = {e.id: f"n{i}" for i, e in enumerate(
        sorted(doc.events, key=lambda x: (x.onset_us, x.id)), 1)}
    out = [f"# {getattr(doc, 'title', '') or '未命名'}", "",
           f"- BPM: {bpm:g}", f"- Meter: {meter[0]}/{meter[1]}", "",
           "## 乐器", ""]
    for ins in doc.instruments or [ev.Instrument("P1", "acoustic_grand_piano")]:
        num = str(ins.id).lstrip("P")
        out.append(f"- {num}: {ins.type}")
    out += ["", "## 乐谱", "", "```notes"]
    for e in sorted(doc.events, key=lambda x: (x.onset_us, x.id)):
        beat = round(e.onset_us / upb, 3)
        beats = round(((e.release_us or e.onset_us) - e.onset_us) / upb, 3)
        level = ""
        if e.dynamics.permille:
            level = " " + _dl.permille_to_nearest_level(e.dynamics.permille)[0]
        out.append(f"[{tags[e.id]}] {e.instrument_id}: {_pitch_str(e.pitch)} "
                   f"@{beat:g}+{beats:g}{level}")
    out += ["```", "", "## 动作", ""]
    for t in doc.turns:
        if t.event_id in tags:
            out.append(f"- turn: {tags[t.event_id]} {t.kind} {t.strength}")
    for p in doc.pedals:
        s = round(p.start_us / upb, 3)
        e_ = round((p.end_us or p.start_us) / upb, 3)
        out.append(f"- pedal: {p.instrument_id} {p.kind} {s:g} {e_:g}")
    return "\n".join(out) + "\n"


_orig_loads = loads


def loads(text: str):  # noqa: F811 —— 自动识别标签式/表格式
    if "```notes" in text or _re.search(r"^\[[A-Za-z_][\w]*\]\s*\d+\s*:", text, _re.M):
        return loads_authoring(text)
    return _orig_loads(text)


def _meta(text: str):
    bpm, meter = 120.0, (4, 4)
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("- bpm:"):
            bpm = float(line.split(":", 1)[1])
        elif low.startswith("- meter:"):
            a, b = line.split(":", 1)[1].strip().split("/")
            meter = (int(a), int(b))
    return bpm, meter


def compile_song(text: str):
    """标签式 MD → Song（编译 + 校验），供报告/导出使用。"""
    from ms.task import Song
    doc = loads_authoring(text)
    bpm, meter = _meta(text)
    return Song(doc, bpm=bpm, meter=meter)


def analyze_authoring(text: str, *, intent=None) -> dict:
    """作者格式 → 编译 → S02 报告（含诊断）；AI 据此改 .md 再编译。"""
    import ms
    song = compile_song(text)
    report = ms.report(song, intent=intent)
    return {"song": song, "report": report,
            "diagnosis": report.get("diagnosis") or {},
            "summary": report.get("summary") or {}}


def lint(text: str) -> dict:
    """写之前快速检查：返回 {ok, issues:[{line,msg}]}，不抛异常。"""
    issues = []
    in_notes, n_notes = False, 0
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("```"):
            in_notes = not in_notes
            continue
        if in_notes and s.startswith("["):
            n_notes += 1
            if not _NOTE_RE.match(s):
                issues.append({"line": i, "msg": f"音符行格式不对：{s!r}"})
    if n_notes == 0:
        issues.append({"line": None, "msg": "没有音符行（## 乐谱 代码块为空）"})
    tags = _re.findall(r"^\[([A-Za-z_][\w]*)\]", text, _re.M)
    seen = set()
    for tag in tags:
        if tag in seen:
            issues.append({"line": None, "msg": f"标签重复：{tag}"})
        seen.add(tag)
    try:
        loads_authoring(text)
    except ValueError as exc:
        msg = str(exc)
        m = _re.search(r"第 (\d+) 行", msg)
        issues.append({"line": int(m.group(1)) if m else None, "msg": msg})
    return {"ok": not issues, "issues": issues}


_orig_loads_for_lint = loads
