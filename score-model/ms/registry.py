# -*- coding: utf-8 -*-
"""乐器登记表：能力查询与扩展接口。"""
from __future__ import annotations

import ms_instruments as _reg
from ms_instruments import (  # noqa: F401  re-export 常用查询
    resolve, resolve_many, list_types, list_subtypes, check_registry,
    ACTION_MECHS, ARTICULATIONS_BY_MECH, ORNAMENTS_BY_MECH, CURVE_PARAMS,
    FAMILIES, MECHANISMS, SUBTYPES, TURN_KINDS, TYPE_PEDALS, ZH_CATALOG,
    REGISTRY_VERSION, LANGUAGES,
    register_instrument, register_turn_kind, register_articulation,
    register_ornament, register_pedal, register_language,
    unregister_instrument,
)

RESERVED = {code: meta for code, meta in ZH_CATALOG.items()
            if code not in _reg._BY_CODE and code not in _reg.EXTENDED}


def _spec_or_reserved(code: str, family: str) -> dict:
    try:
        return _reg.resolve(code)
    except KeyError:
        meta = RESERVED.get(code, {})
        return {"type_code": code, "family": family,
                "mechanism": _reg.MECHANISMS.get(family, "hammered_string"),
                "range": None, "poly": None, "pedals": (),
                "status": meta.get("status", "预留"),
                "group": meta.get("group", ""), "reserved": True}


def _actions_for(mechanism: str) -> list:
    """ACTION_MECHS 是 {转折: 机制元组|None}（None = 所有机制都能做）。"""
    out = []
    for kind, mechs in ACTION_MECHS.items():
        if mechs is None or mechanism in mechs:
            out.append(kind)
    return out


def actions(type_code: str) -> list:
    """这件乐器能做的演奏转折（按机制表过滤）。"""
    mech = _reg.resolve(type_code)["mechanism"]
    return _actions_for(mech)


def articulations(type_code: str) -> list:
    mech = _reg.resolve(type_code)["mechanism"]
    return list(ARTICULATIONS_BY_MECH.get(mech, ()))


def ornaments(type_code: str) -> list:
    mech = _reg.resolve(type_code)["mechanism"]
    return list(ORNAMENTS_BY_MECH.get(mech, ()))


def catalog(*, family: str | None = None, type_code: str | None = None) -> dict:
    """完整能力表（可 JSON 序列化）。

    只给 `type_code` 时返回单件乐器的详细能力；给 `family` 时只列该族。
    """
    if type_code:
        spec = _reg.resolve(type_code)
        mech = spec["mechanism"]
        return {
            "version": f"registry-{REGISTRY_VERSION}",
            "type": {
                "type_code": type_code,
                "family": spec["family"],
                "mechanism": mech,
                "range": list(spec["range"]) if spec.get("range") else None,
                "poly": spec.get("poly"),
                "pedals": list(spec.get("pedals") or ()),
                "subtypes": sorted(SUBTYPES.get(type_code, {})),
                "actions": _actions_for(mech),
                "articulations": list(ARTICULATIONS_BY_MECH.get(mech, ())),
                "ornaments": list(ORNAMENTS_BY_MECH.get(mech, ())),
            },
            "curves": {k: list(v) for k, v in CURVE_PARAMS.items()},
        }

    types = {}
    for _program, code, fam in _reg.list_types():
        if family and fam != family:
            continue
        spec = _spec_or_reserved(code, fam)
        mech = spec.get("mechanism")
        types[code] = {
            "family": fam,
            "mechanism": mech,
            "range": list(spec["range"]) if spec.get("range") else None,
            "poly": spec.get("poly"),
            "pedals": list(spec.get("pedals") or ()),
            "actions": _actions_for(mech),
            "articulations": list(ARTICULATIONS_BY_MECH.get(mech, ())),
            "ornaments": list(ORNAMENTS_BY_MECH.get(mech, ())),
            "reserved": bool(spec.get("reserved")),
        }

    fams = {}
    for code, meta in types.items():
        fams.setdefault(meta["family"], []).append(code)
    return {
        "version": f"registry-{REGISTRY_VERSION}",
        "count": {"types": len(types), "families": len(fams),
                  "turn_kinds": len(TURN_KINDS)},
        "families": {k: sorted(v) for k, v in sorted(fams.items())},
        "types": types,
        "curves": {k: list(v) for k, v in CURVE_PARAMS.items()},
        "languages": dict(LANGUAGES),
    }


