# -*- coding: utf-8 -*-
"""任务脚本：把任务 JSON 变成一首曲子（Song）。"""
from __future__ import annotations


# 外部只暴露一个**短名单**（不是 184 种）：够用、好记、省 token。
FRIENDLY = {
    "piano": "acoustic_grand_piano",
    "epiano": "electric_piano_2",
    "organ": "drawbar_organ",
    "guitar": "acoustic_guitar_steel",
    "bass": "electric_bass_finger",
    "violin": "violin",
    "viola": "viola",
    "cello": "cello",
    "flute": "flute",
    "trumpet": "trumpet",
    "sax": "tenor_sax",
    "drums": "kit_standard",
    "synth": "lead_2_sawtooth",
}

_ALIAS = {_v: _k for _k, _v in FRIENDLY.items()}


def instruments() -> dict:
    """可选乐器短名单（别名 → 类型）：piano / epiano / organ / guitar / bass / violin / viola / cello / flute / trumpet / sax / drums / synth。"""
    import ms_instruments as _reg
    out = {}
    for alias, code in FRIENDLY.items():
        spec = _reg.resolve(code)
        out[alias] = {"type": code, "family": spec.get("family")}
    return out


def instrument_actions(name: str) -> list:
    """这件乐器能做的演奏转折（可查，不必自己写）。接受别名或类型码。"""
    from ms.registry import actions as _acts
    return _acts(resolve_instrument(name))


def instrument_catalog(*, family: str | None = None) -> dict:
    """目录（乐器/动作/踏板/曲线）；人声通道未实现，不显示 voice。"""
    from ms.registry import catalog as _cat
    data = _cat(family=family)
    types = {k: v for k, v in data.get("types", {}).items()
             if v.get("family") != "voice"}
    fams = {k: [c for c in v if c in types] for k, v in data.get("families", {}).items()}
    fams = {k: v for k, v in fams.items() if v}
    data["types"] = types
    data["families"] = fams
    data["count"] = dict(data.get("count", {}), types=len(types), families=len(fams))
    return data


def resolve_instrument(name: str) -> str:
    """别名 → 类型码；也接受完整类型码。未知时只列短名单（不甩 184 种）。"""
    raw = str(name).strip()
    key = raw.lower()
    if key.startswith("voice") or key in ("choir", "vocal", "人声"):
        raise ValueError("人声暂不支持")
    if key in FRIENDLY:
        return FRIENDLY[key]
    import ms_instruments as _reg
    try:
        _reg.resolve(raw if raw in _reg._BY_CODE or raw in _reg.EXTENDED else raw.lower())
        return raw
    except KeyError:
        raise ValueError(f"可选乐器：{sorted(FRIENDLY)}"
                         "（可选乐器见 ms.instruments()）") from None


