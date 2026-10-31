# -*- coding: utf-8 -*-
"""MS 模型 Markdown 文档格式（内部）测试：往返保真。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _p in (ROOT / "ms", ROOT / "ms" / "_core", ROOT / "perform",
           ROOT / "render", ROOT / "audio", ROOT / "analyze",
           ROOT / "importers"):
    sys.path.insert(0, str(_p))

import ms_events as ev  # noqa: E402
import ms_md  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


doc = ev.MSDocument(
    piano_count=1, constraint_mode="single_piano",
    instruments=[ev.Instrument("P1", "acoustic_grand_piano")],
    channels="per_section",
    events=[
        ev.Event(id="w1", instrument_id=1, onset_us=0, release_us=500_000,
                 pitch=ev.Pitch("C", 0, 4, 60),
                 dynamics=ev.Dynamics("VALUE", 800, "relative_permille",
                                      "manual", "composed")),
        ev.Event(id="w2", instrument_id=1, onset_us=700_000,
                 pitch=ev.Pitch("C", 0, 4, 60), release_state="sustaining",
                 dynamics=ev.Dynamics("NOT_PROVIDED")),
    ],
    pedals=[ev.PedalSegment(instrument_id=1, kind="sustain", start_us=0,
                            end_us=1_000_000, depth_permille=800,
                            scope="mechanical", id="D00000001")],
    turns=[ev.TurnPoint(event_id="w2", kind="retrigger", strength=900)],
    curves=[ev.CurvePoint(instrument_id=1, param="dynamics", time_us=0,
                          value=500, ramp=0)],
    segments=[ev.VoiceSegment(structure_id="B00001", index=0, kind="initial",
                              text="ch", tone=2, onset_us=0,
                              release_us=100_000, event_id="w1",
                              binding_id="B00001", lang="zh")],
    gaps=[{"code": "cc_not_imported", "severity": "info", "detail": "test"}],
    trailing_silence_us=250_000,
)
md = ms_md.dumps(doc)
check("M1 输出是 MD", md.lstrip().startswith("# MS 乐谱模型"), md[:30])
check("M2 含乐器表", "| id | type |" in md and "acoustic_grand_piano" in md)
check("M3 含音符表", "| id | inst | onset_us |" in md)
check("M4 含踏板/转折/曲线", "## 踏板" in md and "## 转折" in md and "## 曲线" in md)

back = ms_md.loads(md)
check("M5 事件数一致", len(back.events) == 2, str(len(back.events)))
check("M6 元信息保留", back.channels == "per_section"
      and back.trailing_silence_us == 250_000, f"{back.channels}/{back.trailing_silence_us}")
check("M7 音符字段保留",
      next(e for e in back.events if e.id == "w1").release_us == 500_000
      and next(e for e in back.events if e.id == "w1").dynamics.permille == 800
      and next(e for e in back.events if e.id == "w2").release_state == "sustaining",
      "w1/w2")
check("M8 踏板保留", len(back.pedals) == 1
      and back.pedals[0].id == "D00000001"
      and back.pedals[0].end_us == 1_000_000, str(back.pedals))
check("M9 转折保留", len(back.turns) == 1 and back.turns[0].kind == "retrigger")
check("M10 曲线保留", len(back.curves) == 1 and back.curves[0].value == 500)
check("M11 人声段保留", len(back.segments) == 1 and back.segments[0].text == "ch")
check("M12 缺口保留", len(back.gaps) == 1 and back.gaps[0]["code"] == "cc_not_imported")
check("M13 再往返一致", ms_md.dumps(back) == md)
try:
    ms_md._pitch("H9")
    _bad_ok = False
except ValueError:
    _bad_ok = True
check("M14 非法音名拒绝", _bad_ok)

# ── 标签式作者格式 + Guide 变量 id ──
AUTHOR = """# 我的曲子
- BPM: 120
- Meter: 4/4

## 乐器
- 1: violin
- 2: piano

## 乐谱
```notes
[n1] 1: C5 @0+1 mf
[n2] 1: C5 @2+1
[n3] 2: C3 @0+2
```

