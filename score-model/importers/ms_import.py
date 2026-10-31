# -*- coding: utf-8 -*-
"""MusicXML → 乐谱模型导入器。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ('core', 'notation', 'render', 'audio', 'transform', 'tests', 'tools', 'compose', 'importers', 'gates'))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import ms_dynamics_levels as dl
import ms_events as ev
import ms_semantics as ms

STEP_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DYN_TAGS = {"ppp": "ppp", "pp": "pp", "p": "p", "mp": "mp", "mf": "mf",
            "f": "f", "ff": "ff", "fff": "fff"}


def _tag(el) -> str:
    return el.tag.split("}")[-1]


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def _find(el, name):
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _root_of(path: Path):
    """读取 MusicXML 根元素；支持 `.mxl`（zip 容器，含 META-INF/container.xml 或直接一个 xml）。"""
    if path.suffix.lower() == ".mxl":
        import io
        import zipfile
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".musicxml", ".xml"))]
            names = [n for n in names if not n.startswith("META-INF/")]
            if not names:
                raise ValueError(".mxl 里找不到 .musicxml/.xml")
            # 优先 container.xml 指向的文件，否则取第一个
            target = names[0]
            if "META-INF/container.xml" in z.namelist():
                c = ET.fromstring(z.read("META-INF/container.xml"))
                for rf in c.iter():
                    if _tag(rf) == "rootfile" and rf.get("full-path") in names:
                        target = rf.get("full-path")
                        break
            return ET.parse(io.BytesIO(z.read(target))).getroot()
    return ET.parse(str(path)).getroot()


def import_musicxml(path: str | Path, *, default_bpm: float = 120.0,
                    max_measures: int | None = None,
                    instrument_id: int = 1) -> tuple:
    """返回 `(MSDocument, report)`；report 含 losses / 统计。"""
    root = _root_of(Path(path))
    losses: list = []
    report = {"file": str(path), "tempo_bpm": None, "measures": 0,
              "notes": 0, "rests": 0, "grace": 0, "chords": 0, "pedal_segments": 0,
              "tempo_changes": 0, "losses": losses}

    # ── 拍号/tempo 预扫描 ──
    bpm = default_bpm
    for el in root.iter():
        if _tag(el) == "sound" and el.get("tempo"):
            bpm = float(el.get("tempo"))
            report["tempo_bpm"] = bpm
            break
    if report["tempo_bpm"] is None:
        report["tempo_bpm"] = bpm
        losses.append({"code": "tempo_default", "detail": f"未标注速度，按 {bpm:g} BPM 导入"})
    us_per_q = int(round(60_000_000 / bpm))

    parts = _children(root, "part")
    if not parts:
        raise ValueError("MusicXML 里没有 <part>")
    if len(parts) > 1:
        losses.append({"code": "multi_part", "detail": f"有 {len(parts)} 个 part，只导入第一个"})

    divisions = 1
    events: list = []
    pedals: list = []
    cur_level: str | None = None
    dyn_pm: int | None = None
    cur_semitone_by_staff: dict = {}
    pedal_start: dict = {}
    cursor = 0                    # 以 divisions 计
    last_note_onset = 0
    eid = 0

    def onset_us(div_pos: int) -> int:
        return int(round(div_pos * us_per_q / divisions))

    measures = _children(parts[0], "measure")
    if max_measures:
        measures = measures[:max_measures]

    for m_idx, measure in enumerate(measures):
        report["measures"] += 1
        for el in measure:
            t = _tag(el)
            if t == "attributes":
                d = _find(el, "divisions")
                if d is not None and d.text:
                    divisions = int(d.text)
                if _find(el, "key") is not None or _find(el, "time") is not None:
                    losses.append({"code": "notation_context",
                                   "where": f"measure {m_idx + 1}",
                                   "detail": "调号/拍号不入 MS（呈现时由 RenderOptions 提供）",
                                   "severity": "info"})
            elif t == "sound":
                if el.get("tempo") and float(el.get("tempo")) != bpm:
                    report["tempo_changes"] += 1
            elif t == "backup":
                d = _find(el, "duration")
                if d is not None and d.text:
                    cursor -= int(d.text)
            elif t == "forward":
                d = _find(el, "duration")
                if d is not None and d.text:
                    cursor += int(d.text)
            elif t == "direction":
                # 力度
                for dt in _children(el, "direction-type"):
                    dyn = _find(dt, "dynamics")
                    if dyn is not None:
                        for c in dyn:
                            lv = DYN_TAGS.get(_tag(c))
                            if lv:
                                cur_level = lv
                                dyn_pm = dl.level_to_permille(lv)
                                break
                    ped = _find(dt, "pedal")
                    if ped is not None:
                        kind = ped.get("type")
                        ptype = "sustain"
                        if ped.get("pedal-type") == "sostenuto" or \
                                (ped.get("number") == "2"):
                            ptype = "sostenuto"
                        if kind == "start":
                            pedal_start[ptype] = onset_us(cursor)
                        elif kind in ("stop", "change") and ptype in pedal_start:
                            pedals.append(ev.PedalSegment(
                                instrument_id=instrument_id, kind=ptype,
                                start_us=pedal_start.pop(ptype),
                                end_us=onset_us(cursor), depth_permille=1000))
            elif t == "note":
                is_grace = _find(el, "grace") is not None
                is_chord = _find(el, "chord") is not None
                staff = _find(el, "staff")
                staff_no = int(staff.text) if staff is not None and staff.text else 1
                if _find(el, "rest") is not None:
                    report["rests"] += 1
                    d = _find(el, "duration")
                    if d is not None and d.text and not is_grace:
                        cursor += int(d.text)
                    continue
                p = _find(el, "pitch")
                if p is None:
                    continue
                step = _find(p, "step").text.strip()
                alter = _find(p, "alter")
                alter_v = int(float(alter.text)) if alter is not None and alter.text else 0
                octv = int(_find(p, "octave").text)
                semi = STEP_SEMI[step] + alter_v + (octv + 1) * 12

                d = _find(el, "duration")
                dur_div = int(d.text) if d is not None and d.text else 0
                if is_chord:
                    start_div = last_note_onset
                else:
                    start_div = cursor
                    last_note_onset = cursor
                    if not is_grace:
                        cursor += dur_div
                if is_grace:
                    report["grace"] += 1
                if is_chord:
                    report["chords"] += 1

                start_us = onset_us(start_div)
                if is_grace:
                    end_us = start_us          # 零时长（MS 仅允许 grace 如此）
                else:
                    end_us = onset_us(start_div + dur_div)
                if end_us <= start_us and not is_grace:
                    end_us = start_us + 1

                dyn = (ev.Dynamics(ms.VALUE, dyn_pm, "relative_permille",
                                   dl.LEVELS_VERSION, "notated_inferred")
                       if dyn_pm is not None else ev.Dynamics(ms.NOT_PROVIDED))
                eid += 1
                events.append(ev.Event(
                    id=f"m{m_idx + 1}_{eid}", instrument_id=instrument_id,
                    onset_us=start_us, pitch=ev.Pitch(step, alter_v, octv, semi),
                    release_us=end_us,
                    release_state="given",
                    dynamics=dyn, is_grace=is_grace))
                report["notes"] += 1
                cur_semitone_by_staff[staff_no] = semi

    for ptype, start in pedal_start.items():
        pedals.append(ev.PedalSegment(instrument_id=instrument_id, kind=ptype,
                                      start_us=start, end_us=None, depth_permille=1000))
    pedals = ev.assign_pedal_ids(pedals)   # 踏板也是事件：带 id、带乐器

    doc = ev.MSDocument(piano_count=1, constraint_mode="single_piano",
                        events=events, pedals=pedals, gaps=losses)
    report["pedal_segments"] = len(pedals)
    errs = ev.validate(doc)
    if errs:
        raise ValueError("导入结果未通过校验：" + "；".join(errs[:5]))
    return doc, report
