# -*- coding: utf-8 -*-
"""自检脚本：技能包完整性 + 渲染器真实可用性（路径不存在就标红）。

目的：文档里的“✅”可能过期；以本脚本的真实检查为准。
首次使用先跑一次：绿 → 可直接用；红 → 按 fix 安装/配置。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    ("ms/__init__.py", "文件"),
    ("ms/task.py", "文件"),
    ("tools/mscli.py", "文件"),
    ("perform", "目录"),
    ("render", "目录"),
    ("audio", "目录"),
    ("analyze", "目录"),
    ("importers", "目录"),
    ("examples", "目录"),
    ("cache", "目录"),
    ("output", "目录"),
    ("README.md", "文件"),
    ("SKILL.md", "文件"),
    ("GUIDE.md", "文件"),
]


def _check(name: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": fix}


def report() -> dict:
    """运行全部检查，返回 {ok, checks, renderers, text}。"""
    checks = []

    # 1) 包完整性
    missing = [f"{p}（{k}）" for p, k in REQUIRED if not (ROOT / p).exists()]
    checks.append(_check("包完整性", not missing,
                         "全部存在" if not missing else "缺：" + "、".join(missing),
                         "重新解压/复制技能包，或重新构建发布包"))

    # 2) Python 版本
    ok_py = sys.version_info >= (3, 10)
    checks.append(_check("Python 版本", ok_py, sys.version.split()[0],
                         "需要 Python ≥ 3.10"))

    # 3) 关键接口
    try:
        import ms  # noqa: F401
        need = ["build", "start", "Song", "package", "report",
                "prime", "perform", "schema_text", "renderers"]
        miss = [n for n in need if not hasattr(ms, n)]
        checks.append(_check("关键接口", not miss,
                             "齐全" if not miss else "缺：" + ",".join(miss),
                             "确认装入的是最新发布包"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("关键接口", False, f"import 失败：{exc}",
                             "检查包是否损坏"))

    # 4) 渲染器（真实路径检查由 renderers 完成）
    try:
        from .renderers import check as _rcheck
        items = _rcheck()
        for r in items:
            rec = r.get("recommended", True)
            detail = r["detail"]
            if r["ready"] and not rec:
                detail += "（⚠️ 仅接口测试用，音色差；成品请装外部渲染器/音色库）"
            checks.append(_check(f"渲染器：{r['name']}", r["ready"], detail,
                                 r["install"]))
    except Exception as exc:  # noqa: BLE001
        items = []
        checks.append(_check("渲染器", False, f"检查失败：{exc}",
                             "检查 ms/renderers.py 是否存在"))

    # 4b) 音色库：只列有什么，不逐个检查（用到时再确认）
    try:
        from .renderers import soundfonts as _sf
        libs = _sf()
        checks.append(_check(
            "音色库（不检查）", True,
            f"已有 {len(libs)} 个；缺失在用到时才确认",
            "把音色库放进 soundfonts/ 或设置 SOUNDFONT_DIR"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("音色库（不检查）", True, f"查询失败（不影响）：{exc}"))

    # 5) 上次配置的浏览器路径是否还在
    cfg = ROOT / "cache" / "renderer.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            chrome = data.get("chrome")
            if chrome:
                checks.append(_check("渲染器配置路径", Path(chrome).exists(), chrome,
                                     "路径失效：重新安装或 ms.configure_renderer(新路径)"))
        except Exception:
            checks.append(_check("渲染器配置路径", False, "配置损坏",
                                 "删除 cache/renderer.json 后重跑自检"))

    # 5.9) CLI 入口冒烟（发布布局才有 score/task 参数）
    cli = ROOT / "tools" / "mscli.py"
    ex = ROOT / "examples" / "simple_piano.json"
    if cli.exists() and ex.exists():
        try:
            txt = cli.read_text(encoding="utf-8")
            if 'sc.add_argument("task"' in txt:
                import subprocess
                import tempfile
                with tempfile.TemporaryDirectory() as _td:
                    _out = Path(_td) / "x.abc"
                    r = subprocess.run(
                        [sys.executable, str(cli), "ms", "score", str(ex),
                         "--abc", str(_out)],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=180)
                    good = (r.returncode == 0 and _out.exists()
                            and _out.stat().st_size > 0)
                    checks.append(_check(
                        "CLI score 冒烟", good,
                        "score --abc 正常" if good
                        else ((r.stderr or r.stdout or "")[-180:]),
                        "重新构建发布包 / 检查 tools/mscli.py"))
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("CLI score 冒烟", False, f"{exc}",
                                 "重新构建发布包"))

    # 6) 缓存区/产物区可写
    for p, label in ((ROOT / "cache", "缓存区"), (ROOT / "output", "产物区")):
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".selfcheck_tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append(_check(f"{label}可写", True, str(p)))
        except Exception as exc:  # noqa: BLE001
            checks.append(_check(f"{label}可写", False, f"{p}：{exc}",
                                 "检查目录权限/换可写位置"))

    ok = all(c["ok"] for c in checks)
    lines = ["技能包自检：" + ("✅ 全部可用" if ok else "❌ 有问题，先修复")]
    for c in checks:
        lines.append(f"  {'✅' if c['ok'] else '❌'} {c['name']} — {c['detail']}")
        if not c["ok"] and c["fix"]:
            lines.append(f"      修复：{c['fix']}")
    return {"ok": ok, "checks": checks, "renderers": items,
            "text": "\n".join(lines)}


def text() -> str:
    return report()["text"]


__all__ = ["report", "text"]
