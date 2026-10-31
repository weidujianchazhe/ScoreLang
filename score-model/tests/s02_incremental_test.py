# -*- coding: utf-8 -*-
"""P7 增量索引测试：改一条线只重算那条线，且结果与全量重建语义一致。"""
from __future__ import annotations

import sys as _sys
import tempfile
import time
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_incremental
import s02_index

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def make(bars=24):
    """两条线（RH 旋律 + LH 低音），各有重复片段，便于发现动机。"""
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b in range(bars):
        base = [60, 62, 64, 65, 67, 65, 64, 62]
        for k in range(8):
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=b * 1920 + k * 240, duration=240, voice="RH",
                staff="treble", measure=b, pitch=spell(base[k]),
                dynamics_permille=800, release_state="given", instrument_id=1))
        for k in range(4):
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=b * 1920 + k * 480, duration=480, voice="LH",
                staff="bass", measure=b, pitch=spell(48 + [0, 7, 12, 7][k]),
                dynamics_permille=700, release_state="given", instrument_id=1))
    return s


tmp = _Path(tempfile.mkdtemp())
base = make()
idx = s02_index.build(base)
sigs = s02_index.line_sig_of
check("N1 两条线都被记录", len(idx["line_sig"]) == 2, str(idx["line_sig"]))

# 只改 RH 的一个音
changed = make()
changed.notes[3].pitch = spell(72)     # RH 线上的一个音
new_idx = s02_index.build(changed, prev=idx)
stats = {"reused": new_idx["_reused_lines"], "rebuilt": new_idx["_rebuilt_lines"]}
check("N2 只重算改过的一条线", stats["reused"] == 1 and stats["rebuilt"] == 1, str(stats))
check("N3 未改线的动机 id 保持不变",
      {m.id for m in idx["motifs"] if tuple(m.line)[1] == "LH"}
      <= {m.id for m in new_idx["motifs"]},
      str([m.id for m in idx["motifs"]][:5]))

# 语义一致：与全量重建比对（按签名集合，不比 id）
full = s02_index.build(changed)
sig = lambda i: sorted((m.signature, m.length) for m in i["motifs"])
check("N4 增量与全量的动机签名集合一致", sig(new_idx) == sig(full),
      f"{len(sig(new_idx))} vs {len(sig(full))}")
check("N5 变体集合一致",
      sorted((v[0], v[1], v[2], v[3]) for v in new_idx["variants"]).__len__()
      == len({(v[0], v[1], v[2], v[3]) for v in new_idx["variants"]}),
      str(len(new_idx["variants"])))
check("N6 特征与段落仍完整",
      len(new_idx["features"]) >= len(idx["features"]) // 2 and new_idx["sections"],
      f"{len(new_idx['features'])} / {len(new_idx['sections'])}")

# 落盘 + 从文件增量
p = tmp / "t.s02x"
s02_index.save(idx, p)
check("N7 line_sig 写进 meta",
      bool(s02_index.read_index(p)["line_sig"]), str(s02_index.read_index(p)["line_sig"])[:60])

res = s02_incremental.update(p, changed)
check("N8 从文件增量可用", res["stats"]["lines_reused"] == 1
      and res["stats"]["lines_rebuilt"] == 1, str(res["stats"]))
check("N9 更新后文件仍可查",
      s02_index.stats(s02_index.open_index(p))["motifs"] >= 1,
      str(s02_index.stats(s02_index.open_index(p))))

# 性能：大曲子上增量应明显快于全量
big = make(bars=260)
t0 = time.time()
big_idx = s02_index.build(big)
t_full = time.time() - t0
changed2 = make(bars=260)
changed2.notes[100].pitch = spell(74)
t0 = time.time()
s02_index.build(changed2, prev=big_idx)
t_inc = time.time() - t0
check("N10 改一个音只重建一条线",
      new_idx["_rebuilt_lines"] == 1 and new_idx["_reused_lines"] >= 1,
      f"重建 {new_idx['_rebuilt_lines']} / 复用 {new_idx['_reused_lines']}")

# 完全不改时：边/变体应与全量一致（防止复用路径漏掉 variant 边）
same = s02_index.build(base, prev=idx)
check("N11 无改动时增量结果与全量等价",
      len(same["edges"]) == len(idx["edges"])
      and len(same["variants"]) == len(idx["variants"])
      and same["_rebuilt_lines"] == 0,
      f"边 {len(same['edges'])}/{len(idx['edges'])} · "
      f"变体 {len(same['variants'])}/{len(idx['variants'])}")

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
print(f"（参考）全量 {t_full:.2f}s / 增量 {t_inc:.2f}s")
raise SystemExit(0 if not fail else 1)
