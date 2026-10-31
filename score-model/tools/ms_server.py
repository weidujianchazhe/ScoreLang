# -*- coding: utf-8 -*-
"""本地编辑器服务（排表 IV-3）：HTML 单页 + 薄后端。

设计原则：
  - **界面不重写逻辑**：所有操作都调用现有模块（ms_io / ms_edit / ms_render / ms_score）
  - 只依赖标准库（`http.server`），无第三方依赖
  - 单用户单会话：一个内存文档 + 一个 UndoStack
  - 危险操作有边界：文件读写限制在 `--root` 目录内；编辑走 `ms_edit` 的校验；保存前再校验一次
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ms_edit as ed
import ms_events as ev
import ms_io as mj
import ms_midi as mm
import ms_render as rd
import ms_render_jianpu as jp
import ms_render as ro
import ms_render_staff2 as st
import ms_edit as un

HTML = _Path(__file__).with_name("server_ui.html").read_text(encoding="utf-8")


class Session:
    def __init__(self, root: Path):
        self.root = root
        self.path: Path | None = None
        self.doc: "ev.MSDocument | None" = None
        self.stack: "un.UndoStack | None" = None

    def open(self, name: str) -> dict:
        p = (self.root / "samples" / f"{name}.ms").resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("路径越界")
        doc = mj.loads(p.read_text(encoding="utf-8"))
        self.path, self.doc = p, doc
        self.stack = un.UndoStack(doc)
        return self.payload()

    def payload(self, errors=None) -> dict:
        doc = self.doc
        return {
            "path": str(self.path) if self.path else "",
            "doc": {
                "events": [
                    {"id": e.id, "onset_us": e.onset_us, "release_us": e.release_us,
                     "semitone": e.pitch.semitone,
                     "dynamics_permille": e.dynamics.permille,
                     "dynamics_state": e.dynamics.state}
                    for e in doc.events],
                "pedals": [{"kind": p.kind, "start_us": p.start_us, "end_us": p.end_us,
                            "depth": p.depth_permille} for p in doc.pedals],
            },
            "errors": errors or [],
            "can_undo": bool(self.stack and self.stack.can_undo),
            "can_redo": bool(self.stack and self.stack.can_redo),
        }

    def apply(self, result) -> dict:
        if not result.ok:
            return self.payload(errors=list(result.errors))
        self.doc = result.doc
        self.stack.push(self.doc)
        return self.payload()


def make_handler(root: Path, session: Session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # 静音默认日志，测试更干净
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if u.path == "/api/samples":
                names = sorted(p.name.replace(".ms", "")
                               for p in (root / "samples").glob("*.ms"))
                self._json({"samples": names})
                return
            if u.path == "/api/doc":
                if not session.doc:
                    self._json({"error": "未打开文件"}, 409)
                else:
                    self._json(session.payload())
                return
            if u.path == "/api/render":
                if not session.doc:
                    self._json({"error": "未打开文件"}, 409)
                    return
                q = parse_qs(u.query)
                meter = q.get("meter", ["4/4"])[0]
                tb = int(q.get("tb", ["500000"])[0])
                fmt = q.get("fmt", ["pianoroll"])[0]
                mode = q.get("mode", ["melody"])[0]
                try:
                    opts = ro.RenderOptions(meter=tuple(int(x) for x in meter.split("/")),
                                            time_base_us=tb)
                except Exception as e:  # noqa: BLE001
                    self._json({"error": f"呈现参数非法：{e}"}, 400)
                    return
                try:
                    if fmt == "pianoroll":
                        svg = rd.render_pianoroll(session.doc, options=opts)
                    elif fmt == "staff":
                        svg = rd.render_staff(session.doc, options=opts)
                    elif fmt == "staff2":
                        svg = st.render_staff2(session.doc, opts)
                    elif fmt == "jianpu":
                        svg = jp.render_jianpu(session.doc, opts, mode=mode)
                    else:
                        self._json({"error": f"未知 fmt：{fmt}"}, 400)
                        return
                except Exception as e:  # noqa: BLE001
                    self._json({"error": f"渲染失败：{e}"}, 500)
                    return
                self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
                return
            if u.path == "/api/midi":
                if not session.doc:
                    self._json({"error": "未打开文件"}, 409)
                    return
                q = parse_qs(u.query)
                tb = int(q.get("tb", ["500000"])[0])
                try:
                    data, _rep = mm.write_midi(session.doc, time_base_us=tb)
                except Exception as e:  # noqa: BLE001
                    self._json({"error": f"导出失败：{e}"}, 400)
                    return
                self._send(200, data, "audio/midi")
                return
            if u.path == "/api/s02":
                # S02 视图：/api/s02?file=xxx.s02[&index=xxx.s02x][&notes=1]
                q = parse_qs(u.query)
                rel = q.get("file", [""])[0]
                if not rel:
                    self._json({"error": "缺少 file 参数"}, 400)
                    return
                path = (root / rel)
                if not path.exists():
                    self._json({"error": f"文件不存在：{rel}"}, 404)
                    return
                try:
                    import s02_api
                    idx = q.get("index", [""])[0] or None
                    with_notes = q.get("notes", ["0"])[0] in ("1", "true", "yes")
                    self._json(s02_api.payload(path, s02x_path=idx, with_notes=with_notes))
                except Exception as e:  # noqa: BLE001
                    self._json({"error": f"S02 视图失败：{e}"}, 500)
                return
            if u.path == "/api/s02/svg":
                # S02 矢量分析图：/api/s02/svg?file=xxx.s02
                q = parse_qs(u.query)
                rel = q.get("file", [""])[0]
                path = (root / rel) if rel else None
                if path is None or not path.exists():
                    self._json({"error": f"文件不存在：{rel}"}, 404)
                    return
                try:
                    import s02_io
                    import s02_render
                    score = s02_io.parse(path.read_text(encoding="utf-8"))
                    svg = s02_render.render(score, title=q.get("title", [""])[0])
                    self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
                except Exception as e:  # noqa: BLE001
                    self._json({"error": f"S02 作图失败：{e}"}, 500)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            try:
                body = self._body()
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"无效 JSON：{e}"}, 400)
                return
            if u.path == "/api/open":
                try:
                    self._json(session.open(body.get("name", "")))
                except Exception as e:  # noqa: BLE001
                    self._json({"error": str(e)}, 400)
                return
            if not session.doc:
                self._json({"error": "未打开文件"}, 409)
                return
            if u.path == "/api/edit":
                self._json(self._edit(body))
                return
            if u.path == "/api/undo":
                d = session.stack.undo()
                if d is None:
                    self._json(session.payload(errors=["已在最早状态"]))
                else:
                    session.doc = d
                    self._json(session.payload())
                return
            if u.path == "/api/redo":
                d = session.stack.redo()
                if d is None:
                    self._json(session.payload(errors=["已在最新状态"]))
                else:
                    session.doc = d
                    self._json(session.payload())
                return
            if u.path == "/api/save":
                errs = ev.validate(session.doc)
                if errs:
                    self._json({"errors": errs}, 400)
                    return
                text = mj.dumps(session.doc)
                session.path.write_text(text, encoding="utf-8")
                # 保存成功，但把"演奏收束"的问题一并回给界面。
                # 不阻止保存：编辑器允许存草稿，但必须让人看见"这谱弹不出来"。
                payload = session.payload()
                payload["realization"] = ev.check_realization(session.doc)
                self._json(payload)
                return
            self._json({"error": "not found"}, 404)

        def _edit(self, body: dict) -> dict:
            op = body.get("op")
            doc = session.doc
            if op == "update_event":
                changes = dict(body.get("changes") or {})
                if "release_us" in changes and changes["release_us"] in ("", None):
                    changes["release_us"] = None
                    changes["release_state"] = "NOT_PROVIDED"
                if "semitone" in changes:
                    semi = int(changes.pop("semitone"))
                    changes["pitch"] = ev.Pitch(*_spell(semi), semi)
                return session.apply(ed.update_event(doc, body.get("id"), **changes))
            if op == "set_dynamics":
                pm = body.get("permille")
                if pm is None:
                    return session.apply(ed.update_event(
                        doc, body.get("id"),
                        dynamics=ev.Dynamics("NOT_PROVIDED")))
                return session.apply(ed.set_dynamics(doc, body.get("id"), int(pm)))
            if op == "add_event":
                return session.apply(ed.add_event(
                    doc, pitch=ev.Pitch(*_spell(int(body["semitone"])), int(body["semitone"])),
                    onset_us=int(body["onset_us"]), release_us=int(body.get("release_us") or 0) or None))
            if op == "delete_event":
                return session.apply(ed.delete_event(doc, body.get("id")))
            if op == "transpose":
                return session.apply(ed.transpose(doc, int(body.get("semitones", 0))))
            if op == "quantize":
                return session.apply(ed.quantize(doc, int(body.get("grid_us", 100000))))
            if op == "add_pedal":
                return session.apply(ed.add_pedal(
                    doc, kind=body.get("kind", "sustain"),
                    start_us=int(body.get("start_us", 0)),
                    end_us=int(body["end_us"]) if body.get("end_us") is not None else None,
                    depth_permille=int(body.get("depth", 1000)),
                    instrument_id=(int(body["instrument_id"])
                                   if body.get("instrument_id") is not None else None)))
            if op == "delete_pedal":
                return session.apply(ed.delete_pedal(doc, int(body.get("index", -1))))
            return session.payload(errors=[f"未知操作：{op}"])

    return Handler


_SHARP = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
          6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def _spell(semitone: int) -> tuple:
    step, alter = _SHARP[semitone % 12]
    return step, alter, semitone // 12 - 1


def serve(root: Path, port: int = 8765, host: str = "127.0.0.1"):
    session = Session(Path(root))
    httpd = ThreadingHTTPServer((host, port), make_handler(Path(root), session))
    print(f"serving http://{host}:{httpd.server_address[1]}/  (Ctrl+C 退出)")
    return httpd
