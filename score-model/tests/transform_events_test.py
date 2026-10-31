# -*- coding: utf-8 -*-
"""C2 新入口测试（M-1）。"""
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
import transform_types as tc
import transform_events as te

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def mkdoc():
    return ev.MSDocument(events=[
        ev.Event(id="a", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
                 release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
    ])


DECL = tc.DirectionDecl(direction=tc.DIRECTION_MS_TO_S02, input_model="MS-1.1",
                        output_model="S02", scope_version="SV-1")
SCOPE = tc.ScopeVersion(version="SV-1", direction=tc.DIRECTION_MS_TO_S02,
                        includes=("onset_us", "release_us", "pitch_spelling",
                                  "pitch_semitone", "tuplet_ratio"))
TB = 500_000

# ── 正常路径 ────────────────────────────────────────────────
evd = te.map_events_ms_to_s02(mkdoc(), DECL, SCOPE, time_base_us=TB)
check("N1 前置通过", evd.preconditions_ok and not evd.diagnostic_only, str(evd.preconditions_detail))
check("N2 产出 ScoreV02", evd.target_obj is not None)
check("N3 目标校验通过", evd.target_validation_status == tc.TV_VERIFIED, str(evd.target_validation_errors))
check("N4 一个音符", len(evd.target_obj.notes) == 1)
check("N5 M-6 后无损失 → records 为空（力度/释放已进槽）",
      len(evd.records) == 0, str([r.source_item for r in evd.records]))
check("N6 装配完成 → assembly_complete=True",
      evd.assembly_complete is True)
check("N7 usable_as_delivery 是前置门禁（前置通过即 True），不是“允许交付”",
      evd.usable_as_delivery is True)

# ── 缺 time_base → 诊断，不猜 ──────────────────────────────
bad = te.map_events_ms_to_s02(mkdoc(), DECL, SCOPE, time_base_us=None)
check("N8 缺 time_base → 前置失败", not bad.preconditions_ok)
check("N9 前置失败 → 诊断证据", bad.diagnostic_only and bad.evidence_class == "diagnostic")
check("N10 前置失败 → 不产出目标", bad.target_obj is None)

# ── 方向错 → 拒绝 ──────────────────────────────────────────
wrong = tc.DirectionDecl(direction=tc.DIRECTION_S02_TO_MS, input_model="MS-1.1",
                         output_model="S02", scope_version="SV-1")
bad2 = te.map_events_ms_to_s02(mkdoc(), wrong, SCOPE, time_base_us=TB)
check("N11 方向错 → 前置失败", not bad2.preconditions_ok
      and any("方向" in d for d in bad2.preconditions_detail), str(bad2.preconditions_detail))

# ── 源文档非法 → 前置失败 ─────────────────────────────────
bad_doc = mkdoc()
bad_doc.events.append(ev.Event(id="bad", instrument_id=1, onset_us=1_000_000,
                               pitch=pitch(64), release_us=900_000, release_state="given"))
bad3 = te.map_events_ms_to_s02(bad_doc, DECL, SCOPE, time_base_us=TB)
check("N12 源文档非法 → 前置失败且指出原因",
      not bad3.preconditions_ok and any("不合法" in d for d in bad3.preconditions_detail),
      str(bad3.preconditions_detail))

# ── 空损失场景：无力度缺失也仍会记录 velocity 损失 ────────
# M-6.1/M-6.2 之后：力度进 `dynamics_permille`，不再是损失
check("N13 力度已进槽，不再记为损失",
      evd.target_obj.notes[0].dynamics_permille == 1000
      and not any(r.source_item.startswith("velocity:") for r in evd.records),
      str(evd.target_obj.notes[0].dynamics_permille))

# ── 与示例谱联动 ──────────────────────────────────────────
from pathlib import Path
SAMPLES = ROOT / "fixtures" / "legacy"
d = mj.loads((SAMPLES / "simple_melody.ms").read_text(encoding="utf-8"))
e2 = te.map_events_ms_to_s02(d, DECL, SCOPE, time_base_us=TB)
check("N14 示例谱经新入口 → 目标校验通过", e2.target_validation_status == tc.TV_VERIFIED,
      str(e2.target_validation_errors))
check("N15 示例谱 5 音符", len(e2.target_obj.notes) == 5, str(len(e2.target_obj.notes)))

# ── 旧入口仍在（未破坏冻结区） ────────────────────────────
check("N16 旧字段表入口已退役（transform_core 已归档）",
      not hasattr(tc, "map_fields_ms_to_s02"))

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
