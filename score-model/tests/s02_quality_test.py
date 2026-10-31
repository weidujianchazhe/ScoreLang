# -*- coding: utf-8 -*-
"""结构质量指标（不需要审美评分）：公式可复算、覆盖不足时明确不下结论。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import s02_api
import s02_quality

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def payload(**kw):
    base = {
        "summary": {"notes": 400, "vel_range": [300, 900], "pitch_range": [48, 84]},
        "sections": [],
        "windows": [{"window": i + 1, "density": 4.0 + (i % 3), "centroid": 60.0 + (i % 5),
                     "hard": 0.0} for i in range(12)],
        "phrases": [], "motifs": [], "variants": [], "perturbations": {"events": []},
        "harmony": {"contrary": 5, "similar": 5, "crossing": 0},
    }
    base.update(kw)
    return base


def sec(i, tension=0.4, drive=0.5, space=0.5, bright=0.5, start=None, end=None):
    s = start if start is not None else i * 8 + 1
    e = end if end is not None else (i + 1) * 8
    return {"id": f"S{i}", "start_bar": s, "end_bar": e,
            "dims": {"tension": tension, "drive": drive, "space": space, "bright": bright}}


q = s02_quality.analyze(payload())
check("Q1 指标名与说明一一对应", set(q["explain"]) == set(s02_quality.METRICS),
      str(sorted(q["explain"])))
check("Q2 覆盖不足时低置信", q["coverage"] < 0.6 and q["confidence"] == "不足",
      f"cov={q['coverage']} conf={q['confidence']}")
check("Q3 缺失项有登记", "structure" in q["missing"], str(q["missing"]))

full = payload(
    sections=[sec(0, 0.2, 0.4, 0.6, 0.4), sec(1, 0.6, 0.7, 0.3, 0.5),
              sec(2, 0.9, 0.9, 0.1, 0.6), sec(3, 0.3, 0.4, 0.6, 0.4)],
    phrases=[{"id": f"P{i}", "start_bar": i * 4 + 1, "end_bar": (i + 1) * 4}
             for i in range(8)],
    motifs=[{"id": "M1", "length": 4, "count": 6}, {"id": "M2", "length": 3, "count": 4}],
    variants=[{"motif": "M1", "transform": "inversion"}],
    perturbations={"events": [{"kind": "chromatic"}] * 8},
    voice_endings={"instances": [
        {"inst": 1, "last_end": 64, "last_permille": 700, "release_state": "given", "type": "piano"},
        {"inst": 2, "last_end": 60, "last_permille": 650, "release_state": "sustaining", "type": "violin"},
        {"inst": 3, "last_end": 58, "last_permille": 600, "release_state": "given", "type": "cello"},
    ], "piece_end": 64},
)
qf = s02_quality.analyze(full)
check("Q4 完整数据覆盖率高", qf["coverage"] >= 0.9 and qf["confidence"] == "高",
      f"cov={qf['coverage']} conf={qf['confidence']}")
check("Q5 完整数据给出各项测量值，且**没有总分键**",
      qf["metrics"] and "overall" not in qf, str(sorted(qf)))
check("Q6 均衡段落给高分",
      s02_quality.analyze(payload(sections=[sec(i) for i in range(4)],
                                  phrases=[{"id": "P", "start_bar": 1, "end_bar": 5},
                                           {"id": "P2", "start_bar": 6, "end_bar": 10}],
                                  motifs=full["motifs"], variants=full["variants"],
                                  perturbations=full["perturbations"]))["metrics"]["structure"]
      > 0.8,
      "structure within balanced sections")
tail = [sec(0, start=1, end=4), sec(1, start=5, end=8), sec(2, start=9, end=80)]
q_tail = s02_quality.analyze(payload(sections=tail))
check("Q7 末段过长 → structure 低", q_tail["metrics"]["structure"] < 0.5,
      str(q_tail["metrics"]["structure"]))

no_ret = [sec(0, 0.1, 0.1, 0.9, 0.1), sec(1, 0.5, 0.5, 0.5, 0.5), sec(2, 0.9, 0.9, 0.1, 0.9)]
check("Q8 首尾差异大 → 再现分低",
      s02_quality.analyze(payload(sections=no_ret))["metrics"]["return"] < 0.5,
      str(s02_quality.analyze(payload(sections=no_ret))["metrics"]["return"]))

flat = payload(windows=[{"window": i + 1, "density": 4.0, "centroid": 60.0, "hard": 0.0}
                        for i in range(12)])
check("Q9 密度全平 → variety 低",
      s02_quality.analyze(flat)["metrics"]["variety"] < 0.3,
      str(s02_quality.analyze(flat)["metrics"]["variety"]))

many_hard = payload(windows=[{"window": i + 1, "density": 5.0, "centroid": 60.0, "hard": 1.0}
                             for i in range(12)])
check("Q10 全难 → 好弹分低",
      s02_quality.analyze(many_hard)["metrics"]["playability"] < 0.1,
      str(s02_quality.analyze(many_hard)["metrics"]["playability"]))

check("Q11 确定性", s02_quality.analyze(full) == s02_quality.analyze(full))
check("Q12 明确声明是测量不是评分",
      "测量值" in qf["note"] and "不是评分" in qf["note"]
      and "分位数" in qf["note"], qf["note"])

# ── Q13：两架同类型钢琴（n_pianos）也要评收束 ──
import model_v02 as _mv
_sc = _mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
_sc.constraint_mode = "n_pianos"
_sc.instruments = [{"id": "P1", "type": "acoustic_grand_piano", "subtype": None, "section": None},
                   {"id": "P2", "type": "acoustic_grand_piano", "subtype": None, "section": None}]
_sc.notes = [
    _mv.NoteEvent(id="L00000001", onset=0, duration=480, voice="RH", staff="treble",
                  measure=0, pitch=_mv.PitchSpell("C", 0, 4), dynamics_permille=700,
                  release_state="given", instrument_id=1),
    _mv.NoteEvent(id="L00000002", onset=0, duration=720, voice="RH", staff="treble",
                  measure=0, pitch=_mv.PitchSpell("E", 0, 4), dynamics_permille=700,
                  release_state="given", instrument_id=2),
]
_payload = s02_api.build_payload(_sc)
_q = s02_quality.analyze(_payload)
check("Q13 n_pianos 同类型也评收束",
      _payload.get("constraint_mode") == "n_pianos"
      and _q["metrics"].get("ending_voices") is not None,
      f"cm={_payload.get('constraint_mode')} ve={_q['metrics'].get('ending_voices')}")

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
