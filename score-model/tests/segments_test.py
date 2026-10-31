# -*- coding: utf-8 -*-
"""发音通道（vocal 区块）测试。"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
import ms_events as ev
import ms_io
import ms_semantics as ms
import ms_validate
import pinyin as tbl

R = []
def check(n, c, d=""):
    R.append((n, bool(c), d))

check("G1 合法音节约 400", 380 <= tbl.count() <= 500, str(tbl.count()))
check("G2 s+uan 合法", tbl.is_legal("s", "uan"))
check("G3 b+uan 不合法", not tbl.is_legal("b", "uan"))
check("G4 组合编号存在", tbl.syllable_id("ch", "ang") is not None,
      str(tbl.syllable_id("ch", "ang")))

e = ev.Event(id="L00000001", instrument_id=1, onset_us=0, release_us=600_000,
             pitch=ev.Pitch("C", 0, 4, 60), release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))
bid = tbl.syllable_id("ch", "ang")
segs = [ev.VoiceSegment(bid, 0, "initial", "ch", 2, event_id="L00000001", binding_id=bid, lang="zh"),
        ev.VoiceSegment(bid, 1, "nucleus", "ang", 4, event_id="L00000001", binding_id=bid, lang="zh")]
d = ev.MSDocument(events=[e], segments=segs)
back = ms_io.parse(ms_io.dump(d))
check("G5 段往返", [(x.index, x.text, x.tone, x.lang) for x in back.segments]
      == [(0, "ch", 2, "zh"), (1, "ang", 4, "zh")],
      str([(x.index, x.text, x.tone) for x in back.segments]))
check("G6 结构校验通过", ms_validate.validate(back) == [], str(ms_validate.validate(back)))

bad = ev.MSDocument(events=[e], segments=[
    ev.VoiceSegment(bid, 0, "unknown", "ch", 9, event_id="L00000001", binding_id=bid)])
check("G7 非法段类型/声调 → 拒绝", any("V18" in x for x in ms_validate.validate(bad)),
      str(ms_validate.validate(bad)))

fail = [r for r in R if not r[1]]
print("=" * 40)
print(f"共 {len(R)} 项：通过 {len(R)-len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
