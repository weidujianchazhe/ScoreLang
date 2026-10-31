# -*- coding: utf-8 -*-
"""S02 索引层（`.s02x`）：动机签名、关系边、SQLite 往返与查询。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import tempfile

import model_v02 as mv
import s02_index
import s02_io

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def score_of(semis, durs=None, *, onset0=0):
    """按给定音高/时值造一条单声部旋律。"""
    durs = durs or [480] * len(semis)
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    t = onset0
    for i, (semi, d) in enumerate(zip(semis, durs)):
        step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
        alter = 1 if "#" in step else 0
        s.notes.append(mv.NoteEvent(
            id=f"L{i + 1:08d}", onset=t, duration=d, voice="RH", staff="treble",
            measure=t // 1920, pitch=mv.PitchSpell(step[0], alter, semi // 12 - 1),
            dynamics_permille=800, release_state="given", instrument_id=1))
        t += d
    return s


# ── 1) 完全重复 ────────────────────────────────────────
mel = [60, 62, 64, 65, 67]
s1 = score_of(mel + mel)
idx1 = s02_index.build(s1)
check("I1 完全重复被识别为动机", len(idx1["motifs"]) >= 1,
      str([(m.id, m.length, m.count) for m in idx1["motifs"]]))
m1 = max(idx1["motifs"], key=lambda m: m.length)
check("I2 动机长度覆盖整段（5 音）", m1.length == 5, str(m1.length))
check("I3 两次出现", m1.count == 2, str(m1.count))
check("I4 同高重复 → 移调 0", {o[2] for o in m1.occurrences} == {0},
      str(m1.occurrences))

# ── 2) 移调重复 ────────────────────────────────────────
s2 = score_of(mel + [x + 3 for x in mel])
idx2 = s02_index.build(s2)
m2 = max(idx2["motifs"], key=lambda m: m.length)
check("I5 移调重复被识别", m2.count == 2 and m2.length == 5, str((m2.length, m2.count)))
check("I6 移调量记为 +3", {o[2] for o in m2.occurrences} == {0, 3},
      str([o[2] for o in m2.occurrences]))
check("I7 签名是移调不变的（只有音程）",
      "iv=" in m2.signature and "60" not in m2.signature, m2.signature)

# ── 3) 节奏变形 → 不是同一动机 ─────────────────────────
s3 = score_of(mel + [x + 3 for x in mel],
              [480] * 5 + [960] * 5)
idx3 = s02_index.build(s3)
long_motifs = [m for m in idx3["motifs"] if m.length >= 5 and m.count >= 2]
check("I8 节奏拉宽后不再判为同一动机", not long_motifs,
      str([(m.id, m.length, m.count) for m in long_motifs]))

# ── 4) 无重复 → 无动机 ─────────────────────────────────
s4 = score_of([60, 63, 66, 70, 75])
check("I9 无重复旋律 → 无动机", s02_index.build(s4)["motifs"] == [],
      str(s02_index.build(s4)["motifs"]))

# ── 5) 关系边 ──────────────────────────────────────────
idx5 = s02_index.build(s2)
kinds = {}
for a, b, k, w in idx5["edges"]:
    kinds[k] = kinds.get(k, 0) + 1
check("I10 相邻边 = 音数-1", kinds.get("next") == len(s2.notes) - 1, str(kinds))
check("I11 同动机出现之间建 similar 边", kinds.get("similar", 0) >= 1, str(kinds))

chord = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
chord.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
for i, semi in enumerate([60, 64, 67]):
    chord.notes.append(mv.NoteEvent(
        id=f"L{i + 1:08d}", onset=0, duration=480, voice="RH", staff="treble",
        measure=0, pitch=mv.PitchSpell("C", 0, 4), dynamics_permille=800,
        release_state="given", instrument_id=1))
check("I12 同刻音之间建 simult 边",
      sum(1 for e in s02_index.build(chord)["edges"] if e[2] == "simult") == 3,
      str([e for e in s02_index.build(chord)["edges"] if e[2] == "simult"]))

# ── 6) 落盘与查询 ──────────────────────────────────────
tmp = _Path(tempfile.mkdtemp()) / "t.s02x"
s02_index.save(idx2, tmp, meta={"source": "test"})
con = s02_index.open_index(tmp)
st = s02_index.stats(con)
check("I13 落盘后统计一致",
      st["notes"] == len(s2.notes) and st["motifs"] == len(idx2["motifs"]),
      str(st))
check("I14 动机表可查", any(r[0] == m2.id for r in s02_index.motifs(con)),
      str(s02_index.motifs(con)[:3]))
check("I15 按动机查出现", len(s02_index.occurrences(con, m2.id)) == 2,
      str(s02_index.occurrences(con, m2.id)))
start = m2.occurrences[0][0]
check("I16 按音查动机", any(r[0] == m2.id for r in s02_index.motif_of(con, start)),
      str(s02_index.motif_of(con, start)))
check("I17 特征表有值", s02_index.feature(con, "window", 1).get("density") is not None,
      str(s02_index.feature(con, "window", 1)))
check("I18 meta 写入", con.execute("SELECT value FROM meta WHERE key='source'").fetchone()[0] == "test")

# ── 6b) 段落/句读写进索引 ──────────────────────────────
check("I18b 索引里有段落表", s02_index.stats(con)["sections"] >= 1,
      str(s02_index.stats(con)))
check("I18c 段落可按小节反查",
      s02_index.section_at(con, 1) is not None
      and s02_index.section_at(con, 1)[0] == s02_index.sections(con)[0][0],
      str(s02_index.sections(con)))
con.close()

# ── 7) 确定性 ─────────────────────────────────────────
a = [(m.id, m.signature, m.length, m.count) for m in s02_index.build(s2)["motifs"]]
b = [(m.id, m.signature, m.length, m.count) for m in s02_index.build(s2)["motifs"]]
check("I19 两次建索引结果一致", a == b)

# ── 8) s02 往返与索引可重建 ────────────────────────────
text = s02_io.dump(s2)
back = s02_io.parse(text)
check("I20 从 .s02 重建索引结果一致",
      [(m.id, m.signature, m.length, m.count) for m in s02_index.build(back)["motifs"]] == a)

# ── 7b) 变体分类（倒影 / 逆行 / 节奏变形）──────────────
def melody(semis, durs=None):
    return score_of(semis, durs)


base5 = [60, 62, 64, 65, 67]           # 5 音 / 4 个音程
inv5 = [60, 58, 56, 55, 53]            # 音程取反
ret5 = [67, 65, 64, 62, 60]            # 倒序取反

v_inv = s02_index.build(melody(base5 + base5 + inv5))
v_ret = s02_index.build(melody(base5 + base5 + ret5))
v_rhy = s02_index.build(melody(base5 + base5 + base5,
                              [480] * 10 + [960] * 5))
v_plain = s02_index.build(melody(base5 + base5))

kinds = lambda r: {x[1] for x in r["variants"]}
check("I21 倒影被识别", "inversion" in kinds(v_inv), str(v_inv["variants"]))
check("I22 逆行被识别", "retrograde" in kinds(v_ret), str(v_ret["variants"]))
check("I23 节奏变形被识别", "rhythmic" in kinds(v_rhy), str(v_rhy["variants"]))
check("I24 纯重复不产生变体", v_plain["variants"] == [], str(v_plain["variants"]))
check("I25 变体落在母动机上",
      all(x[0] == v_inv["motifs"][0].id for x in v_inv["variants"]),
      str(v_inv["variants"]))
check("I26 变体边写入关系网",
      any(e[2] == "variant" for e in v_inv["edges"]),
      str([e for e in v_inv["edges"] if e[2] == "variant"][:3]))

# ── 6c) 变体落盘可查 ───────────────────────────────────
tmp2 = _Path(tempfile.mkdtemp()) / "v.s02x"
s02_index.save(v_inv, tmp2)
con2 = s02_index.open_index(tmp2)
check("I27 变体表可查", len(s02_index.variants(con2)) == len(v_inv["variants"]),
      str(s02_index.variants(con2)))
check("I28 动机查询带变体数",
      any(r[4] > 0 for r in s02_index.motifs(con2)), str(s02_index.motifs(con2)))
con2.close()

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
