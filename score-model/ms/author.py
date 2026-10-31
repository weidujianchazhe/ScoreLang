# -*- coding: utf-8 -*-
"""写谱辅助：`Writer`。

目标（管理者要求）：**让 AI/人用这个脚本写的时候，自动知道能写什么、该写哪些演奏动作**。

    from ms import Writer
    w = Writer(bpm=120)
    piano = w.instrument("acoustic_grand_piano")     # -> 1
    vln = w.instrument("violin")                     # -> 2（同类型可以再来一把）
    a = w.note(piano, pitch="C4", beat=0, beats=1, level="mf")
    w.note(vln, pitch="A4", beat=0, beats=2, articulation="marcato")
    w.turn(a[0], "key_noise")                        # 写上才检查这件乐器做不做得了
    w.pedal(piano, "sustain", 0, 4)                  # 不在该乐器踏板表里会直接报错
    doc = w.doc()                                    # 内存文档；此时才落成 MSDocument
    w.save("song.md")                                # 落盘：产物是 .md 文档

`w.menu()` 打印"这件乐器能做什么"（也可以 `w.actions(2)` / `w.pedals(1)`）。
"""
from __future__ import annotations

from pathlib import Path

import ms_model as ev
import ms_author as _au
from ms_instruments import CURVE_PARAMS, resolve

_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_to_semitone(text: str | int) -> int:
    """'C4' / 'C#4' / 'Bb3' / 60 → MIDI 半音（MS 用 21..108）。"""
    if isinstance(text, int):
        from ms_model import KEY_MIN, KEY_MAX, ERR_PITCH_RANGE
        if not (KEY_MIN <= text <= KEY_MAX):
            raise ValueError(f"{ERR_PITCH_RANGE}：{text} 不在 {KEY_MIN}..{KEY_MAX}")
        return text
    s = text.strip()
    if not s:
        raise ValueError("pitch 不能为空")
    letter = s[0].upper()
    if letter not in _PC:
        raise ValueError(f"pitch 非法：{text!r}（例：C4 / F#5 / Bb3）")
    i, acc = 1, 0
    while i < len(s) and s[i] in "#b♯♭":
        acc += 1 if s[i] in "#♯" else -1
        i += 1
    octv = int(s[i:]) if s[i:] else 4
    semi = 12 * (octv + 1) + _PC[letter] + acc
    from ms_model import KEY_MIN, KEY_MAX, ERR_PITCH_RANGE
    if not (KEY_MIN <= semi <= KEY_MAX):
        raise ValueError(f"{ERR_PITCH_RANGE}：{text!r} → {semi} 不在 {KEY_MIN}..{KEY_MAX}")
    return semi


