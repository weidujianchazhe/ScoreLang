# -*- coding: utf-8 -*-
"""S02 结构质量指标（P10）：**不需要审美评分**也能说的那些事。

它回答的是"这首曲子结构上是否合格/是否失衡/是否有发展"，**不回答"好不好听"**：

  · 好听是审美判断，需要人（或以后可信的模型）给标签；
  · 结构质量是**可复算**的：同样的分析结果 → 同样的数字，不依赖任何人打分。

所以两者分开：`quality` 用来"体检"，`taste` 用来"学偏好"。混在一起会把
"结构没毛病"误当成"好听"，这是本项目要避免的偷换。

每项都写成显式公式（见 `METRICS` 的 doc），阈值进 `s02_weights` 的 `[quality]`。
"""
from __future__ import annotations

import math

import s02_weights as wt

# 指标名 → 一句话解释（报告里直接展示）
METRICS = {
    "structure": "段落长度是否均衡（按参照分布校准：CV 0.30–1.20）",
    "return": "是否有再现（首尾段落特征接近 = 有回归感）",
    "development": "动机是否有发展（变体/覆盖率，纯重复不算发展）",
    "phrasing": "句读是否成形（平均 2–8 小节、句子数不过碎）",
    "arc": "张力是否有弧线（有对比 + 峰值不在两端）",
    "register": "音区是否有层次（重心有起伏，不是一条直线）",
    "variety": "密度是否有变化（不过平、不过跳）",
    "counterpoint": "声部是否独立（反向进行占比；单声部时不计）",
    "harmonic": "调性是否稳定（调外音比例落在合理带内）",
    "playability": "是否好弹（难度窗口占比越低分越高）",
    "dynamics": "力度层次（按参照分布校准；导入 MIDI 常为固定力度，低分可能是数据问题，不是作品差）",
    "ending": "收尾的密度回落（按参照分布校准；回落只是收束方式之一，不判好坏）",
    "ending_voices": "各乐器是否按自己的方式收束（结束时间错落/末音渐弱/自然延音），而不是同时停止",
}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _mean(vals):
    return sum(vals) / len(vals) if vals else None


def _std(vals):
    m = _mean(vals)
    if m is None:
        return None
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def _cv(vals):
    m, s = _mean(vals), _std(vals)
    if not m:
        return None
    return s / m


def _ramp(x, lo: float, hi: float) -> float:
    """lo→0，hi→1（线性，越界截断）。"""
    if x is None:
        return None
    if hi <= lo:
        return 1.0
    return _clip((x - lo) / (hi - lo))


def _band(x, lo: float, hi: float) -> float:
    """落在 [lo,hi] 内 = 1；越界线性衰减到 0。"""
    if x is None:
        return None
    if lo <= x <= hi:
        return 1.0
    d = (lo - x) if x < lo else (x - hi)
    span = max(1e-6, (hi - lo))
    return _clip(1.0 - d / span)


