# -*- coding: utf-8 -*-
"""MS 动作 ↔ 谱面记号 的**对照规则**（双向）。

用途：
  ① 由 MS 画谱：`symbol_for()` 给出该动作在谱面上画什么、画在哪；
  ② 由谱面回 MS：`by_symbol()` 由记谱符号查出对应的动作（格式互换）；
  ③ 连音/长音的**结构性规则**：`arcs_for()` 决定两个相邻音之间是"延音线(tie)"
     还是"连音线(slur)"——这两种在 MS 里不是一个字段，而是**由相邻关系推出来的**。

原则：MS 存"怎么奏"，谱面存"怎么读"。对照表是唯一口径，两边都按它走。
"""
from __future__ import annotations

# ── 动作 → 记号 ──────────────────────────────────────────
#   glyph  : 谱面符号（None = 不写符号，靠连线/时长表达）
#   place  : above / below / before（相对音符）
#   category: 弓法 / 音色 / 发音 / 机械
MS_TO_SYMBOL = {
    "bow_up":      ("V",            "above",  "弓法"),
    "bow_down":    ("Π",            "above",  "弓法"),
    "bow_change":  ("𝄐",            "above",  "弓法"),
    "pizz":        ("pizz.",        "above",  "弓法"),
    "arco":        ("arco",         "above",  "弓法"),
    "col_legno":   ("col legno",    "above",  "弓法"),
    "tremolo":     ("trem.",        "above",  "弓法"),
    "harmonic":    ("○",            "above",  "音色"),
    "mute_on":     ("con sord.",    "above",  "音色"),
    "mute_off":    ("senza sord.",  "above",  "音色"),
    "mute_cup":    ("cup mute",     "above",  "音色"),
    "mute_harmon": ("harmon mute",  "above",  "音色"),
    "mute_plunger": ("plunger",     "above",  "音色"),
    "half_valve":  ("½ valve",      "above",  "音色"),
    "growl":       ("growl",        "above",  "音色"),
    "mallet_soft": ("soft",         "above",  "音色"),
    "mallet_hard": ("hard",         "above",  "音色"),
    "mallet":      ("mallets",      "above",  "音色"),
    "brush":       ("brush",        "above",  "音色"),
    "rim_shot":    ("rim",          "above",  "音色"),
    "inhale":      ("’",            "above",  "发音"),
    "breath":      (",",            "above",  "发音"),
    "flutter":     ("flutter",      "above",  "发音"),
    "roll":        ("roll",         "above",  "发音"),
    "key_click":   ("×",            "above",  "机械"),
    "key_noise":   ("×",            "above",  "机械"),
    "retrigger":   ("•",            "above",  "发音"),
    "restrike":    ("•",            "above",  "发音"),
    "liaison":     (None,           "above",  "连线"),   # 靠连音线画
    "break":       (None,           "above",  "连线"),   # 断连，不画符号
}

# ── 记号 → 动作（反向；同名不同写法都收）──────────────
BY_SYMBOL = {}
for _k, (_g, _p, _c) in MS_TO_SYMBOL.items():
    if _g:
        BY_SYMBOL.setdefault(_g, []).append(_k)
# 常见异体写法
BY_SYMBOL.update({
    "∏": ["bow_up"],
    "∨": ["bow_up"],
    "⋀": ["bow_down"],
    "o": ["harmonic"],
    "harm.": ["harmonic"],
    "con sordino": ["mute_on"],
    "senza sordino": ["mute_off"],
    "sord.": ["mute_on"],
    "trem.": ["roll"],
    "cym.": ["roll"],
})


def symbol_for(kind: str):
    """该动作在谱面上怎么画：`(glyph, place, category)`；未登记返回 `(None, "above", "未知")`。"""
    return MS_TO_SYMBOL.get(kind, (None, "above", "未知"))


def by_symbol(glyph: str) -> list:
    """谱面记号 → 可能的动作（按记号查；查不到返回空表）。"""
    return list(BY_SYMBOL.get(glyph.strip(), []))


# ── 连音/长音：由相邻关系推出，不是字段 ──────────────────
#   规则（教科书口径）：
#     ① 同一音高 + 前后相接（无空隙）+ 后音没有 restrike/retrigger  → **延音线 tie**
#     ② 不同音高 + 前后相接 + 后音没有 restrike/retrigger/bow_change → **连音线 slur**
#     ③ 有空隙 → 不画（断奏/分句）
#     ④ 后音带 restrike/retrigger → 不画（那是重新发音，不是连）
ARC_BREAKERS = ("restrike", "retrigger", "bow_change", "break")


def arcs_for(events, turns=()) -> list:
    """返回 `[(arc_kind, id_a, id_b)]`，arc_kind ∈ {"tie", "slur"}。

    规则（教科书口径）：
      · **延音线 tie**：同一音高 + 前后相接 → 一定是"一个音被分成两半"，直接画。
      · **连音线 slur**：不同音高 + 相接 + 后音标了 `liaison` → 画；没标就不画
        （自动给每对相邻音画连音线是错的：谱面上连音线是**有意标**的）。
    """
    turn_of = {t.event_id: t.kind for t in turns}
    out = []
    notes = sorted([e for e in events if e.release_us is not None],
                   key=lambda e: (e.onset_us, e.pitch.semitone))
    for a, b in zip(notes, notes[1:]):
        if b.onset_us != a.release_us:                 # 有空隙
            continue
        if b.id in turn_of and turn_of[b.id] in ARC_BREAKERS:
            continue                                   # 重新发音
        if a.pitch.semitone == b.pitch.semitone:
            out.append(("tie", a.id, b.id))
        elif turn_of.get(b.id) == "liaison":
            out.append(("slur", a.id, b.id))
    return out


# ── 踏板/连续参数 → 记号 ────────────────────────────────
PEDAL_SYMBOL = {
    "sustain": "Ped.",
    "sostenuto": "Sost. ped.",
    "una_corda": "una corda",
    "sordino": "con sord.",
    "swell": "m.g.",
    "tuning": "♭/♮/♯",
    "hihat": "hi-hat",
}
CURVE_SYMBOL = {
    "dynamics": "力度记号（p/mf/f…）",
    "brightness": "音色记号（dolce/brillante…）",
    "pitch_cents": "滑音线 / gliss.",
    "vibrato": "vibr.",
    "bow_position": "sul tasto / sul pont.",
}
