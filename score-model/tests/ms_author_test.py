# -*- coding: utf-8 -*-
"""写谱 API 测试：三表串联、缺失不伪造、结果满足 §7.7。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_author as au
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def one(**kw):
    base = dict(onset_us=0, duration_us=400_000, semitone=60)
    base.update(kw)
    return au.write_note(**base)


# ── 力度解析 ────────────────────────────────────────────────
e = one(level="mf")
check("W1 等级 → 数值 1250", e[0].dynamics.permille == 1250, str(e[0].dynamics))
check("W2 等级来源 notated_inferred", e[0].dynamics.src == "notated_inferred")
check("W3 标定引用为表版本", e[0].dynamics.calibration_ref == "dyn-levels-v1")

e = one(permille=1500)
check("W4 直接给值 → src=None", e[0].dynamics.permille == 1500 and e[0].dynamics.src is None)

e = one()
check("W5 都不给 → NOT_PROVIDED（不填 1000）",
      e[0].dynamics.state == ms.NOT_PROVIDED and e[0].dynamics.permille is None)

try:
    one(level="mf", permille=1200)
except ValueError:
    check("W6 等级与数值同时给 → 拒绝", True)
else:
    check("W6 等级与数值同时给 → 拒绝", False)

# ── 奏法 ────────────────────────────────────────────────────
e = one(level="mf", articulation="staccato")
check("W7 staccato 时长减半", e[0].release_us - e[0].onset_us == 200_000,
      str(e[0].release_us - e[0].onset_us))
check("W8 staccato 不改力度", e[0].dynamics.permille == 1250)

e = one(level="mf", articulation="marcato")
check("W9 marcato 时长 67%", e[0].release_us - e[0].onset_us == 268_000)
check("W10 marcato 力度 ×1.2", e[0].dynamics.permille == 1500, str(e[0].dynamics.permille))

e = one(articulation="marcato")
check("W11 未提供力度 + marcato → 仍 NOT_PROVIDED（不凭空造值）",
      e[0].dynamics.state == ms.NOT_PROVIDED and e[0].dynamics.permille is None)

# ── 装饰音 ──────────────────────────────────────────────────
e = one(level="mf", ornament="grace_short", onset_us=1_000_000)
check("W12 短倚音 → 2 个音", len(e) == 2, str(len(e)))
check("W13 倚音在前、主音在后", e[0].onset_us < e[1].onset_us,
      f"{e[0].onset_us} vs {e[1].onset_us}")

# 边界：主音在 0 秒、前方无空间 → 退化为拍上，且不得同时起音
e0 = one(level="mf", ornament="grace_short", onset_us=0)
check("W13b 无前空间 → 退化为拍上（不同起点）",
      e0[0].onset_us == 0 and e0[1].onset_us > 0, f"{e0[0].onset_us} vs {e0[1].onset_us}")

e = one(level="mf", ornament="mordent", upper_semitone=62)
check("W14 波音 → 3 个音且连续",
      len(e) == 3 and e[0].release_us == e[1].onset_us and e[1].release_us == e[2].onset_us)

e = one(duration_us=1_000_000, level="mf", ornament="trill", upper_semitone=62)
check("W15 颤音 1 秒 ≥10 个音", len(e) >= 10, str(len(e)))
check("W16 颤音交替音高", e[0].pitch.semitone == 60 and e[1].pitch.semitone == 62)

try:
    one(ornament="turn", upper_semitone=62)     # 缺 lower
except ValueError:
    check("W17 回音缺下邻音 → 拒绝", True)
else:
    check("W17 回音缺下邻音 → 拒绝", False)

# ── 组合顺序：先展开装饰音，再逐音应用奏法 ──────────────────
e = one(level="mf", ornament="mordent", upper_semitone=62, articulation="staccato")
check("W18 组合：3 个音", len(e) == 3)
check("W19 组合：每个音都被奏法缩短",
      all((x.release_us - x.onset_us) <= 270_000 for x in e),
      str([x.release_us - x.onset_us for x in e]))

# ── 和弦 ────────────────────────────────────────────────────
ch = au.write_chord(onset_us=0, duration_us=400_000, semitones=[60, 64, 67], level="mf")
check("W20 和弦 3 个音、同起点", len(ch) == 3 and {x.onset_us for x in ch} == {0})
check("W21 和弦 id 唯一", len({x.id for x in ch}) == 3, str([x.id for x in ch]))

# ── 产出必须是合法文档 ─────────────────────────────────────
doc = au.to_document(one(level="mf", ornament="mordent", upper_semitone=62))
check("W22 to_document 通过校验", ev.validate(doc) == [], str(ev.validate(doc)))

try:
    au.to_document([ev.Event(id="x", instrument_id=1, onset_us=1000,
                             pitch=ev.Pitch("C", 0, 4, 60), release_us=500,
                             release_state="given")])
except ValueError:
    check("W23 非法事件 → to_document 抛错", True)
else:
    check("W23 非法事件 → to_document 抛错", False)

# ── 拼写与半音一致 ─────────────────────────────────────────
e = one(semitone=61, spelling=("C", 1, 4))
check("W24 指定拼写可用", e[0].pitch.consistent() and e[0].pitch.semitone == 61)

e = one(semitone=61)          # 未给拼写 → 占位升号形式，必须仍自洽
check("W25 占位拼写自洽", e[0].pitch.consistent(), str(e[0].pitch))

try:
    one(duration_us=0)
except ValueError:
    check("W26 零时长 → 拒绝", True)
else:
    check("W26 零时长 → 拒绝", False)

# ── 写谱 API 覆盖：乐器 / 踏板 / 歌词 / 通道 ──────────────
_a1 = au.write_note(onset_us=0, duration_us=400_000, semitone=60, permille=800)
_a2 = au.write_note(onset_us=400_000, duration_us=400_000, semitone=62, permille=800,
                    used_ids={e.id for e in _a1})
_doc = au.to_document(
    _a1 + _a2,
    instruments=[au.make_instrument("P1", "acoustic_grand_piano", "steinway_d"),
                 au.make_instrument("P2", "violin", None, "strings_1")],
    pedals=[au.write_pedal(1, "sustain", 0, 900_000, 420)],
    segments=au.write_vocal(units=au.vocal_units("chang", 2), onset_us=800_000,
                            duration_us=400_000, semitone=64, permille=800,
                            used_ids={e.id for e in _a1 + _a2})[1],
    channels="per_section")
check("W27 可写乐器表", len(_doc.instruments) == 2, str(_doc.instruments))
check("W28 可写踏板", len(_doc.pedals) == 1 and _doc.pedals[0].depth_permille == 420)
check("W29 可写发声段（带时间/绑定）",
      len(_doc.segments) == 3 and _doc.segments[0].binding_id == "B00001"
      and _doc.segments[-1].release_us > _doc.segments[0].onset_us,
      str([(x.kind, x.text) for x in _doc.segments]))
check("W30 可设通道策略", _doc.channels == "per_section")

# ── 踏板能力校验（V14） ────────────────────────────────────
_n = au.write_note(onset_us=0, duration_us=400_000, semitone=60, permille=800)
try:
    au.to_document(_n, instruments=[au.make_instrument("P1", "harpsichord")],
                   pedals=[au.write_pedal(1, "sustain", 0, 400_000)])
    check("W31 大键琴没有延音踏板 → 拒绝", False, "居然通过")
except ValueError as _e:
    check("W31 大键琴没有延音踏板 → 拒绝", "V14" in str(_e), str(_e)[:40])

_ok = au.to_document(_n, instruments=[au.make_instrument("P1", "celesta")],
                     pedals=[au.write_pedal(1, "sustain", 0, 400_000)])
check("W32 钢片琴有延音踏板 → 允许", len(_ok.pedals) == 1)

# ── 扩展踏板语义：swell / tuning；效果踏板不做 kind ──────
_org = au.to_document(_n, instruments=[au.make_instrument("P1", "church_organ")],
                      pedals=[au.write_pedal(1, "swell", 0, 400_000, 700)])
check("W33 管风琴表情踏板", _org.pedals[0].kind == "swell")

try:
    au.to_document(_n, instruments=[au.make_instrument("P1", "electric_guitar_clean")],
                   pedals=[au.write_pedal(1, "effects", 0, 400_000, 800)])
    check("W34 效果踏板不是 kind → 拒绝", False, "居然通过")
except ValueError as _e:
    check("W34 效果踏板不是 kind → 拒绝", "kind 非法" in str(_e), str(_e)[:40])

try:
    au.to_document(_n, instruments=[au.make_instrument("P1", "acoustic_guitar_nylon")],
                   pedals=[au.write_pedal(1, "sustain", 0, 400_000)])
    check("W35 木吉他写延音踏板 → 拒绝", False, "居然通过")
except ValueError as _e:
    check("W35 木吉他写延音踏板 → 拒绝", "V14" in str(_e))

try:
    au.to_document(_n, instruments=[au.make_instrument("P1", "orchestral_harp")],
                   pedals=[au.write_pedal(1, "tuning", 0, 400_000, 300)])
    check("W36 调音踏板只有三档 → 拒绝", False, "居然通过")
except ValueError as _e:
    check("W36 调音踏板只有三档 → 拒绝", "V6" in str(_e))

# ── W38–40：写入路径必须拒绝越界音高 ──
def _rej(fn):
    try:
        fn()
        return False
    except ValueError as e:
        return "UNSUPPORTED_PITCH_RANGE" in str(e)

import ms.author as _pa
check("W38 C0 越界拒绝", _rej(lambda: _pa.pitch_to_semitone("C0")))
check("W39 C9 越界拒绝", _rej(lambda: _pa.pitch_to_semitone("C9")))
check("W40 整数越界拒绝", _rej(lambda: _pa.pitch_to_semitone(20)))


bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
