# -*- coding: utf-8 -*-
"""S02 编辑补丁协议（P6-3）：S02 是派生层，改它必须走补丁 + 人工评审。

H5 说"S02 不得反向改写后倒灌 MS"，所以本模块**只做两件事**：
  1. `apply(score, patch)`：在**内存里**得到改后的 S02，并列出改动；
  2. `to_ms_hints(changes)`：把改动翻成"MS 里该改哪一行"的提示（id 一一对应）。

它**不写 `.ms`**，也不自动闭环。要落地必须人看过 diff 再手动改 MS。

补丁格式（JSON，人能读、能审）：

```json
{"base": "song.s02",
 "ops": [
   {"op": "set_note",  "id": "L00000012", "field": "permille", "value": 900},
   {"op": "set_note",  "id": "L00000012", "field": "duration", "value": 960},
   {"op": "set_pedal", "id": "D00000003", "field": "depth",    "value": 500},
   {"op": "set_action","id": "A00000003", "field": "strength", "value": 600},
   {"op": "del_note",  "id": "L00000020"},
   {"op": "add_note",  "id": "L00009999", "inst": 1, "voice": "RH",
    "onset": 3840, "duration": 480, "semi": 67, "permille": 700}
 ]}
```
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import model_v02 as mv

NOTE_FIELDS = ("onset", "duration", "permille", "semi", "voice", "staff")
PEDAL_FIELDS = ("depth", "onset")
ACTION_FIELDS = ("strength", "kind")


class PatchError(ValueError):
    """补丁不合法。"""


def parse(text: str) -> dict:
    text = text.lstrip("\ufeff")          # 容忍带 BOM 的文件（编辑器/Windows 常见）
    try:
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        raise PatchError(f"补丁不是合法 JSON：{e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("ops"), list):
        raise PatchError("补丁必须是 {\"ops\": [...]} 结构")
    for i, op in enumerate(data["ops"]):
        if not isinstance(op, dict) or "op" not in op:
            raise PatchError(f"ops[{i}] 缺少 op 字段")
        if op["op"] not in ("set_note", "set_pedal", "set_action", "del_note", "add_note"):
            raise PatchError(f"ops[{i}] 未知操作：{op['op']}")
        if op["op"] in ("set_note", "set_pedal", "set_action", "del_note"):
            if "id" not in op:
                raise PatchError(f"ops[{i}] 缺少 id")
    return data


def _spell(semi: int) -> mv.PitchSpell:
    steps = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    s = steps[semi % 12]
    return mv.PitchSpell(s[0], 1 if "#" in s else 0, semi // 12 - 1)


def apply(score, patch: dict) -> tuple:
    """返回 `(new_score, changes)`；不改原对象。changes 可直接 json 化。"""
    new = copy.deepcopy(score)
    changes = []
    by_note = {n.id: n for n in new.notes}
    by_pedal = {}
    for p in new.pedal_marks:
        by_pedal[p.id] = p
    by_action = {a.id: a for a in new.actions}

    for i, op in enumerate(patch["ops"]):
        kind = op["op"]
        oid = op.get("id")
        if kind == "set_note":
            n = by_note.get(oid)
            if n is None:
                raise PatchError(f"ops[{i}] 音符不存在：{oid}")
            field, value = op.get("field"), op.get("value")
            if field not in NOTE_FIELDS:
                raise PatchError(f"ops[{i}] 音符字段不支持：{field}")
            old = _note_field(n, field)
            _set_note_field(n, field, value)
            changes.append({"op": kind, "id": oid, "field": field, "old": old, "new": value})
        elif kind == "del_note":
            if oid not in by_note:
                raise PatchError(f"ops[{i}] 音符不存在：{oid}")
            new.notes = [n for n in new.notes if n.id != oid]
            by_note.pop(oid, None)
            changes.append({"op": kind, "id": oid})
        elif kind == "add_note":
            if oid in by_note:
                raise PatchError(f"ops[{i}] 音符已存在：{oid}")
            semi = int(op.get("semi", 60))
            note = mv.NoteEvent(
                id=oid, onset=int(op.get("onset", 0)), duration=int(op.get("duration", 480)),
                voice=op.get("voice", "RH"), staff=op.get("staff", "treble"),
                measure=int(op.get("onset", 0)) // (new.grid_units_per_quarter
                                                    * max(1, new.time_beats)),
                pitch=_spell(semi), dynamics_permille=op.get("permille"),
                release_state="given", instrument_id=int(op.get("inst", 1)))
            new.notes.append(note)
            by_note[oid] = note
            changes.append({"op": kind, "id": oid, "semi": semi})
        elif kind == "set_pedal":
            p = by_pedal.get(oid)
            if p is None:
                raise PatchError(f"ops[{i}] 踏板不存在：{oid}")
            field, value = op.get("field"), op.get("value")
            if field not in PEDAL_FIELDS:
                raise PatchError(f"ops[{i}] 踏板字段不支持：{field}")
            old = getattr(p, "depth_permille" if field == "depth" else "onset")
            if field == "depth":
                p.depth_permille = int(value)
            else:
                p.onset = int(value)
            changes.append({"op": kind, "id": oid, "field": field, "old": old, "new": value})
        elif kind == "set_action":
            a = by_action.get(oid)
            if a is None:
                raise PatchError(f"ops[{i}] 动作不存在：{oid}")
            field, value = op.get("field"), op.get("value")
            if field not in ACTION_FIELDS:
                raise PatchError(f"ops[{i}] 动作字段不支持：{field}")
            old = getattr(a, field)
            setattr(a, field, value if field == "kind" else int(value))
            changes.append({"op": kind, "id": oid, "field": field, "old": old, "new": value})

    errs = new.validate()
    if errs:
        raise PatchError("补丁后的 S02 不合法：" + "；".join(errs[:3]))
    return new, changes


def _note_field(n, field):
    if field == "permille":
        return n.dynamics_permille
    if field == "semi":
        return n.pitch.semitone
    return getattr(n, field)


def _set_note_field(n, field, value):
    if field == "permille":
        n.dynamics_permille = None if value is None else int(value)
    elif field == "duration":
        n.duration = int(value)
    elif field == "onset":
        n.onset = int(value)
    elif field == "semi":
        n.pitch = _spell(int(value))
    elif field in ("voice", "staff"):
        setattr(n, field, str(value))


def to_ms_hints(changes: list) -> list:
    """把 S02 改动翻成"MS 里改哪一行"的提示（给人评审用）。"""
    hints = []
    for c in changes:
        cid = c.get("id")
        op = c["op"]
        if op == "set_note":
            field = c["field"]
            where = {"permille": "音符行第 5 列（力度）",
                     "duration": "止音事件 off 的时间",
                     "onset": "音符行第 3 列（起始）",
                     "semi": "音符行第 4 列（键号）",
                     "voice": "S02 声部（MS 不存声部）",
                     "staff": "S02 谱表（MS 不存谱表）"}.get(field, field)
            hints.append(f"{cid}：{where} {c.get('old')} → {c.get('new')}"
                         + ("（MS 无对应字段，需重算）" if field in ("voice", "staff") else ""))
        elif op == "del_note":
            hints.append(f"{cid}：从 MS 事件流删除该音（并登记 retired）")
        elif op == "add_note":
            hints.append(f"{cid}：在 MS 事件流新增音符（onset {c.get('semi')}…），需新 id")
        elif op == "set_pedal":
            hints.append(f"{c.get('id')}：踏板行 depth {c.get('old')} → {c.get('new')}")
        elif op == "set_action":
            hints.append(f"{c.get('id')}：turns 行 {c.get('field')} {c.get('old')} → {c.get('new')}")
    return hints


def diff_text(changes: list) -> str:
    if not changes:
        return "（无改动）"
    lines = []
    for c in changes:
        if "old" in c:
            lines.append(f"  {c['op']}  {c['id']}  {c.get('field', '')}: "
                         f"{c.get('old')} → {c.get('new')}")
        else:
            lines.append(f"  {c['op']}  {c['id']}")
    return "\n".join(lines)
