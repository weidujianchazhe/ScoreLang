# -*- coding: utf-8 -*-
"""MIDI → 乐谱模型导入器。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ('core', 'notation', 'render', 'audio', 'transform', 'tests', 'tools', 'compose', 'importers', 'gates'))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_midi as mm

CC_TO_KIND = {64: "sustain", 66: "sostenuto", 67: "una_corda"}


def _tick_to_us(tick: int, ppq: int, tempo_us: int) -> int:
    return int(round(tick * tempo_us / ppq))


def import_midi(data: bytes, *, max_pianos: int = 2) -> tuple:
    """返回 `(MSDocument, report)`。"""
    parsed = mm.read_midi(data)
    ppq = parsed["ppq"]
    tempo_us = parsed["tempo_us"] or 500000
    gaps: list = []

    # 按 (channel, note) 配对 on/off
    open_notes: dict = {}
    notes: list = []
    for n in parsed["notes"]:
        key = (n["ch"], n["note"])
        if n["on"]:
            open_notes.setdefault(key, []).append(n)
        else:
            stack = open_notes.get(key) or []
            if not stack:
                gaps.append({"code": "orphan_note_off",
                             "where": f"ch{n['ch']} key{n['note']}",
                             "detail": "收到未配对的 note-off，已忽略", "severity": "warn"})
                continue
            on = stack.pop(0)
            notes.append({"ch": n["ch"], "on": on["tick"], "off": n["tick"],
                          "key": n["note"], "vel": on["vel"]})

    for key, stack in open_notes.items():
        for on in stack:
            gaps.append({"code": "missing_note_off",
                         "where": f"ch{key[0]} key{key[1]} tick{on['tick']}",
                         "detail": "音符没有 note-off，已丢弃（不伪造时长）", "severity": "warn"})

    # 通道 → 琴
    channels = sorted({n["ch"] for n in notes})
    if len(channels) > max_pianos:
        gaps.append({"code": "channel_limit", "severity": "warn",
                     "detail": f"{len(channels)} 个通道，只用前 {max_pianos} 个"})
        channels = channels[:max_pianos]
    ch_to_piano = {ch: i + 1 for i, ch in enumerate(channels)}
    piano_count = max(1, len(ch_to_piano))

    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}

    events = []
    for i, n in enumerate(sorted(notes, key=lambda x: (x["on"], x["ch"], x["key"]))):
        semi = n["key"]
        if not (ev.KEY_MIN <= semi <= ev.KEY_MAX):
            gaps.append({"code": "pitch_out_of_range", "severity": "warn",
                         "where": f"key {semi}", "detail": "超出 MS 音高域，已跳过"})
            continue
        step, alter = base[semi % 12]
        on_us = _tick_to_us(n["on"], ppq, tempo_us)
        off_us = _tick_to_us(n["off"], ppq, tempo_us)
        if off_us <= on_us:
            off_us = on_us + 1
        permille = max(1, min(100000, int(round(n["vel"] * 1000 / 64))))
        events.append(ev.Event(
            id=f"mid{i + 1}", instrument_id=ch_to_piano.get(n["ch"], 1),
            onset_us=on_us, pitch=ev.Pitch(step, alter, semi // 12 - 1, semi),
            release_us=off_us, release_state="given",
            dynamics=ev.Dynamics("VALUE", permille, "relative_permille", "midi_import", None)))

    # 踏板：CC 值序列 → 段（记录曲尾，供未抬脚的踏板拆分用）
    piece_end_us = 0
    pedals = []
    for ch in channels:
        for cc, kind in CC_TO_KIND.items():
            series = [c for c in parsed["ccs"] if c.get("ch") == ch and c.get("cc") == cc]
            start_us = None
            depth = 1000
            for c in sorted(series, key=lambda x: x["tick"]):
                val = c["val"]
                t = _tick_to_us(c["tick"], ppq, tempo_us)
                if val > 0 and start_us is None:
                    start_us, depth = t, max(1, int(round(val * 1000 / 127)))
                elif val == 0 and start_us is not None:
                    pedals.append(ev.PedalSegment(instrument_id=ch_to_piano.get(ch, 1), kind=kind,
                                                  start_us=start_us, end_us=t,
                                                  depth_permille=depth))
                    start_us = None
            if start_us is not None:
                pedals.append(ev.PedalSegment(instrument_id=ch_to_piano.get(ch, 1), kind=kind,
                                              start_us=start_us, end_us=None,
                                              depth_permille=depth))

    # 曲尾（用于 end_us=None 的踏板）
    piece_end_us = max([int(e.release_us or e.onset_us) for e in events] or [0])
    # 超长踏板段拆分：连续踩下超过 30s 的段切成 ≤30s、间隔 200ms 的多段，
    # 避免导入后触发 V4c（整曲 80% 以上串成一条踏板链，声音会糊）。
    MAX_PEDAL_US = 30_000_000
    GAP_US = 200_000
    split = []
    for p_ in pedals:
        end = p_.end_us if p_.end_us is not None else (piece_end_us or None)
        if end is None or end - p_.start_us <= MAX_PEDAL_US:
            split.append(p_)
            continue
        s = p_.start_us
        while s < end:
            e = min(end, s + MAX_PEDAL_US)
            split.append(ev.PedalSegment(instrument_id=p_.instrument_id,
                                         kind=p_.kind, start_us=s, end_us=e,
                                         depth_permille=p_.depth_permille,
                                         scope=p_.scope, targets=p_.targets))
            s = e + GAP_US
    pedals = split

    if parsed["ccs"]:
        gaps.append({"code": "cc_not_imported", "severity": "info",
                     "detail": "CC1/CC11 等未导入（MS 不含颤音/表情），仅 CC64/66/67 转为踏板"})
    pedals = ev.assign_pedal_ids(pedals)   # 踏板也是事件：带 id、带乐器

    doc = ev.MSDocument(piano_count=piano_count,
                        constraint_mode="single_piano" if piano_count == 1 else "n_pianos",
                        instruments=[ev.Instrument(id=f"P{i + 1}",
                                                   type="acoustic_grand_piano")
                                     for i in range(piano_count)],
                        events=events, pedals=pedals, gaps=gaps)
    errs = ev.validate(doc)
    if errs:
        raise ValueError("MIDI 导入结果未通过校验：" + "；".join(errs[:5]))
    report = {"ppq": ppq, "tempo_us": tempo_us, "notes": len(events),
              "pedals": len(pedals), "pianos": piano_count,
              "duration_s": (max(e.release_us for e in events) / 1e6) if events else 0.0,
              "gaps": gaps}
    return doc, report
