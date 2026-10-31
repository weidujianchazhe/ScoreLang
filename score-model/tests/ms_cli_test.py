# -*- coding: utf-8 -*-
"""CLI 测试（I-2 / I-3）：通过子进程调用，验证退出码与产物。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = ROOT
SAMPLES = HERE / "fixtures" / "legacy"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


TOOL = ROOT / "tools" / "render_svg.py"      # 引擎内自带，工程可整体搬走


def run_tool(*a):
    cmd = [sys.executable, "-B", str(TOOL), *[str(x) for x in a]]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-B", "tools/mscli.py", *args], cwd=str(HERE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


sample = str(SAMPLES / "simple_melody.ms")

# ── validate ────────────────────────────────────────────────
code, out = run("validate", sample)
check("C1 validate 合法文件 → 0", code == 0 and "合法" in out, out[:60])

with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / "bad.ms"
    bad.write_text(sample and (SAMPLES / "simple_melody.ms").read_text(encoding="utf-8")
                   .replace("ms 1", "ms 9", 1), encoding="utf-8")
    code, out = run("validate", str(bad))
    check("C2 validate 坏文件 → 1 且报版本", code == 1 and "版本" in out, out[:80])

    code, out = run("validate", str(Path(td) / "nope.ms"))
    check("C3 文件不存在 → 报错退出", code != 0 and "不存在" in out, out[:60])

# ── info ────────────────────────────────────────────────────
code, out = run("info", sample)
check("C4 info 输出事件数", code == 0 and "事件      5" in out, out[:80])
check("C5 info 输出时长", "2.000 s" in out, out[:120])

# ── render ──────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    o1 = Path(td) / "a.svg"
    code, out = run_tool(sample, "-o", str(o1), "--mode", "pianoroll")
    check("C6 render pianoroll 出文件", code == 0 and o1.exists() and o1.read_text(encoding="utf-8").startswith("<svg"))

    o2 = Path(td) / "b.svg"
    code, _ = run_tool(sample, "-o", str(o2), "--mode", "staff",
                  "--meter", "4/4", "--time-base", "500000")
    body = o2.read_text(encoding="utf-8")
    check("C7 给 meter+time_base → 画小节线", 'class="barline"' in body, "无 barline")
    check("C8 2s 谱 / 每小节 2s → 仅 0s 处 1 条小节线（终点不画）",
          body.count('class="barline"') == 1, str(body.count('class="barline"')))

    o3 = Path(td) / "c.svg"
    code, _ = run_tool(sample, "-o", str(o3), "--mode", "staff")
    body3 = o3.read_text(encoding="utf-8")
    check("C9 不给 meter → 不画小节线且标注", 'class="barline"' not in body3 and "无拍号" in body3)

    o4 = Path(td) / "d.svg"
    code, _ = run_tool(sample, "-o", str(o4), "--mode", "jianpu", "--meter", "4/4", "--time-base", "500000")
    body4 = o4.read_text(encoding="utf-8")
    check("C10 简谱渲染出音符号", 'class="jp-note"' in body4)

    code, out = run_tool(sample, "--meter", "4/x")
    check("C11 meter 格式错误 → 报错", code != 0 and ("拍号" in out or "meter" in out.lower()), out[:60])

# ── export ──────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    mid = Path(td) / "a.mid"
    code, out = run("export", sample, "-o", str(mid), "--time-base", "500000")
    check("C12 export 出 MIDI", code == 0 and mid.exists() and mid.read_bytes()[:4] == b"MThd", out[:60])

    import ms_midi as mm
    back = mm.read_midi(mid.read_bytes())
    check("C13 导出的 MIDI 可回读且 5 个 note-on",
          len([n for n in back["notes"] if n["on"]]) == 5, str(len(back["notes"])))

    code, out = run("export", sample, "-o", str(Path(td) / "b.mid"))
    check("C14 缺 --time-base → 拒绝", code != 0)

# ── 多模式导出/渲染不报错 ─────────────────────────────────
for mode in ("melody", "two_hands", "chords"):
    code, _ = run_tool(sample, "--mode", "jianpu", "--jianpu-mode", mode)
    check(f"C15 jianpu {mode} 可运行", code == 0)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
