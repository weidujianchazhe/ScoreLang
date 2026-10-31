# -*- coding: utf-8 -*-
"""MS → ScoreV02 投影测试（M-1~M-3 的实现件）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_io as mj
import ms_semantics as ms
import ms_to_s02 as conv

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def ev0(semi, onset, dur=500_000, rel=None, state="given"):
    return ev.Event(id=f"n{semi}_{onset}", instrument_id=1, onset_us=onset, pitch=pitch(semi),
                    release_us=(onset + dur) if rel is None and state == "given" else rel,
                    release_state=state,
                    dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured"))


TB = 500_000

# ── 单音换算 ────────────────────────────────────────────────
doc = ev.MSDocument(events=[ev0(60, 0, 500_000), ev0(64, 500_000, 500_000)])
score, losses = conv.to_s02(doc, time_base_us=TB)
check("X1 两个音符进入 S02", len(score.notes) == 2, str(len(score.notes)))
check("X2 500ms → 480 网格（guq=480, ♩=120）", score.notes[0].duration == 480,
      str(score.notes[0].duration))
check("X3 第二个音起点 480", score.notes[1].onset == 480)
check("X4 投影结果通过 ScoreV02.validate", score.validate() == [], str(score.validate()))
check("X5 拼写被保留", (score.notes[0].pitch.step, score.notes[0].pitch.alter) == ("C", 0))
check("X6 力度写入 dynamics_permille 槽（1000）", score.notes[0].dynamics_permille == 1000, str(score.notes[0].dynamics_permille))

# ── 谱表划分 ────────────────────────────────────────────────
mix = ev.MSDocument(events=[ev0(72, 0), ev0(48, 0)])
s2, _ = conv.to_s02(mix, time_base_us=TB)
check("X7 C5 在高音谱表、C3 在低音谱表",
      {n.staff for n in s2.notes} == {"treble", "bass"}, str({n.staff for n in s2.notes}))

# ── 重叠 → 声部分配 ────────────────────────────────────────
overlap = ev.MSDocument(events=[ev0(60, 0, 1_000_000), ev0(62, 300_000, 1_000_000)])
s3, l3 = conv.to_s02(overlap, time_base_us=TB)
check("X8 重叠被分配到不同 voice", len({n.voice for n in s3.notes}) == 2,
      str([n.voice for n in s3.notes]))
check("X9 分配记录在 losses", any(l["item"].startswith("voice_created:") for l in l3))
check("X10 投影仍通过校验", s3.validate() == [], str(s3.validate()))

# ── sustaining：时长取到段末 + 记录 ────────────────────────
sus = ev.MSDocument(events=[ev0(72, 0, rel=None, state="sustaining"), ev0(60, 1_000_000, 400_000)])
s4, l4 = conv.to_s02(sus, time_base_us=TB)
check("X11 sustaining 有时长（取到段末）", s4.notes[0].duration > 0, str(s4.notes[0].duration))
check("X12 sustaining 由 release_state 承载且时长为正", s4.notes[0].release_state == "sustaining" and s4.notes[0].duration > 0, f"{s4.notes[0].release_state}/{s4.notes[0].duration}")

# ── 踏板 ────────────────────────────────────────────────────
ped = ev.MSDocument(events=[ev0(60, 0, 500_000)],
                    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000),
                            ev.PedalSegment(1, "sostenuto", 0, None, 800, "mechanical")])
s5, l5 = conv.to_s02(ped, time_base_us=TB)
kinds = [(p.pedal_type, p.action_notated) for p in s5.pedal_marks]
check("X13 踏板记号：sustain start/stop + sostenuto start",
      ("sustain", "start") in kinds and ("sustain", "stop") in kinds and ("sostenuto", "start") in kinds,
      str(kinds))
check("X14 sostenuto 带 target_scope（否则 validate 不过）",
      all(p.target_scope is not None for p in s5.pedal_marks if p.pedal_type == "sostenuto"),
      str([(p.id, p.target_scope) for p in s5.pedal_marks]))
check("X15 踏板深度写入 depth_permille 槽", s5.pedal_marks[0].depth_permille == 1000, str(s5.pedal_marks[0].depth_permille))
check("X16 踏板结果通过校验", s5.validate() == [], str(s5.validate()))

# ── 时间基准必填 ───────────────────────────────────────────
try:
    conv.to_s02(doc, time_base_us=0)
except ValueError:
    check("X17 缺 time_base → 拒绝", True)
else:
    check("X17 缺 time_base → 拒绝", False)

# ── 模型级损失记录 ────────────────────────────────────────
check("X18 模型边界不记为转换损失（M-6 归因修正）", not any(l["item"].startswith("model:") for l in losses))

# ── 示例谱端到端 ───────────────────────────────────────────
from pathlib import Path
SAMPLES = ROOT / "fixtures" / "legacy"
ok = True
detail = []
for name in ("simple_melody", "chords_and_pedal", "ornaments"):
    d = mj.loads((SAMPLES / f"{name}.ms").read_text(encoding="utf-8"))
    s, l = conv.to_s02(d, time_base_us=TB)
    errs = s.validate()
    detail.append(f"{name}:{len(s.notes)}音/{len(l)}损失/{len(errs)}错")
    if errs:
        ok = False
check("X19 三份示例谱均可投影且通过校验", ok, " | ".join(detail))

# ── M20/21：sustained 尾巴不跨全曲 ──
_d = ev.MSDocument(
    piano_count=1, instruments=[ev.Instrument("P1", "acoustic_grand_piano")],
    events=[
        ev.Event(id="a", instrument_id=1, onset_us=0,
                 pitch=ev.Pitch("C", 0, 4, 60), release_state="sustaining"),
        ev.Event(id="b", instrument_id=1, onset_us=2_000_000,
                 pitch=ev.Pitch("D", 0, 4, 62), release_us=3_000_000),
    ])
_sc, _loss = conv.to_s02(_d, time_base_us=500_000)
_na = next(n for n in _sc.notes if n.id == "a")
_nb = next(n for n in _sc.notes if n.id == "b")
check("M20 sustained 尾巴按下一音头截断",
      _na.onset + _na.duration == _nb.onset,
      f"a_end={_na.onset + _na.duration} b_on={_nb.onset}")
check("M21 记录 sustained 截断 loss",
      any("sustaining_tail" in x.get("item", "") for x in _loss), str(_loss[:2]))

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
