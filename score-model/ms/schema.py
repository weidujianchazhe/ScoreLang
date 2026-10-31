# -*- coding: utf-8 -*-
"""数据字典：字段、单位、力度等级、奏法、曲线参数。"""
from __future__ import annotations

import ms_articulation as _art
import ms_dynamics_levels as _dl
import ms_ornament as _orn
from ms_instruments import CURVE_PARAMS

from .task import FRIENDLY, instrument_actions


def detail() -> dict:
    """完整数据字典。"""
    return {
        "version": "ms-task-1",
        "units": {"time": "beat（拍）", "tempo": "bpm", "meter": "[拍数, 拍值]"},
        "fields": {
            "bpm": {"type": "number", "default": 120, "note": "每分钟拍数"},
            "meter": {"type": "[int,int]", "default": [4, 4]},
            "instruments": {
                "type": "list[{type, subtype?}]",
                "aliases": sorted(FRIENDLY),
                "note": "同类型可多件（写两次就是两把）；类型表见 ms.instruments()",
            },
            "notes": {
                "type": "list[{inst, pitch|pitches, beat, beats, level?, permille?, articulation?, ornament?}]",
                "note": "beat/beats 以拍为单位；pitch 用 'C4'/'F#5'/'Bb3'；pitches 写和弦",
            },
            "pedals": {
                "type": "list[{inst, kind, start, end}]",
                "default": "auto（脚本派生：每小节一踩、抬脚 100ms）",
                "kinds": {"piano": ["sustain", "sostenuto", "una_corda"], "strings": ["sordino"]},
            },
            "turns": {
                "type": "list[{note: 音符组下标, kind, strength?}]",
                "note": "动作可查 ms.instrument_actions('violin')；不写 = 不派生",
            },
            "curves": {
                "type": "list[{inst, param, points: [[beat, value], ...]}]",
                "params": {k: {"min": v[0], "max": v[1]} for k, v in CURVE_PARAMS.items()},
            },
            "pedal": {"type": "string", "values": ["auto", "none"], "default": "auto"},
        },
        "levels": dict(_dl.PERMILLE),
        "level_anchor": {"permille": _dl.ANCHOR_PERMILLE, "velocity": _dl.ANCHOR_VELOCITY},
        "articulations": {k: {"gate_pm": v["gate_pm"], "vel_pm": v["vel_pm"]}
                          for k, v in _art.ARTICULATIONS.items()},
        "ornaments": {"grace_short_permille": _orn.GRACE_SHORT_PM,
                      "appoggiatura_permille": _orn.APPOGGIATURA_LONG_PM,
                      "mordent_aux_permille": _orn.MORDENT_AUX_PM,
                      "trill_rate_hz": _orn.TRILL_RATE_HZ,
                      "turn_each_permille": _orn.TURN_EACH_PM},
        "voice": {"available": False,
                  "note": "人声暂不支持"},
        "limits": {
            "pitch_range": [21, 108],
            "pedal_chain": "单条 sustain 链 ≥60s 且覆盖 ≥80% 曲长 → 判错（会糊成一片）",
            "pedal_gap": "自动派生抬脚 100ms；<50ms 会被判为同一脚",
        },
        "perform": perform(),
        "examples": {
            "minimal": {"bpm": 96, "instruments": [{"type": "piano"}],
                        "notes": [{"inst": 1, "pitch": "C4", "beat": 0, "beats": 1}]},
            "with_actions": {"turns": [{"note": 0, "kind": "retrigger"}],
                             "curves": [{"inst": 1, "param": "dynamics",
                                         "points": [[0, 500], [4, 900]]}]},
        },
    }


def perform() -> dict:
    """演奏字典：每件乐器能用的奏法/装饰音/转折/踏板，以及怎么写。"""
    from .task import FRIENDLY, instrument_actions
    from ms.registry import articulations as _art, ornaments as _orn
    from ms_instruments import resolve as _resolve

    by = {}
    for alias, code in FRIENDLY.items():
        by[alias] = {
            "type": code,
            "articulations": _art(code),
            "ornaments": _orn(code),
            "turns": instrument_actions(alias),
            "pedals": list(_resolve(code).get("pedals") or ()),
        }
    return {
        "how": {
            "articulations": 'notes 里加 "articulation": "staccato"',
            "ornaments": 'notes 里加 "ornament": "trill"',
            "turns": '顶层 "turns": [{"note": <音符下标>, "kind": "bow_change"}]',
            "curves": '顶层 "curves": [{"inst": 1, "param": "dynamics", '
                      '"points": [[0, 600], [4, 900]]}]',
            "pedals": '顶层 "pedals": [{"inst": 1, "kind": "sustain", '
                      '"start": 0, "end": 4}]',
            "levels": 'notes 里加 "level": "mf"（等级表见 ms.schema()）',
        },
        "curves": {k: list(v) for k, v in CURVE_PARAMS.items()},
        "levels": sorted(_dl.PERMILLE),
        "instruments": by,
    }


