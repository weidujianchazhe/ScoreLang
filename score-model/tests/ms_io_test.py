# -*- coding: utf-8 -*-
"""`.ms` 格式读写测试：往返、确定性、id 规则、歌词/乐器、拒绝非法输入。"""
from __future__ import annotations

import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_io as io
import ms_io as mj
import ms_semantics as ms

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


SPELL = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
         5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
         10: ("B", -1), 11: ("B", 0)}


def base_doc(n=4):
    events = []
    for i in range(n):
        semi = 60 + i
        step, alter = SPELL[semi % 12]
        events.append(ev.Event(
            id=f"L{i + 1}", instrument_id=1, onset_us=i * 250_000,
            release_us=i * 250_000 + 200_000,
            pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
            dynamics=ev.Dynamics(ms.VALUE, 1000 + i * 10, "relative_permille", "cal", "measured")))
    return ev.MSDocument(events=events)


# ── 基本往返 ──────────────────────────────────────────────
doc = base_doc()
text = io.dump(doc)
check("R1 往返事件数一致", len(io.parse(text).events) == 4)

check("R2 两次写出字节一致（确定性）", io.dump(doc) == text)

check("R3 id 为 8 位零填充",
      all(len(e.id) == 9 and e.id[0] == "L" and e.id[1:].isdigit()
          for e in io.parse(text).events),
      str([e.id for e in io.parse(text).events]))

back = io.parse(text)
check("R4 数值往返（起始/音高/力度）",
      [(e.onset_us, e.pitch.semitone, e.dynamics.permille) for e in back.events]
      == [(e.onset_us, e.pitch.semitone, e.dynamics.permille) for e in doc.events])

# ── 发声段（写在事件流里）────────────────────────────────
seg_ev = ev.Event(id="L00000001", instrument_id=1, onset_us=0, release_us=500_000,
                  pitch=ev.Pitch("C", 0, 4, 60), release_state="given",
                  dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))
d2 = ev.MSDocument(events=[seg_ev], segments=[
    ev.VoiceSegment("B00001", 0, "initial", "ch", 2, 0, 100_000,
                    event_id="L00000001", binding_id="B00001", lang="zh"),
    ev.VoiceSegment("B00001", 1, "nucleus", "ang", 2, 100_000, 500_000,
                    event_id="L00000001", binding_id="B00001", lang="zh"),
])
t2 = io.dump(d2)
b2 = io.parse(t2)
check("R5 发声段往返（段文本/时间/绑定保留）",
      [(x.kind, x.text, x.onset_us, x.release_us, x.binding_id) for x in b2.segments]
      == [(x.kind, x.text, x.onset_us, x.release_us, x.binding_id) for x in d2.segments],
      str([(x.kind, x.text) for x in b2.segments]))
check("R5b 发声段写在事件流里（无独立 vocal 块）",
      "vocal 2" not in t2 and sum(1 for ln in t2.splitlines() if " vocal " in ln) == 2)
check("R5c 音符行只写起始时间，止音是独立事件",
      all(len(ln.split()) == 15 for ln in t2.splitlines()
          if ln.startswith("L0") and " vocal " not in ln and " off " not in ln)
      and sum(1 for ln in t2.splitlines() if " off " in ln) == 1,
      str([ln for ln in t2.splitlines() if " off " in ln]))

# ── 多乐器 ────────────────────────────────────────────────
d3 = base_doc()
d3.instruments = [ev.Instrument("P1", "acoustic_grand_piano", "steinway_d"),
                  ev.Instrument("P2", "violin", None, "strings_1")]
d3.channels = "per_section"
t3 = io.dump(d3)
b3 = io.parse(t3)
check("R6 乐器表往返（类型/子类型/声部组/通道策略）",
      [(i.id, i.type, i.subtype, i.section) for i in b3.instruments]
      == [(i.id, i.type, i.subtype, i.section) for i in d3.instruments]
      and b3.channels == "per_section",
      str([(i.id, i.type, i.subtype, i.section) for i in b3.instruments]))

# ── 拒绝非法输入 ──────────────────────────────────────────
def rejects(label, mutate):
    bad = mutate(text)
    try:
        io.parse(bad)
    except io.FormatError:
        check(label, True)
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"抛了 {type(exc).__name__}")
    else:
        check(label, False, "未拒绝")

_n_ev = int(next(l for l in text.splitlines() if l.startswith("events ")).split()[1])
rejects("N1 未知区块 → 拒绝", lambda t: t.replace(f"events {_n_ev}", f"bogus {_n_ev}", 1))
rejects("N2 事件列数不符 → 拒绝",
        lambda t: t.replace("L00000002 1 250000", "L00000002 99 1 250000", 1))
rejects("N3 id 非 8 位 → 拒绝", lambda t: t.replace("L00000001", "L1", 1))
rejects("N4 计数不符 → 拒绝",
        lambda t: t.replace(f"events {_n_ev}", f"events {_n_ev + 1}", 1))
rejects("N5 缺字典 → 拒绝", lambda t: "\n".join(
    ln for ln in t.splitlines() if not ln.startswith("dict kind ")) + "\n")
rejects("N6 伪版本 → 拒绝", lambda t: t.replace("ms 1", "ms 9", 1))

# ── 流式读 ────────────────────────────────────────────────
with tempfile.NamedTemporaryFile("w", suffix=".ms", delete=False, encoding="utf-8") as fh:
    fh.write(text)
    tmp = _Path(fh.name)
try:
    check("R7 流式读事件数一致", sum(1 for _ in io.iter_events(tmp)) == 4)
finally:
    tmp.unlink(missing_ok=True)

# ── 真实谱：体积与往返 ────────────────────────────────────
sample = ROOT / "fixtures" / "legacy" / "chords_and_pedal.ms"
if sample.exists():
    d4 = mj.loads(sample.read_text(encoding="utf-8"))
    t4 = io.dump(d4)
    b4 = io.parse(t4)
    check("R8 真实谱往返（事件/踏板）",
          len(b4.events) == len(d4.events) and len(b4.pedals) == len(d4.pedals))
    check("R9 体积紧凑（每事件 < 200 字节）",
          len(t4.encode()) / max(1, len(b4.events)) < 200,
          f"{len(t4.encode()) / max(1, len(b4.events)):.0f} B/事件")

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