def analyze(payload: dict, *, weights=None) -> dict:
    """从 `s02_api.payload` 的结果算结构质量。返回 {metrics, overall, missing, flags}。"""
    cfg = (weights or wt.load()).get("quality", {}) or {}
    qcfg = {**wt.DEFAULTS.get("quality", {}), **cfg}
    secs = payload.get("sections") or []
    wins = payload.get("windows") or []
    s = payload.get("summary") or {}
    inter = payload.get("interference") or payload.get("harmony") or {}
    inter = inter if isinstance(inter, dict) else {}

    out, missing = {}, []
    notes = ""

    def put(name, val):
        if val is None:
            missing.append(name)
        else:
            out[name] = round(_clip(val), 3)

    # 1 段落均衡：CV 越小越好（0.8 以上算散）
    lens = [max(1, int(x.get("end_bar", 0)) - int(x.get("start_bar", 0)) + 1) for x in secs]
    cv = _cv(lens)
    put("structure", None if cv is None or len(lens) < 2
        else _clip(1.0 - (cv - qcfg["structure_cv_lo"]) /
              max(1e-6, qcfg["structure_cv_hi"] - qcfg["structure_cv_lo"])))

    # 2 再现：首段与末段四维距离（越小越像 → 有回归）
    def dims(x):
        return [float((x.get("dims") or {}).get(k) or 0.0)
                for k in ("tension", "drive", "space", "bright")]

    if len(secs) >= 3:
        d0, dN = dims(secs[0]), dims(secs[-1])
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(d0, dN))) / 2.0   # 归一 0..2
        put("return", _clip(1.0 - dist / qcfg["return_scale"]))
    else:
        put("return", None)

    # 3 动机发展：变体数/动机数（有变化）+ 覆盖率（用得上）
    nm = len(payload.get("motifs") or [])
    nv = len(payload.get("variants") or [])
    notes_cnt = max(1, int(s.get("notes") or 0))
    covered = sum(int(m.get("length") or 0) * int(m.get("count") or 0)
                  for m in (payload.get("motifs") or []))
    cover = covered / notes_cnt
    if nm == 0:
        put("development", None)
    else:
        dev_ratio = nv / max(1, nm)
        put("development", _clip(0.5 * _band(dev_ratio, 0.3, 2.0) + 0.5 * _band(cover, 0.15, 0.9)))

    # 4 句读成形：平均句长 2–8 小节 + 句数不过碎
    ph = payload.get("phrases") or []
    if len(ph) >= 2:
        plens = [max(1, int(p.get("end_bar", 0)) - int(p.get("start_bar", 0)) + 1) for p in ph]
        put("phrasing", _clip(_band(_mean(plens), qcfg["phrasing_min_bars"], qcfg["phrasing_max_bars"])))
    else:
        put("phrasing", None)

    # 5 张力弧线：段张力有对比（std）且峰值不在两端
    tens = [float((x.get("dims") or {}).get("tension") or 0.0) for x in secs]
    if len(tens) >= 3:
        sd = _std(tens)
        peak = max(range(len(tens)), key=lambda i: tens[i])
        interior = 0 < peak < len(tens) - 1
        put("arc", _clip(0.6 * _clip(sd / qcfg["arc_sd_scale"]) + 0.4 * (1.0 if interior
                                                       else qcfg["arc_edge"])))
    else:
        put("arc", None)

    # 6 音区层次：窗口音区重心的波动
    cents = [float(w.get("centroid") or 0.0) for w in wins]
    put("register", _clip(_std(cents) / qcfg["register_scale"]) if len(cents) >= 4 else None)

    # 7 密度变化：CV 落在 0.25–1.2 之间最像"有起伏"
    dens = [float(w.get("density") or 0.0) for w in wins]
    cv_dens = _cv(dens)
    if len(dens) < 4 or cv_dens is None:
        put("variety", None)
    elif cv_dens < 0.15:
        put("variety", _ramp(cv_dens, 0.0, qcfg["variety_low"]))          # 越平越差
    else:
        put("variety", _clip(cv_dens / qcfg["variety_scale"]))               # 连续缩放，避免饱和

    # 8 声部独立：反向进行占比（需要 harmony 的干涉统计）
    if inter:
        c = float(inter.get("contrary") or 0)
        sim = float(inter.get("similar") or 0)
        r_contr = c / max(1.0, c + sim)
        put("counterpoint", _clip(1.0 - abs(r_contr - qcfg["counterpoint_center"]) /
                    qcfg["counterpoint_scale"]))
    else:
        put("counterpoint", None)

    # 9 调性稳定：调外音比例落在 0.5%–12% 之间（太低=单调，太高=不稳）
    pr = (payload.get("perturbations") or {})
    ev = pr.get("events") or []
    chrom = sum(1 for e in ev if e.get("kind") == "chromatic")
    if notes_cnt > 20:
        put("harmonic", _clip(1.0 - abs(chrom / notes_cnt - qcfg["harmonic_center"]) /
                    qcfg["harmonic_scale"]))
    else:
        put("harmonic", None)

    # 10 好弹：难度窗口占比越低越好
    hards = [float(w.get("hard") or 0.0) for w in wins]
    put("playability", _clip(1.0 - (sum(1 for h in hards if h > 0) / max(1, len(hards)))))

    # 11 力度层次
    vr = s.get("vel_range") or [0, 0]
    put("dynamics", _clip(float(vr[1] - vr[0]) / 1000.0 / qcfg["dynamics_scale"])
        if len(vr) == 2 else None)

    # 12 收尾：末段密度/音区相对全曲（回落 = 收得住）
    if len(secs) >= 2 and wins:
        last = secs[-1]
        inside = [w for w in wins
                  if int(last.get("start_bar", 0)) <= int(w.get("window", 0)) <= int(last.get("end_bar", 0))]
        if inside:
            d_last = _mean([float(w.get("density") or 0.0) for w in inside])
            d_all = _mean(dens)
            put("ending", _clip(((d_all - d_last) / max(1.0, d_all) + qcfg["ending_offset"]) /
                    qcfg["ending_scale"]))
        else:
            put("ending", None)
    else:
        put("ending", None)

    # 只给测量值与覆盖度：**不做加权总分**。
    # 理由：一旦合成一个"质量分"，就会被当成评价（实测 Chopin 叙事曲 0.62、梦幻曲 0.99），
    # 而 S02 的职责是"翻译 + 测量"；跨曲比较请用 `s02 compare` 的分位数，不是分数。
    # 13 各乐器收束：结束时间错落 + 末音渐弱 + 自然延音
    ve = payload.get("voice_endings") or {}
    insts = ve.get("instances") or []
    kinds = {str(d.get("type")) for d in insts if d.get("type")}
    if len(insts) >= 2 and (len(kinds) >= 2
                            or payload.get("constraint_mode") == "n_pianos"):
        ends = [d["last_end"] for d in insts]
        piece_end = max(ve.get("piece_end") or 0, 1)
        stagger = (max(ends) - min(ends)) / piece_end
        perms = [d["last_permille"] for d in insts
                 if d.get("last_permille") is not None]
        allp = ve.get("avg_permille")
        fade = 0.0
        if perms and allp:
            fade = 0.0 if allp <= 0 else _clip((allp - min(perms)) / allp * qcfg["voice_fade_scale"])
        hold = sum(1 for d in insts
                   if d.get("release_state") == "sustaining") / len(insts)
        stagger_term = (0.0 if stagger < qcfg["voice_stagger_min"]
                        else _band(stagger, qcfg["voice_stagger_lo"],
                                   qcfg["voice_stagger_hi"]))
        put("ending_voices", _clip(qcfg["voice_w_stagger"] * stagger_term
                                  + qcfg["voice_w_fade"] * fade
                                  + qcfg["voice_w_hold"] * hold))
    else:
        put("ending_voices", None)

    coverage = round(len(out) / len(METRICS), 2)
    confidence = ("不足" if coverage < 0.6 else ("中" if coverage < 0.85 else "高"))

    labels = {}
    for k, v in out.items():
        labels[k] = "高" if v >= 0.75 else ("中" if v >= 0.45 else "低")
    # ── 测量层（不是评分；与“好不好听”无关） ──
    meas = {}
    mexplain = {}
    tens2 = [float((x.get("dims") or {}).get("tension") or 0.0) for x in secs]
    if len(tens2) >= 3:
        peak = max(range(len(tens2)), key=lambda i: tens2[i])
        peak_at = peak / (len(tens2) - 1)
        rng = max(0.001, max(tens2) - min(tens2))
        meas["expectation_release"] = {
            "peak_at": round(peak_at, 3),
            "rise": round((tens2[peak] - tens2[0]) / rng, 3),
            "fall": round((tens2[peak] - tens2[-1]) / rng, 3),
        }
        mexplain["expectation_release"] = (
            "张力峰值位置（0=开头,1=结尾）、上升幅度、峰值后回落幅度；"
            "**测量值，不判断好坏**（峰值晚=期待久，回落大=释放充分，都不等于好听）")
    tech = payload.get("technique") or {}
    if tech.get("notes"):
        meas["technique_density"] = {
            "per_note": tech.get("per_note"),
            "per_bar": tech.get("per_bar"),
            "actions": tech.get("actions"),
            "articulations": tech.get("articulations"),
        }
        mexplain["technique_density"] = (
            "每音/每小节的技术记号密度（奏法+转折）；"
            "**测量值，与好坏无关**：高密度可以好听也可以难听，低密度同理")

    return {
        "metrics": out,
        "measurements": meas,
        "measure_explain": mexplain,
        "coverage": coverage,
        "labels": labels,
        "missing": missing,
        "explain": METRICS,
        "confidence": confidence,
        "note": ("这是**测量值**，不是评分：0..1 是按公式归一后的位置，只描述结构形态。"
                 "跨曲比较请用参照集的分位数；"
                 "审美判断不在 S02 里，属于单独的学习层（taste）。"),
    }
