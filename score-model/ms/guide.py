# -*- coding: utf-8 -*-
"""写作向导：AI 只填数据；结构、id、时间默认值由脚本派生，但**全部参数可覆盖**。

流程：
    1) AI 选乐器（提交给脚本，脚本派生实例号 P1/P2…）
    2) 脚本派生事件 id（L00000001 起），AI 每填一个事件就有稳定 id
    3) AI 可自由填声音参数：力度、奏法、踏板、曲线、微秒时间、释放状态、力度刻度
       脚本只做**范围收束**（越界拒绝）
    4) 用 id 精准定位修改/删除：events() / edit(id, ...) / delete(id)
    5) finish() 做结构校验，返回 Song
"""
from __future__ import annotations

try:  # 源码布局
    from .author import Writer, pitch_to_semitone
    from .task import Song, instrument_actions, resolve_instrument
    from ._core.ms_author import _mk_pitch
except Exception:  # 发布布局（平铺 import）
    from ms_writer import Writer, pitch_to_semitone  # type: ignore
    from ms_author import _mk_pitch  # type: ignore
    from .task import Song, instrument_actions, resolve_instrument  # type: ignore

import ms_edit  # noqa: E402
import ms_model as ev  # noqa: E402
import ms_validate  # noqa: E402
import ms_semantics as sem  # noqa: E402
from .intent_gen import plan as _intent_plan  # noqa: E402

LEVELS = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
RELEASE_STATES = tuple(ev.RELEASE_STATES)
EXCITATION = tuple(ev.EXCITATION_TYPES)

# 收束：同一乐器同一踏板，两次踩下的间隔不得小于 100µs（写不进去）
PEDAL_MIN_GAP_US = 100

RANGES = {
    "onset_us": "整数 ≥ 0（微秒）",
    "release_us": "None 或 > onset_us（微秒）",
    "permille": "1–100000",
    "release_state": list(RELEASE_STATES),
    "excitation_type": list(EXCITATION),
    "level": LEVELS,
}


