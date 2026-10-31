# -*- coding: utf-8 -*-
"""ABC → LilyPond .ly 曲谱生成器（LilyPond 未随附 abc2ly，自写）。

映射：ABC token 逐个直译 —— 音高按 abc_parse 的 MIDI 转 LilyPond 绝对音名
（LilyPond c' = C4），时值同为四分基准；和弦 <…>；力度记号在变换处附着；
!fermata! → \\fermata。力度采用 ABC 语义：仅在与前一个有变化时打印记号。

用法：cd score-model && python abc2ly.py [abc 路径] [输出 .ly 路径]
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent / "score-model"   # 不写死绝对路径
for _p in (ROOT, *(ROOT / _d for _d in ('core', 'notation', 'render', 'audio', 'transform', 'tests', 'tools', 'compose', 'importers'))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import os
import sys

import abc_parse                                    # noqa: E402

LY_NAME = {0: "c", 1: "cis", 2: "d", 3: "dis", 4: "e", 5: "f",
           6: "fis", 7: "g", 8: "gis", 9: "a", 10: "ais", 11: "b"}
LY_DUR = {4.0: "1", 3.0: "2.", 2.0: "2", 1.5: "4.", 1.0: "4", 0.75: "8.",
          0.5: "8", 0.375: "16.", 0.25: "16", 0.125: "32", 0.0625: "64"}
DYN_TO_LY = {"ppp": "\\ppp", "pp": "\\pp", "p": "\\p", "mp": "\\mp",
             "mf": "\\mf", "f": "\\f", "ff": "\\ff", "fff": "\\fff",
             "ffff": "\\ffff"}


def ly_pitch(key: int) -> str:
    """MIDI → LilyPond 绝对音名：c' = C4；C5 = c''；A2 = a,。"""
    oct_ = key // 12 - 1
    nm = LY_NAME[key % 12]
    if oct_ >= 4:
        return nm + ("'" * (oct_ - 3))
    return nm + ("," * (3 - oct_))


def ly_dur(beats: float) -> str:
    for v, tok in LY_DUR.items():
        if abs(beats - v) < 1e-6:
            return tok
    raise ValueError(f"不支持的 LilyPond 时值: {beats} 拍")


def render_voice(bars) -> str:
    out, prev_dyn = [], None
    for bar in bars:
        toks = []
        for t in bar:
            d = ly_dur(t["dur"])
            if t["kind"] == "rest":
                s = f"r{d}"
            elif t["kind"] == "chord":
                s = "< " + " ".join(ly_pitch(k) for k in t["keys"]) + f" >{d}"
            else:
                s = ly_pitch(t["keys"][0]) + d
            if t["dyn"] and t["dyn"] != prev_dyn:      # 力度仅在变化处打印
                s += DYN_TO_LY[t["dyn"]]
                prev_dyn = t["dyn"]
            if t["fermata"]:
                s += "\\fermata"
            toks.append(s)
        out.append(" ".join(toks) + " |")
    return "\n".join(out)


def build(abc_path: str, out_path: str):
    data = abc_parse.parse_abc(abc_path)
    h = data["header"]
    title = h.get("T", "无题")
    bpm = int(data["bpm"])
    key_name = data["key"]
    key_lily = f"\\key {key_name.lower()} \\major"
    if key_name.endswith("m"):
        key_lily = f"\\key {key_name[:-1].lower()} \\minor"

    ly = f"""\\version "2.13.62"
\\header {{
  title = "{title}"
  composer = "step-5"
  subtitle = "音型规律引擎（自动拼装） · 音色：Steinway Model D 卧式三角钢琴"
}}
\\score {{
  \\new PianoStaff <<
    \\new Staff = "RH" {{
      \\tempo 4 = {bpm}
      \\time {data['meter']}/4
      {key_lily}
      \\clef treble
{render_voice(data['bars']['1'])}
    }}
    \\new Staff = "LH" {{
      \\clef bass
{render_voice(data['bars']['2'])}
    }}
  >>
  \\layout {{ }}
}}
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ly)
    print(f"ly OK: {data['n_bars']} bars, {len(ly)} chars -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法：python tools/abc2ly.py <input.abc> <output.ly>")
        print("（不设默认路径：工程要能整体搬走，写死绝对路径是隐患）")
        raise SystemExit(2)
    build(sys.argv[1], sys.argv[2])
