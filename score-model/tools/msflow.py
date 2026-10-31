# -*- coding: utf-8 -*-
"""统一工作流（工具链协议）：任何模型/工具要产出成果，都走 `flow run`。

一次 run 固定六步（少一步就不算合规）：
    1. ingest   读入（`.md` 文档写法；旧档案只读兼容）+ 结构校验
    2. project  → `.s02` 骨架（落进 run 目录，可追溯）
    3. index    → `.s02x`（动机/关系/特征）
    4. analyze  → `analysis.json`（段落/维度/扰动/难度/动机，前端与学习都用它）
    5. report   → `report.md`（五层报告）
    6. render   → `analysis.svg`（矢量分析图）
可选：7. audio → `audio.wav`

产物目录（工作区，不在引擎内）：
    <workspace>/inbox/runs/<run_id>/   本次全部产物 + manifest.json
    <workspace>/inbox/dataset.jsonl    学习数据集（一行一次 run：特征 + 评分）
    <workspace>/inbox/models/          训练出来的模型

`flow check` 校验一次 run 是否真的按协议走完（缺件/脏改都会报错）。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
for _p in (ENGINE, *(ENGINE / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms_events as ev
import ms_io
import ms_md
import s02_api
import s02_index
import s02_io
import s02_probe
import s02_report
import s02_score
import s02_segment
import s02_fingering
import s02_perturb
import s02_taste
from ms_to_s02 import to_s02

WORKSPACE = ENGINE.parent
LIBRARY = WORKSPACE / "library"

STEPS = ("ingest", "project", "index", "analyze", "report", "render")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def run(piece_path, *, time_base_us: int = 500_000, work_root=None, audio: bool = False,
        title: str = "", weights=None, keep_source: bool = True) -> dict:
    """跑一次完整流程，返回 {run_id, run_dir, steps, features, artifacts}。"""
    piece = Path(piece_path)
    lib = Path(work_root) if work_root else LIBRARY
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{piece.stem}-{stamp}"
    runs_root = lib / "runs"
    n = 1
    while (runs_root / run_id).exists():          # 同一秒内多次 run：加序号，保证唯一
        n += 1
        run_id = f"{piece.stem}-{stamp}-{n}"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    steps = []
    artifacts = {}
    t_all = time.perf_counter()

    def step(name, fn):
        t = time.perf_counter()
        out = fn()
        steps.append({"name": name, "ok": True, "ms": round((time.perf_counter() - t) * 1000, 1)})
        return out

    # 1 ingest
    def do_ingest():
        # 写作格式是 `.md`；旧档案仍可读入（只读兼容）
        doc = ms_md.load(piece) if Path(piece).suffix.lower() == ".md" else ms_io.load(piece)
        errs = ev.validate(doc)
        if errs:
            raise ValueError("结构不合法：" + "；".join(errs[:5]))
        artifacts["source"] = {"path": str(piece), "sha256": _sha256(piece),
                               "events": len(doc.events)}
        return doc

    doc = step("ingest", do_ingest)

    # 2 project
    def do_project():
        score, losses = to_s02(doc, time_base_us=time_base_us)
        p = run_dir / "piece.s02"
        s02_io.save(score, p)
        artifacts["s02"] = {"path": p.name, "sha256": _sha256(p), "losses": len(losses)}
        return score

    score = step("project", do_project)

    # 3 index
    def do_index():
        idx = s02_index.build(score)
        p = run_dir / "piece.s02x"
        s02_index.save(idx, p, meta={"source": piece.name, "run_id": run_id})
        artifacts["s02x"] = {"path": p.name, "motifs": len(idx["motifs"]),
                             "variants": len(idx["variants"]), "edges": len(idx["edges"])}
        return p

    idx_path = step("index", do_index)

    # 4 analyze
    def do_analyze():
        con = s02_index.open_index(idx_path)
        try:
            payload = s02_api.build_payload(score, index_con=con, weights=weights)
        finally:
            con.close()
        try:
            import s02_capability
            payload["capability"] = s02_capability.analyze(doc)
        except Exception as e:  # noqa: BLE001
            payload["capability"] = {"error": str(e)}
        p = run_dir / "analysis.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["analysis"] = {"path": p.name, "sha256": _sha256(p)}
        return payload

    payload = step("analyze", do_analyze)

    # 5 report
    def do_report():
        con = s02_index.open_index(idx_path)
        try:
            text = s02_report.build(score, index=con, weights=weights,
                                    title=title or piece.stem)
        finally:
            con.close()
        # 追加"演奏能力覆盖"：报告本来只吃 S02，能力表要 MS 乐谱模型
        try:
            import s02_capability
            cap = payload.get("capability") or s02_capability.analyze(doc)
            lines = ["", "## 2b. 演奏能力覆盖（会用了吗）", "",
                     f"- 乐器 {cap['summary']['instrument_count']} 件 · "
                     f"发声机制 {cap['summary']['mechanism_count']} 种 · "
                     f"转折 {cap['summary']['turns']} · 踏板 {cap['summary']['pedals']} · "
                     f"曲线 {cap['summary']['curves']}"]
            if cap["summary"]["gaps"]:
                lines.append("")
                lines += [f"- ⚠ {g}" for g in cap["summary"]["gaps"]]
            for inst in cap["instruments"]:
                if inst.get("error"):
                    continue
                u = inst["unused"]
                bits = []
                if u["turns"]:
                    bits.append("转折未用：" + "、".join(u["turns"][:6]))
                if u["pedals"]:
                    bits.append("踏板未用：" + "、".join(u["pedals"]))
                if u["curves"]:
                    bits.append("曲线未用：" + "、".join(u["curves"]))
                if bits:
                    lines.append(f"- `{inst['id']}` {inst['type']}：" + "；".join(bits))
            lines.append("")
            text = text + "\n".join(lines)
        except Exception:
            pass
        p = run_dir / "report.md"
        p.write_text(text, encoding="utf-8")
        artifacts["report"] = {"path": p.name, "lines": len(text.splitlines()),
                               "sha256": _sha256(p)}
        return text

    step("report", do_report)

    # 6 render
    def do_render():
        import s02_render
        svg = s02_render.render(score, title=title or piece.stem)
        p = run_dir / "analysis.svg"
        p.write_text(svg, encoding="utf-8")
        artifacts["svg"] = {"path": p.name, "bytes": len(svg), "sha256": _sha256(p)}
        return svg

    step("render", do_render)

    if audio:
        def do_audio():
            import make_audio
            samples = make_audio.render(doc)
            p = run_dir / "audio.wav"
            make_audio.write_wav(samples, p)
            artifacts["audio"] = {"path": p.name,
                                  "seconds": round(len(samples) / make_audio.SR, 1),
                                  "sha256": _sha256(p)}
            return p
        step("audio", do_audio)

    features = s02_taste.features_of(payload)
    manifest = {
        "run_id": run_id,
        "created": _now(),
        "protocol": "flow-v1",
        "title": title or piece.stem,
        "time_base_us": time_base_us,
        "steps": steps,
        "artifacts": artifacts,
        "features": features,
        "total_ms": round((time.perf_counter() - t_all) * 1000, 1),
        "ratings": [],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 曲子本体归档：inbox/pieces/<stem>/source<原后缀>（第一次或内容变化时留一份）
    if keep_source:
        pieces = lib / "pieces" / piece.stem
        pieces.mkdir(parents=True, exist_ok=True)
        src_sha = _sha256(piece)
        suffix = piece.suffix.lower() or ".md"
        dst = pieces / f"source{suffix}"
        if not dst.exists() or _sha256(dst) != src_sha:
            import shutil
            if dst.exists():
                shutil.copy2(dst, pieces / f"source-{_sha256(dst)}{suffix}")
            shutil.copy2(piece, dst)
        manifest["source_copy"] = {"dir": str(pieces), "file": f"source{suffix}",
                                   "sha256": src_sha}

    # 数据集追加（一次 run 一行；评分后由 taste rate 回填）
    q = payload.get("quality") or {}
    s02_taste.append_row(lib / "dataset.jsonl", {
        "run_id": run_id,
        "created": manifest["created"],
        "title": manifest["title"],
        "features": features,
        "quality": {"metrics": q.get("metrics") or {},
                    "coverage": q.get("coverage"), "confidence": q.get("confidence")},
        "overall": None,
        "dims": {},
        "ratings": [],
    })
    return {"run_id": run_id, "run_dir": str(run_dir), "steps": steps,
            "features": features, "artifacts": artifacts,
            "total_ms": manifest["total_ms"]}


# ── 协议校验 ──────────────────────────────────────────

REQUIRED_ARTIFACTS = ("source", "s02", "s02x", "analysis", "report", "svg")
REPORT_HEADINGS = ("## 0. 摘要", "## 1. 结构", "## 5. 诊断")


def check(run_dir, *, work_root=None) -> dict:
    """校验一次 run 是否按协议完成。返回 {ok, problems, warnings, run_id}。"""
    rd = Path(run_dir)
    problems, warnings = [], []
    manifest_path = rd / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "run_id": rd.name,
                "problems": ["缺 manifest.json（没走 flow run）"], "warnings": []}
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "run_id": rd.name,
                "problems": [f"manifest.json 不是合法 JSON：{e}"], "warnings": []}

    if m.get("protocol") != "flow-v1":
        problems.append(f"protocol 不是 flow-v1：{m.get('protocol')}")
    names = [s.get("name") for s in m.get("steps") or []]
    for required in STEPS:
        if required not in names:
            problems.append(f"缺步骤：{required}")
        else:
            st = next(s for s in m["steps"] if s["name"] == required)
            if not st.get("ok"):
                problems.append(f"步骤失败：{required}")
    if names != [n for n in names if n in STEPS] + [n for n in names if n not in STEPS]:
        problems.append("步骤顺序不合协议（ingest→project→index→analyze→report→render）")

    for key in REQUIRED_ARTIFACTS:
        art = (m.get("artifacts") or {}).get(key)
        if not art:
            problems.append(f"缺产物记录：{key}")
            continue
        f = rd / art["path"] if key != "source" else None
        if f is not None and not f.exists():
            problems.append(f"产物文件不存在：{art['path']}")
        if f is not None and "sha256" in art and f.exists() and _sha256(f) != art["sha256"]:
            problems.append(f"产物被改过（sha 不符）：{art['path']}")

    # analysis 结构
    ap = rd / "analysis.json"
    if ap.exists():
        try:
            a = json.loads(ap.read_text(encoding="utf-8"))
            for k in ("summary", "sections", "windows"):
                if k not in a:
                    problems.append(f"analysis.json 缺 {k}")
        except Exception as e:
            problems.append(f"analysis.json 解析失败：{e}")

    # report 结构
    rp = rd / "report.md"
    if rp.exists():
        text = rp.read_text(encoding="utf-8")
        for h in REPORT_HEADINGS:
            if h not in text:
                problems.append(f"report.md 缺章节：{h}")
        if len(text.splitlines()) < 20:
            warnings.append("report.md 行数偏少（<20 行），确认是否正常")

    # 数据集登记
    lib = Path(work_root) if work_root else LIBRARY
    ds = lib / "dataset.jsonl"
    if not ds.exists():
        warnings.append("数据集不存在（首次运行会创建）")
    else:
        rows = [json.loads(line) for line in ds.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not any(r.get("run_id") == m.get("run_id") for r in rows):
            problems.append("数据集里没有这次 run 的记录（未经 flow run 写入）")

    return {"ok": not problems, "run_id": m.get("run_id"),
            "problems": problems, "warnings": warnings}


def batch(src_dir, *, pattern: str = "*.md", tag: str = "", work_root=None,
          time_base_us: int = 500_000, audio: bool = False) -> dict:
    """批量跑一个目录里的所有曲谱，并归档成一批（供"每周/每月统一学习"用）。

    产物：inbox/batches/<tag>/index.json（本批 run 列表 + 汇总统计）
    """
    lib = Path(work_root) if work_root else LIBRARY
    import datetime as _dt
    tag = tag or _dt.date.today().strftime("%Y-%m-%d")
    batch_dir = lib / "batches" / tag
    batch_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(src_dir).glob(pattern))
    results, failed = [], []
    for f in files:
        try:
            r = run(f, time_base_us=time_base_us, work_root=lib, audio=audio)
            results.append({"source": f.name, "run_id": r["run_id"],
                            "run_dir": r["run_dir"], "total_ms": r["total_ms"],
                            "coverage": None})
            # 从数据集里把 quality 补进索引
            ds = lib / "dataset.jsonl"
            if ds.exists():
                for line in ds.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("run_id") == r["run_id"]:
                        results[-1]["coverage"] = (row.get("quality") or {}).get("coverage")
                        break
        except Exception as e:  # noqa: BLE001
            failed.append({"source": f.name, "error": str(e)})
    idx = {"tag": tag, "created": _now(), "pattern": pattern,
           "runs": results, "failed": failed,
           "count": len(results), "failed_count": len(failed)}
    (batch_dir / "index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    idx["index_path"] = str(batch_dir / "index.json")
    return idx


def list_runs(work_root=None) -> list:
    lib = Path(work_root) if work_root else LIBRARY
    out = []
    ds = lib / "dataset.jsonl"
    ratings = {}
    if ds.exists():
        for line in ds.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ratings[r.get("run_id")] = r
    runs_dir = lib / "runs"
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir()):
            m = d / "manifest.json"
            row = {"run_id": d.name, "created": "",
                   "overall": (ratings.get(d.name) or {}).get("overall")}
            if m.exists():
                try:
                    man = json.loads(m.read_text(encoding="utf-8"))
                    row["created"] = man.get("created", "")
                    row["title"] = man.get("title", "")
                    row["notes"] = man.get("features", {}).get("notes")
                except Exception:
                    pass
            out.append(row)
    return out
