# -*- coding: utf-8 -*-
"""本地编辑器服务测试（IV-3）：起真实 HTTP 服务，用 urllib 打接口。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import ms_events as ev
import ms_io as mj
import ms_server as srv

HERE = ROOT
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def call(base, path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            return r.status, raw.decode("utf-8") if "json" in ctype or "svg" in ctype or "html" in ctype else raw, ctype
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw, ""


tmp = Path(tempfile.mkdtemp())
(tmp / "samples").mkdir()
shutil.copy(HERE / "fixtures" / "legacy" / "simple_melody.ms", tmp / "samples" / "simple_melody.ms")

httpd = srv.serve(tmp, port=0)
port = httpd.server_address[1]
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()
BASE = f"http://127.0.0.1:{port}"

try:
    # ── 页面与列表 ──
    st, body, _ = call(BASE, "/")
    check("S1 首页返回 HTML 且含编辑器标记", st == 200 and "pianomusic" in body, str(st))

    st, body, _ = call(BASE, "/api/samples")
    names = json.loads(body)["samples"]
    check("S2 样例列表", st == 200 and names == ["simple_melody"], str(names))

    # ── 打开 ──
    st, body, _ = call(BASE, "/api/open", "POST", {"name": "simple_melody"})
    j = json.loads(body)
    check("S3 打开样例 → 5 事件", st == 200 and len(j["doc"]["events"]) == 5, body[:80])
    check("S4 初态不可撤销", j["can_undo"] is False)

    # ── 渲染 ──
    st, body, _ = call(BASE, "/api/render?fmt=pianoroll")
    check("S5 事件谱渲染", st == 200 and 'class="note"' in body, str(st))

    st, body, _ = call(BASE, "/api/render?fmt=jianpu&mode=melody")
    check("S6 简谱渲染", st == 200 and 'class="jp-note"' in body, str(st))

    st, body, _ = call(BASE, "/api/render?fmt=staff2&meter=2/4")
    check("S7 五线规范渲染（2/4 → 每 1s 一条小节线）", st == 200 and 'class="staffline"' in body
          and 'class="barline"' in body, str(st))

    st, body, _ = call(BASE, "/api/render?fmt=pianoroll&meter=4/x")
    check("S8 非法 meter → 400", st == 400 and "呈现参数非法" in body, body[:60])

    # ── 编辑 / 撤销 / 重做 ──
    eid = j["doc"]["events"][0]["id"]
    orig_rel = j["doc"]["events"][0]["release_us"]
    st, body, _ = call(BASE, "/api/edit", "POST",
                       {"op": "update_event", "id": eid, "changes": {"release_us": 123456}})
    j2 = json.loads(body)
    check("S9 改起点成功入栈", st == 200 and j2["can_undo"] is True, body[:80])
    check("S10 新值生效", j2["doc"]["events"][0]["release_us"] == 123456,
          str(j2["doc"]["events"][0]["release_us"]))

    st, body, _ = call(BASE, "/api/undo", "POST", {})
    j3 = json.loads(body)
    check("S11 撤销回到原值", j3["doc"]["events"][0]["release_us"] == orig_rel,
          str(j3["doc"]["events"][0]["release_us"]))

    st, body, _ = call(BASE, "/api/redo", "POST", {})
    j4 = json.loads(body)
    check("S12 重做回到新值", j4["doc"]["events"][0]["release_us"] == 123456)

    # ── 非法编辑被拒且不改文档 ──
    st, body, _ = call(BASE, "/api/edit", "POST",
                       {"op": "update_event", "id": eid, "changes": {"onset_us": 9_000_000}})
    j5 = json.loads(body)
    check("S13 非法编辑 → 有错误且值未变",
          (j5["errors"] != []) and j5["doc"]["events"][0]["release_us"] == 123456,
          str(j5["errors"])[:80])

    # ── 力度设置 ──
    st, body, _ = call(BASE, "/api/edit", "POST",
                       {"op": "set_dynamics", "id": eid, "permille": 1500})
    j6 = json.loads(body)
    check("S14 设力度生效", j6["doc"]["events"][0]["dynamics_permille"] == 1500,
          str(j6["doc"]["events"][0]["dynamics_permille"]))

    # ── 保存 ──
    st, body, _ = call(BASE, "/api/save", "POST", {})
    saved = mj.loads((tmp / "samples" / "simple_melody.ms").read_text(encoding="utf-8"))
    check("S15 保存成功且落盘合法", st == 200 and ev.validate(saved) == [] and
          saved.events[0].dynamics.permille == 1500,
          str(ev.validate(saved))[:80])
    # 保存响应必须带"演奏收束"结论（可为空列表，但字段要在）
    check("S15b 保存响应含 realization 字段",
          "realization" in json.loads(body), body[:80])

    # ── 踏板编辑与 MIDI 下载 ──────────────────────────────
    st, body, _ = call(BASE, "/api/edit", "POST",
                       {"op": "add_pedal", "kind": "sustain", "start_us": 0,
                        "end_us": 1_000_000, "depth": 1000, "instrument_id": 1})
    jp1 = json.loads(body)
    check("S17 加踏板成功", st == 200 and len(jp1["doc"]["pedals"]) == 1,
          str(jp1["doc"]["pedals"]))

    st, body, _ = call(BASE, "/api/edit", "POST",
                       {"op": "add_pedal", "kind": "sustain", "start_us": 500_000,
                        "end_us": 1_500_000, "depth": 800, "instrument_id": 1})
    jp2 = json.loads(body)
    check("S18 同轨重叠踏板被拒", st == 200 and jp2["errors"] and len(jp2["doc"]["pedals"]) == 1,
          str(jp2["errors"])[:60])

    st, body, _ = call(BASE, "/api/edit", "POST", {"op": "delete_pedal", "index": 0})
    jp3 = json.loads(body)
    check("S19 删踏板成功", jp3["doc"]["pedals"] == [], str(jp3["doc"]["pedals"]))

    req = urllib.request.Request(BASE + "/api/midi?tb=500000")
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
    check("S20 MIDI 下载返回 SMF", r.status == 200 and raw[:4] == b"MThd", str(raw[:4]))

    st, body, _ = call(BASE, "/api/open", "POST", {"name": "../../etc/passwd"})
    check("S21 越界路径被拒", st == 400, str(st))

finally:
    httpd.shutdown()
    httpd.server_close()
    shutil.rmtree(tmp, ignore_errors=True)

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