def text() -> str:
    """精简文本版（一屏）。"""
    d = detail()
    levels = " ".join(f"{k}={v}" for k, v in d["levels"].items())
    arts = " ".join(f"{k}(gate{v['gate_pm']},vel{v['vel_pm']})"
                    for k, v in d["articulations"].items())
    curves = " ".join(f"{k}[{v['min']}..{v['max']}]" for k, v in d["fields"]["curves"]["params"].items())
    aliases = " ".join(d["fields"]["instruments"]["aliases"])
    return "\n".join([
        f"数据字典 {d['version']}（按字段填写任务 JSON）",
        f"时间单位：拍；速度 bpm；拍号 meter=[拍数,拍值]",
        f"乐器别名：{aliases}（同类型多件=写两次）",
        f"音符：inst, pitch('C4'/'F#5'), beat, beats, level?, articulation?, ornament?",
        f"力度等级（permille）：{levels}（锚点 {d['level_anchor']['permille']}）",
        f"奏法影响：{arts}",
        f"曲线参数：{curves}",
        f"踏板：默认 auto（每小节一踩、抬脚100ms）；kinds piano=sustain/sostenuto/una_corda",
        f"动作：ms.instrument_actions(乐器) 查；turns=[{{note:下标, kind:'bow_change'}}]",
        f"演奏字典：ms.perform()（每件乐器的奏法/装饰音/转折/踏板 + 怎么写）",
        f"限制：音高 21..108；踏板链 ≥60s 且 ≥80% 曲长判错",
        "人声：暂不支持",
    ])


__all__ = ["detail", "text", "perform", "prime"]

def prime() -> str:
    """写谱前必读：可选乐器全表 + 每件能写哪些演奏 + 两种写法 + 最小示例。"""
    from ms_instruments import resolve as _resolve
    from ms.registry import articulations as _art, ornaments as _orn

    perf = perform()
    lines = ["# 写谱前必读（乐谱模型）", ""]
    lines += ["## 一、可选乐器（别名 → 类型 / 音域 / 踏板）", ""]
    for alias, code in FRIENDLY.items():
        spec = _resolve(code)
        rng = spec.get("range") or (0, 127)
        ped = list(spec.get("pedals") or ())
        lines.append(f"- `{alias}` → {code}｜音域 {rng[0]}..{rng[1]}｜"
                     f"踏板 {('/'.join(ped)) or '无'}")
    lines += ["", "## 二、每件乐器能写什么演奏", ""]
    for alias in FRIENDLY:
        info = perf["instruments"][alias]
        lines.append(f"### {alias}")
        lines.append(f"- 奏法：{'/'.join(info['articulations']) or '无'}")
        lines.append(f"- 装饰音：{'/'.join(info['ornaments']) or '无'}")
        lines.append(f"- 转折（音头/技法）：{'/'.join(info['turns']) or '无'}")
        lines.append(f"- 踏板：{'/'.join(info['pedals']) or '无'}")
        lines.append("")
    lines += ["## 三、怎么写（两种方式，效果相同）", "",
              "### A. 任务 JSON（一次交完整数据）", "```json",
              '{"bpm": 96, "instruments": [{"type": "piano"}],',
              ' "notes": [{"inst":1,"pitch":"C4","beat":0,"beats":1,"level":"mf",',
              '            "articulation":"staccato","ornament":"trill"}],',
              ' "turns": [{"note":0,"kind":"key_noise"}],',
              ' "curves": [{"inst":1,"param":"dynamics","points":[[0,600],[4,900]]}],',
              ' "pedals": [{"inst":1,"kind":"sustain","start":0,"end":4}]}',
              "```", "",
              "### B. 向导（逐步填，id 自动派生）", "```python",
              'g = ms.start(bpm=96, instruments=[{"type": "piano"}])',
              'g.note(1, "C4", beat=0, beats=1, level="mf",',
              '       articulation="staccato", ornament="trill")',
              'g.pedal(1, "sustain", 0, 4)',
              'song = g.finish()',
              "```", ""]
    lines += ["## 四、力度与曲线", "",
              f"- 力度等级：{' '.join(sorted(_dl.PERMILLE))}",
              f"- 曲线参数：{'；'.join(f'{k}[{v[0]}..{v[1]}]' for k, v in CURVE_PARAMS.items())}",
              "- 写法：notes 里 `level`/`permille`；曲线用顶层 `curves`", ""]
    lines += ["## 五、限制（收束）", "",
              "- 音高 21..108；时间≥0；释放状态/激励类型用枚举；",
              "- 踏板同乐器同踏板两次踩下间隔 <100µs 拒绝；",
              "- 人声通道未实现；",
              "- **内置合成器仅用于接口测试**（音色差）；成品请安装外部渲染器 + 音色库。", ""]
    return "\n".join(lines)