class Guide:
    """一步一步写：脚本派生结构，AI 选数据。"""

    def __init__(self, *, bpm: float = 120.0, meter=(4, 4), title: str = "",
                 instruments=None, intent=None):
        self._w = Writer(bpm=bpm, meter=meter)
        self._bpm = float(bpm)
        self._meter = tuple(meter)
        self._title = title
        self._alias = {}
        self._notes = []
        self._edits = []
        self._deletes = set()
        self._pedals = []        # [(inst, kind, start_us, end_us)]
        self._spec_notes = []    # 还原任务 JSON 用
        self._spec_pedals = []
        self._spec_turns = []
        self._spec_curves = []
        self._plan = _intent_plan(intent)
        self._tech = 0
        self._note_total = 0
        self._end_beat = 0.0
        for it in (instruments or [{"type": "piano"}]):
            self.add_instrument(it)

    # ── 1) 乐器头（AI 选乐器，脚本派生实例号） ─────────────
    def add_instrument(self, spec) -> int:
        raw = spec["type"] if isinstance(spec, dict) else str(spec)
        code = resolve_instrument(raw)
        iid = self._w.instrument(
            code, subtype=(spec.get("subtype") if isinstance(spec, dict) else None))
        self._alias[iid] = raw
        return iid

    def instruments(self) -> list:
        from ms.registry import articulations as _art, ornaments as _orn
        out = []
        for iid in sorted(self._alias):
            raw = self._alias[iid]
            out.append({"id": iid, "alias": raw,
                        "articulations": _art(resolve_instrument(raw)),
                        "ornaments": _orn(resolve_instrument(raw)),
                        "turns": instrument_actions(raw),
                        "pedals": list(self._w.pedals(iid))})
        return out

    # ── 2) 可填选项（含范围；AI 自由选） ───────────────────
    def options(self) -> dict:
        return {
            "levels": LEVELS,
            "ranges": RANGES,
            "constraints": {"pedal_min_gap_us": PEDAL_MIN_GAP_US},
            "instruments": self.instruments(),
            "note": "note(inst, pitch, beat=?, beats=?, level=?, articulation=?, "
                    "ornament=?, onset_us=?, release_us=?, release_state=?, "
                    "permille=?, excitation_type=?)",
            "chord": "chord(inst, [pitch...], beat=?, beats=?, level=?)",
            "pedal": "pedal(inst, kind, start_beat, end_beat)",
            "turn": "turn(note_index, kind)",
            "curve": "curve(inst, param, [(beat, value), ...])",
            "events": "events() → 带 id 的事件列表",
            "edit": "edit(id, **参数) 精准修改；delete(id) 删除",
            "finish": "finish() → Song",
            "intent": self._plan.status(self._note_total, self._tech),
            "intent_hints": self._plan.hints(),
            "used_beats": round(self._end_beat, 3),
            "curves_written": len(self._spec_curves),
            "planned_bars": self._plan.total_bars,
            "actual_bars": getattr(self, "_bars", None),
            "warnings": getattr(self, "_warnings", []),
            "notes_written": len(self._notes),
        }

    # ── 3) 填事件（id 自动派生，声音参数可覆盖） ───────────
    def note(self, inst: int, pitch: str, *, beat: float | None = None,
             beats: float = 1.0, level=None, articulation=None, ornament=None,
             upper: str | None = None, lower: str | None = None,
             grace: str | None = None,
             onset_us=None, release_us=None, release_state=None, permille=None,
             excitation_type=None) -> str:
        if onset_us is not None:
            beat = int(onset_us) / self._w.us_per_beat
            beats = ((int(release_us) - int(onset_us)) / self._w.us_per_beat
                     if release_us else beats)
        if beat is None:
            raise ValueError("beat 与 onset_us 至少给一个")
        if articulation or ornament:
            self._plan.check_add_tech(self._note_total, self._tech)
            self._tech += 1
        evs = self._w.note(inst, pitch=pitch, beat=float(beat), beats=float(beats),
                           level=level, permille=permille,
                           articulation=articulation, ornament=ornament,
                           upper=upper, lower=lower, grace=grace)
        eid = evs[0].id
        self._note_total += 1
        self._notes.append(eid)
        self._spec_notes.append({"inst": inst, "pitch": pitch,
                                 "beat": float(beat), "beats": float(beats),
                                 **({"level": level} if level else {}),
                                 **({"articulation": articulation} if articulation else {}),
                                 **({"ornament": ornament} if ornament else {}),
                                 **({"upper": upper} if upper else {}),
                                 **({"lower": lower} if lower else {}),
                                 **({"grace": grace} if grace else {})})
        self._end_beat = max(self._end_beat, float(beat) + float(beats))
        raw = {k: v for k, v in {
            "release_state": release_state,
            "excitation_type": excitation_type, "release_us": release_us,
        }.items() if v is not None}
        if raw:
            self._edits.append((eid, raw))
        return eid

    def notes(self, items) -> int:
        n = 0
        for it in items:
            if isinstance(it, str):
                s = it.strip()
                inst = 1
                level = None
                if ":" in s:
                    head, s = s.split(":", 1)
                    inst = int(head)
                if "/" in s:
                    s, level = s.rsplit("/", 1)
                pitch, rest = s.split("@", 1)
                beat, beats = rest.split("+", 1)
                self.note(inst, pitch, beat=float(beat), beats=float(beats),
                          level=level)
            elif isinstance(it, (list, tuple)):
                inst = int(it[0])
                level = it[4] if len(it) > 4 else None
                self.note(inst, it[1], beat=float(it[2]), beats=float(it[3]),
                          level=level)
            elif isinstance(it, dict):
                self.note(int(it.get("inst", 1)), it.get("pitch"),
                          beat=float(it.get("beat", 0)),
                          beats=float(it.get("beats", 1)),
                          level=it.get("level"),
                          articulation=it.get("articulation"),
                          ornament=it.get("ornament"))
            else:
                raise ValueError(f"无法识别的音符：{it!r}")
            n += 1
        return n

    def chord(self, inst: int, pitches, *, beat: float = 0.0,
              beats: float = 1.0, level=None) -> list:
        evs = self._w.chord(inst, pitches=pitches, beat=beat, beats=beats,
                            level=level)
        ids = [e.id for e in evs]
        self._note_total += len(pitches)
        self._notes.extend(ids)
        self._spec_notes.append({"inst": inst, "pitches": list(pitches),
                                 "beat": float(beat), "beats": float(beats),
                                 **({"level": level} if level else {})})
        self._end_beat = max(self._end_beat, beat + beats)
        return ids

    def pedal(self, inst: int, kind: str, start_beat: float, end_beat: float) -> None:
        """写踏板；收束：kind 必须是该乐器支持的，且同踏板两次踩下间隔 ≥100µs。"""
        if kind not in self._w.pedals(inst):
            raise ValueError(f"乐器 {inst} 不支持踏板 {kind!r}（可用：{list(self._w.pedals(inst))}）")
        upb = self._w.us_per_beat
        start_us, end_us = int(start_beat * upb), int(end_beat * upb)
        if end_us <= start_us:
            raise ValueError("踏板 end 必须大于 start")
        for p_inst, p_kind, _s, p_end in self._pedals:
            if p_inst == inst and p_kind == kind:
                gap = start_us - p_end
                if 0 <= gap < PEDAL_MIN_GAP_US:
                    raise ValueError(
                        f"踏板间隔 {gap}µs < {PEDAL_MIN_GAP_US}µs，无法写入")
        self._w.pedal(inst, kind, start_beat, end_beat)
        self._pedals.append((inst, kind, start_us, end_us))
        self._spec_pedals.append({"inst": inst, "kind": kind,
                                  "start": float(start_beat), "end": float(end_beat)})
        self._end_beat = max(self._end_beat, end_beat)

    def turn(self, note, kind: str) -> None:
        """`note` 可以是 note 索引，也可以是 `n = g.note(...)` 返回的稳定 id。"""
        if isinstance(note, str):
            if note not in self._notes:
                raise ValueError(f"没有这个 note id：{note!r}")
            self._w.turn(note, kind)
            self._spec_turns.append({"note": self._notes.index(note),
                                     "kind": kind})
            return
        note_index = int(note)
        if not (0 <= note_index < len(self._notes)):
            raise ValueError(f"note_index 越界：{note_index}")
        self._w.turn(self._notes[note_index], kind)
        self._spec_turns.append({"note": note_index, "kind": kind})

    def curve(self, inst: int, param: str, points) -> None:
        self._w.curve(inst, param, points)
        self._spec_curves.append({"inst": inst, "param": param,
                                  "points": [[float(b), float(v)] for b, v in points]})

    # ── 4) 精准定位 / 修改 / 删除（按事件 id） ──────────────
    def events(self) -> list:
        doc = self._doc_with_edits()
        return [{
            "id": e.id, "inst": e.instrument_id,
            "pitch": e.pitch.step + ("#" * max(0, e.pitch.alter)) +
                     ("b" * max(0, -e.pitch.alter)) + str(e.pitch.octave),
            "onset_us": e.onset_us, "release_us": e.release_us,
            "release_state": e.release_state,
            "dynamics": {"state": e.dynamics.state,
                         "permille": e.dynamics.permille},
        } for e in doc.events]

    def edit(self, event_id: str, **changes) -> dict:
        """按 id 修改事件；只做范围收束，不限制取值。"""
        clean = {}
        if "pitch" in changes:
            semi = pitch_to_semitone(changes.pop("pitch"))
            clean["pitch"] = _mk_pitch(semi)
        if "dynamics" in changes and isinstance(changes["dynamics"], dict):
            d = changes.pop("dynamics")
            clean["dynamics"] = ev.Dynamics(
                d.get("state", sem.VALUE), d.get("permille"),
                d.get("scale", "relative_permille"),
                d.get("calibration_ref", "manual"), d.get("src", "composed"))
        if "permille" in changes:
            pm = int(changes.pop("permille"))
            if not 1 <= pm <= 100000:
                return {"ok": False, "errors": ["permille 需在 1–100000"]}
            clean["dynamics"] = ev.Dynamics(
                sem.VALUE, pm, "relative_permille", "manual", "composed")
        if "release_state" in changes:
            rs = changes["release_state"]
            if rs not in RELEASE_STATES:
                return {"ok": False, "errors": [f"release_state 需为 {RELEASE_STATES}"]}
        if "onset_us" in changes and int(changes["onset_us"]) < 0:
            return {"ok": False, "errors": ["onset_us 需 ≥ 0"]}
        if "release_us" in changes:
            r = changes["release_us"]
            if r is not None and int(r) < 0:
                return {"ok": False, "errors": ["release_us 需 ≥ 0 或 None"]}
        clean.update(changes)
        res = self._apply_on_doc(self._doc_with_edits(), event_id, clean, delete=False)
        if not res["ok"]:
            return res
        self._edits.append((event_id, clean))
        return {"ok": True, "event_id": event_id, "changes": clean}

    def delete(self, event_id: str) -> dict:
        res = self._apply_on_doc(self._doc_with_edits(), event_id, {}, delete=True)
        if not res["ok"]:
            return res
        self._deletes.add(event_id)
        return {"ok": True, "deleted": event_id}

    def _apply_on_doc(self, doc, event_id, changes, *, delete):
        if delete:
            r = ms_edit.delete_event(doc, event_id)
        else:
            r = ms_edit.update_event(doc, event_id, **changes)
        if not r.ok:
            return {"ok": False, "errors": list(r.errors)}
        return {"ok": True}

    def _doc_with_edits(self):
        doc = self._w.doc()
        insts = list(doc.instruments)
        for eid, changes in self._edits:
            r = ms_edit.update_event(doc, eid, **changes)
            if not r.ok:
                raise ValueError(f"编辑 {eid} 被拒绝：{list(r.errors)}")
            doc = r.doc
        for eid in self._deletes:
            r = ms_edit.delete_event(doc, eid)
            if not r.ok:
                raise ValueError(f"删除 {eid} 被拒绝：{list(r.errors)}")
            doc = r.doc
        if not doc.instruments and insts:
            doc.instruments = insts
        return doc

    def intent_status(self) -> dict:
        """当前意图满足情况（技术密度等）。"""
        return self._plan.status(self._note_total, self._tech)

    def spec(self) -> dict:
        """还原成任务 JSON（用于存缓存区，不是产物）。"""
        spec = {"bpm": self._bpm, "meter": list(self._meter),
                "instruments": [{"type": self._alias[i]} for i in sorted(self._alias)],
                "notes": list(self._spec_notes)}
        if self._spec_pedals:
            spec["pedals"] = list(self._spec_pedals)
        if self._spec_turns:
            spec["turns"] = list(self._spec_turns)
        if self._spec_curves:
            spec["curves"] = list(self._spec_curves)
        return spec

    # ── 5) 收尾：结构校验 → Song ───────────────────────────
    def _stagger_endings(self, doc):
        last = {}
        for e in doc.events:
            end = e.release_us if e.release_us is not None else e.onset_us
            iid = e.instrument_id
            if iid not in last or end >= last[iid][0]:
                last[iid] = (end, e.id)
        if len(last) < 2:
            return doc
        ends = sorted(v[0] for v in last.values())
        piece = max(ends) or 1
        if max(ends) - min(ends) >= max(50_000, 0.02 * piece):
            return doc
        step = max(120_000, int(0.02 * piece))
        order = sorted(last.items(), key=lambda kv: kv[1][0])
        base = order[0][1][0]
        for i, (_iid, (end, eid)) in enumerate(order):
            target = base + i * step
            if target <= end:
                continue
            r = ms_edit.update_event(doc, eid, release_us=target,
                                     release_state="given")
            if r.ok:
                doc = r.doc
        return doc

    def _auto_expression(self) -> None:
        """按期待值加一条力度弧线（各乐器）。"""
        exp = self._plan.expectation
        if exp is None or self._end_beat <= 0:
            return
        exp = max(0.0, min(1.0, float(exp)))
        peak = self._end_beat * (0.45 + 0.35 * exp)
        pts = [(0.0, 500), (peak, 950), (self._end_beat, 450)]
        for iid in sorted(self._alias):
            self._w.curve(iid, "dynamics", pts)
            self._spec_curves.append({"inst": iid, "param": "dynamics",
                                      "points": [[float(b), float(v)] for b, v in pts]})

    def finish(self) -> Song:
        self._auto_expression()
        doc = self._doc_with_edits()
        if self._plan.stagger:
            doc = self._stagger_endings(doc)
        bars = max(1, int(round(self._end_beat / max(1, self._meter[0]))))
        self._bars = bars
        self._warnings = []
        if self._plan.total_bars and abs(bars - self._plan.total_bars) > max(
                2, int(0.2 * self._plan.total_bars)):
            self._warnings.append(
                f"结构目标 {self._plan.total_bars} 小节，实际 {bars} 小节（偏差过大）")
        errs = ms_validate.validate(doc)
        if errs:
            raise ValueError("；".join(errs[:5]))
        return Song(doc, bpm=self._bpm, meter=self._meter, title=self._title)

    def summary(self) -> dict:
        return {"bpm": self._bpm, "meter": list(self._meter),
                "notes": len(self._notes), "instruments": len(self._alias)}


__all__ = ["Guide", "LEVELS", "RANGES"]
