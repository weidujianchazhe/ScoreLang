# -*- coding: utf-8 -*-
"""把长曲的五线谱分页，再拼成一张可读 PNG。"""
from __future__ import annotations

import base64
import math
from dataclasses import replace

import ms_model as ev

_BASS_FAMILIES = {"bass", "brass"}


def _bar_us(meter, time_base_us: int) -> int:
    return int(meter[0] * time_base_us)


def _clef_for(instrument) -> str:
    try:
        import ms_instruments as _reg
        fam = _reg.resolve(instrument.type).get("family")
        if fam == "piano":
            return "grand"
        return "bass" if fam in _BASS_FAMILIES else "treble"
    except Exception:  # noqa: BLE001
        return "treble"


def _page_doc(doc, t0: int, t1: int, bar: int,
              start_bar: int, end_bar: int, iid=None):
    """切一页（可选只看某件乐器），时间平移到 0。"""
    events = []
    for e in doc.events:
        if iid is not None and e.instrument_id != iid:
            continue
        if e.onset_us >= t1 or (e.release_us or e.onset_us) <= t0:
            continue
        onset = max(0, e.onset_us - t0)
        release = max(onset + 1, (e.release_us or e.onset_us) - t0)
        events.append(replace(e, onset_us=onset, release_us=release))

    pedals = []
    for p in doc.pedals:
        if iid is not None and p.instrument_id != iid:
            continue
        s = max(t0, p.start_us)
        e_ = t1 if p.end_us is None else min(t1, p.end_us)
        if e_ <= s:
            continue
        pedals.append(replace(p, start_us=s - t0,
                              end_us=None if p.end_us is None else e_ - t0))

    ids = {e.id for e in events}
    turns = [t for t in doc.turns if t.event_id in ids]
    curves = []
    for c in doc.curves:
        if iid is not None and c.instrument_id != iid:
            continue
        if c.time_us < t0 or c.time_us >= t1:
            continue
        curves.append(replace(c, time_us=c.time_us - t0))

    content = max([e.release_us or e.onset_us for e in events] + [0])
    trailing = max(0, (end_bar - start_bar) * bar - content)
    return replace(doc, events=events, pedals=pedals, turns=turns,
                   curves=curves, segments=[], trailing_silence_us=trailing)


def pages(doc, *, bars_per_page: int = 8, meter=(4, 4), time_base_us: int,
          per_instrument: bool = True) -> list:
    """按小节分页；每页内每件乐器一行（带小节线）。返回 SVG 列表。"""
    from ms_render import render_staff, RenderOptions, estimate_key_sig

    bar = _bar_us(meter, time_base_us)
    content = ev.content_end_us(doc)
    total_bars = max(1, math.ceil(content / bar))
    if per_instrument:
        seen = []
        for e in doc.events:
            if e.instrument_id not in seen:
                seen.append(e.instrument_id)
        insts = sorted(seen) or [None]
    else:
        insts = [None]

    out = []
    start_bar = 0
    while start_bar < total_bars:
        end_bar = min(total_bars, start_bar + bars_per_page)
        t0, t1 = start_bar * bar, end_bar * bar
        for iid in insts:
            page = _page_doc(doc, t0, t1, bar, start_bar, end_bar, iid)
            if not page.events:
                continue
            clef = "treble"
            if iid and 0 < iid <= len(page.instruments):
                clef = _clef_for(page.instruments[iid - 1])
            opt = RenderOptions(px_per_sec=90.0, meter=meter,
                                time_base_us=time_base_us, clef=clef,
                                key_sig=estimate_key_sig(doc))
            out.append(render_staff(page, options=opt))
        start_bar = end_bar
    return out


def header_svg(title: str, subtitle: str = "", *, width: float = 1000.0) -> str:
    """标题栏（纯 SVG）：标题 + 副标题 + 横线。"""
    h = 92 if subtitle else 64
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
           f'height="{h}" viewBox="0 0 {width:.0f} {h}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']
    out.append(f'<text x="{width / 2:.1f}" y="40" text-anchor="middle" '
               f'font-family="Georgia, Times New Roman, serif" font-size="30" '
               f'font-weight="600" fill="#111">{title}</text>')
    if subtitle:
        out.append(f'<text x="{width / 2:.1f}" y="66" text-anchor="middle" '
                   f'font-family="Georgia, Times New Roman, serif" font-size="14" '
                   f'fill="#555">{subtitle}</text>')
    out.append(f'<line x1="{width * 0.12:.1f}" y1="{h - 10}" x2="{width * 0.88:.1f}" '
               f'y2="{h - 10}" stroke="#999" stroke-width="0.8"/>')
    out.append("</svg>")
    return "\n".join(out)