class Song:
    """一首曲子：可导出 ABC 谱、五线谱（SVG/PNG）与音频。"""

    def __init__(self, doc, *, bpm: float = 120.0, meter=(4, 4), title: str = "",
                 spec=None):
        self._doc = doc
        self._spec = spec          # 内部；不提供公开访问器
        self.bpm = float(bpm)
        self.meter = tuple(meter)
        self.title = title

    # 保存（内部工程区）
    def save_md(self, path) -> str:
        """保存为标签式 Markdown 作者文档。"""
        import ms_md
        return ms_md.save(self._doc, path)

    def save_ms(self, path) -> str:
        """保存为 .ms 线格式（内部）。"""
        import ms_io
        return str(ms_io.save(self._doc, path))

    # 导出（外部唯一三种用法）
    def export_abc(self) -> str:
        """返回 ABC 谱文本（字符串，不写文件）。"""
        from ms_abc import to_abc
        return to_abc(self._doc, title=self.title, bpm=self.bpm, meter=self.meter)

    def export_staff(self, *, px_per_sec: float | None = None, options=None) -> str:
        """返回五线谱 SVG 文本（字符串，不写文件）。

        未给 options 时自动按本曲 bpm/meter 生成（画小节线需要）；钢琴用大谱表。
        """
        from ms_render import render_staff, RenderOptions, PX_PER_SEC
        if options is None:
            fams = set()
            try:
                import ms_instruments as _reg
                for ins in self._doc.instruments:
                    fams.add(_reg.resolve(ins.type).get("family"))
            except Exception:  # noqa: BLE001
                pass
            clef = "grand" if "piano" in fams else (
                "bass" if fams and fams <= {"bass", "brass"} else "treble")
            from ms_render import estimate_key_sig
            options = RenderOptions(
                meter=tuple(self.meter), clef=clef,
                time_base_us=int(round(60_000_000 / self.bpm)),
                key_sig=estimate_key_sig(self._doc))
        return render_staff(self._doc,
                            px_per_sec=PX_PER_SEC if px_per_sec is None else px_per_sec,
                            options=options)

    def export_audio(self, *, tail: float = 0.8):
        """返回音频采样数组（PCM，不写文件）。"""
        from make_audio import render as _r
        return _r(self._doc, tail=tail)

    def export_midi(self) -> bytes:
        """返回标准 MIDI 字节（.mid 内容，不写文件）。"""
        from ms_midi import write_midi_files
        us = int(round(60_000_000 / self.bpm))
        files, _report = write_midi_files(self._doc, time_base_us=us)
        return files[0]

    def export_png(self, path, *, bars_per_page: int = 8, width: int = 1800,
                   title: str | None = None, subtitle: str | None = None) -> str:
        """五线谱 → 分页 → 一张 PNG（可读版）。需要本机 Chrome。

        title/subtitle 给定时在顶部加标题栏（纯 SVG，不依赖外部页面）。
        """
        from ms_staff_pages import pages, svg_pages_to_png, header_svg
        tb = int(round(60_000_000 / self.bpm))
        svgs = pages(self._doc, bars_per_page=bars_per_page,
                     meter=self.meter, time_base_us=tb)
        if title:
            svgs = [header_svg(title, subtitle or "", width=width)] + svgs
        return svg_pages_to_png(svgs, path, width=width)

    def export_pdf(self, path, *, bars_per_page: int = 8, width: int = 1800,
                   title: str | None = None, subtitle: str | None = None) -> str:
        """五线谱 → 分页 → 多页 PDF（矢量）。需要本机 Chrome。"""
        from ms_staff_pages import pages, svg_pages_to_pdf, header_svg
        tb = int(round(60_000_000 / self.bpm))
        svgs = pages(self._doc, bars_per_page=bars_per_page,
                     meter=self.meter, time_base_us=tb)
        if title:
            svgs = [header_svg(title, subtitle or "", width=width)] + svgs
        return svg_pages_to_pdf(svgs, path, width=width)

    def save_delivery(self, out_dir, stem: str = "piece", *,
                      bars_per_page: int = 8, width: int = 1800,
                      title: str | None = None, subtitle: str | None = None,
                      tail: float = 0.8) -> dict:
        """交付四件套：`.md`（MS 模型）+ `.pdf` + `.mid` + `.wav`。

        返回 {md,pdf,mid,wav} 路径。
        """
        from pathlib import Path as _P
        d = _P(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        md = self.save_md(str(d / f"{stem}.md"))
        pdf = self.export_pdf(str(d / f"{stem}.pdf"), bars_per_page=bars_per_page,
                              width=width, title=title, subtitle=subtitle)
        (d / f"{stem}.mid").write_bytes(self.export_midi())
        wav = self.export_wav(str(d / f"{stem}.wav"), tail=tail)
        return {"md": md, "pdf": pdf, "mid": str(d / f"{stem}.mid"),
                "wav": str(wav)}

    def export_wav(self, path, *, tail: float = 0.8):
        """**写出** WAV 音频文件。"""
        from make_audio import render as _r, write_wav
        write_wav(_r(self._doc, tail=tail), path)
        return path

    # 只读摘要（不暴露结构，帮助外部排查）
    def summary(self) -> dict:
        doc = self._doc
        return {"notes": len(doc.events), "pedals": len(doc.pedals),
                "instruments": len(doc.instruments), "bpm": self.bpm,
                "meter": list(self.meter)}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Song {self.summary()}>"


def package(spec_or_song, out_dir, *, slug: str | None = None,
            bars_per_page: int = 8, width: int = 1800,
            fix: bool = False, intent: dict | None = None,
            check: bool = False, strict: bool = False) -> dict:
    """产物协议：每首曲一个文件夹，里面三个文件：`.mid` / `.wav` / `.png`。

    ```python
    ms.package(spec, "output")     # → output/<曲名>/<曲名>.mid|.wav|.png
    ```
    """
    from pathlib import Path as _Path
    _check_res = None
    if check and isinstance(spec_or_song, dict):
        from .export_check import export_check as _ec
        _check_res = _ec(spec_or_song, intent=intent, strict=strict)
        if not _check_res["ok"]:
            raise ValueError("导出前检查未通过：\n" + _check_res["summary"])
    song = (build(spec_or_song, fix=fix, intent=intent)
            if isinstance(spec_or_song, dict) else spec_or_song)
    name = slug or song.title or "piece"
    name = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)[:60] or "piece"
    folder = _Path(out_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    mid = folder / f"{name}.mid"
    wav = folder / f"{name}.wav"
    png = folder / f"{name}.png"
    abc = folder / f"{name}.abc"
    mid.write_bytes(song.export_midi())
    song.export_wav(wav)
    png_ok = True
    try:
        song.export_png(png, bars_per_page=bars_per_page, width=width)
    except Exception as _png_err:  # noqa: BLE001 —— PNG 需要浏览器，缺失时仍出其它产物
        png_ok = False
        png = None
    abc.write_text(song.export_abc(), encoding="utf-8")
    return {"folder": str(folder), "mid": str(mid), "wav": str(wav),
            "png": str(png) if png_ok else None,
            "abc": str(abc), "export_check": _check_res, "summary": song.summary()}


def _norm_note(n):
    """把音符简写统一成 dict。

    支持三种写法（省 token 用后两种）：
      · dict：{"inst":1,"pitch":"C4","beat":0,"beats":1,"level":"mf"}
      · 数组：[inst, pitch, beat, beats, level?]
      · 字符串："inst:pitch@beat+beats/level"（inst 可省，默认 1）
    """
    import re as _re
    if isinstance(n, dict):
        return n
    if isinstance(n, (list, tuple)):
        if len(n) < 4:
            raise ValueError(f"音符数组至少 4 项 [inst,pitch,beat,beats]：{n!r}")
        d = {"inst": int(n[0]), "pitch": str(n[1]),
             "beat": float(n[2]), "beats": float(n[3])}
        if len(n) > 4 and n[4]:
            d["level"] = n[4]
        return d
    if isinstance(n, str):
        s = n.strip()
        inst = 1
        level = None
        if ":" in s:
            head, s = s.split(":", 1)
            inst = int(head)
        if "/" in s:
            s, level = s.rsplit("/", 1)
        m = _re.match(r"^([A-Ga-g][#b]?-?\d)@([0-9.]+)\+([0-9.]+)$", s)
        if not m:
            raise ValueError(f"音符写法应为 pitch@beat+beats[/level]：{n!r}")
        d = {"inst": inst, "pitch": m.group(1),
             "beat": float(m.group(2)), "beats": float(m.group(3))}
        if level:
            d["level"] = level.strip()
        return d
    raise ValueError(f"无法识别的音符写法：{n!r}")


def save_spec(spec_or_guide, path=None, *, name: str = "spec") -> str:
    """把完整任务数据存到**缓存区**（cache/spec/），不作为产物。

    · 传 dict（任务 JSON）或 Guide（`g.spec()`）；
    · 默认写到包内 `cache/spec/<name>.json`（可随时清理）。
    """
    import json as _json
    from pathlib import Path as _Path

    if hasattr(spec_or_guide, "spec") and callable(spec_or_guide.spec):
        spec = spec_or_guide.spec()
    elif isinstance(spec_or_guide, dict):
        spec = spec_or_guide
    else:
        raise TypeError("需要 dict 或 Guide（用 g.spec()）")
    if path is None:
        root = _Path(__file__).resolve().parent.parent
        folder = root / "cache" / "spec"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.json"
    path = _Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def clear_cache(*, dry_run: bool = False) -> dict:
    """清理缓存区（cache/），**不动 output/ 的成品**。

    返回 {"removed": [...], "kept": [...]}；dry_run=True 只列不删。
    """
    from pathlib import Path as _Path

    root = (_Path(__file__).resolve().parent.parent / "cache").resolve()
    if not root.exists():
        return {"removed": [], "kept": []}
    removed, kept = [], []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if f.name == "README.md":
            kept.append(rel)
            continue
        removed.append(rel)
        if not dry_run:
            f.unlink()
    if not dry_run:
        for d in sorted((x for x in root.rglob("*") if x.is_dir()),
                        key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
    return {"removed": removed, "kept": kept}


def check_spec(spec) -> dict:
    """检查任务 JSON 能否生成：返回 {ok, errors, summary}，不抛异常。

    给 AI/使用者做“填完数据先验证”用；只看数据对不对，不涉及内部结构。
    """
    try:
        song = build(spec)
    except Exception as exc:  # noqa: BLE001 —— 检查接口：把错误变成结果
        return {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"],
                "summary": None}
    return {"ok": True, "errors": [], "summary": song.summary()}


def build(spec: dict, *, title: str = "", fix: bool = False,
          intent: dict | None = None) -> Song:
    """任务 JSON → Song。

spec 里 instruments 可用别名：piano / epiano / organ / guitar / bass /
violin / viola / cello / flute / trumpet / sax / drums / synth；
**同一类型写两次就是两把**（例如两个 piano = P1、P2）。
字段与取值范围见 ms.schema_text()。

省 token 写法（等价）：
  notes: [{"inst":1,"pitch":"C4","beat":0,"beats":1}]
  notes: [[1,"C4",0,1,"mf"]]
  notes: ["C4@0+1/mf", "2:E5@2+1/p"]
"""
    import ms_model as ev
    from .author import Writer, pitch_to_semitone

    if not isinstance(spec, dict):
        raise TypeError("spec 必须是 dict")
    _fix_report = None
    if fix:
        from .fix import analyze_fix as _af
        _res = _af(spec, intent=intent)
        spec = _res["spec"]
        _fix_report = _res
    bpm = float(spec.get("bpm", 120.0))
    meter = tuple(spec.get("meter", (4, 4)))
    w = Writer(bpm=bpm, meter=meter)
    spec = dict(spec)
    spec["notes"] = [_norm_note(n) for n in spec.get("notes", [])]

    insts = []
    for i, it in enumerate(spec.get("instruments") or [{"type": "acoustic_grand_piano"}], 1):
        raw_type = it["type"] if isinstance(it, dict) else str(it)
        type_code = resolve_instrument(raw_type)
        import ms_instruments as _reg
        if _reg.resolve(type_code).get("family") == "voice":
            raise ValueError("人声暂不支持")
        insts.append(w.instrument(type_code,
                                  subtype=(it.get("subtype") if isinstance(it, dict) else None)))
    if not insts:
        insts = [w.instrument("acoustic_grand_piano")]

    made = []          # 与 notes 下标对应，供 turns 引用
    for n in spec.get("notes", []):
        iid = int(n.get("inst", 1))
        if iid not in insts:
            raise ValueError(f"notes.inst={iid} 不存在（已声明 {insts}）")
        pitches = n.get("pitches") or ([n["pitch"]] if "pitch" in n else None)
        if not pitches:
            raise ValueError(f"notes 缺 pitch/pitches：{n!r}")
        evs = []
        for pitch in pitches:
            evs += w.note(iid, pitch=pitch, beat=float(n.get("beat", 0)),
                          beats=float(n.get("beats", 1)),
                          level=n.get("level"), permille=n.get("permille"),
                          articulation=n.get("articulation"),
                          ornament=n.get("ornament"),
                          upper=n.get("upper"), lower=n.get("lower"),
                          grace=n.get("grace"))
        made.append(evs)

    auto_pedal = spec.get("pedal", "auto")
    pedals_spec = spec.get("pedals")
    if pedals_spec:
        for p in pedals_spec:
            w.pedal(int(p.get("inst", 1)), p.get("kind", "sustain"),
                    float(p.get("start", 0)), float(p.get("end", 0)))
    elif auto_pedal == "auto":
        # 脚本派生：逐小节踩 sustain，抬脚留 100ms（≥50ms 容差 → 不会串成一条）
        bar = float(spec.get("beats_per_bar", meter[0] if meter else 4))
        total = max([float(n.get("beat", 0)) + float(n.get("beats", 1))
                     for n in spec.get("notes", [])] + [bar])
        for iid in insts:
            if "sustain" not in w.pedals(iid):
                continue
            # 抬脚留 0.4 拍（150bpm = 160ms，> 50ms 的"同一脚"容差），
            # 否则段与段会被校验合并成一条超长踏板（V4c）。
            lift = 0.4
            b = 0.0
            while b < total - 1e-9:
                end = min(b + bar, total)
                ped_end = end - lift
                if ped_end > b + 0.05:
                    w.pedal(iid, "sustain", b, ped_end)
                b += bar

    for t in spec.get("turns", []):
        idx = int(t.get("note", 0))
        if idx >= len(made):
            raise ValueError(f"turns.note={idx} 越界（共 {len(made)} 组音）")
        for e in made[idx]:
            w.turn(e, t.get("kind", "retrigger"), int(t.get("strength", 1000)))
            break

    for c in spec.get("curves", []):
        pts = [(float(b), int(v)) for b, v in c.get("points", [])]
        if pts:
            w.curve(int(c.get("inst", 1)), c.get("param", "dynamics"), pts)

    _song = Song(w.doc(), bpm=bpm, meter=meter,
                title=title or str(spec.get("title", "")), spec=spec)
    _song.fix_report = _fix_report
    return _song


__all__ = ["Song", "build"]
