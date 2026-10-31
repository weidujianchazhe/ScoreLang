# -*- coding: utf-8 -*-
"""命令行入口（排表 I-2 / I-3）。

子命令：
  validate <file.md>                 校验并列出错误（退出码 0/1）
  info <file.md>                     摘要：事件/踏板/时长/力度缺失
  render <file.md> -o out.svg        渲染（--mode pianoroll|staff|jianpu）
  export <file.md> -o out.mid        导出 MIDI（需 --time-base）

设计约束：
  - **不猜**：`render` 要画小节线必须显式给 `--meter` 与 `--time-base`；缺则只标注
  - `export` 必须给 `--time-base`（µs/四分音符），否则无法把微秒换成 tick
  - 只调用现有模块，不内嵌业务逻辑（界面层同理）
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import argparse
import sys
from pathlib import Path

import ms_events as ev
import ms_io
import ms_io as mj
import ms_midi as mm


def _load(path: str) -> "ev.MSDocument":
    """按文件尾标识读入：`.md` → 文档写法（标签式/表格式自动识别）；旧档案 → 只读兼容。"""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"文件不存在：{path}")
    try:
        if p.suffix.lower() == ".md":
            import ms_md
            return ms_md.load(p)
        if p.suffix == ".ms":
            return ms_io.load(p)          # 旧档案：只读兼容，不是写作格式
        return mj.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"读入失败：{e}")


def _parse_meter(text: str | None):
    if not text:
        return None
    try:
        a, b = text.split("/")
        return (int(a), int(b))
    except Exception:
        raise SystemExit(f"--meter 格式应为 4/4：{text!r}")


def cmd_validate(args) -> int:
    doc = _load(args.file)
    errs = ev.validate(doc)
    if errs:
        print(f"不合法（{len(errs)} 项）：")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"合法：{len(doc.events)} 事件 / {len(doc.pedals)} 踏板段")
    return 0


def cmd_info(args) -> int:
    doc = _load(args.file)
    end = 0
    for e in doc.events:
        end = max(end, e.release_us if e.release_us is not None else e.onset_us)
    from ms_semantics import NOT_PROVIDED as NP
    np_count = sum(1 for e in doc.events if e.dynamics.state == NP)
    print(f"文件      {args.file}")
    print(f"琴数      {doc.piano_count}（{doc.constraint_mode}）")
    print(f"事件      {len(doc.events)}")
    print(f"踏板段    {len(doc.pedals)}")
    print(f"时长      {end / 1_000_000:.3f} s")
    print(f"力度缺失  {np_count}")
    kinds = sorted({p.kind for p in doc.pedals})
    if kinds:
        print(f"踏板种类  {', '.join(kinds)}")
    try:
        from ms_validate import pedal_diagnostics
        d = pedal_diagnostics(doc)
        if d["chains"]:
            print(f"踏板链    最长 {d['longest_chain_us'] / 1e6:.1f} s（{len(d['chains'])} 条）")
        print(f"发声总长  {d['sounding_us'] / 1e6:.1f} s（含踏板延长）")
        content = max(1, d["content_us"])
        if (d["longest_chain_us"] > 60_000_000
                and d["longest_chain_us"] >= 0.8 * content):
            print("提示      疑似整曲被串成一条踏板：抬脚间隙是否 <50ms"
                  "（<50ms 会被判为同一脚，声音一直按住）")
    except Exception as exc:  # noqa: BLE001
        print(f"踏板诊断  （跳过：{exc}）")
    return 0


def cmd_export(args) -> int:
    doc = _load(args.file)
    files, report = mm.write_midi_files(doc, time_base_us=args.time_base)
    if args.out:
        out = Path(args.out)
        if len(files) == 1:
            out.write_bytes(files[0])
            print(f"已写出 {out}（{len(files[0])} 字节）")
        else:
            stem = out.with_suffix("")
            for n, data in enumerate(files, 1):
                q = stem.with_name(f"{stem.name}_{n}").with_suffix(".mid")
                q.write_bytes(data)
                print(f"已写出 {q}（{len(data)} 字节）")
            print(f"共 {len(files)} 个文件（通道超 16 自动分文件）")
    else:
        sys.stdout.buffer.write(files[0])
    if report.get("realization"):
        print(f"⚠ 演奏收束：{len(report['realization'])} 项不可弹"
              f"（结构上合法，但一架琴做不到）")
        for v in report["realization"][:5]:
            print(f"    - {v}")
    if report["sustaining_note_offs"]:
        print(f"注意：{len(report['sustaining_note_offs'])} 个延音音在轨末强制收尾："
              f"{[r['id'] for r in report['sustaining_note_offs']]}")
    if report.get("playability"):
        print(f"⚠ 可演奏性：{len(report['playability'])} 项（结构合法但按机制弹不了）")
        for v in report["playability"][:5]:
            print(f"    - {v}")
    if report.get("channel_merged"):
        for g in report["channel_merged"]:
            print(f"合并：{g['group']} 的 {len(g['members'])} 个实例 → 通道 {g['channel'] + 1}")
    if report.get("files", 1) > 1:
        print(f"多文件：{report['files']} 个（每个最多 16 通道）")
    if report["not_provided_dynamics"]:
        print(f"注意：{len(report['not_provided_dynamics'])} 个音的力度未提供，按锚点 64 导出："
              f"{report['not_provided_dynamics']}")
    return 0


def cmd_serve(args) -> int:
    import ms_server as srv
    httpd = srv.serve(Path(args.root or ".").resolve(), port=args.port, host=args.host)
    print("浏览器打开上面的地址；Ctrl+C 退出")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("已退出")
    finally:
        httpd.server_close()
    return 0


def cmd_import(args) -> int:
    src = Path(args.file)
    if not src.exists():
        raise SystemExit(f"文件不存在：{args.file}")
    suffix = src.suffix.lower()
    if suffix in (".musicxml", ".xml", ".mxl") or args.format == "musicxml":
        import ms_import as mi
        doc, rep = mi.import_musicxml(src, default_bpm=args.tempo_bpm or 120.0,
                                      max_measures=args.max_measures)
        print(f"MusicXML 导入：{rep['measures']} 小节 / {rep['notes']} 音 / "
              f"{rep['chords']} 和弦 / tempo {rep['tempo_bpm']:g}")
    elif suffix in (".mid", ".midi") or args.format == "midi":
        import ms_import_midi as imi
        doc, rep = imi.import_midi(src.read_bytes())
        print(f"MIDI 导入：{rep['notes']} 音 / {rep['pedals']} 踏板段 / "
              f"{rep['pianos']} 台琴 / {rep['duration_s']:.2f}s")
    else:
        raise SystemExit(f"无法识别格式：{suffix}（用 --format musicxml|midi 指定）")

    for g in doc.gaps:
        print(f"  缺口 {g.get('code')}: {g.get('detail')}")
    out = args.out or str(src.with_suffix(".md"))
    if str(out).lower().endswith(".md"):
        import ms_md
        ms_md.save(doc, out)            # 写作格式：md 文档
    else:
        Path(out).write_text(mj.dumps(doc), encoding="utf-8")   # 旧档案：仅显式指定后缀时
    print(f"已写出 {out}（{len(doc.events)} 事件）")
    return 0


def cmd_s02_build(args) -> int:
    """MS → `.s02`（+ 可选报告）。"""
    import s02_io
    from ms_to_s02 import to_s02

    doc = _load(args.file)
    meter = _parse_meter(args.meter) or (4, 4)
    try:
        score, losses = to_s02(doc, time_base_us=args.time_base,
                               grid_units_per_quarter=args.grid,
                               time_beats=meter[0], time_beat_type=meter[1],
                               key_fifths=args.key_fifths, title=args.title or "")
    except ValueError as e:
        print(f"投影失败：{e}")
        return 1
    out = args.out or str(Path(args.file).with_suffix(".s02"))
    s02_io.save(score, out)
    print(f"已写出 {out}（音符 {len(score.notes)} · 动作 {len(score.actions)} · "
          f"曲线 {len(score.curves)} · 踏板 {len(score.pedal_marks)} · 段 {len(score.segments)}）")
    if losses:
        print(f"投影损失 {len(losses)} 条：")
        for l in losses[:10]:
            print(f"  {l.get('item', l.get('code'))}: {l.get('reason', l.get('detail', ''))}")
        if len(losses) > 10:
            print(f"  … 还有 {len(losses) - 10} 条")
    return 0


def cmd_s02_check(args) -> int:
    """校验 + 往返比对。"""
    import s02_io

    text = Path(args.file).read_text(encoding="utf-8")
    try:
        score = s02_io.parse(text)
    except s02_io.FormatError as e:
        print(f"读入失败：{e}")
        return 1
    back = s02_io.dump(score)
    ok = back == text
    print(f"{args.file}：音符 {len(score.notes)} · 动作 {len(score.actions)} · "
          f"曲线 {len(score.curves)} · 踏板 {len(score.pedal_marks)} · 段 {len(score.segments)}")
    print("往返：" + ("一致" if ok else f"不一致（{len(text)} → {len(back)} 字节）"))
    return 0 if ok else 1


def _load_score(path: str, time_base: int | None = None):
    """读 `.s02`；若给的是 `.md`（或旧档案），先投影（需 `--time-base`，不猜）。"""
    import s02_io

    p = Path(path)
    if p.suffix.lower() in {".md", ".ms"}:
        if not time_base:
            raise SystemExit("从乐谱投影需要 --time-base（µs / 四分音符），不猜时间基准")
        from ms_to_s02 import to_s02
        score, _losses = to_s02(_load(path), time_base_us=int(time_base))
        return score
    return s02_io.parse(p.read_text(encoding="utf-8"))


def cmd_s02_probe(args) -> int:
    """客观特征探针（零权重）：逐小节特征表 + ASCII 曲线。"""
    import json

    import s02_probe

    score = _load_score(args.file, getattr(args, "time_base", None))
    result = s02_probe.analyze(score, bars_per_window=args.window)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result["summary"], ensure_ascii=False))
        print(s02_probe.format_table(result, limit=args.limit))
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"已写出 {args.out}")
    return 0


def cmd_s02_index(args) -> int:
    """`.s02`（或 `.md`）→ `.s02x`（SQLite 索引：动机/关系/特征/段落）。"""
    import s02_index

    score = _load_score(args.file, getattr(args, "time_base", None))
    out = args.out or str(Path(args.file).with_suffix(".s02x"))
    if args.update and Path(out).exists():
        import s02_incremental
        res = s02_incremental.update(out, score)
        idx, st = res["index"], res["stats"]
        print(f"已增量更新 {out}")
        print(f"  复用 {st['lines_reused']} 条线 / 重算 {st['lines_rebuilt']} 条线"
              f" · 复用动机 {st['motifs_reused']}/{st['motifs_total']}")
    else:
        idx = s02_index.build(score)
        s02_index.save(idx, out, meta={"source": Path(args.file).name})
        print(f"已写出 {out}")
    lens = {}
    for m in idx["motifs"]:
        lens[m.length] = lens.get(m.length, 0) + 1
    print(f"  音符 {len(idx['notes'])} · 边 {len(idx['edges'])} · 动机 {len(idx['motifs'])}"
          f" · 特征 {len(idx['features'])}")
    if lens:
        print("  动机长度分布：" + "、".join(f"{k}音×{v}" for k, v in sorted(lens.items())))
    return 0


def cmd_s02_query(args) -> int:
    """查 `.s02x`：统计 / 动机列表 / 某音的动机 / 某动机的出现。"""
    import s02_index

    con = s02_index.open_index(args.file)
    if args.sections:
        for sid, a, b, label, notes, dens, tens, cent in s02_index.sections(con):
            print(f"{sid}  {a}–{b}  {label}  音{notes}  密度{dens}  张力{tens}  音区{cent}")
    elif args.at_bar is not None:
        row = s02_index.section_at(con, args.at_bar)
        print(f"第 {args.at_bar} 小节：{row}" if row else f"第 {args.at_bar} 小节：不在任何段")
    elif args.phrases:
        for pid, sec, a, b, why in s02_index.phrases(con, args.phrases if args.phrases != "all" else None):
            print(f"{pid}  {sec}  {a}–{b}  {why}")
    elif args.motifs:
        for mid, sig, length, count, nvar in s02_index.motifs(con):
            mark = f"  变体×{nvar}" if nvar else ""
            print(f"{mid}  {length}音  ×{count}  {sig}{mark}")
    elif args.variants:
        rows = s02_index.variants(con)
        if not rows:
            print("（没有变体）")
        for mid, trans, st, en, voice, bar in rows:
            print(f"{mid}  {trans}  {st}→{en}  {voice}  第{bar + 1}小节")
    elif args.motif_of:
        for row in s02_index.motif_of(con, args.motif_of):
            print(f"{row[0]}  {row[2]}→{row[3]}  移调={row[4]:+d}  {row[1]}")
    elif args.occurrences:
        for row in s02_index.occurrences(con, args.occurrences):
            print(f"{row[0]}→{row[1]}  移调={row[2]:+d}  {row[3]}  第{row[4] + 1}小节")
    else:
        print(s02_index.to_json(con))
    return 0


def cmd_s02_segment(args) -> int:
    """分段 + 句读 + 标签（规则层，阈值来自 s02_weights）。"""
    import json

    import s02_segment
    import s02_weights as wt

    score = _load_score(args.file, getattr(args, "time_base", None))
    cfg = wt.load(args.weights)
    res = s02_segment.segment(score, weights=cfg)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(s02_segment.to_text(res))
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"已写出 {args.out}")
    return 0


def cmd_s02_report(args) -> int:
    """生成 `.report.md` 五层报告。"""
    import s02_index
    import s02_report
    import s02_weights as wt

    score = _load_score(args.file, getattr(args, "time_base", None))
    con = s02_index.open_index(args.index) if args.index else None
    text = s02_report.build(score, index=con, weights=wt.load(args.weights),
                            title=args.title or "")
    out = args.out or str(Path(args.file).with_suffix(".report.md"))
    Path(out).write_text(text, encoding="utf-8")
    print(f"已写出 {out}（{len(text.splitlines())} 行）")
    return 0


def cmd_s02_baseline(args) -> int:
    """基线分布：多首曲子跑同一套特征 → JSON + 汇总表。"""
    import s02_baseline

    rows = s02_baseline.run(args.files, args.out, time_base_us=args.time_base)
    for r in rows:
        print(f"{r['name']}: {r['notes']} 音 / {r['sections']} 段 / 密度μ {r['density_mean']}"
              f" / 重复率 {r['repeat_ratio']:.0%}")
    print(f"已写出 {Path(args.out) / 'summary.md'}（{len(rows)} 首）")
    return 0


def cmd_s02_fingers(args) -> int:
    """指法/物理可行性：够不够得着、来不来得及。"""
    import json

    import s02_fingering
    import s02_weights as wt

    score = _load_score(args.file, getattr(args, "time_base", None))
    res = s02_fingering.analyze(score, weights=wt.load(args.weights))
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        o = res["overall"]
        print(f"最大跨度 {o['max_span']} 半音（上限 {o['span_limit']:.0f}）· "
              f"最大手位移动 {o['max_jump']:.1f} · 超限窗口 {o['stretch_bars']}")
        print("win  跨度  移动  难度  结论")
        print("---  ----  ----  ----  ----")
        for w in res["hard_bars"][:args.limit]:
            print(f"{w['window']:3d}  {w['hand_span']:4d}  {w['hand_jump']:4.1f}  "
                  f"{w['hard']:4.2f}  {s02_fingering.label(w)}")
        if len(res["hard_bars"]) > args.limit:
            print(f"… 还有 {len(res['hard_bars']) - args.limit} 个")
        if not res["hard_bars"]:
            print("（全部够得着、来得及）")
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"已写出 {args.out}")
    return 0


def cmd_s02_perturb(args) -> int:
    """局部扰动：力度偏移 / 调外音 / 音区突变 / 密度突变。"""
    import json

    import s02_perturb
    import s02_weights as wt

    score = _load_score(args.file, getattr(args, "time_base", None))
    res = s02_perturb.analyze(score, weights=wt.load(args.weights))
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        o = res["overall"]
        print(f"扰动 {o['events']} 处（突强 {o['by_kind']['accent']} · 调外音 "
              f"{o['by_kind']['chromatic']} · 音区 {o['by_kind']['register']} · 密度 "
              f"{o['by_kind']['density']}）· 推断调式 {','.join(o['scale'])}")
        print("类型  小节  强度  说明")
        print("----  ----  ----  ----")
        for e in res["events"][:args.limit]:
            print(f"{s02_perturb.label(e):4s}  {e['window']:4d}  {e['strength']:4.2f}  {e['detail']}")
        if len(res["events"]) > args.limit:
            print(f"… 还有 {len(res['events']) - args.limit} 处")
        if not res["events"]:
            print("（没有检出扰动）")
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"已写出 {args.out}")
    return 0


def cmd_s02_score(args) -> int:
    """连续维度打分（紧张/推进/留白/明亮）+ 反权重建议。"""
    import json

    import s02_score
    import s02_segment
    import s02_weights as wt

    cfg = wt.load(args.weights)
    score = _load_score(args.file, getattr(args, "time_base", None))
    seg = s02_segment.segment(score, weights=cfg)
    res = s02_score.analyze_sections(score, seg["sections"], weights=cfg)

    target = {}
    if args.target:
        for part in args.target.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                target[k.strip()] = float(v)

    if args.json:
        payload = {"sections": res["sections"]}
        if target:
            cur = res["sections"][0] if res["sections"] else {}
            payload["suggest"] = s02_score.suggest(target, {
                "density": cur.get("drive", 0) and cur.get("drive"), "centroid": 64.0},
                res["cfg"]) if res["sections"] else {}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("段   小节      标签       紧张   推进   留白   明亮")
        print("---  --------  --------   ----   ----   ----   ----")
        for x in res["sections"]:
            print(f"{x['id']}   {x['start_bar']:2d}–{x['end_bar']:3d}     "
                  f"{str(x['label']):8s}   {x['tension']:.3f}  {x['drive']:.3f}  "
                  f"{x['space']:.3f}  {x['bright']:.3f}")
        if target:
            cur = res["sections"][0] if res["sections"] else {"drive": 0.5}
            sug = s02_score.suggest(target, {"density": 8.0, "centroid": 64.0,
                                             "tension_raw": 0.3}, res["cfg"])
            print("\n反权重建议：" + s02_score.explain(sug))
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"已写出 {args.out}")
    return 0


def cmd_s02_capability(args) -> int:
    """演奏能力覆盖：可用的转折/踏板/曲线，哪些没用，怎么写。"""
    import json

    import s02_capability

    doc = _load(args.file)
    rep = s02_capability.analyze(doc)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    s = rep["summary"]
    print(f"乐器 {s['instrument_count']} 件 · 发声机制 {s['mechanism_count']} 种"
          f"（{'、'.join(s['mechanisms']) or '—'}）")
    print(f"转折 {s['turns']} · 踏板段 {s['pedals']} · 曲线 {s['curves']}")
    if s["gaps"]:
        print("\n明显空着的维度：")
        for g in s["gaps"]:
            print(f"  · {g}")
    for inst in rep["instruments"]:
        if inst.get("error"):
            print(f"\n{inst['id']} {inst['type']}：{inst['error']}")
            continue
        u = inst["unused"]
        print(f"\n{inst['id']} {inst['type']}（{inst['mechanism']}，音域 {inst['range']}）")
        print(f"  已用：转折 {inst['used']['turns'] or '无'} · 踏板 {inst['used']['pedals'] or '无'}"
              f" · 曲线 {inst['used']['curves'] or '无'}")
        if u["turns"]:
            print(f"  可用未用转折：{'、'.join(u['turns'][:8])}")
        if u["pedals"]:
            print(f"  可用未用踏板：{'、'.join(u['pedals'])}")
        if u["curves"]:
            print(f"  可用未用曲线：{'、'.join(u['curves'])}")
        if inst["hints"] and args.hints:
            print("  写法示例：")
            for h in inst["hints"][:6]:
                print(f"    [{h['kind']}] {h['name']}：{h['how']}")
    print("\n（能力覆盖 ≠ 质量分；奏法/装饰音不单独存在 MS 里，只能给可用清单与写法。）")
    return 0


def cmd_s02_instruments(args) -> int:
    """列出可用乐器（外部 AI 最常问"我有哪些乐器"）。"""
    import s02_capability

    rows = s02_capability.available_instruments(family=args.family)
    for r in rows:
        ped = "/".join(r["pedals"]) if r["pedals"] else "-"
        print(f"{r['type']:34s} {str(r['family']):12s} {str(r['mechanism']):14s} "
              f"{str(r['range']):10s} poly={r['poly']} 踏板={ped}")
    print(f"共 {len(rows)} 种")
    return 0


def cmd_s02_quality(args) -> int:
    """结构质量：不需要审美评分的那套指标。"""
    import json

    import s02_api
    import s02_quality
    import s02_weights as wt

    score = _load_score(args.file, getattr(args, "time_base", None))
    payload = s02_api.build_payload(score, weights=wt.load(args.weights))
    # 没给 .s02x 时临时建一份内存索引，让"动机发展"这项也能算（约 0.2s）
    if not payload.get("motifs"):
        import s02_index
        idx = s02_index.build(score)
        payload["motifs"] = [{"id": m.id, "length": m.length, "count": m.count}
                             for m in idx["motifs"]]
        payload["variants"] = [{"motif": v[0], "transform": v[1]} for v in idx["variants"]]
    q = s02_quality.analyze(payload)
    if args.json:
        print(json.dumps(q, ensure_ascii=False, indent=2))
        return 0
    print(f"结构测量（不是评分）· 覆盖 {q['coverage']:.0%} · 置信 {q['confidence']}")
    print("指标            测量值  说明")
    for k, v in q["metrics"].items():
        print(f"  {k:14s} {v:5.2f}  {q['explain'].get(k, '')}")
    if q["missing"]:
        print("未计算：" + "、".join(q["missing"]) + "（数据不足，单声部/段落过少等）")
    print("注意：这些是测量值，不是评分；跨曲比较请用 `s02 compare`（分位）。")
    return 0


def cmd_s02_compare(args) -> int:
    """与参照集比较：每项指标给本曲值 + 分位（不给分）。"""
    import json

    import s02_compare

    score = _load_score(args.file, getattr(args, "time_base", None))
    import s02_api
    mine = s02_compare._metrics_of(score)

    if args.batch:
        import msflow
        lib = Path(args.library) if args.library else msflow.LIBRARY
        refs = s02_compare.refs_from_batch(lib / "batches" / args.batch)
    elif args.refs:
        refs = s02_compare.refs_from_dir(args.refs)
    else:
        print("要给参照：--refs <目录> 或 --batch <批次名>")
        return 2

    res = s02_compare.compare(mine, refs)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(s02_compare.to_text(res))
    return 0


def cmd_s02_calibrate(args) -> int:
    """用参照曲目校准 `[score]` 与 `[label]` 阈值（不覆盖默认值）。"""
    import s02_calibrate
    import s02_weights as wt

    scores = []
    for f in args.files:
        scores.append(_load_score(f, args.time_base))
    if not scores:
        print("没有可用的参照曲目")
        return 1
    collected = s02_calibrate.collect(scores)
    derived = s02_calibrate.derive(collected)
    out = args.out or "weights.calibrated.toml"
    s02_calibrate.write_toml(derived, out, meta={
        "samples": derived["stats"]["samples"], "pieces": derived["stats"]["pieces"]})
    print(f"已写出 {out}（{derived['stats']['pieces']} 首 / {derived['stats']['samples']} 窗口）")
    print("  density: low {} / high {}".format(derived["label"]["density_low"],
                                               derived["label"]["density_high"]))
    print("  tension: low {} / high {}".format(derived["label"]["tension_low"],
                                               derived["label"]["tension_high"]))
    if args.report:
        text = s02_calibrate.report(derived, current=wt.load(), path=args.report)
        print(f"已写出 {args.report}（{len(text.splitlines())} 行）")
    return 0


def cmd_s02_render(args) -> int:
    """S02 矢量分析图：段落带 + 维度曲线 + 扰动标记。"""
    import s02_io
    import s02_render

    score = _load_score(args.file, getattr(args, "time_base", None))
    svg = s02_render.render(score, title=args.title or "")
    out = args.out or str(Path(args.file).with_suffix(".analysis.svg"))
    Path(out).write_text(svg, encoding="utf-8")
    print(f"已写出 {out}（{len(svg)} 字节）")
    return 0


def cmd_s02_api(args) -> int:
    """S02 JSON 视图（前端用）。"""
    import json

    import s02_api

    data = s02_api.payload(args.file, s02x_path=args.index,
                           weights=args.weights, with_notes=args.notes)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写出 {args.out}（{len(text)} 字节）")
    else:
        print(text)
    return 0


def cmd_s02_patch(args) -> int:
    """补丁：默认 dry-run（只打印 diff 与 MS 提示），`--apply` 才写出新 `.s02`。"""
    import s02_io
    import s02_patch

    score = s02_io.parse(Path(args.file).read_text(encoding="utf-8"))
    try:
        patch = s02_patch.parse(Path(args.patch).read_text(encoding="utf-8-sig"))
    except s02_patch.PatchError as e:
        print(f"补丁格式不合法：{e}")
        return 1
    try:
        new, changes = s02_patch.apply(score, patch)
    except s02_patch.PatchError as e:
        print(f"补丁被拒绝：{e}")
        return 1
    print(f"改动 {len(changes)} 处：")
    print(s02_patch.diff_text(changes))
    print("\nMS 侧的落地提示（需人工评审，本工具不自动改 .md）：")
    for h in s02_patch.to_ms_hints(changes):
        print("  " + h)
    if args.apply:
        out = args.out or str(Path(args.file).with_suffix(".patched.s02"))
        s02_io.save(new, out)
        print(f"\n已写出 {out}（仅为提案，MS 仍未改）")
    else:
        print("\n（dry-run：未写出任何文件；确认后加 --apply 生成提案 .s02）")
    return 0


def cmd_s02_bench(args) -> int:
    """性能基线：跑一遍各层，输出 markdown 表。"""
    import json

    import ms_io
    import s02_bench

    rows = []
    for f in args.files:
        rows.append({**s02_bench.bench_doc(ms_io.load(Path(f)), time_base_us=args.time_base),
                     "file": Path(f).name})
    text = s02_bench.to_markdown(rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写出 {args.out}")
        print(text)
    else:
        print(text)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"已写出 {args.json}")
    return 0


def cmd_s02_diff(args) -> int:
    """改前改后对比：音符级 + 结构级 + 窗口级。"""
    import json

    import s02_diff

    a = _load_score(args.old, getattr(args, "time_base", None))
    b = _load_score(args.new, getattr(args, "time_base", None))
    diff = s02_diff.compare(a, b, top=args.top)
    text = s02_diff.to_markdown(diff, title=args.title or "")
    if args.json:
        out = args.json if args.json is not True else str(Path(args.new).with_suffix(".diff.json"))
        Path(out).write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写出 {out}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写出 {args.out}（{len(text.splitlines())} 行）")
    else:
        print(text)
    return 0


def cmd_audio(args) -> int:
    """渲染音频（wav），改完谱能立刻听。"""
    import time

    import make_audio

    t0 = time.time()
    doc = _load(args.file)
    samples = make_audio.render(doc, tail=args.tail)
    out = Path(args.out or Path(args.file).with_suffix(".wav"))
    make_audio.write_wav(samples, out)
    secs = len(samples) / make_audio.SR
    print(f"已写出 {out}（{secs:.1f} 秒音频，渲染 {time.time() - t0:.1f}s"
          f"，{out.stat().st_size / 1e6:.1f} MB）")
    return 0


def cmd_s02_refs(args) -> int:
    """参照曲目库：登记 / 列表 / 校准（含留一法稳定性）。"""
    import json

    import s02_refs

    root = args.root or None
    if args.add:
        for f in args.add:
            e = s02_refs.add(f, title="", root=root, time_base_us=args.time_base)
            print(f"已登记 {e['file']}（{e.get('notes')} 事件）")
    if args.list or (not args.add and not args.calibrate):
        rows = s02_refs.list_pieces(root)
        if not rows:
            print("（还没有登记参照曲目；用 s02 refs --add <file.md>）")
        for r in rows:
            mark = "" if r["exists"] else "  ⚠ 文件缺失"
            print(f"{r['file']:28s} {r.get('title', ''):16s} {r.get('added', '')}{mark}")
    if args.calibrate:
        res = s02_refs.calibrate(root=root, time_base_us=args.time_base)
        print(f"已校准：{res['pieces']} 首 / {res['samples']} 窗口")
        print(f"  密度 {res['label']['density_low']}/{res['label']['density_high']}"
              f" · 张力 {res['label']['tension_low']}/{res['label']['tension_high']}")
        print(f"  留一法最大漂移：密度 {res['loo_max_drift']['density']}"
              f"（{res['loo_max_drift']['density_rel']:.0%}）、"
              f"张力 {res['loo_max_drift']['tension']}")
        print(f"  判断：{res['verdict']}")
        print(f"  版本：{res['versioned']}")
        print(f"  最新：{res['latest']}")
        print(f"  报告：{res['report']}")
        if args.json:
            Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
            print(f"  明细：{args.json}")
    return 0


def cmd_flow(args) -> int:
    """工具链协议：flow run / check / list。"""
    import json

    import msflow

    lib = Path(args.library) if args.library else None
    if args.flow_cmd == "batch":
        res = msflow.batch(args.dir, pattern=args.pattern, tag=args.tag or "",
                           work_root=lib, time_base_us=args.time_base,
                           audio=args.audio)
        print(f"批次 {res['tag']}：成功 {res['count']} · 失败 {res['failed_count']}")
        for r in res["runs"]:
            cov = r.get("coverage")
            print(f"  {r['run_id']:34s} 指标覆盖={'—' if cov is None else f'{cov:.0%}'} "
                  f"({r['total_ms']:.0f} ms)")
        for f in res["failed"]:
            print(f"  失败 {f['source']}：{f['error']}")
        print(f"索引：{res['index_path']}")
        return 0 if res["failed_count"] == 0 else 1
    if args.flow_cmd == "run":
        weights = None
        if args.weights:
            import s02_weights as wt
            weights = wt.load(args.weights)
        res = msflow.run(args.file, time_base_us=args.time_base, work_root=lib,
                         audio=args.audio, title=args.title or "", weights=weights)
        print(f"run_id：{res['run_id']}")
        print(f"目录：{res['run_dir']}")
        for s in res["steps"]:
            print(f"  {s['name']:8s} ok  {s['ms']:8.1f} ms")
        print(f"总耗时 {res['total_ms']:.0f} ms · 特征 {len(res['features'])} 维")
        chk = msflow.check(res["run_dir"], work_root=lib)
        print("协议自检：" + ("通过" if chk["ok"] else "不通过·" + "；".join(chk["problems"])))
        return 0 if chk["ok"] else 1
    if args.flow_cmd == "check":
        chk = msflow.check(args.target, work_root=lib)
        print(json.dumps(chk, ensure_ascii=False, indent=2))
        return 0 if chk["ok"] else 1
    if args.flow_cmd == "list":
        rows = msflow.list_runs(lib)
        if not rows:
            print("（还没有 run；用 flow run <piece.md>）")
        for r in rows:
            score = "-" if r.get("overall") is None else f"{r['overall']:.2f}"
            print(f"{r['run_id']:34s} {r.get('created', '')[:19]:19s} "
                  f"notes={str(r.get('notes')):6s} score={score}")
        return 0
    print("未知子命令")
    return 2


def cmd_taste(args) -> int:
    """品味学习：rate / train / predict / stats。"""
    import json

    import msflow
    import s02_taste

    lib = Path(args.library) if args.library else msflow.LIBRARY
    ds = lib / "dataset.jsonl"
    models = lib / "models"

    if args.taste_cmd == "rate":
        dims = {}
        if args.dims:
            for part in args.dims.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    dims[k.strip()] = float(v)
        row = s02_taste.rate(ds, args.run_id, overall=args.overall, dims=dims,
                             scorer=args.scorer, model=args.model, note=args.note)
        print(f"已评分 {args.run_id}：overall={row['overall']} "
              f"scorer={args.scorer} dims={row['dims']}")
        n = len(s02_taste.rated(s02_taste.load_dataset(ds)))
        print(f"数据集已评 {n} 条（最小训练样本默认 12）")
        return 0

    if args.taste_cmd == "train":
        rows = s02_taste.load_dataset(ds)
        model = s02_taste.train(rows, min_samples=args.min, alpha=args.alpha)
        if model.get("insufficient"):
            print("样本不足，未训练：" + model["reason"])
            print("（继续 flow run + taste rate 积累；达到样本数再跑一次）")
            return 1
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        out = models / f"taste-{stamp}.json"
        s02_taste.save_model(model, out)
        latest = models / "taste.latest.json"
        latest.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已训练：{model['samples']} 样本 / {len(model['features'])} 特征")
        print(f"  留一法 R² = {model['metrics']['loo_r2']:.3f}"
              f" · MAE = {model['metrics']['loo_mae']:.3f}")
        print(f"  模型：{out}")
        print(f"  最新：{latest}")
        return 0

    if args.taste_cmd == "predict":
        mp = args.model_file or (models / "taste.latest.json")
        if not Path(mp).exists():
            print(f"没有模型：{mp}（先 taste train）")
            return 1
        model = s02_taste.load_model(mp)
        if args.target.endswith(".s02"):
            import s02_api
            payload = s02_api.payload(args.target)
        else:
            rd = lib / "runs" / args.target
            payload = json.loads((rd / "analysis.json").read_text(encoding="utf-8"))
        feats = s02_taste.features_of(payload)
        res = s02_taste.predict(model, feats)
        print(f"预估品味分：{res['score']:.3f}（模型样本 {model['samples']}，"
              f"LOO R²={model['metrics']['loo_r2']:.2f}）")
        print("主要贡献：")
        for c in res["contributions"][:8]:
            print(f"  {c['feature']:14s} 值={c['value']:<10.3f} 贡献={c['contrib']:+.4f}")
        return 0

    if args.taste_cmd == "stats":
        rows = s02_taste.load_dataset(ds)
        st = s02_taste.stats(rows)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        latest = models / "taste.latest.json"
        if latest.exists():
            m = s02_taste.load_model(latest)
            print(f"当前模型：样本 {m['samples']} · LOO R² {m['metrics']['loo_r2']:.3f}"
                  f" · MAE {m['metrics']['loo_mae']:.3f}")
        else:
            print("当前没有模型（taste train）")
        return 0
    print("未知子命令")
    return 2


def cmd_ms(args) -> int:
    """MS 包入口：能力菜单 / 脚手架 / 校验+踏板诊断。"""
    import json as _json

    import ms as MS

    action = getattr(args, "mscmd", None)
    if action == "catalog":
        data = MS.catalog(family=getattr(args, "family", None),
                          type_code=getattr(args, "type_code", None))
        if getattr(args, "json", False):
            print(_json.dumps(data, ensure_ascii=False, indent=2))
        elif getattr(args, "markdown", False) or getattr(args, "type_code", None):
            print(MS.markdown(family=getattr(args, "family", None)))
        else:
            c = data["count"]
            print(f"乐器能力菜单（{MS.VERSION}）：{c['types']} 个类型 · "
                  f"{c['families']} 个族 · {c['turn_kinds']} 种演奏转折")
            print("族：" + "、".join(f"{k}({len(v)})" for k, v in data["families"].items()))
            print("加 --markdown 看全表；加 --type violin 看单件乐器；加 --json 给程序用")
        return 0
    if action == "menu":
        print(MS.menu())
        return 0
    if action == "schema":
        if args.json:
            print(_json.dumps(MS.schema(), ensure_ascii=False, indent=2))
        else:
            print(MS.schema_text())
        return 0
    if action == "package":
        import json as _json3
        spec = _json3.loads(Path(args.spec).read_text(encoding="utf-8"))
        info = MS.package(spec, args.out, slug=args.slug)
        print("已生成产物文件夹：", info["folder"])
        for k in ("mid", "wav", "png", "abc"):
            v = info.get(k)
            if not v:
                continue
            pth = Path(v)
            print(f"  {pth.name:24s} {pth.stat().st_size:>12,d} 字节")
        print("  摘要：", info["summary"])
        return 0
    if action == "score":
        import json as _json2

        spec = _json2.loads(Path(args.spec).read_text(encoding="utf-8"))
        song = MS.build(spec, title=getattr(args, "title", "") or "")
        if args.abc:
            Path(args.abc).write_text(song.export_abc(), encoding="utf-8")
            print(f"已导出 ABC：{args.abc} · {song.summary()}")
            return 0
        if args.staff:
            Path(args.staff).write_text(song.export_staff(), encoding="utf-8")
            print(f"已导出五线谱：{args.staff} · {song.summary()}")
            return 0
        if args.audio:
            song.export_wav(args.audio)
            print(f"已导出音频：{args.audio} · {song.summary()}")
            return 0
        print(MS.cheatsheet())
        print("\n摘要：", song.summary())
        return 0
    if action == "export":
        doc = _load(args.file)
        if args.abc:
            text = MS.export_abc(doc, title=args.title or "",
                                 bpm=args.bpm or 120.0)
            Path(args.abc).write_text(text, encoding="utf-8")
            print(f"已导出 ABC：{args.abc}（{len(text.splitlines())} 行）")
            return 0
        if args.staff:
            svg = MS.export_staff(doc)
            Path(args.staff).write_text(svg, encoding="utf-8")
            print(f"已导出五线谱 SVG：{args.staff}（{len(svg)} 字节）")
            return 0
        print("导出格式：--abc <out.abc> 或 --staff <out.svg>")
        return 2
    if action == "check":
        doc = _load(args.file)
        errs = MS.validate(doc)
        d = MS.pedal_diagnostics(doc)
        print(f"文件 {args.file}：{'合法' if not errs else f'{len(errs)} 个问题'}")
        for e in errs[:40]:
            print("  " + e)
        if d["chains"]:
            print(f"踏板链 {len(d['chains'])} 条，最长 {d['longest_chain_us'] / 1e6:.1f}s")
        print(f"发声总长 {d['sounding_us'] / 1e6:.1f}s（含踏板延长）")
        return 0 if not errs else 1
    if action == "new":
        try:
            w = MS.Writer(bpm=args.bpm)
        except AttributeError:
            print("外部版不提供写谱脚手架：请写任务 JSON，用 ms score 导出")
            return 2
        codes = [c.strip() for c in args.instruments.split(",") if c.strip()]
        for c in codes:
            w.instrument(c)
        # 每件乐器写一个长音（示例），钢琴若能踩踏板就踩一小节
        for iid in range(1, len(codes) + 1):
            w.note(iid, pitch="C4", beat=0, beats=args.beats_per_bar * args.bars,
                   level="mf")
        if "sustain" in w.pedals(1):
            w.pedal(1, "sustain", 0, args.beats_per_bar * args.bars)
        try:
            import ms_md
            text = ms_md.dumps_authoring(w.doc(), bpm=w.bpm, meter=w.meter)
        except Exception:
            print("脚手架生成失败：请改用 ms export --abc / --staff 导出")
            return 2
        # 默认只打印文本：.md 是写作格式，不默认落文件
        if not (args.out and getattr(args, "allow_write", False)):
            print(text)
            print("# ↑ 以上是脚手架文本（未写文件）。确需落盘时："
                  "加 --out <路径.md> --allow-write", file=sys.stderr)
            return 0
        w.save(args.out)
        print(f"已写出脚手架 {args.out}（显式 --allow-write）")
        print(w.menu())
        return 0
    print("未知 ms 子命令")
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mscli", description="pianomusic MS 命令行")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="校验 .md（文档写法）")
    v.add_argument("file")
    v.set_defaults(func=cmd_validate)

    i = sub.add_parser("info", help="摘要")
    i.add_argument("file")
    i.set_defaults(func=cmd_info)


    e = sub.add_parser("export", help="导出 MIDI")
    e.add_argument("file")
    e.add_argument("-o", "--out")
    e.add_argument("--time-base", type=int, dest="time_base", required=True,
                   help="µs / 四分音符（必填，否则无法把微秒换成 tick）")
    e.set_defaults(func=cmd_export)

    au = sub.add_parser("audio", help="渲染 WAV（改完谱直接听）")
    au.add_argument("file")
    au.add_argument("-o", "--out")
    au.add_argument("--tail", type=float, default=0.8, help="结尾留白秒数")
    au.set_defaults(func=cmd_audio)

    s = sub.add_parser("serve", help="启动本地编辑器（HTML 单页 + API）")
    s.add_argument("--root", default=None, help="数据根目录（默认当前目录）")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    s.set_defaults(func=cmd_serve)

    i = sub.add_parser("import", help="导入 MusicXML / MIDI → .md")
    i.add_argument("file")
    i.add_argument("-o", "--out")
    i.add_argument("--format", choices=("musicxml", "midi"))
    i.add_argument("--tempo-bpm", type=float, dest="tempo_bpm")
    i.add_argument("--max-measures", type=int, dest="max_measures")
    i.set_defaults(func=cmd_import)

    s02 = sub.add_parser("s02", help="S02：投影 / 校验 / 特征探针")
    s02sub = s02.add_subparsers(dest="s02cmd", required=True)

    b = s02sub.add_parser("build", help="MS → .s02")
    b.add_argument("file")
    b.add_argument("-o", "--out")
    b.add_argument("--time-base", type=int, dest="time_base", required=True,
                   help="µs / 四分音符（必填）")
    b.add_argument("--grid", type=int, default=480, help="每四分音符的网格数（默认 480）")
    b.add_argument("--meter", help="拍号，如 4/4（默认 4/4）")
    b.add_argument("--key-fifths", type=int, dest="key_fifths", default=0)
    b.add_argument("--title", default="")
    b.set_defaults(func=cmd_s02_build)

    c = s02sub.add_parser("check", help="校验 .s02 并做往返比对")
    c.add_argument("file")
    c.set_defaults(func=cmd_s02_check)

    pr = s02sub.add_parser("probe", help="逐小节特征（零权重）")
    pr.add_argument("file")
    pr.add_argument("--window", type=int, default=1, help="每几个小节算一个窗口（默认 1）")
    pr.add_argument("--limit", type=int, default=40, help="表格最多显示多少窗口")
    pr.add_argument("--json", action="store_true", help="输出完整 JSON")
    pr.add_argument("-o", "--out", help="把 JSON 写到文件")
    pr.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    pr.set_defaults(func=cmd_s02_probe)

    ix = s02sub.add_parser("index", help=".s02 → .s02x（动机/关系/特征索引）")
    ix.add_argument("file")
    ix.add_argument("-o", "--out")
    ix.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    ix.add_argument("--update", action="store_true",
                    help="已有 .s02x 时按旋律线增量更新（只重算改过的线）")
    ix.set_defaults(func=cmd_s02_index)

    q = s02sub.add_parser("query", help="查 .s02x（统计/动机/某音/某动机）")
    q.add_argument("file")
    q.add_argument("--motifs", action="store_true", help="列动机")
    q.add_argument("--variants", action="store_true", help="列变体（倒影/逆行/节奏变形）")
    q.add_argument("--sections", action="store_true", help="列段落（含标签）")
    q.add_argument("--phrases", nargs="?", const="all", help="列句读（可给段号）")
    q.add_argument("--at-bar", dest="at_bar", type=int, help="第几小节属于哪段")
    q.add_argument("--motif-of", dest="motif_of", help="某音落在哪些动机里")
    q.add_argument("--occurrences", help="某动机的所有出现")
    q.add_argument("--stats", action="store_true", help="统计（默认）")
    q.set_defaults(func=cmd_s02_query)

    sg = s02sub.add_parser("segment", help="分段/句读/标签（规则层）")
    sg.add_argument("file")
    sg.add_argument("--weights", help="权重 TOML（默认内置）")
    sg.add_argument("--json", action="store_true")
    sg.add_argument("-o", "--out", help="把 JSON 写到文件")
    sg.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    sg.set_defaults(func=cmd_s02_segment)

    rp = s02sub.add_parser("report", help="生成 .report.md 五层报告")
    rp.add_argument("file")
    rp.add_argument("-o", "--out")
    rp.add_argument("--index", help="可选 .s02x（带上动机表）")
    rp.add_argument("--weights", help="权重 TOML（默认内置）")
    rp.add_argument("--title", default="")
    rp.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    rp.set_defaults(func=cmd_s02_report)

    ba = s02sub.add_parser("baseline", help="多首曲子跑同一套特征（基线分布）")
    ba.add_argument("out", help="输出目录")
    ba.add_argument("files", nargs="+", help="输入 .md")
    ba.add_argument("--time-base", type=int, dest="time_base", required=True,
                    help="µs / 四分音符（必填）")
    ba.set_defaults(func=cmd_s02_baseline)

    fg = s02sub.add_parser("fingers", help="指法/物理可行性（跨度/手位移动）")
    fg.add_argument("file")
    fg.add_argument("--weights", help="权重 TOML（默认内置）")
    fg.add_argument("--limit", type=int, default=20)
    fg.add_argument("--json", action="store_true")
    fg.add_argument("-o", "--out", help="把 JSON 写到文件")
    fg.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    fg.set_defaults(func=cmd_s02_fingers)

    pb = s02sub.add_parser("perturb", help="局部扰动（突强/调外音/音区/密度）")
    pb.add_argument("file")
    pb.add_argument("--weights", help="权重 TOML（默认内置）")
    pb.add_argument("--limit", type=int, default=20)
    pb.add_argument("--json", action="store_true")
    pb.add_argument("-o", "--out", help="把 JSON 写到文件")
    pb.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    pb.set_defaults(func=cmd_s02_perturb)

    sc = s02sub.add_parser("score", help="连续维度打分（紧张/推进/留白/明亮）")
    sc.add_argument("file")
    sc.add_argument("--weights", help="权重 TOML（默认内置）")
    sc.add_argument("--target", help="反权重目标，如 drive=0.9,tension=0.8")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("-o", "--out", help="把 JSON 写到文件")
    sc.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    sc.set_defaults(func=cmd_s02_score)

    cmp = s02sub.add_parser("compare", help="与参照集比较（分位，不给分）")
    cmp.add_argument("file")
    cmp.add_argument("--refs", help="参照目录（.md / .s02）")
    cmp.add_argument("--batch", help="inbox/batches 下的批次名")
    cmp.add_argument("--library", help="数据目录")
    cmp.add_argument("--json", action="store_true")
    cmp.add_argument("--time-base", type=int, dest="time_base",
                     help="输入 .md 时必填（µs / 四分音符）")
    cmp.set_defaults(func=cmd_s02_compare)

    cp = s02sub.add_parser("capability", help="演奏能力覆盖（可用 vs 已用 + 写法）")
    cp.add_argument("file")
    cp.add_argument("--json", action="store_true")
    cp.add_argument("--hints", action="store_true", help="显示写法示例")
    cp.set_defaults(func=cmd_s02_capability)

    ins = s02sub.add_parser("instruments", help="列出可用乐器（类型/机制/音域）")
    ins.add_argument("--family", help="只列某个族（piano/strings/reed/brass…）")
    ins.set_defaults(func=cmd_s02_instruments)

    ql = s02sub.add_parser("quality", help="结构质量指标（不需要审美评分）")
    ql.add_argument("file")
    ql.add_argument("--weights", help="权重 TOML")
    ql.add_argument("--json", action="store_true")
    ql.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    ql.set_defaults(func=cmd_s02_quality)

    ca = s02sub.add_parser("calibrate", help="用参照曲目校准阈值（分位数）")
    ca.add_argument("files", nargs="+", help="参照曲目（.md 或 .s02）")
    ca.add_argument("-o", "--out", help="输出 weights.calibrated.toml")
    ca.add_argument("--report", help="输出校准对比报告 .md")
    ca.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    ca.set_defaults(func=cmd_s02_calibrate)

    rd2 = s02sub.add_parser("render", help="矢量分析图（段落带/维度曲线/扰动）")
    rd2.add_argument("file")
    rd2.add_argument("-o", "--out")
    rd2.add_argument("--title", default="")
    rd2.add_argument("--time-base", type=int, dest="time_base",
                     help="输入 .md 时必填（µs / 四分音符）")
    rd2.set_defaults(func=cmd_s02_render)

    ap = s02sub.add_parser("api", help="S02 JSON 视图（前端用）")
    ap.add_argument("file")
    ap.add_argument("--index", help="可选 .s02x")
    ap.add_argument("--weights", help="权重 TOML")
    ap.add_argument("--notes", action="store_true", help="附带逐音符数据")
    ap.add_argument("-o", "--out")
    ap.set_defaults(func=cmd_s02_api)

    pt = s02sub.add_parser("patch", help="补丁 dry-run（+ --apply 生成提案）")
    pt.add_argument("file", help="基础 .s02")
    pt.add_argument("patch", help="补丁 .json")
    pt.add_argument("--apply", action="store_true", help="写出提案 .s02（MS 仍不改）")
    pt.add_argument("-o", "--out")
    pt.set_defaults(func=cmd_s02_patch)

    bn = s02sub.add_parser("bench", help="性能基线（各层耗时表）")
    bn.add_argument("files", nargs="+", help="输入 .md")
    bn.add_argument("-o", "--out", help="把 markdown 表写到文件")
    bn.add_argument("--json", help="把原始数字写到 JSON")
    bn.add_argument("--time-base", type=int, dest="time_base", default=500000,
                    help="µs / 四分音符（默认 500000）")
    bn.set_defaults(func=cmd_s02_bench)

    df = s02sub.add_parser("diff", help="改前改后对比（音符/结构/窗口）")
    df.add_argument("old", help="旧版（.s02 或 .md）")
    df.add_argument("new", help="新版（.s02 或 .md）")
    df.add_argument("-o", "--out", help="输出 markdown")
    df.add_argument("--json", nargs="?", const=True, help="输出 JSON（可给路径）")
    df.add_argument("--top", type=int, default=10, help="窗口级最多列几个")
    df.add_argument("--title", default="")
    df.add_argument("--time-base", type=int, dest="time_base",
                    help="输入 .md 时必填（µs / 四分音符）")
    df.set_defaults(func=cmd_s02_diff)

    rf = s02sub.add_parser("refs", help="参照曲目库（登记/列表/校准）")
    rf.add_argument("--add", nargs="+", help="登记参照曲目（.md）")
    rf.add_argument("--list", action="store_true", help="列出已登记")
    rf.add_argument("--calibrate", action="store_true", help="跑校准 + 留一法稳定性")
    rf.add_argument("--root", help="参照目录（默认 references/）")
    rf.add_argument("--json", help="把校准明细写到 JSON")
    rf.add_argument("--time-base", type=int, dest="time_base", default=500000,
                    help="µs / 四分音符（默认 500000）")
    rf.set_defaults(func=cmd_s02_refs)

    # ── 工具链协议：flow run / check / list ──
    fl = sub.add_parser("flow", help="工具链协议：一次 run 走完固定六步并留档")
    flsub = fl.add_subparsers(dest="flow_cmd", required=True)
    fr = flsub.add_parser("run", help="跑一次完整流程（ingest→project→index→analyze→report→render）")
    fr.add_argument("file", help=".md 曲谱")
    fr.add_argument("--time-base", type=int, dest="time_base", default=500000)
    fr.add_argument("--audio", action="store_true", help="顺带渲染 audio.wav")
    fr.add_argument("--title", default="")
    fr.add_argument("--weights", help="分析用权重 TOML（可选）")
    fr.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    fr.set_defaults(func=cmd_flow)
    fc = flsub.add_parser("check", help="校验一次 run 是否按协议完成")
    fc.add_argument("target", help="run 目录")
    fc.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    fc.set_defaults(func=cmd_flow)
    fb = flsub.add_parser("batch", help="批量跑一个目录（每周/每月统一积累）")
    fb.add_argument("dir", help="曲谱目录")
    fb.add_argument("--pattern", default="*.md")
    fb.add_argument("--tag", default="", help="批次名（默认当天日期）")
    fb.add_argument("--audio", action="store_true")
    fb.add_argument("--time-base", type=int, dest="time_base", default=500000)
    fb.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    fb.set_defaults(func=cmd_flow)
    fll = flsub.add_parser("list", help="列出所有 run")
    fll.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    fll.set_defaults(func=cmd_flow)

    # ── 品味学习：taste rate / train / predict / stats ──
    ta = sub.add_parser("taste", help="品味学习：给 run 打分、训练权重、预测")
    tasub = ta.add_subparsers(dest="taste_cmd", required=True)
    tr = tasub.add_parser("rate", help="给一次 run 打整体分（0..1）")
    tr.add_argument("run_id")
    tr.add_argument("--overall", type=float, required=True, help="整体分 0..1")
    tr.add_argument("--dims", help='分维度，如 "tension=0.8,drive=0.6"')
    tr.add_argument("--scorer", default="llm", help="llm / human / 模型名")
    tr.add_argument("--model", default="", help="评分者模型名（如 deepseek-v3）")
    tr.add_argument("--note", default="")
    tr.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    tr.set_defaults(func=cmd_taste)
    tt = tasub.add_parser("train", help="用已评分数据训练（样本不足会明确拒绝）")
    tt.add_argument("--min", type=int, default=12, help="最小样本数（默认 12）")
    tt.add_argument("--alpha", type=float, default=1.0, help="岭回归正则（默认 1.0）")
    tt.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    tt.set_defaults(func=cmd_taste)
    tp = tasub.add_parser("predict", help="用当前模型预测品味分")
    tp.add_argument("target", help="run_id 或 .s02 路径")
    tp.add_argument("--model-file", dest="model_file", help="指定模型 JSON")
    tp.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    tp.set_defaults(func=cmd_taste)
    ts = tasub.add_parser("stats", help="数据集与模型现状")
    ts.add_argument("--library", help="数据目录（默认 <workspace>/library）")
    ts.set_defaults(func=cmd_taste)

    ms_p = sub.add_parser("ms", help="MS 包：能力菜单 / 脚手架 / 校验")
    mssub = ms_p.add_subparsers(dest="mscmd", required=True)

    mc = mssub.add_parser("catalog", help="乐器能力菜单（类型/机制/音域/动作/踏板）")
    mc.add_argument("--family")
    mc.add_argument("--type", dest="type_code")
    mc.add_argument("--json", action="store_true")
    mc.add_argument("--markdown", action="store_true")
    mc.set_defaults(func=cmd_ms)

    mm = mssub.add_parser("menu", help="一句话菜单（能写什么/怎么查/怎么写）")
    mm.set_defaults(func=cmd_ms)

    msh = mssub.add_parser("schema", help="外部数据字典（字段/单位/等级/参数）")
    msh.add_argument("--json", action="store_true")
    msh.set_defaults(func=cmd_ms)

    msp = mssub.add_parser("package", help="任务 JSON → 每曲一个文件夹（.mid/.wav/.png）")
    msp.add_argument("spec", help="任务 JSON 路径")
    msp.add_argument("--out", required=True, help="输出根目录")
    msp.add_argument("--slug", help="文件夹/文件名（默认用标题）")
    msp.set_defaults(func=cmd_ms)

    msc = mssub.add_parser("score", help="任务 JSON → ABC/五线谱/音频（外部推荐）")
    msc.add_argument("spec", help="任务 JSON 路径")
    msc.add_argument("--abc"); msc.add_argument("--staff"); msc.add_argument("--audio")
    msc.add_argument("--title")
    msc.set_defaults(func=cmd_ms)

    mx = mssub.add_parser("export", help="导出 ABC 谱 / 五线谱（外部可读格式）")
    mx.add_argument("file")
    mx.add_argument("--abc", help="输出 .abc 路径")
    mx.add_argument("--staff", help="输出五线谱 .svg 路径")
    mx.add_argument("--title")
    mx.add_argument("--bpm", type=float, default=120.0)
    mx.set_defaults(func=cmd_ms)

    mck = mssub.add_parser("check", help="校验并打印踏板诊断")
    mck.add_argument("file")
    mck.set_defaults(func=cmd_ms)

    mn = mssub.add_parser("new", help="生成脚手架文本（默认只打印，不写文件）")
    mn.add_argument("out", nargs="?", help=".ms 路径（需同时加 --allow-write）")
    mn.add_argument("--instruments", default="acoustic_grand_piano",
                    help="逗号分隔类型码（如 piano,violin）")
    mn.add_argument("--bpm", type=float, default=120.0)
    mn.add_argument("--beats-per-bar", type=int, default=4)
    mn.add_argument("--bars", type=int, default=2)
    mn.add_argument("--allow-write", dest="allow_write", action="store_true",
                    help="显式允许写 .ms 文件（默认不写）")
    mn.set_defaults(func=cmd_ms)

    return p


def main(argv: list) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