class Writer:
    """内存里写谱：不落文件，直到 `save()`。"""

    def __init__(self, *, bpm: float = 120.0, meter=(4, 4), channels: str = "per_instance"):
        if bpm <= 0:
            raise ValueError("bpm 必须为正")
        self.bpm = float(bpm)
        self.us_per_beat = int(round(60_000_000 / bpm))
        self.meter = tuple(meter)
        self.channels = channels
        self._insts: list = []
        self._types: dict = {}
        self._events: list = []
        self._pedals: list = []
        self._turns: list = []
        self._curves: list = []
        self._used: set = set()

    # ── 乐器件 ─────────────────────────────────────────────
    def instrument(self, type_code: str, *, subtype: str | None = None,
                   section: str | None = None) -> int:
        """声明一件乐器，返回实例号（1 基）。同类型可重复调用 = 多把。"""
        spec = resolve(type_code, subtype)          # 未知类型/子类型立刻报错
        iid = len(self._insts) + 1
        self._insts.append(ev.Instrument(id=f"P{iid}", type=type_code,
                                          subtype=subtype, section=section))
        self._types[iid] = type_code
        return iid

    def _type_of(self, iid: int) -> str:
        t = self._types.get(iid)
        if t is None:
            raise ValueError(f"乐器实例 {iid} 未声明：先 w.instrument(...)")
        return t

    def actions(self, iid: int) -> list:
        """这件乐器能做的演奏转折。"""
        from ms.registry import actions as _actions
        return _actions(self._type_of(iid))

    def pedals(self, iid: int) -> tuple:
        """这件乐器能踩的踏板。"""
        return tuple(resolve(self._type_of(iid)).get("pedals") or ())

    # ── 音符 ───────────────────────────────────────────────
    def note(self, iid: int, *, pitch, beat: float, beats: float = 1.0,
             level: str | None = None, permille: int | None = None,
             articulation: str | None = None,
             ornament: str | None = None,
             upper: str | None = None, lower: str | None = None,
             grace: str | None = None) -> list:
        """写一个音；返回事件列表。`beats` 为时值（拍）。"""
        if beats <= 0:
            raise ValueError("beats 必须为正")
        onset = int(round(beat * self.us_per_beat))
        dur = int(round(beats * self.us_per_beat))
        evs = _au.write_note(
            onset_us=onset, duration_us=dur, semitone=pitch_to_semitone(pitch),
            instrument_id=iid, level=level, permille=permille,
            articulation=articulation, ornament=ornament,
            upper_semitone=pitch_to_semitone(upper) if upper else None,
            lower_semitone=pitch_to_semitone(lower) if lower else None,
            grace_semitone=pitch_to_semitone(grace) if grace else None,
            instrument_type=self._type_of(iid),
            used_ids=self._used)
        self._events += evs
        self._used.update(e.id for e in evs)
        return evs

    def chord(self, iid: int, *, pitches, beat: float, beats: float = 1.0,
              level: str | None = None, permille: int | None = None,
              articulation: str | None = None) -> list:
        out = []
        for p in pitches:
            out += self.note(iid, pitch=p, beat=beat, beats=beats, level=level,
                             permille=permille, articulation=articulation)
        return out

    # ── 演奏动作 ───────────────────────────────────────────
    def pedal(self, iid: int, kind: str, start_beat: float, end_beat: float,
              *, depth_permille: int = 1000) -> object:
        """写一段踏板；kind 不在该乐器踏板表里 → 直接报错并列出可用值。"""
        allowed = self.pedals(iid)
        if kind not in allowed:
            raise ValueError(f"P{iid}({self._type_of(iid)}) 没有 {kind!r} 踏板；"
                             f"可用：{list(allowed) or '无'}")
        start = int(round(start_beat * self.us_per_beat))
        end = int(round(end_beat * self.us_per_beat))
        seg = _au.write_pedal(iid, kind, start, end, depth_permille=depth_permille,
                              used_ids=self._used)
        self._pedals.append(seg)
        self._used.add(seg.id)
        return seg

    def turn(self, event_or_id, kind: str, strength: int = 1000) -> object:
        """给某个音加演奏转折；乐器做不做得了在 `doc()`/`validate()` 时硬校验。"""
        eid = getattr(event_or_id, "id", event_or_id)
        t = _au.write_turn(eid, kind, strength)
        self._turns.append(t)
        return t

    def curve(self, iid: int, param: str, points) -> list:
        """写控制曲线：points = [(beat, value), ...]；首点为阶跃起点。"""
        if param not in CURVE_PARAMS:
            raise ValueError(f"未知曲线参数 {param!r}；可用：{list(CURVE_PARAMS)}")
        lo, hi = CURVE_PARAMS[param]
        out = []
        for i, (b, v) in enumerate(points):
            if not (lo <= int(v) <= hi):
                raise ValueError(f"{param} 取值越界：{v}（合法 {lo}..{hi}）")
            out.append(ev.CurvePoint(instrument_id=iid, param=param,
                                     time_us=int(round(b * self.us_per_beat)),
                                     value=int(v), ramp=0 if i == 0 else 1))
        self._curves += out
        return out

    # ── 收束 ───────────────────────────────────────────────
    def doc(self):
        """合成 `MSDocument`（内存；这一步会校验，非法直接抛错）。"""
        doc = _au.to_document(
            self._events, piano_count=max(1, len(self._insts)),
            channels=self.channels,
            instruments=self._insts, pedals=self._pedals,
            turns=self._turns)
        doc.curves = list(self._curves)
        return doc

    def validate(self) -> list:
        """返回结构/物理错误（空 = 合法）。"""
        from ms_validate import validate as _val
        return _val(self.doc())

    def save(self, path) -> Path:
        """落盘：产物是 `.md`（文档写法）。不给后缀时自动补 `.md`。"""
        from pathlib import Path as _P
        p = _P(path)
        if not p.suffix:
            p = p.with_suffix(".md")
        if p.suffix.lower() == ".md":
            import ms_md as _md
            _md.save(self.doc(), p)
            return p
        from ms_io import save as _save      # 旧档案：仅显式指定时写出
        return _save(self.doc(), p)

    def menu(self) -> str:
        lines = [f"MS Writer（bpm={self.bpm:g}, 拍长 {self.us_per_beat} µs）",
                 "已声明乐器："]
        for iid, t in sorted(self._types.items()):
            lines.append(f"  P{iid} {t}: 转折 {len(self.actions(iid))} 种；"
                         f"踏板 {list(self.pedals(iid)) or '无'}")
        lines.append("可写：note/chord/pedal/turn/curve；doc() 得内存文档；save() 才落盘")
        return "\n".join(lines)


__all__ = ["Writer", "pitch_to_semitone"]
