# -*- coding: utf-8 -*-
"""对外 API 门面。"""
from __future__ import annotations

from pathlib import Path

import ms_author as _author
import ms_io as _io
import ms_validate as _validate
from ms_model import MSDocument, Event, Instrument, PedalSegment, TurnPoint, CurvePoint

from .author import Writer, pitch_to_semitone
from .report import report  # noqa: F401
from .report import text as report_text  # noqa: F401
def soundfonts() -> list:
    """已有音色库列表（只列有什么，不检查）。"""
    return _renderers.soundfonts()


def selfcheck() -> dict:
    """技能包自检：包完整性 + 渲染器真实可用性（路径不存在标红）。"""
    return _selfcheck.report()


def renderers() -> list:
    """渲染器清单与状态（audio 合成 / image 浏览器渲染）。"""
    return _renderers.check()


def render_status() -> str:
    """渲染器状态文本（✅/❌）。"""
    return _renderers.status()


def render_init() -> dict:
    """首次使用初始化：检查渲染器，返回 first_use/renderers/status/all_ready。"""
    return _renderers.init()


def configure_renderer(chrome_path: str) -> dict:
    """手动指定浏览器路径（用于 SVG→PNG）。"""
    return _renderers.configure(chrome_path)


from .task import (Song, package, instruments, resolve_instrument,  # noqa: F401
                   instrument_actions, instrument_catalog, check_spec,
                   save_spec, clear_cache)
from .schema import (detail as _schema_detail, text as _schema_text,
                     perform, prime)
from .guide import Guide
from .draft_gen import draft
from .textfmt import parse_text, dump_text
from .fix import analyze_fix
from .diagnose import diagnose
from .export_check import export_check
from . import renderers as _renderers
from . import selfcheck as _selfcheck
from .registry import catalog, markdown, menu, actions, articulations, ornaments

# ── 文档 ────────────────────────────────────────────────
def new_document(*, instruments=None, piano_count=None, constraint_mode=None,
                 channels: str = "per_instance"):
    """空文档（可带乐器）。instruments 可以是类型码字符串，或 Instrument。"""
    insts = []
    for i, it in enumerate(instruments or [], 1):
        if isinstance(it, Instrument):
            insts.append(it)
        else:
            insts.append(Instrument(id=f"P{i}", type=str(it)))
    return MSDocument(piano_count=piano_count or max(1, len(insts)),
                      constraint_mode=constraint_mode
                      or ("single_piano" if (piano_count or len(insts) or 1) == 1 else "n_pianos"),
                      instruments=insts, channels=channels)


# ── 作者 API（函数式；需要状态时用 Writer） ──────────────
write_note = _author.write_note
write_chord = _author.write_chord
write_pedal = _author.write_pedal
write_turn = _author.write_turn
write_vocal = _author.write_vocal
vocal_units = _author.vocal_units
make_instrument = _author.make_instrument
to_document = _author.to_document

# ── 读写 / 校验 / 诊断 ──────────────────────────────────
def load(path):
    """按文件尾标识读入：`.md` → 文档写法（标签式/表格式自动识别）；旧档案 → 只读兼容。"""
    from pathlib import Path as _P
    p = _P(path)
    if p.suffix.lower() == ".md":
        import ms_md as _md
        return _md.load(p)
    return _io.load(p)

def save(doc_or_song, path):
    """写文档：产物是 `.md`。不给后缀时自动补 `.md`。

    `doc_or_song` 可以是 MSDocument，也可以是 Song。
    显式指定旧档案后缀时才走旧读取器的写出（仅为兼容，不作写作口径）。
    """
    from pathlib import Path as _P
    doc = getattr(doc_or_song, "_doc", doc_or_song)
    p = _P(path)
    if not p.suffix:
        p = p.with_suffix(".md")
    if p.suffix.lower() == ".md":
        import ms_md as _md
        return _md.save(doc, p)
    return _io.save(doc, p)

def save_md(doc_or_song, path):
    doc = getattr(doc_or_song, "_doc", doc_or_song)
    import ms_md as _md
    return _md.save(doc, path)

def load_md(path):
    import ms_md as _md
    return _md.load(path)

def dump(doc) -> str:
    return _io.dump(doc)

def parse(text):
    return _io.parse(text)

def validate(doc) -> list:
    return _validate.validate(doc)

def pedal_diagnostics(doc) -> dict:
    """踏板链 / 实际发声总长（V4c 数据层）。"""
    return _validate.pedal_diagnostics(doc)


# ── 渲染 / 音频（延迟导入，避免无谓依赖） ────────────────
def render_svg(doc, *, mode: str = "pianoroll", px_per_sec: float | None = None,
               options=None) -> str:
    """返回 SVG 文本（pianoroll / staff）。"""
    from ms_render import render_pianoroll, render_staff, PX_PER_SEC
    pps = PX_PER_SEC if px_per_sec is None else px_per_sec
    if mode == "staff":
        return render_staff(doc, px_per_sec=pps, options=options)
    return render_pianoroll(doc, px_per_sec=pps, options=options)

def export_abc(doc, *, title: str = "", bpm: float = 120.0,
               meter=(4, 4), unit_note: float = 0.5) -> str:
    """导出 ABC 谱文本（外部可读格式之一）。"""
    from .export_abc import to_abc
    return to_abc(doc, title=title, bpm=bpm, meter=meter, unit_note=unit_note)

def export_staff(doc, *, px_per_sec: float | None = None, options=None) -> str:
    """导出五线谱 SVG 文本（外部可读格式之二）。"""
    return render_svg(doc, mode="staff", px_per_sec=px_per_sec, options=options)

