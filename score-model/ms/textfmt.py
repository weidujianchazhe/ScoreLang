# -*- coding: utf-8 -*-
"""发布版文本谱格式：一行一个音，接近手写谱；解析成 task spec（不暴露 MS 内部字段）。

语法（`#` 后为注释，空行忽略）：

    # 水镜
    title 水镜
    bpm 63
    meter 4/4
    inst 1 piano
    inst 2 cello

    P1 C4 0 1 mf          # 乐器 音高 起始拍 时值(拍) [力度] [奏法]
    P2 C2 0 4 p
    C4@0+1/mf             # 省写法：默认乐器 1；2:E5@2+0.5/p 指定乐器
    pedal P1 sustain 0 4
    curve P1 dynamics 0 500 16 950 32 450
    turn 0 trill 1000

规则：
  · 力度：ppp/pp/p/mp/mf/f/ff/fff 或 0..1000 的 permille
  · 奏法/装饰音：staccato / tenuto / accent / trill / mordent 等（由 build 校验）
  · 时间单位是拍，不是微秒；BPM 由 bpm 指令给出
"""
from __future__ import annotations

LEVELS = {"ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"}
CURVE_PARAMS = {"dynamics", "tempo", "pedal", "brightness", "expression"}


def _is_num(x: str) -> bool:
    try:
        float(x)
        return True
    except ValueError:
        return False


def _inst_token(tok: str):
    """P1 / p1 / 1 → 1；不是乐器标记时返回 None。"""
    t = tok.strip()
    if not t:
        return None
    if t[0] in "Pp" and t[1:].isdigit():
        return int(t[1:])
    if t.isdigit():
        return int(t)
    return None


def _parse_compact(tok: str, default_inst: int):
    """`C4@0+1/mf` 或 `2:E5@2+0.5/p`。"""
    inst, body = default_inst, tok
    if ":" in body:
        head, rest = body.split(":", 1)
        iid = _inst_token(head)
        if iid is None:
            raise ValueError(f"无法解析乐器：{tok!r}")
        inst, body = iid, rest
    if "@" not in body:
        raise ValueError(f"简写音符缺 @：{tok!r}")
    pitch, tail = body.split("@", 1)
    if "+" in tail:
        beat_s, beats_s = tail.split("+", 1)
        beats = float(beats_s.split("/")[0])
        rest = tail.split("/", 1)[1] if "/" in tail else ""
    else:
        beat_s = tail.split("/", 1)[0]
        beats = 1.0
        rest = tail.split("/", 1)[1] if "/" in tail else ""
    level = rest or None
    return {"inst": inst, "pitch": pitch, "beat": float(beat_s),
            "beats": beats, **({"level": level} if level else {})}