def svg_pages_to_png(svgs: list, path, *, width: int = 1800) -> str:
    """多页 SVG → 一张纵向拼接的 PNG（本机 Chrome 无头渲染）。"""
    import re
    import subprocess
    import tempfile
    from pathlib import Path

    if not svgs:
        raise ValueError("没有可分页的内容")

    parts = ["<html><body style='margin:0;background:#fff'>"]
    total_h = 0
    max_w = 0
    for s in svgs:
        m = re.search(r'width="([\d.]+)" height="([\d.]+)"', s)
        w, h = (float(m.group(1)), float(m.group(2))) if m else (1000.0, 150.0)
        scale = min(width / w, 2.0)          # 小页不放大到失真
        ww, hh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        max_w = max(max_w, ww)
        total_h += hh + 6
        b64 = base64.b64encode(s.encode("utf-8")).decode("ascii")
        parts.append(f"<img src='data:image/svg+xml;base64,{b64}' "
                     f"style='display:block;width:{ww}px;height:{hh}px;"
                     f"margin-bottom:6px'>")
    parts.append("</body></html>")
    html = "".join(parts)

    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Edge：PNG 需要浏览器渲染。先运行 ms.renderer_status() 检查；缺失时 ms.configure_renderer(路径) 指定，或改用 --staff 出 SVG")
    td = tempfile.mkdtemp(prefix="staffpng_")
    try:
        html_path = Path(td) / "page.html"
        html_path.write_text(html, encoding="utf-8")
        tmp_png = Path(td) / "out.png"
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               f"--screenshot={tmp_png}",
               f"--window-size={max(max_w, width)},{total_h}",
               html_path.as_uri()]
        subprocess.run(cmd, capture_output=True, timeout=300)
        if not tmp_png.exists():
            raise RuntimeError("Chrome 截图失败（SVG→PNG）")
        try:
            from PIL import Image
            img = Image.open(tmp_png)
            w, h = img.size
            limit = 32_000_000
            if w * h > limit:
                sc = (limit / (w * h)) ** 0.5
                img = img.resize((max(1, int(w * sc)), max(1, int(h * sc))),
                                 Image.LANCZOS)
                img.save(tmp_png, "PNG", optimize=True)
        except ImportError:
            pass
        Path(path).write_bytes(tmp_png.read_bytes())
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return str(path)


def svg_pages_to_pdf(svgs: list, path, *, width: int = 1800) -> str:
    """多页 SVG → 多页 PDF（Chrome 打印，矢量输出）。

    比 PNG 简单：不截图、不拼大图；每页 SVG 一页 PDF。
    """
    import subprocess
    import tempfile
    from pathlib import Path

    if not svgs:
        raise ValueError("没有可分页的内容")
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Edge：PDF 需要浏览器打印。"
                           "先运行 ms.renderer_status()；或直接导出 SVG。")
    parts = ["<html><head><meta charset='utf-8'><style>",
             "@page { size: A4; margin: 10mm; }",
             "body { margin:0; background:#fff; }",
             ".pg { page-break-after: always; text-align:center; }",
             ".pg:last-child { page-break-after: auto; }",
             ".pg svg { width:100%; height:auto; }",
             "</style></head><body>"]
    for svg in svgs:
        parts.append(f"<div class='pg'>{svg}</div>")
    parts.append("</body></html>")
    td = tempfile.mkdtemp(prefix="staffpdf_")
    try:
        html_path = Path(td) / "page.html"
        html_path.write_text("\n".join(parts), encoding="utf-8")
        tmp_pdf = Path(td) / "out.pdf"
        cmd = [chrome, "--headless=new", "--disable-gpu",
               "--no-pdf-header-footer",
               f"--print-to-pdf={tmp_pdf}", html_path.as_uri()]
        subprocess.run(cmd, capture_output=True, timeout=300)
        if not tmp_pdf.exists():
            raise RuntimeError("Chrome 打印失败（SVG→PDF）")
        Path(path).write_bytes(tmp_pdf.read_bytes())
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return str(path)


def _find_chrome() -> str | None:
    import os
    from pathlib import Path
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


__all__ = ["pages", "svg_pages_to_png", "svg_pages_to_pdf"]
