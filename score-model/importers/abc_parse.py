# -*- coding: utf-8 -*-
"""ABC 谱面解析库 —— 适配 pattern_assembler 产出的 ABC 格式。

音高约定（源自 pattern_assembler.abc_pitch，注意：这不是标准 ABC 八度约定）：
  小写无撇号 = 八度 5（C5..B5）；小写 + n 个撇号 = 八度 5+n；
  大写无逗号 = 八度 4（C4..B4）；大写 + n 个逗号 = 八度 4-n。
  例：d = D5(74)，d' = D6(86)，D = D4(62)，D, = D3(50)，A,, = A2(45)。
时值约定：L:1/4（1 个单位 = 1 拍 = 四分音符）：
  "" = 1，"2" = 2，"4" = 4；"/" = 0.5，"//" = 0.25；
  "3/" = 0.75，"3//" = 0.375，"3/2" = 1.5（与引擎 DUR_TABLE 完全一致）。
调号：K:D → F→F#、C→C#；本文件无显式临时记号（^_=）。
装饰：!pp! !mp! !mf! !ff! 等力度记号（可持续），!fermata! 延长记号。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ('core', 'notation', 'render', 'audio', 'transform', 'tests', 'tools', 'compose', 'importers', 'gates'))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re

LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

SIG_BY_KEY = {
    "C": {}, "G": {"F": 1}, "D": {"F": 1, "C": 1},
    "A": {"F": 1, "C": 1, "G": 1}, "E": {"F": 1, "C": 1, "G": 1, "D": 1},
    "B": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1},
    "F": {"B": -1}, "Bb": {"B": -1, "E": -1}, "Eb": {"B": -1, "E": -1, "A": -1},
    "Am": {}, "Em": {"F": 1}, "Bm": {"F": 1, "C": 1}, "Dm": {"B": -1},
    "Gm": {"B": -1, "E": -1}, "Cm": {"B": -1, "E": -1, "A": -1},
    "Fm": {"B": -1, "E": -1, "A": -1, "D": -1},
}

# 力度记号 → score-model 的 permille（与 compose_step5.DYN 同一标尺）
DYN_TO_PERMILLE = {"ppp": 430, "pp": 540, "p": 660, "mp": 790, "mf": 900,
                   "f": 1060, "ff": 1280, "fff": 1580, "ffff": 1900}

PITCH_RE = re.compile(r"([=_^]*)([A-Ga-g])([,']*)")
DECOR_RE = re.compile(r"!([^!]+)!")


def token_to_midi(token: str, sig: dict) -> int:
    """ABC 音高 token → MIDI 号（C4 = 60）。token 形如 'd' 'd'' 'A,,' '^F'。"""
    m = PITCH_RE.fullmatch(token)
    if not m:
        raise ValueError(f"无法解析音高 token: {token!r}")
    acc, letter, octmarks = m.groups()
    if letter.islower():
        octave = 5 + octmarks.count("'")
    else:
        octave = 4 - octmarks.count(",")
    alter = 0
    for ch in acc:
        alter += 1 if ch == "^" else (-1 if ch == "_" else 0)
    if not acc:
        alter = sig.get(letter.upper(), 0)   # 调号内音级隐含升降
    return 12 * (octave + 1) + LETTER_PC[letter.upper()] + alter


def dur_beats(s: str) -> float:
    """ABC 时值后缀 → 拍数（L:1/4）。"""
    if not s:
        return 1.0
    m = re.fullmatch(r"(\d+)/(\d+)", s)          # 3/2 → 1.5
    if m:
        return float(m.group(1)) / float(m.group(2))
    m = re.fullmatch(r"(\d*)(/*)", s)            # 2 → 2.0；/ → 0.5；3/ → 0.75；3// → 0.375
    if m:
        n, slashes = m.group(1), m.group(2)
        if n:
            return float(n) / (2 ** (len(slashes) + 1)) if slashes else float(n)
        return 1.0 / (2 ** len(slashes))         # / → 0.5；// → 0.25
    raise ValueError(f"无法解析时值: {s!r}")


def parse_abc(path: str) -> dict:
    """解析 ABC 文件 → {header, key, meter, bpm, bars: {voice: [bar, ...]}}。

    每个 bar 是 token 列表；token = {
      "kind": "note"|"rest"|"chord",
      "keys": [MIDI...],      # rest 时为 []
      "off": 小节内起始拍, "dur": 拍数,
      "dyn": 当前力度名（持续制，ABC 语义）,
      "fermata": bool,
    }
    """
    header: dict = {}
    raw_voices: dict = {}
    cur, seen_body = None, False

    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n").strip()
        if not line or line.startswith("%"):
            continue
        if line.startswith("[V:"):
            cur = line[3:line.index("]")]
            line = line[line.index("]") + 1:].strip()
            seen_body = True
            if not line:
                continue
        elif not seen_body and re.fullmatch(r"[A-Za-z]:.*", line):
            k, v = line.split(":", 1)
            header[k] = v.strip()
            continue
        raw_voices.setdefault(cur, []).append(line)

    key = header.get("K", "C")
    sig = SIG_BY_KEY[key]
    meter = int(header.get("M", "4/4").split("/")[0])
    bpm = float(header.get("Q", "1/4=120").split("=")[1])

    bars: dict = {}
    for voice, lines in raw_voices.items():
        vbars: list = [[]]
        beat = 0.0
        dyn = None
        for line in lines:
            for tok in line.split():
                decors = DECOR_RE.findall(tok)
                core = DECOR_RE.sub("", tok)
                if not core or re.fullmatch(r"[|:\[\]]+", core):
                    # 小节线：拍位必须对齐（本引擎产出，理应精确）
                    if core and abs(beat - meter) > 1e-6:
                        raise ValueError(
                            f"V:{voice} 小节线处拍位不齐: beat={beat:.4f} != {meter}")
                    beat = 0.0
                    vbars.append([]) if core else None
                    continue
                for dc in decors:
                    if dc in DYN_TO_PERMILLE:
                        dyn = dc
                fermata = any(dc == "fermata" for dc in decors)
                if core.startswith("["):
                    end = core.index("]")
                    inner, rest = core[1:end], core[end + 1:]
                    keys = sorted({token_to_midi(m.group(0), sig)
                                   for m in PITCH_RE.finditer(inner)})
                    d = dur_beats(rest)
                    vbars[-1].append({"kind": "chord", "keys": keys, "off": beat,
                                      "dur": d, "dyn": dyn, "fermata": fermata})
                    beat += d
                elif core[0] in "zx":
                    d = dur_beats(core[1:])
                    vbars[-1].append({"kind": "rest", "keys": [], "off": beat,
                                      "dur": d, "dyn": dyn, "fermata": fermata})
                    beat += d
                else:
                    m = PITCH_RE.match(core)
                    if not m:
                        raise ValueError(f"无法解析 token: {core!r}")
                    d = dur_beats(core[m.end():])
                    vbars[-1].append({"kind": "note", "keys": [token_to_midi(m.group(0), sig)],
                                      "off": beat, "dur": d, "dyn": dyn,
                                      "fermata": fermata})
                    beat += d
        # 去掉可能因结尾小节线产生的空尾 bar
        if vbars and not vbars[-1]:
            vbars.pop()
        bars[voice] = vbars

    counts = {v: len(b) for v, b in bars.items()}
    if len(set(counts.values())) != 1:
        raise ValueError(f"两声部小节数不一致: {counts}")
    return {"header": header, "key": key, "sig": sig, "meter": meter,
            "bpm": bpm, "bars": bars, "n_bars": counts.get("1", 0)}