def parse_text(text: str) -> dict:
    """文本谱 → task spec（不 build；写完先 `ms.check_spec`）。"""
    spec = {"bpm": 120.0, "meter": [4, 4], "instruments": [], "notes": []}
    lines = text.splitlines()
    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.replace("=", " ").split()
        head = toks[0].lower()
        try:
            if head == "title":
                spec["title"] = " ".join(toks[1:])
            elif head == "bpm":
                spec["bpm"] = float(toks[1])
            elif head == "meter":
                if "/" not in toks[1]:
                    raise ValueError("meter 应为 a/b")
                a, b = toks[1].split("/", 1)
                spec["meter"] = [int(a), int(b)]
            elif head == "inst":
                iid = _inst_token(toks[1])
                if iid is None:
                    raise ValueError("inst 第二项应为 P1/1")
                entry = {"type": toks[2]} if len(toks) > 2 else {"type": "piano"}
                if len(toks) > 3:
                    entry["subtype"] = toks[3]
                entry["id"] = iid
                spec["instruments"].append(entry)
            elif head == "pedal":
                iid = _inst_token(toks[1])
                if iid is None:
                    raise ValueError("pedal 第二项应为 P1/1")
                spec.setdefault("pedals", []).append({
                    "inst": iid, "kind": toks[2],
                    "start": float(toks[3]), "end": float(toks[4])})
            elif head == "curve":
                iid = _inst_token(toks[1])
                if iid is None:
                    raise ValueError("curve 第二项应为 P1/1")
                param = toks[2]
                if param not in CURVE_PARAMS:
                    raise ValueError(f"curve 参数非法：{param!r}")
                nums = [float(x) for x in toks[3:]]
                if len(nums) % 2:
                    raise ValueError("curve 需要成对的 拍/值")
                pts = [[nums[i], int(nums[i + 1])] for i in range(0, len(nums), 2)]
                spec.setdefault("curves", []).append(
                    {"inst": iid, "param": param, "points": pts})
            elif head == "turn":
                spec.setdefault("turns", []).append({
                    "note": int(toks[1]), "kind": toks[2],
                    "strength": int(toks[3]) if len(toks) > 3 else 1000})
            elif "@" in toks[0]:
                spec["notes"].append(_parse_compact(toks[0], 1))
            else:
                inst = _inst_token(toks[0])
                if inst is None:
                    inst, rest = 1, toks
                else:
                    rest = toks[1:]
                if len(rest) < 2:
                    raise ValueError("音符行至少需要：音高 起始拍")
                note = {"inst": inst, "pitch": rest[0], "beat": float(rest[1])}
                if len(rest) > 2:
                    note["beats"] = float(rest[2])
                if len(rest) > 3:
                    note["level"] = rest[3]
                if len(rest) > 4:
                    note["articulation"] = rest[4]
                spec["notes"].append(note)
        except IndexError as exc:
            raise ValueError(f"第 {lineno} 行解析失败：{raw!r}") from exc
        except ValueError as exc:
            raise ValueError(f"第 {lineno} 行：{exc}（原文 {raw!r}）") from exc
    if not spec["notes"]:
        raise ValueError("文本谱里没有音符")
    if not spec["instruments"]:
        spec["instruments"] = [{"type": "piano"}]
    return spec


def dump_text(spec: dict) -> str:
    """spec → 文本谱（可再 parse 回来）。"""
    lines = []
    if spec.get("title"):
        lines.append(f"title {spec['title']}")
    lines.append(f"bpm {spec.get('bpm', 120)}")
    m = spec.get("meter") or [4, 4]
    lines.append(f"meter {m[0]}/{m[1]}")
    for i, ins in enumerate(spec.get("instruments") or [{"type": "piano"}], 1):
        if isinstance(ins, dict):
            t = ins.get("type") or "piano"
            sub = ins.get("subtype")
        else:
            t, sub = str(ins), None
        lines.append("inst " + (f"P{i}" if not isinstance(ins, dict) or not ins.get("id")
                                else f"P{ins.get('id')}") + f" {t}" + (f" {sub}" if sub else ""))
    lines.append("")
    for n in spec.get("notes") or []:
        parts = [f"P{n.get('inst', 1)}", str(n.get("pitch")), str(n.get("beat", 0))]
        if n.get("beats") is not None:
            parts.append(str(n.get("beats")))
        if n.get("level"):
            parts.append(str(n["level"]))
        if n.get("articulation"):
            parts.append(str(n["articulation"]))
        lines.append(" ".join(parts))
    for p in spec.get("pedals") or []:
        lines.append(f"pedal P{p.get('inst', 1)} {p.get('kind', 'sustain')} "
                     f"{p.get('start', 0)} {p.get('end', 0)}")
    for c in spec.get("curves") or []:
        pts = " ".join(f"{int(b)} {int(v)}" for b, v in c.get("points") or [])
        lines.append(f"curve P{c.get('inst', 1)} {c.get('param', 'dynamics')} {pts}")
    for t in spec.get("turns") or []:
        lines.append(f"turn {t.get('note', 0)} {t.get('kind', 'retrigger')} "
                     f"{t.get('strength', 1000)}")
    return "\n".join(lines) + "\n"


__all__ = ["parse_text", "dump_text"]
