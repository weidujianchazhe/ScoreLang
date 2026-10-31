# -*- coding: utf-8 -*-
"""踏板按乐器绑定：踏板是 per-instrument 的持续控制，不是全局区间。

守的是这条：**P1 的延音踏板不得延长 P8 / 弦乐 / 鼓的任何音**。
（兼容缺陷：消费者忽略 `instrument_id`，把踏板当全局区间套到所有乐器上。）
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import make_audio
import ms_audio
import ms_events as ev
import ms_io
import ms_midi
import ms_semantics as ms
import ms_validate

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


_BASE = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
         6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def note(i, inst, onset, dur, semi=60):
    step, alter = _BASE[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=inst, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


def piano(pid):
    return ev.Instrument(pid, "acoustic_grand_piano", "steinway_d")


# ── 1) 踏板行本来就带乐器（7 列：instrument kind start end depth scope targets）
p = ms_io.parse(ms_io.dump(ev.MSDocument(
    events=[note(1, 1, 0, 500_000)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 800)])))
check("P1 踏板行带 instrument_id（不是全局编号）",
      len(p.pedals) == 1 and p.pedals[0].instrument_id == 1
      and p.pedals[0].kind == "sustain", str(p.pedals[0]))

# ── 2) 发声结尾：踏板只延长自己乐器的音 ────────────────────
doc_p1_pedal = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P2")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 1000)])
check("P2 P1 的音被自己的踏板延长到 3.0s",
      ev.sounding_end_us(doc_p1_pedal) == 3_000_000, str(ev.sounding_end_us(doc_p1_pedal)))

doc_p2_only = ev.MSDocument(
    events=[note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P8")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 1000)])
check("P3 P1 的踏板不延长 P8/2 号乐器的音（踏板乐器 1 无音）",
      ev.sounding_end_us(doc_p2_only) == 500_000, str(ev.sounding_end_us(doc_p2_only)))

# ── 3) 渲染：P1 的踏板对 P2 的音零影响 ─────────────────────
d_pedal = ev.MSDocument(
    events=[note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P2")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 1000)])
d_dry = ev.MSDocument(events=[note(2, 2, 0, 500_000, 67)],
                      instruments=[piano("P1"), piano("P2")])
a_pedal = make_audio.render(d_pedal)
a_dry = make_audio.render(d_dry)
check("P4 有人踏板 / 无人踏板 → P2 的渲染完全一致",
      a_pedal.shape == a_dry.shape and np.allclose(a_pedal, a_dry),
      f"{a_pedal.shape} vs {a_dry.shape}")

d_own = ev.MSDocument(events=[note(2, 2, 0, 500_000, 67)],
                      instruments=[piano("P1"), piano("P2")],
                      pedals=[ev.PedalSegment(2, "sustain", 0, 3_000_000, 1000)])
a_own = make_audio.render(d_own)
check("P5 踏板挂在自己乐器上 → 发声结尾变长（真的延音）",
      ev.sounding_end_us(d_own) == 3_000_000 and len(a_own) > len(a_dry),
      f"end={ev.sounding_end_us(d_own)} len={len(a_own)} vs {len(a_dry)}")

def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0

_SR = make_audio.SR
before = _rms(a_own[int(2.60 * _SR):int(2.90 * _SR)])
after = _rms(a_own[int(3.05 * _SR):int(3.35 * _SR)])
check("P5b 踏板抬起（3.0s）后落制音器：尾巴立刻收干",
      before > 5 * after and after < 0.01, f"{before:.4f} → {after:.4f}")

# ── 4) 显式 targets：只作用于列出的音 ─────────────────────
d_tg = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 1, 1_000_000, 500_000, 64)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 1000, "explicit", ("L00000001",))])
check("P6 targets 只延长列出的音（后者不受影响）",
      ev.sounding_end_us(d_tg) == 3_000_000 and
      max(e.release_us for e in d_tg.events) == 1_500_000)
d_tg2 = ev.MSDocument(
    events=[note(2, 1, 1_000_000, 500_000, 64)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 3_000_000, 1000, "explicit", ("L00000001",))])
check("P7 targets 不含这个音 → 不延长",
      ev.sounding_end_us(d_tg2) == 1_500_000, str(ev.sounding_end_us(d_tg2)))

# ── 5) 乐器没声明 sustain → 校验拒绝（不能默认继承）────────
d_strings = ev.MSDocument(
    events=[note(2, 4, 0, 500_000)],
    instruments=[ev.Instrument("P4", "string_ensemble_1", "ensemble")],
    pedals=[ev.PedalSegment(4, "sustain", 0, 3_000_000, 1000)])
errs = ms_validate.validate(d_strings)
check("P8 弦乐上写 sustain → V14 拒绝", any("V14" in e for e in errs), str(errs[:2]))

# ── 6) MIDI：CC64 只发到踏板所属乐器的通道 ──────────────────
d_midi = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 8, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P8")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)],
    channels="per_instance")
blobs, _rep = ms_midi.write_midi_files(d_midi, time_base_us=500_000)
raw = b"".join(blobs)
has_p1_cc = bytes([0xB0, 64]) in raw
has_other_cc = any(bytes([0xB0 | ch, 64]) in raw for ch in range(1, 16))
check("P9 CC64 只出现在 P1 的通道", has_p1_cc and not has_other_cc,
      f"p1={has_p1_cc} other={has_other_cc}")

# ── 7) 后端参数：按 (instrument, kind) 分组 ────────────────
tracks = ms_audio.pedal_track_parameters(d_midi)
check("P10 踏板轨按 乐器:kind 分组", list(tracks) == ["1:sustain"], str(list(tracks)))

# ── 8) 往返：踏板行 7 列不丢乐器/目标 ──────────────────────
text = ms_io.dump(d_tg)
back = ms_io.parse(text)
check("P11 踏板行往返字节一致", ms_io.dump(back) == text)
check("P12 往返后乐器与 targets 不变",
      back.pedals[0].instrument_id == 1 and tuple(back.pedals[0].targets) == ("L00000001",),
      str((back.pedals[0].instrument_id, back.pedals[0].targets)))

# ── 9) 换踩（抬脚后很快再踩）要接续，不是只看音头那一段 ─────
d_rep = ev.MSDocument(
    events=[note(1, 1, 0, 1_000_000)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000),
            ev.PedalSegment(1, "sustain", 1_020_000, 2_000_000, 1000)])
check("P14 换踩间隔 20ms → 声音不断，按到 2.0s",
      ev.sustain_end_us(d_rep, d_rep.events[0]) == 2_000_000,
      str(ev.sustain_end_us(d_rep, d_rep.events[0])))

d_gap = ev.MSDocument(
    events=[note(1, 1, 0, 1_000_000)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000),
            ev.PedalSegment(1, "sustain", 1_200_000, 2_000_000, 1000)])
check("P15 换踩间隔 200ms → 制音器落下，不再接续",
      ev.sustain_end_us(d_gap, d_gap.events[0]) == 1_000_000,
      str(ev.sustain_end_us(d_gap, d_gap.events[0])))

# ── 10) 踏板就是事件：带 id、带乐器、按时间绑定 ────────────
import ms_author as au

seg = au.write_pedal(1, "sustain", 0, 2_000_000, 800)
check("P16 写踏板自动带 D+8 位 id", seg.id == "D00000001" and seg.instrument_id == 1, str(seg.id))

d_id = au.to_document([note(1, 1, 0, 500_000)],
                      instruments=[piano("P1")], pedals=[seg])
txt_id = ms_io.dump(d_id)
line_id = next(l for l in txt_id.splitlines() if l.startswith("D"))
check("P17 8 列：id 在最前，乐器第二列", line_id.split()[0] == "D00000001"
      and line_id.split()[1] == "1", line_id)
back_id = ms_io.parse(txt_id)
check("P18 带 id 的踏板行往返字节一致", ms_io.dump(back_id) == txt_id
      and back_id.pedals[0].id == "D00000001")

# 旧 7 列（无 id）写法仍原样读写
d_legacy = au.to_document([note(1, 1, 0, 500_000)], instruments=[piano("P1")],
                          pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 800)])
txt_legacy = ms_io.dump(d_legacy)
check("P19 旧 7 列写法仍字节稳定（不强加 id）",
      ms_io.dump(ms_io.parse(txt_legacy)) == txt_legacy
      and ms_io.parse(txt_legacy).pedals[0].id is None)

# 重复 id → 校验拒绝
dup = ev.MSDocument(events=[note(1, 1, 0, 500_000)], instruments=[piano("P1")],
                    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 800, id="D00000001"),
                            ev.PedalSegment(1, "sustain", 2_000_000, 3_000_000, 800, id="D00000001")])
check("P20 踏板 id 重复 → V4 拒绝",
      any("V4" in e and "重复" in e for e in ms_validate.validate(dup)),
      str(ms_validate.validate(dup)))

# 按时间绑定：踏板在音发声中途踩下 → 接住这个音（不是只看音头）
d_mid = ev.MSDocument(events=[note(1, 1, 0, 2_000_000)], instruments=[piano("P1")],
                      pedals=[ev.PedalSegment(1, "sustain", 1_000_000, 3_000_000, 1000)])
check("P21 音发到一半才踩踏板 → 从踩下起接住，延到 3.0s",
      ev.sustain_end_us(d_mid, d_mid.events[0]) == 3_000_000,
      str(ev.sustain_end_us(d_mid, d_mid.events[0])))

# 按时间绑定：踏板恰好压在同刻起点 → 绑定该音
d_same = ev.MSDocument(events=[note(1, 1, 1_000_000, 200_000)], instruments=[piano("P1")],
                       pedals=[ev.PedalSegment(1, "sustain", 1_000_000, 2_000_000, 1000)])
check("P22 同刻踩下 → 绑定该音",
      ev.sustain_end_us(d_same, d_same.events[0]) == 2_000_000,
      str(ev.sustain_end_us(d_same, d_same.events[0])))

# ── 11) 一个踏板只管一台乐器：targets 不得跨乐器 ────────────
d_cross = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P2")], piano_count=2, constraint_mode="n_pianos",
    pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 1000, "explicit",
                            ("L00000001", "L00000002"))])
errs_cross = ms_validate.validate(d_cross)
check("P23 targets 跨乐器 → V4 拒绝",
      any("跨乐器" in e for e in errs_cross), str([e for e in errs_cross if "踏板" in e]))

d_dangle = ev.MSDocument(
    events=[note(1, 1, 0, 500_000)], instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 1000, "explicit", ("L00000099",))])
check("P24 targets 指向不存在的音 → V4 拒绝",
      any("不存在" in e and "踏板" in e for e in ms_validate.validate(d_dangle)),
      str(ms_validate.validate(d_dangle)))

d_ok = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P2")], piano_count=2, constraint_mode="n_pianos",
    pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 1000, "explicit", ("L00000001",))])
check("P25 本乐器内的 targets 合法", ms_validate.validate(d_ok) == [],
      str(ms_validate.validate(d_ok)))

# global = 该乐器所有音；另一台乐器仍然不受影响
d_glob = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 2, 0, 500_000, 67)],
    instruments=[piano("P1"), piano("P2")], piano_count=2, constraint_mode="n_pianos",
    pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 1000, "explicit", ("global",))])
check("P26 global 只覆盖本乐器（P2 不被延长）",
      ev.sustain_end_us(d_glob, d_glob.events[0]) == 2_000_000
      and ev.sustain_end_us(d_glob, d_glob.events[1]) == 500_000,
      f"{ev.sustain_end_us(d_glob, d_glob.events[0])}/{ev.sustain_end_us(d_glob, d_glob.events[1])}")

# ── 12) 踏板是事件流里的一行（不单列、按时间排序）──────────
d_stream = ev.MSDocument(
    events=[note(1, 1, 0, 500_000), note(2, 1, 1_000_000, 500_000, 64)],
    instruments=[piano("P1")],
    pedals=[ev.PedalSegment(1, "sustain", 500_000, 1_200_000, 800, id="D00000001")])
txt_stream = ms_io.dump(d_stream)
blocks = [l for l in txt_stream.splitlines() if l.split()[:1] in (["events"], ["pedals"])]
check("P27 不再有独立的 pedals 区块（事件流 = 音符 + 踏板）",
      any(l.startswith("events ") for l in blocks) and not any(l.startswith("pedals ") for l in blocks),
      str(blocks))
ev_head = next(l for l in txt_stream.splitlines() if l.startswith("events "))
check("P28 事件计数含踏板与止音（2 音 + 2 止音 + 1 踏板 = 5）", ev_head == "events 5", ev_head)
lines = txt_stream.splitlines()
i_ped = next(i for i, l in enumerate(lines) if l.startswith("D00000001 "))
i_n2 = next(i for i, l in enumerate(lines) if l.startswith("L00000002 "))
check("P29 踏板行按时间插在音之间（0.5s 在 0s 与 1.0s 之间）",
      lines[i_ped].startswith("D00000001 1 0 500000") and i_ped < i_n2,
      f"ped@{i_ped} n2@{i_n2}")

# 旧文件（独立 pedals 区块）仍可读，写回时并入事件流
legacy_text = (ROOT / "fixtures" / "legacy" / "chords_and_pedal.ms").read_text(encoding="utf-8")
legacy_doc = ms_io.parse(legacy_text)
check("P30 旧文件（pedals 区块）仍解析出 2 段踏板", len(legacy_doc.pedals) == 2,
      str(len(legacy_doc.pedals)))
rewritten = ms_io.dump(legacy_doc)
check("P31 重写后踏板并入事件流、语义不变",
      "pedals 2" not in rewritten and rewritten.count(" 1 0 ") >= 1
      and len(ms_io.parse(rewritten).pedals) == 2,
      str([l for l in rewritten.splitlines() if l.startswith("events ")]))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
