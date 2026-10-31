# -*- coding: utf-8 -*-
"""S02 连续打分（P4）与反权重映射。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_score
import s02_weights as wt

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def score_of(per_bar, *, bar=1920):
    """per_bar: [[(semi, dur), ...], ...] 每个元素是一小节；同小节内音符同刻（和弦）。"""
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b, notes in enumerate(per_bar):
        t = b * bar
        for semi, dur in notes:
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=t, duration=dur, voice="RH", staff="treble",
                measure=b, pitch=spell(semi), dynamics_permille=800,
                release_state="given", instrument_id=1))
    return s


cfg = wt.load()
check("D1 权重含 score 段", "score" in cfg and cfg["score"]["drive_scale"] > 0,
      str(cfg.get("score")))

# ── 1) 范围 0..1 ──────────────────────────────────────
sparse = score_of([[(60, 1920)]] * 4)
dense = score_of([[(60, 240), (62, 240), (64, 240), (65, 240), (67, 240),
                   (69, 240), (71, 240), (72, 240)]] * 4)
a_sparse = s02_score.analyze(sparse)
a_dense = s02_score.analyze(dense)
vals = [w[k] for w in a_sparse["windows"] + a_dense["windows"] for k in s02_score.DIMS]
check("D2 四个维度都在 0..1", all(0.0 <= v <= 1.0 for v in vals), f"{min(vals)}..{max(vals)}")

# ── 2) 方向性 ─────────────────────────────────────────
check("D3 密 → 推进力高",
      a_dense["windows"][0]["drive"] > a_sparse["windows"][0]["drive"] + 0.3,
      f"{a_dense['windows'][0]['drive']} vs {a_sparse['windows'][0]['drive']}")
check("D4 稀 → 留白度高",
      a_sparse["windows"][0]["space"] > a_dense["windows"][0]["space"] + 0.3,
      f"{a_sparse['windows'][0]['space']} vs {a_dense['windows'][0]['space']}")

high = s02_score.analyze(score_of([[(84, 1920)]] * 3))
low = s02_score.analyze(score_of([[(48, 1920)]] * 3))
check("D5 高音区 → 明亮度高",
      high["windows"][0]["bright"] > low["windows"][0]["bright"] + 0.5,
      f"{high['windows'][0]['bright']} vs {low['windows'][0]['bright']}")

# 不协和和弦 vs 协和和弦
consonant = score_of([[(60, 1920), (64, 1920), (67, 1920)]] * 3)
dissonant = score_of([[(60, 1920), (61, 1920), (66, 1920)]] * 3)
t_con = s02_score.analyze(consonant)["windows"][0]["tension"]
t_dis = s02_score.analyze(dissonant)["windows"][0]["tension"]
check("D6 不协和 → 紧张度高", t_dis > t_con + 0.1, f"{t_dis} vs {t_con}")

# ── 3) 反权重 ─────────────────────────────────────────
sug = s02_score.suggest({"drive": 0.9}, {"density": 3.0}, cfg["score"])
check("D7 目标推进力高 → 密度要上调",
      sug["density"]["target"] > 3.0 and sug["density"]["delta"] > 0, str(sug))
sug2 = s02_score.suggest({"drive": 0.1}, {"density": 12.0}, cfg["score"])
check("D8 目标推进力低 → 密度要下调",
      sug2["density"]["target"] < 12.0 and sug2["density"]["delta"] < 0, str(sug2))
sug3 = s02_score.suggest({"space": 0.9}, {"density": 12.0}, cfg["score"])
check("D9 留白与密度反向", sug3["density"]["target"] < 12.0, str(sug3))
check("D10 建议带解释", "density" in s02_score.explain(sug), s02_score.explain(sug))
check("D11 空目标不崩", s02_score.explain(s02_score.suggest({}, {}, cfg["score"])))

# ── 4) 权重可换 ───────────────────────────────────────
wide = wt.load()
wide["score"]["drive_scale"] = 0.5      # 更陡 → 同样密度的推进力更接近 1
steeper = s02_score.analyze(dense, weights=wide)["windows"][0]["drive"]
check("D12 换 scale 会改变分数", steeper != a_dense["windows"][0]["drive"],
      f"{steeper} vs {a_dense['windows'][0]['drive']}")

# ── 5) 确定性 ─────────────────────────────────────────
check("D13 两次打分一致",
      s02_score.analyze(dense) == s02_score.analyze(dense))

# ── 6) 段落聚合 ───────────────────────────────────────
secs = [{"id": "SA", "label": "x", "start_bar": 1, "end_bar": 2},
        {"id": "SB", "label": "y", "start_bar": 3, "end_bar": 4}]
res = s02_score.analyze_sections(dense, secs)
check("D14 段落维度齐全",
      len(res["sections"]) == 2 and all(k in res["sections"][0] for k in s02_score.DIMS),
      str(res["sections"][0]))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