def render_text(doc) -> str:
    from ms_render import render_text as _rt
    return _rt(doc)

def audio_samples(doc, *, tail: float = 0.8):
    from make_audio import render as _r
    return _r(doc, tail=tail)

def to_wav(doc, path, *, tail: float = 0.8) -> Path:
    from make_audio import render as _r, write_wav
    write_wav(_r(doc, tail=tail), path)
    return Path(path)

# ── 导入：把现成曲谱变成 Song（外部可用） ────────────────
def open(path):  # noqa: A001
    """读 MIDI / MusicXML → `Song`。

    导入后同样可以 `export_abc()` / `export_staff()` / `export_wav()` / `export_png()`。
    """
    from pathlib import Path as _Path
    p = _Path(path)
    suf = p.suffix.lower()
    if suf in (".mid", ".midi"):
        from ms_import_midi import import_midi as _im
        doc, _rep = _im(p.read_bytes())
    elif suf in (".musicxml", ".xml"):
        from ms_import import import_musicxml as _ix
        doc, _rep = _ix(p)
    else:
        raise ValueError("支持 .mid/.midi/.musicxml/.xml（.mxl 请先解压）")
    tempo_us = int((_rep or {}).get("tempo_us") or 500_000)
    bpm = round(60_000_000 / tempo_us, 3)
    meter = tuple((_rep or {}).get("meter") or (4, 4))
    return Song(doc, bpm=bpm, meter=meter, title=p.stem)

# ── 导入（MIDI / MusicXML） ──────────────────────────────
def import_midi(path_or_bytes, *, max_pianos: int = 2):
    from ms_import_midi import import_midi as _m
    data = (Path(path_or_bytes).read_bytes()
            if isinstance(path_or_bytes, (str, Path)) else bytes(path_or_bytes))
    return _m(data, max_pianos=max_pianos)

def import_musicxml(path, *, default_bpm: float = 120.0, **kw):
    from ms_import import import_musicxml as _m
    return _m(path, default_bpm=default_bpm, **kw)

# ── 任务脚本接口（外部推荐用法：不必知道 .ms 结构） ──────
def start(*, bpm: float = 120.0, meter=(4, 4), title: str = "",
          instruments=None, intent=None):
    """写作向导：按顺序填数据；intent 会编译成生成约束（密度/收束）。"""
    return Guide(bpm=bpm, meter=meter, title=title, instruments=instruments,
                 intent=intent)


def build(spec, *, title: str = "", fix: bool = False,
          intent: dict | None = None):
    """任务 JSON → Song。

spec 里 instruments 可用别名：piano / epiano / organ / guitar / bass /
violin / viola / cello / flute / trumpet / sax / drums / synth；
**同一类型写两次就是两把**（例如两个 piano = P1、P2）。
字段与取值范围见 ms.schema_text()。

省 token 写法（等价）：
  notes: [{"inst":1,"pitch":"C4","beat":0,"beats":1}]
  notes: [[1,"C4",0,1,"mf"]]
  notes: ["C4@0+1/mf", "2:E5@2+1/p"]"""
    from .task import build as _build
    return _build(spec, title=title, fix=fix, intent=intent)

def schema() -> dict:
    """数据字典：字段、单位、力度等级、奏法影响、曲线参数、限制。"""
    return _schema_detail()

def schema_text() -> str:
    """一屏数据字典。"""
    return _schema_text()

def cheatsheet() -> str:
    """最简用法示例。"""
    return (
        "1) spec = {bpm, meter, instruments:[{type}], notes:[{inst,pitch|pitches,beat,beats,"
        "level?,articulation?}], pedals:[{inst,kind,start,end}], turns:[{note,kind}], "
        "curves:[{inst,param,points}]}\n"
        "2) song = ms.build(spec)\n"
        "3) song.export_abc() / song.export_staff() / song.export_wav('out.wav')\n"
        "用法：ms.build(spec) → Song → 导出 ABC 谱 / 五线谱 / 音频。"
    )

# ── 与 S02 的单向桥（S02 读 MS；MS 不读 S02） ──────────
def to_s02(doc, *, time_base_us: int, **kw):
    """把内存文档投影成 S02 骨架对象（不落文件）。"""
    from ms_to_s02 import to_s02 as _to
    return _to(doc, time_base_us=time_base_us, **kw)


__all__ = [
    # 版本/文档
    "MSDocument", "Event", "Instrument", "PedalSegment", "TurnPoint", "CurvePoint",
    "new_document", "load", "save", "save_md", "load_md", "dump", "parse",
    # 写作
    "Writer", "pitch_to_semitone", "write_note", "write_chord", "write_pedal",
    "write_turn", "write_vocal", "vocal_units", "make_instrument", "to_document",
    # 校验/诊断
    "validate", "pedal_diagnostics",
    # 渲染/音频
    "render_svg", "render_text", "audio_samples", "to_wav",
    "export_abc", "export_staff",
    # 导入
    "open", "import_midi", "import_musicxml",
    # 能力菜单
    "catalog", "markdown", "menu", "actions", "articulations", "ornaments",
    # 任务脚本（外部推荐）
    "build", "Song", "package", "report", "report_text", "export_check",
    "check_spec",
    "save_spec",
    "cheatsheet", "clear_cache",
    "start", "Guide", "draft", "parse_text", "dump_text",
    "analyze_fix", "diagnose", "export_check",
    "perform", "prime",
    "selfcheck", "soundfonts", "renderers", "render_status", "render_init",
    "configure_renderer",
    "instruments", "resolve_instrument",
    "instrument_actions", "instrument_catalog", "schema", "schema_text",
    # 桥
    "to_s02",
]
