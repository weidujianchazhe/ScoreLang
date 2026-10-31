# -*- coding: utf-8 -*-
"""CLI 冒烟测试：覆盖用户真实入口（score/package/import/check-spec/draft…）。

默认测工程区 CLI；设置环境变量 MS_CLI_ROOT 指向发布包可测发布包。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results = []


def _cli() -> Path:
    base = Path(os.environ.get("MS_CLI_ROOT") or ROOT)
    for name in ("tools/mscli_external.py", "tools/mscli.py"):
        p = base / name
        if p.exists():
            return p
    raise FileNotFoundError("找不到 mscli")


CLI = _cli()
BASE = CLI.parent.parent


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def run(*args, timeout=300):
    r = subprocess.run([sys.executable, "-B", str(CLI), *map(str, args)],
                       cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# 最小的合法任务（不依赖 examples/）
TASK = {"bpm": 120, "meter": [4, 4],
        "notes": [{"pitch": "C4", "beat": 0, "beats": 1, "level": "mf"},
                  {"pitch": "E4", "beat": 1, "beats": 1},
                  {"pitch": "G4", "beat": 2, "beats": 2}]}

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    task = td / "task.json"
    task.write_text(json.dumps(TASK, ensure_ascii=False), encoding="utf-8")

    # 源码树/发布包都可能缺某些目录；自检只在完整发布布局下强制
    rc, out = run("ms", "selfcheck")
    full_layout = (BASE / "examples").exists() and (BASE / "README.md").exists()
    check("S1 selfcheck 可执行（完整布局）" if full_layout else "S1 selfcheck（源码树跳过）",
          rc == 0 if full_layout else True, out[-80:])

    rc, out = run("ms", "check-spec", task)
    check("S2 check-spec 合法任务通过", rc == 0 and '"ok": true' in out, out[:80])

    bad = td / "bad.json"
    bad.write_text(json.dumps({"bpm": 120, "notes": [{"pitch": "H9"}]}),
                   encoding="utf-8")
    rc, out = run("ms", "check-spec", bad)
    check("S3 check-spec 非法任务拒绝", rc != 0, out[:80])

    abc = td / "x.abc"
    rc, out = run("ms", "score", task, "--abc", abc)
    check("S4 score --abc", rc == 0 and abc.exists() and abc.stat().st_size > 0
          and abc.read_text(encoding="utf-8").startswith("X:"), out[-80:])

    svg = td / "x.svg"
    rc, out = run("ms", "score", task, "--staff", svg)
    check("S5 score --staff", rc == 0 and svg.exists()
          and svg.read_text(encoding="utf-8").startswith("<svg"), out[-80:])

    mid = td / "x.mid"
    rc, out = run("ms", "score", task, "--midi", mid)
    check("S6 score --midi", rc == 0 and mid.exists()
          and mid.read_bytes()[:4] == b"MThd", out[-80:])

    wav = td / "x.wav"
    rc, out = run("ms", "score", task, "--audio", wav)
    check("S7 score --audio", rc == 0 and wav.exists()
          and wav.read_bytes()[:4] == b"RIFF", out[-80:])

    png = td / "x.png"
    rc, out = run("ms", "score", task, "--png", png)
    check("S8 score --png", rc == 0 and png.exists()
          and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", out[-80:])

    pkgdir = td / "pkg"
    rc, out = run("ms", "package", task, "--out", pkgdir, timeout=900)
    exts = set()
    if pkgdir.exists():
        exts = {f.suffix.lower() for f in pkgdir.rglob("*") if f.is_file()}
    check("S9 package 四件产物", rc == 0 and {".mid", ".wav", ".png", ".abc"} <= exts,
          out[-80:])

    # 确保有 MIDI 供 import 测（若上一步失败，用库直接生成）
    if not mid.exists():
        sys.path.insert(0, str(BASE))
        import ms as _ms
        mid.write_bytes(_ms.build(TASK).export_midi())

    rc, out = run("ms", "import", mid, "--abc", td / "imp.abc")
    check("S10 import MIDI → ABC", rc == 0 and (td / "imp.abc").exists(), out[-80:])

    rc, out = run("ms", "import", mid, "--staff", td / "imp.svg")
    check("S11 import MIDI → SVG", rc == 0 and (td / "imp.svg").exists(), out[-80:])

    intent = td / "intent.json"
    intent.write_text(json.dumps({"expression": {"expectation": 0.7}}), encoding="utf-8")
    rc, out = run("ms", "draft", intent, "--out", td / "draft.json")
    ok = rc == 0 and (td / "draft.json").exists()
    if ok:
        spec = json.loads((td / "draft.json").read_text(encoding="utf-8"))
        ok = bool(spec.get("notes"))
    check("S12 draft 出初稿", ok, out[-80:])

    rc, out = run("ms", "report", task, "--json")
    ok = rc == 0
    if ok:
        try:
            ok = "quality" in json.loads(out[out.find("{"):])
        except Exception:  # noqa: BLE001
            ok = False
    check("S13 report --json", ok, out[:80])

    rc, out = run("ms", "schema", "--text")
    check("S14 schema --text", rc == 0 and "bpm" in out, out[:60])

    rc, out = run("ms", "renderers")
    check("S15 renderers", rc == 0 and ("内置" in out or "chrome" in out), out[:80])

    rc, out = run("ms", "clear-cache", "--dry-run")
    check("S16 clear-cache --dry-run", rc == 0, out[:80])

    rc, out = run("ms", "prime")
    check("S17 prime", rc == 0 and len(out) > 20, out[:60])

    rc, out = run("ms", "fix", task, "--dry-run")
    check("S20 fix --dry-run", rc == 0 and "修复" in out, out[-80:])

    rc, out = run("ms", "score", task, "--fix", "--abc", td / "fix.abc")
    check("S21 score --fix", rc == 0 and (td / "fix.abc").exists(), out[-80:])

    rc, out = run("ms", "diagnose", task, "--json")
    check("S22 diagnose --json", rc == 0 and "findings" in out, out[-80:])

    rc, out = run("ms", "report", task)
    check("S23 report 文本含诊断", rc == 0 and "诊断" in out, out[-80:])

    rc, out = run("ms", "export-check", task)
    check("S24 export-check 干净通过", rc == 0 and "可以导出" in out, out[-80:])
    bad2 = td / "bad2.json"
    bad2.write_text(json.dumps({"bpm": 100, "notes": [{"pitch": "H9"}]}), encoding="utf-8")
    rc, out = run("ms", "score", bad2, "--abc", td / "z.abc", "--check")
    check("S25 score --check 阻断拒绝", rc != 0, out[-80:])

    rc, out = run("ms", "selfcheck", "--json")
    check("S26 selfcheck --json", "checks" in out and out.lstrip().startswith("{"), out[:80])

    txtf = td / "piece.txt"
    txtf.write_text("bpm 100\nmeter 4/4\nP1 C4 0 1 mf\nP1 E4 1 1\n", encoding="utf-8")
    rc, out = run("ms", "text", txtf, "--abc", td / "t.abc")
    check("S27 text → ABC", rc == 0 and (td / "t.abc").exists(), out[-80:])

    rc, _ = run("ms", "score", td / "nope.json", "--abc", td / "y.abc")
    check("S18 score 缺文件 → 非零退出", rc != 0)

    rc, _ = run("ms", "score")
    check("S19 score 缺参数 → 非零退出", rc != 0)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("[通过] " if ok else "[失败] ") + name + ("" if ok else f"  :: {detail}"))
print("=" * 48)
print(f"共 {len(results)} 项：通过 {len(results)-len(failed)}，失败 {len(failed)}")
if failed:
    raise SystemExit(1)
