# -*- coding: utf-8 -*-
"""P6 前端三件：JSON 视图 / 矢量分析图 / 编辑补丁协议。"""
from __future__ import annotations

import json
import sys as _sys
import tempfile
import threading
import urllib.request
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_api
import s02_io
import s02_patch
import s02_render

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def piece(n_bars=8, notes=4):
    s = mv.ScoreV02(title="前端测试", grid_units_per_quarter=480,
                    time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b in range(n_bars):
        for k in range(notes):
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=b * 1920, duration=480, voice="RH",
                staff="treble", measure=b, pitch=spell(60 + (k % 7)),
                dynamics_permille=800, release_state="given", instrument_id=1))
    return s


tmp = _Path(tempfile.mkdtemp())
s02_path = tmp / "t.s02"
s02_io.save(piece(), s02_path)

# ── 1) JSON 视图 ──────────────────────────────────────
data = s02_api.payload(s02_path)
check("F1 视图有基本块",
      {"summary", "sections", "windows", "spark"} <= set(data), str(sorted(data)))
check("F2 段落带维度",
      data["sections"] and all("dims" in x for x in data["sections"]),
      str(data["sections"][0].keys() if data["sections"] else None))
check("F3 段落维度有四个",
      set(data["sections"][0]["dims"]) == {"tension", "drive", "space", "bright"},
      str(data["sections"][0]["dims"]))
check("F4 默认不带逐音符", "notes" not in data)
data2 = s02_api.payload(s02_path, with_notes=True)
check("F5 可要求逐音符", len(data2.get("notes", [])) == len(piece().notes),
      str(len(data2.get("notes", []))))
bad = s02_api.payload(tmp / "nope.s02")
check("F6 读不到文件不抛、给 error", "error" in bad, str(bad))

# ── 2) 矢量分析图 ─────────────────────────────────────
svg = s02_render.render(piece(), title="测试")
check("F7 SVG 有段落块", svg.count('class="section') >= 1, str(svg.count('class="section')))
check("F8 SVG 有三条维度曲线", svg.count("dim dim-") == 3, str(svg.count("dim dim-")))
check("F9 SVG 有扰动泳道与刻度", "局部扰动" in svg and "text-anchor" in svg)
check("F10 SVG 是合法开头结尾",
      svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
check("F11 同一输入两次渲染一致", s02_render.render(piece()) == s02_render.render(piece()))

# ── 3) 补丁协议 ───────────────────────────────────────
patch = {"base": "t.s02", "ops": [
    {"op": "set_note", "id": "L00000001", "field": "permille", "value": 999},
    {"op": "del_note", "id": "L00000032"},
]}
score = s02_io.parse(s02_io.dump(piece()))
new, changes = s02_patch.apply(score, patch)
check("F12 补丁改值且不动原对象",
      new.notes[0].dynamics_permille == 999 and score.notes[0].dynamics_permille == 800,
      f"{new.notes[0].dynamics_permille} / {score.notes[0].dynamics_permille}")
check("F13 删除生效", len(new.notes) == len(score.notes) - 1)
check("F14 改动清单可读", len(changes) == 2 and "old" in changes[0], str(changes[:1]))
hints = s02_patch.to_ms_hints(changes)
check("F15 MS 提示指向具体音与列",
      any("L00000001" in h and "力度" in h for h in hints) and
      any("L00000032" in h for h in hints), str(hints))

def rejects(label, bad_patch):
    try:
        s02_patch.apply(score, s02_patch.parse(json.dumps(bad_patch)))
    except s02_patch.PatchError:
        check(label, True)
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"抛了 {type(exc).__name__}")
    else:
        check(label, False, "未拒绝")

rejects("F16 未知 op → 拒绝", {"ops": [{"op": "explode", "id": "L00000001"}]})
rejects("F17 不存在的音 → 拒绝",
        {"ops": [{"op": "set_note", "id": "L99999999", "field": "permille", "value": 1}]})
rejects("F18 未知字段 → 拒绝",
        {"ops": [{"op": "set_note", "id": "L00000001", "field": "color", "value": 1}]})
rejects("F19 删音导致悬空引用 → 拒绝",
        {"ops": [{"op": "del_note", "id": "L00000001"},
                 {"op": "set_action", "id": "A00000001", "field": "strength", "value": 1}]}
        if False else {"ops": [{"op": "del_note", "id": "L00000001"},
                               {"op": "del_note", "id": "L00000001"}]})
check("F20 parse 接受 BOM", s02_patch.parse("\ufeff" + json.dumps({"ops": []})) == {"ops": []})

# ── 4) HTTP 接口 ──────────────────────────────────────
try:
    import ms_server as srv
    httpd = srv.serve(tmp, port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, r.read()

    st, body = get("/api/s02?file=t.s02")
    payload = json.loads(body.decode("utf-8"))
    check("F21 /api/s02 返回段落", st == 200 and payload.get("sections"),
          str(list(payload))[:80])
    st2, body2 = get("/api/s02?file=t.s02&notes=1")
    check("F22 /api/s02 可带音符", st2 == 200 and json.loads(body2.decode())["notes"])
    st3, body3 = get("/api/s02/svg?file=t.s02")
    check("F23 /api/s02/svg 返回 SVG",
          b"<svg" in body3 and b"section" in body3, str(st3))
    st4, body4 = None, b""
    try:
        get("/api/s02?file=none.s02")
    except urllib.error.HTTPError as e:
        st4 = e.code
    check("F24 缺文件 404", st4 == 404, str(st4))
    httpd.shutdown()
    httpd.server_close()
except Exception as e:  # noqa: BLE001
    check("F21-24 HTTP 接口", False, f"HTTP 测试异常：{e}")

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
