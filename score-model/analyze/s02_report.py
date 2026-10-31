# -*- coding: utf-8 -*-
"""S02 报告（`.report.md`）：把分段/动机/特征/诊断写成给人（和 LLM）看的小作文。

层次（对应 `S02认知引擎设计备忘.md` 的五层漏斗）：
  1 结构（段落/句读） → 2 拓扑（动机与变体） → 3 特征（密度/音区/张力曲线）
  → 4 语义（每段标签 + 依据） → 5 诊断（If-Then，阈值只来自 `s02_weights`）
"""
from __future__ import annotations

import s02_harmony as hm
import s02_index as idx_mod
import s02_probe as probe_mod
import s02_segment as seg_mod
import s02_weights as wt


def _diag(pr: dict, seg: dict, cfg: dict) -> list:
    """If-Then 诊断（只输出可核对的判断，不写玄学）。"""
    s = pr["summary"]
    out = []
    dens = [b["density"] for b in pr["bars"] if b.get("density") is not None]
    rng = (max(dens) - min(dens)) if dens else 0.0
    if rng < cfg["diagnose"]["flat_density_range"]:
        out.append(f"密度极差只有 {rng:.1f}（< {cfg['diagnose']['flat_density_range']}）："
                   f"全曲疏密几乎不变，听感容易平。")
    rr = s.get("repeat_ratio", 0.0)
    if rr > cfg["diagnose"]["high_repeat_ratio"]:
        out.append(f"重复窗口占 {rr:.0%}（> {cfg['diagnose']['high_repeat_ratio']:.0%}）："
                   f"结构靠重复撑，需检查是否有发展。")
    elif rr < cfg["diagnose"]["low_repeat_ratio"]:
        out.append(f"重复窗口只占 {rr:.0%}（< {cfg['diagnose']['low_repeat_ratio']:.0%}）："
                   f"几乎不呼应，容易记不住。")
    labels = [x["label"] for x in seg["sections"]]
    if len(seg["sections"]) <= 1:
        out.append("只切出 1 段：要么本来是一段体，要么突变不够（可调 `change_z`）。")
    if "高潮" not in labels and len(seg["sections"]) >= 3:
        out.append("没有任何一段被判为「高潮」：全场没有「高密度 + 高张力」的段落。")
    if labels.count("留白") >= 2:
        out.append(f"「留白」出现 {labels.count('留白')} 次：空得多，注意是否拖。")
    return out


