# -*- coding: utf-8 -*-
"""ABC → 乐谱模型文档（`.md`）的导入桥（技能产出物 → 工程模型）。

技能（`skills/`）产出 ABC 双行谱，而工程只认模型文档 —— 本桥把两者接起来，
之后可走 `mscli validate / render / export / flow run` 原生管线。

输出按后缀分派：`.md` → 文档写法（现行）；其它 → 兼容 JSON 写法（只读兼容）。

用法：cd score-model && python importers/abc2ms.py <输入.abc> <输出.md>
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms/_core", "perform", "analyze", "render",
                                         "audio", "importers", "tools", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import os
import sys

import abc_parse                                    # noqa: E402
import ms_events as ev                              # noqa: E402
import ms_io as msj                               # noqa: E402

SHARP = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
         6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def spell(key: int):
    step, alter = SHARP[key % 12]
    return step, alter, key // 12 - 1


def build(abc_path: str, out_path: str):
    data = abc_parse.parse_abc(abc_path)
    n_bars, meter, bpm = data["n_bars"], data["meter"], data["bpm"]
    q_us = 60_000_000.0 / bpm
    bar_us = meter * q_us

    notes: list[dict] = []
    pedals: list[dict] = []
    _last_rel: dict = {}          # key → 该键最后释放时刻（µs）：未释放的同键再击
                                   # 物理上不可能，把后击者微移到释放之后（1µs 不可闻）
    _id = [0]

    def add_note(onset_us, dur_us, key, vel, hand, extend=0.0):
        onset_us = int(round(onset_us))
        # 音尾留 25ms 抬指间隙：谱面上的 legato 让前音 release 与后音 onset 完全重合，
        # 而钢琴同键必须抬起才能重击，MIDI 校验会判"间隔 0ms < 20ms"不可弹。
        gap = 25_000.0 if dur_us > 60_000.0 else 5_000.0
        release_us = int(round(onset_us + dur_us - gap + extend))
        if release_us <= onset_us:
            release_us = onset_us + 1_000
        prev = _last_rel.get(key, -1)
        if onset_us < prev:                   # 仅"早于上一音释放"才算真重叠
            shift = prev + 1 - onset_us
            onset_us += shift
            release_us += shift
        _last_rel[key] = release_us
        step, alter, oct_ = spell(key)
        _id[0] += 1
        notes.append({
            "id": f"n{_id[0]:05d}",
            "instrument_id": 1,
            "onset_us": onset_us,
            "pitch": ev.Pitch(step=step, alter=alter, octave=oct_, semitone=key),
            "excitation_type": "impulse",
            "release_us": release_us,
            "release_state": "given",
            "dynamics": ev.Dynamics("VALUE", permille=vel,
                                    scale="relative_permille",
                                    calibration_ref="dyn-levels-v1",
                                    src="notated_inferred"),
            "is_grace": False,
        })

    # ── 1) 音符事件 ────────────────────────────────────────────
    # 必须先按时间全局排序再落音符：_last_rel 是按音高的全局表，若先跑完右手
    # 96 小节再回头跑左手，左手开头就会撞上右手末尾才释放的同键音，被平移几百秒。
    pending = []
    for voice, hand in (("1", "rh"), ("2", "lh")):
        for bi, bar in enumerate(data["bars"][voice]):
            t0 = bi * bar_us
            for tok in bar:
                if tok["kind"] == "rest":
                    continue
                onset = t0 + tok["off"] * q_us
                dur = tok["dur"] * q_us
                vel = abc_parse.DYN_TO_PERMILLE[tok["dyn"] or "mf"]
                extend = 6_000_000.0 if tok["fermata"] else 0.0   # 尾音多响 6s
                for k in tok["keys"]:
                    pending.append((onset, dur, k, vel, hand, extend))
    pending.sort(key=lambda x: (x[0], x[2]))
    for onset, dur, k, vel, hand, extend in pending:
        add_note(onset, dur, k, vel, hand, extend)

    # ── 2) 自动踏板（ABC 无踏板信息，按叙事密度分段做渲染踏板）────
    def add_pedal(s_us, e_us):
        pedals.append(ev.PedalSegment(instrument_id=1, kind="sustain",
                                      start_us=int(round(s_us)),
                                      end_us=int(round(e_us)),
                                      depth_permille=1000,
                                      scope="mechanical", targets=None))

    DENSE_START, DENSE_END = 49, 112          # B 段 + 副歌：十六分/八度密集区
    for bi in range(n_bars - 1):
        b0 = bi * bar_us
        if DENSE_START <= bi + 1 <= DENSE_END:
            add_pedal(b0, b0 + bar_us / 2 - 150_000)
            add_pedal(b0 + bar_us / 2, b0 + bar_us - 150_000)
        else:
            add_pedal(b0, b0 + bar_us - 150_000)
    # 末小节：长踏板让主和弦余音延续（配合 fermata 延音）
    add_pedal((n_bars - 1) * bar_us,
              (n_bars - 1) * bar_us + bar_us + 6_000_000)

    # ── 3) 组装 + 双保险校验 ──────────────────────────────────
    evs = [ev.Event(id=n["id"], instrument_id=n["instrument_id"], onset_us=n["onset_us"],
                    pitch=n["pitch"], excitation_type=n["excitation_type"],
                    release_us=n["release_us"], release_state=n["release_state"],
                    dynamics=n["dynamics"], is_grace=n["is_grace"])
           for n in notes]
    doc = ev.MSDocument(piano_count=1, constraint_mode="single_piano",
                        events=evs, pedals=pedals, gaps=[], retired_ids=[])
    errs = ev.validate(doc)
    if errs:
        print("VALIDATE FAILED:")
        for e in errs[:20]:
            print("  -", e)
        sys.exit(1)
    if out_path.lower().endswith(".md"):
        import ms_md
        payload = ms_md.dumps_authoring(doc, bpm=bpm)
    else:
        payload = msj.dumps(doc)                # 兼容 JSON 写法：只读兼容用
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(payload)

    lo = min(n["pitch"].semitone for n in notes)
    hi = max(n["pitch"].semitone for n in notes)
    print(f"已写出：{len(evs)} 事件 / {len(pedals)} 踏板 / "
          f"{n_bars} 小节 @ {bpm}bpm = {n_bars * meter * q_us / 1e6:.1f}s")
    print(f"pitch range: {lo}..{hi} ({hi - lo} semitones)")
    print(f"written: {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法：python importers/abc2ms.py <输入.abc> <输出.md>")
        print("（不设默认路径：工程要能整体搬走，写死绝对路径是隐患）")
        raise SystemExit(2)
    build(sys.argv[1], sys.argv[2])
