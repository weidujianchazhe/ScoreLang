# -*- coding: utf-8 -*-
"""命令行：写乐谱（schema / instruments / score / package / report / cheatsheet）。

这是发布版的 CLI，只包含对外能力；不包含任何内部工具或占位命令。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ms  # noqa: E402


def _spec(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mscli", description="写乐谱（乐谱模型）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("ms", help="写乐谱")
    act = m.add_subparsers(dest="action", required=True)

    s = act.add_parser("schema", help="数据字典")
    s.add_argument("--text", action="store_true", help="一屏精简版")

    act.add_parser("instruments", help="可选乐器")
    act.add_parser("cheatsheet", help="最简用法")
    act.add_parser("prime", help="写谱前必读（乐器+演奏+写法）")
    rn = act.add_parser("renderers", help="渲染器状态（首次使用先检查）")
    rn.add_argument("--chrome", help="指定浏览器可执行文件路径")
    _selfck = act.add_parser("selfcheck", help="技能包自检（完整性+渲染器）")
    _selfck.add_argument("--json", action="store_true")
    dr = act.add_parser("draft", help="按意图生成初稿任务 JSON")
    dr.add_argument("intent", nargs="?", help="意图 JSON 文件（可省）")
    dr.add_argument("--out", help="写到文件（默认打印）")
    act.add_parser("render-init", help="首次使用初始化检查")
    cc = act.add_parser("clear-cache", help="清缓存区（不动 output 产物）")
    cc.add_argument("--dry-run", action="store_true")

    sc = act.add_parser("score", help="任务 JSON → ABC / 五线谱 / 音频")
    sc.add_argument("task")
    sc.add_argument("--abc")
    sc.add_argument("--staff")
    sc.add_argument("--png")
    sc.add_argument("--audio")
    sc.add_argument("--midi")
    sc.add_argument("--fix", action="store_true", help="出图/导出前先分析修复")
    sc.add_argument("--check", action="store_true", help="导出前检查（阻断则拒绝）")

    im = act.add_parser("import", help="导入 MusicXML / MIDI 再导出")
    im.add_argument("file")
    im.add_argument("--abc")
    im.add_argument("--staff")
    im.add_argument("--png")
    im.add_argument("--audio")
    im.add_argument("--midi")

    pk = act.add_parser("package", help="产物文件夹（mid/wav/png/abc）")
    pk.add_argument("task")
    pk.add_argument("--out", default="output")
    pk.add_argument("--bars-per-page", type=int, default=8)
    pk.add_argument("--fix", action="store_true", help="生成产物前先分析修复")
    pk.add_argument("--check", action="store_true", help="出包前检查（阻断则拒绝）")
    pk.add_argument("--strict", action="store_true", help="检查时警告也算不通过")

    ec = act.add_parser("export-check", help="导出前检查（阻断/警告/提示）")
    ec.add_argument("task")
    ec.add_argument("--intent", help="意图 JSON（可选）")
    ec.add_argument("--json", action="store_true")
    ec.add_argument("--strict", action="store_true", help="警告也算不通过")
    tx = act.add_parser("text", help="文本谱 → 导出（一行一个音）")
    tx.add_argument("file")
    tx.add_argument("--out", help="写出规范化的任务 JSON")
    tx.add_argument("--abc")
    tx.add_argument("--staff")
    tx.add_argument("--midi")
    tx.add_argument("--audio")
    tx.add_argument("--png")
    dg = act.add_parser("diagnose", help="诊断：位置+原因+建议（不改音符）")
    dg.add_argument("task")
    dg.add_argument("--intent", help="意图 JSON（可选）")
    dg.add_argument("--json", action="store_true")
    fx = act.add_parser("fix", help="分析→修改→复核（返回修复后任务）")
    fx.add_argument("task")
    fx.add_argument("--intent", help="意图 JSON（可选）")
    fx.add_argument("--out", help="写出修复后的任务 JSON")
    fx.add_argument("--dry-run", action="store_true", help="只给建议不改")
    cs = act.add_parser("check-spec", help="检查任务 JSON 能否生成")
    cs.add_argument("task")

    rp = act.add_parser("report", help="分析报告")
    rp.add_argument("task")
    rp.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.action == "schema":
        if args.text:
            print(ms.schema_text())
        else:
            print(json.dumps(ms.schema(), ensure_ascii=False, indent=2))
        return 0
    if args.action == "instruments":
        for alias, info in ms.instruments().items():
            print(f"{alias:10s} {info.get('type', ''):28s} {info.get('family', '')}")
        return 0
    if args.action == "cheatsheet":
        print(ms.cheatsheet())
        return 0
    if args.action == "prime":
        print(ms.prime())
        return 0
    if args.action == "renderers":
        if getattr(args, "chrome", None):
            ms.configure_renderer(args.chrome)
        print(ms.render_status())
        return 0
    if args.action == "draft":
        intent = _spec(args.intent) if args.intent else {}
        spec = ms.draft(intent)
        text = json.dumps(spec, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print("初稿：", args.out)
        else:
            print(text)
        return 0
    if args.action == "selfcheck":
        info = ms.selfcheck()
        if args.json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(info["text"])
        return 0 if info["ok"] else 1
    if args.action == "render-init":
        info = ms.render_init()
        print(info["status"])
        print("首次使用：" + ("是" if info["first_use"] else "否"),
              "| 全部可用：" + ("是" if info["all_ready"] else "否"))
        return 0
    if args.action == "clear-cache":
        res = ms.clear_cache(dry_run=args.dry_run)
        print("将清理" if args.dry_run else "已清理", len(res["removed"]), "个缓存文件")
        for x in res["removed"]:
            print("  -", x)
        print("保留（不是缓存）：", len(res["kept"]), "个")
        return 0

    if args.action == "score":
        spec = _spec(args.task)          # 先读任务，再 build（避免 spec 未赋值）
        if getattr(args, "check", False):
            _chk = ms.export_check(spec)
            print(_chk["summary"], file=sys.stderr)
            if not _chk["ok"]:
                return 1
        song = ms.build(spec, fix=getattr(args, "fix", False))
        wrote = False
        if args.abc:
            Path(args.abc).write_text(song.export_abc(), encoding="utf-8")
            print("ABC 谱：", args.abc)
            wrote = True
        if args.staff:
            Path(args.staff).write_text(song.export_staff(), encoding="utf-8")
            print("五线谱：", args.staff)
            wrote = True
        if args.png:
            try:
                song.export_png(args.png)
                print("PNG：", args.png)
            except Exception as _e:  # noqa: BLE001
                print("PNG 跳过（渲染器不可用）：", _e, file=sys.stderr)
                print(ms.render_status(), file=sys.stderr)
            wrote = True
        if args.audio:
            song.export_wav(args.audio)
            print("WAV：", args.audio)
            wrote = True
        if args.midi:
            Path(args.midi).write_bytes(song.export_midi())
            print("MIDI：", args.midi)
            wrote = True
        if not wrote:
            print(song.summary())
        return 0
    if args.action == "import":
        song = ms.open(args.file)
        print("导入：", song.summary())
        if args.abc:
            Path(args.abc).write_text(song.export_abc(), encoding="utf-8")
            print("ABC 谱：", args.abc)
        if args.staff:
            Path(args.staff).write_text(song.export_staff(), encoding="utf-8")
            print("五线谱：", args.staff)
        if args.png:
            try:
                song.export_png(args.png)
                print("PNG：", args.png)
            except Exception as _e:  # noqa: BLE001
                print("PNG 跳过（渲染器不可用）：", _e, file=sys.stderr)
        if args.audio:
            song.export_wav(args.audio)
            print("WAV：", args.audio)
        if args.midi:
            Path(args.midi).write_bytes(song.export_midi())
            print("MIDI：", args.midi)
        return 0
    spec = _spec(args.task) if getattr(args, "task", None) else None
    if args.action == "package":
        info = ms.package(spec, args.out, bars_per_page=args.bars_per_page,
                          fix=getattr(args, "fix", False),
                          check=getattr(args, "check", False),
                          strict=getattr(args, "strict", False))
        print("已生成产物文件夹：", info["folder"])
        for k in ("mid", "wav", "png", "abc"):
            v = info.get(k)
            if v:
                print(f"  {Path(v).name}")
        print("  摘要：", info["summary"])
        return 0
    if args.action == "export-check":
        _spec_ = _spec(args.task)
        _intent = _spec(args.intent) if getattr(args, "intent", None) else None
        res = ms.export_check(_spec_, intent=_intent, strict=args.strict)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(res["summary"])
        return 0 if res["ok"] else 1
    if args.action == "text":
        _txt = Path(args.file).read_text(encoding="utf-8")
        _spec_ = ms.parse_text(_txt)
        if args.out:
            Path(args.out).write_text(
                json.dumps(_spec_, ensure_ascii=False, indent=2), encoding="utf-8")
            print("任务 JSON：", args.out)
        _song = ms.build(_spec_)
        _wrote = False
        for _flag, _fn in (("abc", lambda p: Path(p).write_text(_song.export_abc(), encoding="utf-8")),
                           ("staff", lambda p: Path(p).write_text(_song.export_staff(), encoding="utf-8")),
                           ("midi", lambda p: Path(p).write_bytes(_song.export_midi())),
                           ("audio", lambda p: _song.export_wav(p)),
                           ("png", lambda p: _song.export_png(p))):
            _path = getattr(args, _flag, None)
            if not _path:
                continue
            try:
                _fn(_path)
                print(_flag.upper() + "：", _path)
                _wrote = True
            except Exception as _e:  # noqa: BLE001
                print(_flag.upper() + " 跳过：", _e, file=sys.stderr)
        if not _wrote and not args.out:
            print(json.dumps(_spec_, ensure_ascii=False, indent=2))
        return 0
    if args.action == "diagnose":
        _spec_ = _spec(args.task)
        _intent = _spec(args.intent) if getattr(args, "intent", None) else None
        res = ms.diagnose(_spec_, intent=_intent)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(res["summary"])
        return 0 if res.get("ok") else 1
    if args.action == "fix":
        _spec_ = _spec(args.task)
        _intent = _spec(args.intent) if getattr(args, "intent", None) else None
        res = ms.analyze_fix(_spec_, intent=_intent, apply=not args.dry_run)
        print("修复：", "成功" if res.get("ok") else "失败",
              "| 应用", sum(1 for f in res.get("fixes", []) if f.get("applied")), "项",
              "| 复核：", "通过" if res.get("verified") else "未通过")
        for f in res.get("fixes", []):
            print(f"  - [{f.get('kind')}] {f.get('action')}"
                  + ("" if f.get("applied") else "（未应用）"))
        for w in res.get("warnings") or []:
            print("  ⚠", w)
        print("  指标前:", json.dumps(res.get("before", {}).get("metrics") or {},
                                    ensure_ascii=False))
        print("  指标后:", json.dumps(res.get("after", {}).get("metrics") or {},
                                    ensure_ascii=False))
        if args.out:
            Path(args.out).write_text(
                json.dumps(res.get("spec") or _spec_, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print("  写出：", args.out)
        return 0
    if args.action == "check-spec":
        res = ms.check_spec(_spec(args.task))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    if args.action == "report":
        rep = ms.report(spec)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            print(ms.report_text(rep))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