## 动作
- turn: n2 retrigger 900
- pedal: 2 sustain 0 2
"""
_adoc = ms_md.loads_authoring(AUTHOR)
check("A1 标签式编译出 3 事件", len(_adoc.events) == 3, str(len(_adoc.events)))
check("A2 自动稳定 id", [e.id for e in _adoc.events] ==
      ["L00000001", "L00000002", "L00000003"],
      str([e.id for e in _adoc.events]))
check("A3 拍→微秒（120bpm）",
      _adoc.events[0].onset_us == 0 and _adoc.events[0].release_us == 500_000,
      str((_adoc.events[0].onset_us, _adoc.events[0].release_us)))
check("A4 turn 引用 n2 → L00000002",
      len(_adoc.turns) == 1 and _adoc.turns[0].event_id == "L00000002",
      str([(x.event_id, x.kind) for x in _adoc.turns]))
check("A5 pedal 编译", len(_adoc.pedals) == 1
      and _adoc.pedals[0].end_us == 1_000_000, str(_adoc.pedals))
_rt = ms_md.loads_authoring(ms_md.dumps_authoring(_adoc, bpm=120, meter=(4, 4)))
check("A6 dump→compile 一致", len(_rt.events) == 3 and len(_rt.turns) == 1,
      f"{len(_rt.events)}/{len(_rt.turns)}")

import ms as _ms
_g = _ms.start(bpm=120, instruments=[{"type": "piano"}])
_n1 = _g.note(1, "C4", beat=0, beats=1)
_n2 = _g.note(1, "C4", beat=2, beats=1)
_g.turn(_n2, "retrigger")
_song = _g.finish()
check("A7 Guide 变量名即 id", isinstance(_n1, str)
      and _n1.startswith("w") and _song.summary()["notes"] == 2,
      f"{_n1}/{_n2}")

# ── 自定义标签 / curve 动作 / 分析闭环 ──
LOOP = """# 闭环测试
- BPM: 120
- Meter: 4/4

## 乐器
- 1: piano

## 乐谱
```notes
[motif_a] 1: C4 @0+1 mf
[n2] 1: E4 @1+1
```

## 动作
- curve: 1 dynamics 0 500 4 900
"""
_loop = ms_md.analyze_authoring(LOOP)
check("A8 自定义标签可用", len(_loop["song"]._doc.events) == 2,
      str(len(_loop["song"]._doc.events)))
check("A9 curve 动作编译", len(_loop["song"]._doc.curves) == 2,
      str(len(_loop["song"]._doc.curves)))
check("A10 作者格式→S02 报告", bool(_loop["report"].get("quality"))
      and _loop["summary"].get("notes") == 2,
      str(_loop["summary"]))

# ── 保存/加载分派 + Song.save_md ──
import tempfile as _tf, os as _os
with _tf.TemporaryDirectory() as _td:
    _p = _os.path.join(_td, "x.md")
    import ms as _ms
    _g = _ms.start(bpm=100, instruments=[{"type": "piano"}])
    _n = _g.note(1, "C4", beat=0, beats=1)
    _s = _g.finish()
    _s.save_md(_p)
    _doc2 = _ms.load(_p)
    check("B1 Song.save_md → ms.load(.md)", len(_doc2.events) == 1,
          str(len(_doc2.events)))
    _p2 = _os.path.join(_td, "x.ms")
    _s.save_ms(_p2)
    _doc3 = _ms.load(_p2)
    check("B2 Song.save_ms → ms.load(.ms)", len(_doc3.events) == 1)

# ── lint 预检 ──
_lint_ok = ms_md.lint("""# x
- BPM: 120
- Meter: 4/4
## 乐器
- 1: piano
## 乐谱
```notes
[n1] 1: C4 @0+1
```
""")
check("B3 lint 合法通过", _lint_ok["ok"], str(_lint_ok))
_lint_bad = ms_md.lint("""# x
- BPM: 120
## 乐谱
```notes
[n1] 1: H9 @0+1
```
""")
check("B4 lint 非法有行号/原因", not _lint_bad["ok"]
      and _lint_bad["issues"], str(_lint_bad))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
if bad:
    raise SystemExit(1)
