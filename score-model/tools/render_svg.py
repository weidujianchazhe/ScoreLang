# -*- coding: utf-8 -*-
"""`.md` → SVG。四个模式与引擎内渲染器一致。

用法：
    python score-model/tools/render_svg.py piece.md -o piece.svg --mode staff2 --meter 7/8 --time-base 500000

读入按文件尾标识分派：`.md` 走文档写法；旧档案只读兼容。
路径全部由 `__file__` 推导，整个 `score-model/` 可以搬到任何位置；
工程外 `../tools/render_svg.py` 只是转发壳（保持旧命令可用）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
for _d in ("", "ms", "ms/_core", "perform", "analyze", "render", "audio", "importers", "tools", "scripts"):
    p = str(ENGINE / _d) if _d else str(ENGINE)
    if p not in sys.path:
        sys.path.insert(0, p)

import ms
import ms_render as rd
import ms_render as ro
import ms_render_jianpu as jp

MODES = ("pianoroll", "staff", "staff2", "jianpu")


def parse_meter(s):
    if not s:
        return None
    try:
        n, d = s.split("/")
        return int(n), int(d)
    except Exception:
        raise SystemExit(f"拍号格式应为 N/D：{s}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=".md → SVG（四模式）")
    ap.add_argument("file")
    ap.add_argument("-o", "--out", help="输出 SVG（缺省写到 stdout）")
    ap.add_argument("--mode", default="pianoroll", choices=MODES)
    ap.add_argument("--jianpu-mode", default="melody", choices=jp.MODES)
    ap.add_argument("--meter", help="如 4/4；不给则不画小节线")
    ap.add_argument("--time-base", type=int, dest="time_base", help="µs / 四分音符")
    ap.add_argument("--px-per-sec", type=float, default=120.0, dest="px_per_sec")
    ap.add_argument("--clef", default="treble", choices=ro.CLEFS)
    ap.add_argument("--key-sig", type=int, dest="key_sig", default=None)
    args = ap.parse_args(argv)

    doc = ms.load(args.file)
    opts = ro.RenderOptions(
        meter=parse_meter(args.meter),
        time_base_us=args.time_base,
        px_per_sec=args.px_per_sec,
        clef=args.clef,
        key_sig=args.key_sig,
    )
    warn: list = []
    if args.mode == "pianoroll":
        svg = rd.render_pianoroll(doc, options=opts, warnings=warn)
    elif args.mode == "staff":
        svg = rd.render_staff(doc, options=opts, warnings=warn)
    elif args.mode == "staff2":
        import ms_render_staff2 as st
        svg = st.render_staff2(doc, opts, warnings=warn)
    else:
        svg = jp.render_jianpu(doc, opts, mode=args.jianpu_mode, warnings=warn)

    if warn:
        print(f"⚠ 演奏收束：{len(warn)} 项不可弹（结构合法，图仍生成）", file=sys.stderr)
        for w in warn[:5]:
            print(f"    - {w}", file=sys.stderr)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(svg, encoding="utf-8")
        print(f"已写出 {args.out}（{len(svg)} 字符）")
    else:
        sys.stdout.write(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
