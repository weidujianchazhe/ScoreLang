# -*- coding: utf-8 -*-
"""把意图编译成生成约束：技术密度上限 + 各声部收束错落 + 提示。

意图不是评分，只作为“生成时的约束”：
  · technique.density = low/medium/high → 限制奏法/装饰音密度；
  · ending.stagger_voices = true → finish 时自动错开各声部结束时间；
  · expression.expectation → 只给提示（不自动改音符）。
"""
from __future__ import annotations

# 每音技术记号密度上限（奏法+装饰音）/音符数
DENSITY_BANDS = {
    "low": (0.0, 0.08),
    "medium": (0.08, 0.25),
    "high": (0.25, 1.0),
}


class IntentPlan:
    def __init__(self, intent: dict | None):
        self.intent = dict(intent or {})
        t = self.intent.get("technique") or {}
        d = str(t.get("density") or "").lower()
        self.density = d if d in DENSITY_BANDS else None
        e = self.intent.get("ending") or {}
        self.stagger = bool(e.get("stagger_voices"))
        st = self.intent.get("structure") or {}
        sb = st.get("section_bars")
        self.section_bars = [int(x) for x in sb] if isinstance(sb, list) and sb else None
        self.total_bars = (sum(self.section_bars) if self.section_bars
                           else (int(st["total_bars"]) if st.get("total_bars") else None))
        x = self.intent.get("expression") or {}
        self.expectation = x.get("expectation")

    # ── 技术密度 ────────────────────────────────────────────
    def density_left(self, notes: int, tech: int) -> float | None:
        """还能写多少个技术记号（None=不限）。"""
        if not self.density or notes <= 0:
            return None
        _, hi = DENSITY_BANDS[self.density]
        left = hi * notes + 1.0 - tech
        return max(0.0, left)

    def check_add_tech(self, notes: int, tech: int) -> None:
        if not self.density:
            return
        hi = DENSITY_BANDS[self.density][1]
        if notes > 0 and (tech + 1) > hi * notes + 1.0:
            raise ValueError(
                f"意图要求技术密度={self.density}（≤{hi:.2f}/音）："
                f"当前 {tech}/{notes}，不能再加奏法/装饰音")

    def status(self, notes: int, tech: int) -> dict:
        return {"density": self.density,
                "notes": notes, "technique_marks": tech,
                "per_note": round(tech / notes, 4) if notes else None,
                "left": self.density_left(notes, tech),
                "stagger_voices": self.stagger,
                "expectation": self.expectation,
                "section_bars": self.section_bars,
                "total_bars": self.total_bars}

    def hints(self) -> list:
        out = []
        if self.expectation is not None:
            out.append(f"期待值 {self.expectation}：优先让张力峰值靠后、收尾再释放")
        if self.density:
            lo, hi = DENSITY_BANDS[self.density]
            out.append(f"技术密度目标 {self.density}：每音 {lo:.2f}–{hi:.2f} 个记号")
        if self.expectation is not None:
            out.append(f"张力弧线：峰值约在 {0.45 + 0.35 * float(self.expectation):.0%} 处，收尾回落")
        if self.total_bars:
            out.append(f"结构目标：总长约 {self.total_bars} 小节")
        return out


def plan(intent: dict | None) -> IntentPlan:
    return IntentPlan(intent)


__all__ = ["IntentPlan", "plan", "DENSITY_BANDS"]
