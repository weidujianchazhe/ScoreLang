# -*- coding: utf-8 -*-
"""出图/出包前的检查清单（pre-flight）。

只检查、不改音符：
    res = ms.export_check(spec, intent=None)
    res["ok"]        # 无阻断项
    res["blockers"]  # 必须修（否则拒绝导出）
    res["warnings"]  # 可接受，但建议看（位置/原因/复核）
    res["info"]      # 提示
"""
from __future__ import annotations

BLOCK_CODES = {"same_pitch_overlap", "pedal_gap"}


def export_check(spec, *, intent=None, strict: bool = False) -> dict:
    """导出前检查：blockers / warnings / info / summary。

    strict=True 时 warnings 也算不通过（`ok=False`）。
    """
    import ms

    res = {"ok": False, "blockers": [], "warnings": [], "info": [],
           "summary": "", "findings": []}
    try:
        diag = ms.diagnose(spec, intent=intent)
    except Exception as exc:  # noqa: BLE001
        res["blockers"].append({"code": "diagnose_failed",
                                "why": f"无法生成/诊断：{exc}"})
        res["summary"] = "导出前检查：1 个阻断（无法生成）"
        return res

    if not diag.get("ok"):
        res["blockers"].append({"code": "build_failed",
                                "why": diag.get("summary") or "无法生成"})
        res["summary"] = "导出前检查：1 个阻断（无法生成）"
        return res

    findings = diag.get("findings") or []
    res["findings"] = findings
    for f in findings:
        if f["code"] in BLOCK_CODES:
            res["blockers"].append(f)
        else:
            res["warnings"].append(f)

    # 信息项（不评/数据现象）
    try:
        rep = ms.report(spec, intent=intent, include_diagnosis=False)
    except Exception:  # noqa: BLE001
        rep = {}
    summary = rep.get("summary") or {}
    if summary.get("instruments") == 1:
        res["info"].append("单编制：ending_voices 不评估（正常）")
    if summary.get("pedals") == 0:
        res["info"].append("无踏板：想用踏板可加 pedals 或 pedal=auto")
    metrics = ((rep.get("quality") or {}).get("metrics") or {})
    if metrics.get("dynamics") is not None and float(metrics["dynamics"]) < 0.05:
        res["info"].append("力度变化很低：如果不是有意，可加 level/permille")

    ok = not res["blockers"] and (not strict or not res["warnings"])
    res["ok"] = ok
    res["summary"] = _text(res)
    return res


def _text(res: dict) -> str:
    lines = [f"导出前检查：{len(res['blockers'])} 个阻断 / "
             f"{len(res['warnings'])} 个警告 / {len(res['info'])} 个提示 → "
             + ("可以导出" if res["ok"] else "不通过")]
    for label, items, mark in (("阻断", res["blockers"], "❌"),
                               ("警告", res["warnings"], "⚠️"),
                               ("提示", res["info"], "ℹ️")):
        for f in items:
            if isinstance(f, str):
                lines.append(f"  {mark} {f}")
                continue
            w = f.get("where") or {}
            loc = " ".join(f"{k}={v}" for k, v in w.items())
            lines.append(f"  {mark} [{f.get('code')}] @ {loc}："
                         f"{f.get('why')}；复核：{f.get('verify', '')}")
    return "\n".join(lines)


__all__ = ["export_check"]
