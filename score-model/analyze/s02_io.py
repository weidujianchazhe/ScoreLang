# -*- coding: utf-8 -*-
"""`.s02` 文件读写（s02-2）：行式文本，一行一条记录。

设计口径见 `docs/spec/S02认知引擎设计备忘.md`：
  · 只存**结论**（谁、在哪、属于什么），不存关系推导；
  · 可 diff、可 grep、可往返（`dump(parse(x)) == x`）；
  · 与 `.ms` 同词法：空格分列、`#` 注释、`-` 表示缺省。

块顺序（固定）：头 → instruments → notes → rests → pedals → actions → curves → segments
             → ties / tuplets / articulations / words（空块整块不写）。
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import model_v02 as mv

MAGIC = "s02"
FORMAT_VERSION = 2


class FormatError(ValueError):
    """`.s02` 文本不合法。"""


def _die(msg, no=None):
    raise FormatError(f"第 {no} 行：{msg}" if no else msg)


def _i(s: str, default=None):
    return default if s in ("-", "") else int(s)


def _s(v, default="-"):
    return default if v is None else str(v)


# ── 写出 ─────────────────────────────────────────────────

def dump(score: "mv.ScoreV02") -> str:
    """ScoreV02 → `.s02` 文本。同一份数据两次写出字节一致。"""
    errs = score.validate()
    if errs:
        raise FormatError("文档不合法，拒绝写出：" + "；".join(errs[:3]))

    out = [f"{MAGIC} {FORMAT_VERSION}",
           f"grid {score.grid_units_per_quarter}",
           f"meter {score.time_beats} {score.time_beat_type}",
           f"key_fifths {score.key_fifths}"]
    if score.title:
        out.append("title " + score.title.replace("\n", " "))

    inst = list(score.instruments)
    out += ["", f"instruments {len(inst)}"]
    for i in inst:
        out.append(" ".join([i["id"], i["type"], _s(i.get("subtype")), _s(i.get("section"))]))

    notes = sorted(score.notes, key=lambda n: (n.onset, n.voice, n.id))
    out += ["", f"notes {len(notes)}"]
    for n in notes:
        p = n.pitch
        out.append(" ".join([
            n.id, str(n.instrument_id), n.voice, n.staff,
            str(n.onset), str(n.duration),
            p.step, str(p.alter), str(p.octave),
            _s(getattr(n, "dynamics_permille", None)),
            getattr(n, "release_state", "given"),
            "1" if n.is_grace else "0"]))

    rests = sorted(score.rests, key=lambda r: (r.onset, r.voice, r.id))
    if rests:
        out += ["", f"rests {len(rests)}"]
        for r in rests:
            out.append(" ".join([r.id, r.voice, r.staff,
                                 str(r.onset), str(r.duration)]))

    ped = sorted(score.pedal_marks, key=lambda p: (p.onset, p.id))
    if ped:
        out += ["", f"pedals {len(ped)}"]
        for p in ped:
            tgt = ",".join(p.target_scope) if p.target_scope else "-"
            out.append(" ".join([p.id, p.pedal_type, p.action_notated, str(p.onset),
                                 str(p.measure), _s(getattr(p, "depth_permille", None)), tgt]))

    acts = sorted(score.actions, key=lambda a: (a.target_id, a.id))
    if acts:
        out += ["", f"actions {len(acts)}"]
        for a in acts:
            out.append(" ".join([a.id, a.kind, a.target_id, str(a.strength)]))

    curves = sorted(score.curves, key=lambda c: (c.instrument_id, c.param, c.time_us))
    if curves:
        out += ["", f"curves {len(curves)}"]
        for c in curves:
            out.append(" ".join([str(c.instrument_id), c.param, str(c.time_us),
                                 str(c.value), str(c.ramp)]))

    segs = sorted(score.segments, key=lambda s: (s.event_id, s.index))
    if segs:
        out += ["", f"segments {len(segs)}"]
        for s in segs:
            out.append(" ".join([s.event_id, str(s.index), s.kind, s.text, s.binding_id,
                                 str(s.tone), str(s.turn), _s(s.lang),
                                 str(s.onset_us), str(s.end_us)]))

    if score.tie_groups:
        out += ["", f"ties {len(score.tie_groups)}"]
        for g in score.tie_groups:
            out.append(" ".join([g.id, g.voice] + list(g.member_ids)))
    if score.tuplets:
        out += ["", f"tuplets {len(score.tuplets)}"]
        for t in score.tuplets:
            out.append(" ".join([t.id, f"{t.ratio[0]}:{t.ratio[1]}",
                                 _s(t.parent_id)] + list(t.member_ids)))
    if score.articulations:
        out += ["", f"articulations {len(score.articulations)}"]
        for a in score.articulations:
            out.append(" ".join([a.id, a.kind] + list(a.target_ids)))
    if score.words:
        out += ["", f"words {len(score.words)}"]
        for w in score.words:
            out.append(" ".join([str(w.get("onset", 0)), str(w.get("text", ""))]))
    return "\n".join(out) + "\n"


dumps = dump


# ── 读入 ─────────────────────────────────────────────────

def parse(text: str) -> "mv.ScoreV02":
    """解析 `.s02` 文本；任何结构问题都抛 `FormatError`。"""
    try:
        return _parse_inner(text)
    except FormatError:
        raise
    except (ValueError, IndexError, KeyError) as e:      # 列数/数字/字典问题统一成格式错误
        raise FormatError(f"格式错误（{type(e).__name__}: {e}）") from None


def _parse_inner(text: str) -> "mv.ScoreV02":
    lines = text.splitlines()
    score = mv.ScoreV02()
    state, expect = "head", 0
    dic = {}
    no = 0
    seen_version = None

    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()

        if state == "head":
            head = parts[0]
            if head == MAGIC:
                seen_version = int(parts[1])
                if seen_version > FORMAT_VERSION:
                    _die(f"不支持的文件版本 {seen_version}（本程序支持到 {FORMAT_VERSION}）", no)
            elif head == "grid":
                score.grid_units_per_quarter = int(parts[1])
            elif head == "meter":
                score.time_beats, score.time_beat_type = int(parts[1]), int(parts[2])
            elif head == "key_fifths":
                score.key_fifths = int(parts[1])
            elif head == "title":
                score.title = line.split(None, 1)[1] if len(parts) > 1 else ""
            elif head == "instruments":
                expect = int(parts[1])
                state = "instruments" if expect else "head"
            elif head in ("notes", "rests", "pedals", "actions", "curves", "segments",
                          "ties", "tuplets", "articulations", "words"):
                expect = int(parts[1])
                state = head if expect else "head"
            else:
                _die(f"未知区块：{head}", no)
            continue

        if state == "instruments":
            score.instruments.append({"id": parts[0], "type": parts[1],
                                      "subtype": None if parts[2] == "-" else parts[2],
                                      "section": None if parts[3] == "-" else parts[3]})
        elif state == "notes":
            (nid, inst, voice, staff, onset, dur, step, alter, octave,
             vel, rel, grace) = parts[:12]
            score.notes.append(mv.NoteEvent(
                id=nid, onset=int(onset), duration=int(dur), voice=voice, staff=staff,
                measure=int(onset) // (score.grid_units_per_quarter * max(1, score.time_beats)),
                pitch=mv.PitchSpell(step, int(alter), int(octave)),
                is_grace=grace == "1",
                dynamics_permille=_i(vel), release_state=rel,
                instrument_id=int(inst)))
        elif state == "rests":
            rid, voice, staff, onset, dur = parts[:5]
            score.rests.append(mv.RestEvent(
                id=rid, onset=int(onset), duration=int(dur), voice=voice, staff=staff,
                measure=int(onset) // (score.grid_units_per_quarter * max(1, score.time_beats))))
        elif state == "pedals":
            pid, kind, action, onset, measure, depth, tgt = parts[:7]
            score.pedal_marks.append(mv.PedalMark(
                id=pid, pedal_type=kind, action_notated=action, onset=int(onset),
                measure=int(measure), depth_permille=_i(depth),
                target_scope=None if tgt == "-" else tgt.split(",")))
        elif state == "actions":
            aid, kind, target, strength = parts[:4]
            score.actions.append(mv.ActionMark(id=aid, kind=kind, target_id=target,
                                               strength=int(strength)))
        elif state == "curves":
            inst, param, t, v, ramp = parts[:5]
            score.curves.append(mv.CurveLane(int(inst), param, int(t), int(v), int(ramp)))
        elif state == "segments":
            eid, idx, kind, text_, bind, tone, turn, lang, st, en = parts[:10]
            score.segments.append(mv.VoiceSegmentV02(
                event_id=eid, index=int(idx), kind=kind, text=text_, binding_id=bind,
                tone=int(tone), turn=int(turn), lang=None if lang == "-" else lang,
                onset_us=int(st), end_us=int(en)))
        elif state == "ties":
            score.tie_groups.append(mv.TieGroup(id=parts[0], member_ids=parts[2:], voice=parts[1]))
        elif state == "tuplets":
            tid, ratio, parent = parts[0], parts[1].split(":"), parts[2]
            score.tuplets.append(mv.Tuplet(id=tid, ratio=(int(ratio[0]), int(ratio[1])),
                                           member_ids=parts[3:],
                                           parent_id=None if parent == "-" else parent))
        elif state == "articulations":
            score.articulations.append(mv.ArticulationMark(id=parts[0], kind=parts[1],
                                                           target_ids=parts[2:]))
        elif state == "words":
            score.words.append({"onset": int(parts[0]), "text": " ".join(parts[1:])})

        expect -= 1
        if expect == 0:
            state = "head"

    if state != "head":
        raise FormatError(f"文件在 {state} 区块中途结束（还应读 {expect} 行）")
    if seen_version is None:
        raise FormatError("缺少 s02 魔数行")
    errs = score.validate()
    if errs:
        raise FormatError("读入的文档不合法：" + "；".join(errs[:3]))
    return score


loads = parse


def save(score, path) -> Path:
    p = Path(path)
    p.write_text(dump(score), encoding="utf-8")
    return p