def markdown(*, family: str | None = None) -> str:
    """能力菜单（Markdown 表格）。"""
    data = catalog(family=family)
    lines = [f"# 乐器能力菜单（{data['version']} / ms 包）", "",
             f"- 类型 {data['count']['types']} 种 · 族 {data['count']['families']} 个 "
             f"· 演奏转折 {data['count']['turn_kinds']} 种",
             "- 用法：`ms.Writer` 写谱；`ms.menu()` 看待写清单；"
             "`ms.registry.actions(类型)` 查动作", "",
             "| 类型 | 族 | 机制 | 音域 | 复音 | 踏板 | 转折数 | 奏法数 |",
             "|---|---|---|---|---|---|---|---|"]
    for code, m in data["types"].items():
        rng = f"{m['range'][0]}–{m['range'][1]}" if m["range"] else "—"
        flag = "（预留）" if m["reserved"] else ""
        lines.append(
            f"| `{code}`{flag} | {m['family']} | {m['mechanism']} | {rng} | "
            f"{m['poly'] if m['poly'] is not None else '—'} | "
            f"{', '.join(m['pedals']) or '—'} | {len(m['actions'])} | "
            f"{len(m['articulations'])} |")
    lines += ["", "## 曲线参数", ""]
    for k, (lo, hi) in data["curves"].items():
        lines.append(f"- `{k}`：{lo}..{hi}")
    lines += ["", "## 人声语言", "", "- " + "、".join(
        f"`{k}`（{v}）" for k, v in data["languages"].items())]
    return "\n".join(lines) + "\n"


def menu() -> str:
    """一句话菜单：可写什么、怎么查、怎么写。"""
    return (
        "MS 能写：任意多件乐器（同类型可多把，实例 P1..Pn）；每件乐器有按机制过滤的"
        "演奏转折、奏法、装饰音、踏板与 5 种曲线（dynamics/brightness/pitch_cents/"
        "vibrato/bow_position）。\n"
        "查：registry.actions(\"violin\") 看能做的转折；registry.catalog() 看全表；"
        "命令行 `mscli ms catalog --markdown`。\n"
        "写：ms.Writer 的 note()/chord()/pedal()/turn()/curve()，或 ms.write_note(...)；"
        "写完 ms.validate(doc) 会把病态写法（含 V4c 长踏板链）连原因一起列出来。"
    )


__all__ = ["catalog", "markdown", "menu", "actions", "articulations",
           "ornaments", "resolve", "list_types", "list_subtypes",
           "check_registry", "register_instrument", "register_turn_kind",
           "register_articulation", "register_ornament", "register_pedal",
           "register_language", "unregister_instrument", "RESERVED",
           "ACTION_MECHS", "CURVE_PARAMS", "TURN_KINDS", "LANGUAGES"]



# ── 演奏语义聚合（奏法/装饰音/动作/曲线）：单一查询入口 ──
AUDIO_CURVES = ("dynamics",)


def _sem_articulations() -> dict:
    import ms_articulation as _a
    return _a.table()


def _sem_ornaments() -> dict:
    import ms_ornament as _o
    return {"grace_short": {"pm": _o.GRACE_SHORT_PM, "rule": "主音前 25%"},
            "appoggiatura_long": {"pm": _o.APPOGGIATURA_LONG_PM, "rule": "拍上 50%"},
            "mordent": {"pm": _o.MORDENT_AUX_PM, "rule": "主45/上邻10/主45"},
            "turn": {"pm": _o.TURN_EACH_PM, "rule": "上15/主15/下15/主55"},
            "trill": {"hz": _o.TRILL_RATE_HZ, "rule": "主/上邻 10Hz 交替"}}


def _sem_actions() -> dict:
    import ms_performance as _p
    return {k: _p.TURN_TRANSIENT.get(k) for k in TURN_KINDS}


def curves() -> dict:
    return {name: {"audio": name in AUDIO_CURVES, "spec": spec}
            for name, spec in CURVE_PARAMS.items()}


def semantics(name: str | None = None) -> dict:
    """汇总奏法/装饰音/动作/曲线；传 name 返回单项。"""
    allmap = {"articulations": _sem_articulations(),
              "ornaments": _sem_ornaments(),
              "actions": _sem_actions(),
              "curves": curves()}
    if name is None:
        return allmap
    if name in allmap:
        return {"group": name, "items": allmap[name]}
    for group, table in allmap.items():
        if name in table:
            return {"group": group, "name": name, "spec": table[name]}
    raise KeyError(f"未知语义：{name!r}")


def semantics_check() -> list:
    """一致性：动作有瞬态定义、奏法/装饰音被机制支持。"""
    issues = []
    mech_art = {a for vals in ARTICULATIONS_BY_MECH.values() for a in vals}
    for a in _sem_articulations():
        if a not in mech_art:
            issues.append(f"奏法无机制支持：{a}")
    mech_orn = {o for vals in ORNAMENTS_BY_MECH.values() for o in vals}
    for o in _sem_ornaments():
        if o not in mech_orn:
            issues.append(f"装饰音无机制支持：{o}")
    return issues