def build(score, *, index=None, weights=None, title: str = "") -> str:
    """生成报告 markdown。`index` 可选（传入 SQLite 连接则带上动机统计）。"""
    cfg = weights or wt.load()
    pr = probe_mod.analyze(score)
    hz = hm.analyze(score)
    seg = seg_mod.segment(score, weights=cfg)
    s = pr["summary"]

    lines = [f"# S02 报告 · {title or score.title or '（未命名）'}", ""]
    lines += ["## 0. 摘要", "",
              f"- 音符 {s['notes']} · 窗口 {s['windows']} · 段落 {len(seg['sections'])}"
              f" · 短语 {len(seg['phrases'])}",
              f"- 音域 {s['pitch_range']} · 力度 {s['vel_range']} · 重复窗口占比 {s['repeat_ratio']:.0%}",
              f"- 全局纵向张力 {hz['overall'].get('v_tension', 0):.3f}"
              f" · 平均跳进张力 {hz['overall'].get('leap_mean', 0):.3f}"
              f" · 反向进行 {hz['overall'].get('contrary', 0)} 次", ""]

    lines += ["## 1. 结构（段落 / 句读）", "",
              "| 段 | 小节 | 音数 | 密度 | 张力 | 音区 | 扰动 | 标签 | 依据 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for x in seg["sections"]:
        f = x["features"]
        lines.append(f"| {x['id']} | {x['start_bar']}–{x['end_bar']} | {x['notes']} | "
                     f"{f['density']} | {f['v_tension_mean']} | {f['centroid']} | "
                     f"{x.get('perturb', 0)} | **{x['label']}** | {x['why']} |")
    lines.append("")
    shown = seg["phrases"][:12]
    lines.append("句读：" + "、".join(f"{p['id']}({p['start_bar']}–{p['end_bar']})" for p in shown)
                 + (f" …（共 {len(seg['phrases'])} 个）" if len(seg["phrases"]) > 12 else ""))
    lines.append("")

    # 手部可行性（P2）
    try:
        import s02_fingering
        fg = s02_fingering.analyze(score, weights=cfg)
        o = fg["overall"]
        lines += ["### 1b 手部可行性", "",
                  f"- 单手最大跨度 **{o['max_span']}** 半音（上限 {o['span_limit']:.0f}）、"
                  f"最大手位移动 **{o['max_jump']:.1f}**、超限窗口 **{o['stretch_bars']}** 个"]
        if fg["hard_bars"]:
            lines += ["", "| 小节 | 跨度 | 移动 | 结论 |", "|---|---|---|---|"]
            for w in fg["hard_bars"][:8]:
                lines.append(f"| {w['window']} | {w['hand_span']} | {w['hand_jump']:.1f} | "
                             f"{s02_fingering.label(w)} |")
            if len(fg["hard_bars"]) > 8:
                lines.append(f"| … | | | 共 {len(fg['hard_bars'])} 个 |")
        lines.append("")
    except Exception:
        pass

    # 局部扰动（P3）：列出最值得看的几条
    try:
        pb = seg.get("perturb") or {}
        ev = pb.get("events") or []
        if ev:
            lines += ["### 1c 局部扰动（前 8 条）", "",
                      "| 类型 | 小节 | 强度 | 说明 |", "|---|---|---|---|"]
            import s02_perturb
            for e in ev[:8]:
                lines.append(f"| {s02_perturb.label(e)} | {e['window']} | "
                             f"{e['strength']:.2f} | {e['detail']} |")
            if len(ev) > 8:
                lines.append(f"| … | | | 共 {len(ev)} 处 |")
            lines.append("")
    except Exception:
        pass

    # 结构质量（P10）：不需要审美评分的体检指标
    try:
        import s02_api
        import s02_quality
        con_q = index
        payload_q = s02_api.build_payload(score, index_con=con_q, weights=cfg)
        q = s02_quality.analyze(payload_q)
        lines += ["### 1e 结构测量（测量值，不是评分）", "",
                  f"- 覆盖 {q['coverage']:.0%}（置信 {q['confidence']}）",
                  "", "| 指标 | 测量值 | 说明 |", "|---|---|---|"]
        for k, v in q["metrics"].items():
            lines.append(f"| `{k}` | {v:.2f} | {q['explain'].get(k, '')} |")
        if q["missing"]:
            lines.append("")
            lines.append(f"- 未算：{'、'.join(q['missing'])}（数据不足）")
        lines += ["", "- 想和参照集比位置："
                  "`mscli s02 compare <曲> --refs <目录> | --batch <批次>`", ""]
    except Exception:
        pass

    # 连续维度（P4）：紧张/推进/留白/明亮
    try:
        import s02_score
        sc = s02_score.analyze_sections(score, seg["sections"], weights=cfg)
        lines += ["### 1d 连续维度（0..1）", "",
                  "| 段 | 紧张 | 推进 | 留白 | 明亮 |", "|---|---|---|---|---|"]
        for x in sc["sections"]:
            lines.append(f"| {x['id']} | {x['tension']:.2f} | {x['drive']:.2f} | "
                         f"{x['space']:.2f} | {x['bright']:.2f} |")
        lines.append("")
    except Exception:
        pass

    lines += ["## 2. 拓扑（动机）", ""]
    if index is not None:
        rows = idx_mod.motifs(index)
        top = sorted(rows, key=lambda r: (-r[3], -r[2]))[:10]
        lines += ["| 动机 | 长度 | 出现 | 变体 | 签名 |", "|---|---|---|---|---|"]
        for mid, sig, length, count, nvar in top:
            lines.append(f"| {mid} | {length} 音 | ×{count} | {nvar if nvar else '-'} | `{sig}` |")
    else:
        mts = getattr(score, "actions", []) and []  # 无索引时只报重复窗口
        lines.append(f"（未提供索引）重复窗口占比 {s['repeat_ratio']:.0%}。")
    lines.append("")

    lines += ["## 3. 特征曲线", "",
              "```",
              "密度   " + pr["spark"]["density"],
              "音区   " + pr["spark"]["centroid"],
              "力度σ  " + pr["spark"]["vel_std"],
              "```", ""]

    lines += ["## 4. 语义（每段推导）", ""]
    for x in seg["sections"]:
        f = x["features"]
        lines.append(f"- **{x['id']}（{x['start_bar']}–{x['end_bar']} 小节）= {x['label']}**："
                     f"密度 {f['density']}、张力 {f['v_tension_mean']}、音区 {f['centroid']}、"
                     f"跳进 {f['leap_mean']}；{x['why']}。")
    lines.append("")

    lines += ["## 5. 诊断", ""]
    d = _diag(pr, seg, cfg)
    lines += [f"- {x}" for x in d] if d else ["- 未触发任何诊断规则。"]
    lines.append("")
    lines += ["---", "",
              "> 本报告由 `s02_probe`（死算）+ `s02_harmony`（固定常数）+ `s02_segment`（规则层）生成；",
              "> 阈值全部来自 `s02_weights`，改权重即可重跑，不用改代码。"]
    return "\n".join(lines) + "\n"
