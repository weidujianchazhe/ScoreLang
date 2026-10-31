# -*- coding: utf-8 -*-
"""图片乐谱 → MS：Audiveris OMR（逐页）→ 合并 → .ms/.md/MIDI/WAV/PNG。

用法：
    python tools/omr_score.py --root inbox/cloudmusic/cloudmusic --out inbox/omr_batch \
        --song "钢琴 - 嘘" --bpm 120
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms", "ms/_core", "perform", "render",
                                       "audio", "analyze", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms  # noqa: E402
import ms_io  # noqa: E402
import ms_model as ev  # noqa: E402
import ms_validate  # noqa: E402
from ms.task import Song  # noqa: E402

AUDIVERIS = ROOT / "inbox" / "audiveris" / "Audiveris" / "Audiveris.exe"


def _extract_xml(mxl: Path, dst: Path) -> Path:
    with zipfile.ZipFile(mxl) as z:
        names = [n for n in z.namelist() if n.endswith((".xml", ".musicxml"))]
        dst.write_bytes(z.read(names[0]))
    return dst


def _page_info(xml: Path):
    """从 MusicXML 读 (小节数, meter) —— tempo 由调用方给。"""
    tree = ET.parse(xml)
    root = tree.getroot()
    measures = root.findall(".//measure")
    beats, beat_type = 4, 4
    t = root.find(".//attributes/time")
    if t is not None:
        b = t.findtext("beats")
        bt = t.findtext("beat-type")
        if b and bt:
            beats, beat_type = int(b), int(bt)
    return len(measures), (beats, beat_type)


def _import_page(xml: Path):
    song = ms.open(str(xml))
    return song._doc


def _merge(docs, bars, meter, bpm: float, prefix: str):
    upb = int(round(60_000_000 / bpm))
    bar_us = int(round(meter[0] * upb))
    events, pedals, turns, curves, segments = [], [], [], [], []
    offset = 0
    for page_no, (doc, nbars) in enumerate(zip(docs, bars), 1):
        idmap = {}
        for e in doc.events:
            nid = f"{prefix}p{page_no}_{e.id}"
            idmap[e.id] = nid
            events.append(replace(
                e, id=nid, onset_us=e.onset_us + offset,
                release_us=(None if e.release_us is None else e.release_us + offset)))
        page_end = offset + nbars * bar_us
        for p in doc.pedals:
            end = page_end if p.end_us is None else p.end_us + offset
            pedals.append(replace(p, id=None, start_us=p.start_us + offset,
                                  end_us=end))
        for t in doc.turns:
            if t.event_id in idmap:
                turns.append(replace(t, event_id=idmap[t.event_id]))
        for c in doc.curves:
            curves.append(replace(c, time_us=c.time_us + offset))
        for s in doc.segments:
            segments.append(replace(s, event_id=idmap.get(s.event_id, s.event_id),
                                    onset_us=s.onset_us + offset,
                                    release_us=s.release_us + offset))
        offset += nbars * bar_us
    # 踏板 id 重编 + 同轨重叠修剪
    pedals.sort(key=lambda x: (x.instrument_id, x.start_us))
    fixed = []
    for p in pedals:
        if fixed and fixed[-1].instrument_id == p.instrument_id \
                and fixed[-1].kind == p.kind and p.start_us <= (fixed[-1].end_us or 0):
            prev = fixed[-1]
            fixed[-1] = replace(prev, end_us=max(prev.start_us + 1, p.start_us - 1000))
        fixed.append(p)
    fixed = [p for p in fixed if p.end_us is not None and p.end_us > p.start_us]
    pedals = ev.assign_pedal_ids(fixed)
    instruments = next((d.instruments for d in docs if d.instruments), [])
    return ev.MSDocument(
        piano_count=max(1, len(instruments)),
        constraint_mode="single_piano" if len(instruments) <= 1 else "n_pianos",
        events=events, pedals=pedals, turns=turns, curves=curves,
        segments=segments, instruments=list(instruments))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="解压后的 cloudmusic 目录")
    ap.add_argument("--out", required=True)
    ap.add_argument("--song", help="曲目子目录名")
    ap.add_argument("--song-dir", help="曲目目录（优先）")
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    song_dir = Path(args.song_dir) if args.song_dir else Path(args.root) / args.song
    song_name = song_dir.name
    pages = sorted(song_dir.glob("*.jpg"), key=lambda p: int(p.stem))
    if args.limit:
        pages = pages[: args.limit]
    out = Path(args.out) / song_name
    out.mkdir(parents=True, exist_ok=True)
    docs, bars = [], []
    tag = hashlib.md5(str(song_name).encode("utf-8")).hexdigest()[:10]
    work = ROOT / "inbox" / "omr_work" / tag
    (work / "out").mkdir(parents=True, exist_ok=True)
    for pg in pages:
        ascii_img = work / f"p{pg.stem}.jpg"
        if not ascii_img.exists():
            try:
                from PIL import Image
                im = Image.open(pg).convert("L")
                if im.width < 1800:
                    f = 1800 / im.width
                    im = im.resize((int(im.width * f), int(im.height * f)),
                                   Image.LANCZOS)
                im.save(ascii_img, "JPEG", quality=92)
            except Exception:  # noqa: BLE001
                shutil.copyfile(pg, ascii_img)
        omr_out = work / "out"
        mxl = omr_out / f"p{pg.stem}.mxl"
        if not mxl.exists():
            r = subprocess.run([str(AUDIVERIS), "-batch", "-export",
                                "-output", str(omr_out), str(ascii_img)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1800)
            if r.returncode != 0 or not mxl.exists():
                print("OMR 失败:", pg.name, (r.stderr or r.stdout or "")[-300:])
                continue
        xml = _extract_xml(mxl, out / f"{pg.stem}.xml")
        nbars, meter = _page_info(xml)
        docs.append(_import_page(xml))
        bars.append(nbars)
        print(f"页 {pg.stem}: {nbars} 小节, {len(docs[-1].events)} 音")
    if not docs:
        print("没有可合并的页")
        return 1
    meter = (4, 4)
    doc = _merge(docs, bars, meter, args.bpm, prefix="omr")
    errs = ms_validate.validate(doc)
    if errs:
        print("合并后校验失败（前 5 条）：", errs[:5])
    ms_io.save(doc, out / f"{song_name}.ms")

    try:
        import ms_md
        (out / f"{song_name}.md").write_text(
            ms_md.dumps_authoring(doc, bpm=args.bpm, meter=meter),
            encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print("MD 跳过:", exc)
    song = Song(doc, bpm=args.bpm, meter=meter)
    (out / f"{song_name}.mid").write_bytes(song.export_midi())
    song.export_wav(out / f"{song_name}.wav")
    try:
        song.export_png(out / f"{song_name}.png", bars_per_page=4, width=2000)
    except Exception as e:  # noqa: BLE001
        print("PNG 跳过:", e)
    print("完成：", out, "| 事件", len(doc.events), "| 页", len(docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
