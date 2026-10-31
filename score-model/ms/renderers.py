# -*- coding: utf-8 -*-
"""渲染器接口：可替换 / 可检测 / 首次使用初始化。

为什么需要：
  · 音频：内置 numpy 合成器（随包自带，无需下载）；
  · 图片：五线谱 PNG 需要本机 Chromium 内核浏览器（Chrome/Edge），这是**外部缺口**；
  · 未来可加：采样音色库 / 神经渲染器（可选，不绑死）。

用法：
    ms.renderers()            # 列出渲染器与状态（✅/❌）
    ms.renderers.text()       # 文本表格
    ms.renderers.configure(r"<path-to-chrome>")   # 手动指定
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# 渲染器清单：接口与实现分离，后续可替换/新增
RENDERERS = [
    {
        "id": "synth",
        "name": "内置合成器（numpy）",
        "kind": "audio",
        "required": True,
        "recommended": False,
        "role": "test-only",
        "install": "随包自带，但**仅用于接口测试**；成品请安装外部渲染器 + 音色库",
    },
    {
        "id": "chrome",
        "name": "Chrome / Edge 无头渲染",
        "kind": "image",
        "required": False,
        "recommended": True,
        "install": "安装 Chrome 或 Edge；或用 CHROME_PATH 指定可执行文件路径",
    },
]


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "cache" / "renderer.json"


def _load_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("chrome"):
                os.environ.setdefault("CHROME_PATH", str(data["chrome"]))
            return data
        except Exception:
            return {}
    return {}


def _save_config(data: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_chrome() -> str | None:
    try:
        from ms_staff_pages import _find_chrome as _fc  # type: ignore
        return _fc()
    except Exception:
        cands = [os.environ.get("CHROME_PATH")]
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            for rel in ("Google/Chrome/Application/chrome.exe",
                        "Microsoft/Edge/Application/msedge.exe"):
                cands.append(str(Path(base) / rel))
        cands += ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
        for c in cands:
            if c and Path(c).exists():
                return c
        return None


def soundfonts() -> list[dict]:
    """列出**已有**音色库（只列有什么，不检查能否加载）。

    规则：有什么列什么；缺失在用的时候才发现（不在自检里逐个检查）。
    查找位置：包内 `soundfonts/`、环境变量 `SOUNDFONT_DIR`。
    """
    dirs = [Path(__file__).resolve().parent.parent / "soundfonts"]
    env = os.environ.get("SOUNDFONT_DIR")
    if env:
        dirs.append(Path(env))
    out = []
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() in (".sf2", ".sf3", ".sfz", ".wav", ".flac"):
                out.append({"name": f.stem, "path": str(f), "format": f.suffix.lower()})
    return out


def check() -> list[dict]:
    """检查所有渲染器状态；返回 [{id,name,kind,ready,detail,install}]。"""
    _load_config()
    chrome = _find_chrome()
    out = []
    for r in RENDERERS:
        item = dict(r)
        item.setdefault("recommended", True)
        if r["id"] == "synth":
            item.update(ready=True, detail="内置")
        elif r["id"] == "chrome":
            item.update(ready=bool(chrome), detail=chrome or "未找到")
        else:
            item.update(ready=False, detail="未实现")
        out.append(item)
    return out


def status() -> str:
    """文本表格：✅ 可用 / ❌ 缺失。"""
    lines = ["渲染器状态："]
    for r in check():
        if not r["ready"]:
            mark = "❌"
        elif r.get("recommended") is False:
            mark = "⚠️"
        else:
            mark = "✅"
        lines.append(f"  {mark} {r['name']}（{r['kind']}）— {r['detail']}")
        if not r["ready"]:
            lines.append(f"      安装：{r['install']}")
        elif r.get("recommended") is False:
            lines.append(f"      注意：{r['install']}")
    return "\n".join(lines)


def ready(kind: str | None = None) -> bool:
    items = check()
    if kind:
        items = [r for r in items if r["kind"] == kind]
    return all(r["ready"] for r in items)


def require(kind: str) -> None:
    """需要某类渲染器时调用；缺失则给出明确指引。"""
    items = [r for r in check() if r["kind"] == kind]
    missing = [r for r in items if not r["ready"]]
    if missing:
        raise RuntimeError("缺少渲染器：" + "；".join(
            f"{r['name']}（{r['install']}）" for r in missing))


def configure(chrome_path: str) -> dict:
    """手动指定浏览器路径并保存（写入 cache/renderer.json）。"""
    p = Path(chrome_path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{chrome_path}")
    os.environ["CHROME_PATH"] = str(p)
    _save_config({"chrome": str(p)})
    return {"chrome": str(p), "ready": check()}


def init() -> dict:
    """首次使用初始化：返回 {first_use, renderers, status}。

    AI/使用者在第一次写谱/导出前调用，把 ❌ 的渲染器告诉用户并按需安装。
    """
    items = check()
    first_use = not _config_path().exists()
    if first_use:
        chrome = next((r["detail"] for r in items
                       if r["id"] == "chrome" and r["ready"]), None)
        _save_config({"chrome": chrome, "checked": True})
    return {"first_use": first_use, "renderers": items, "status": status(),
            "all_ready": all(r["ready"] for r in items)}


__all__ = ["RENDERERS", "check", "status", "ready", "require", "configure",
           "init", "soundfonts"]
