# -*- coding: utf-8 -*-
"""人声段间转折：复用 MS 的 `turns`，缺省才用默认值。

  · liaison(strength) → 重叠 = strength/1000 × 默认上限
  · break(strength)   → 断开 = strength/1000 × 默认上限
  · 没标记            → 默认重叠 15%
"""
DEFAULT_OVERLAP = 0.15
MAX_OVERLAP_MS = 120
MAX_BREAK_MS = 200


def _marks(doc):
    m = {}
    for t in getattr(doc, "turns", []):
        if t.kind in ("liaison", "break"):
            m[(t.event_id, t.seg_index)] = t
    return m


def build_transitions(plan, doc=None):
    """返回 [{syl,i,kind,start_us,end_us,overlap_us,turn,stress}]。"""
    marks = _marks(doc) if doc is not None else {}
    out = []
    for syl in plan.syllables:
        eid = syl.event_ids[0] if syl.event_ids else None
        prev_end = None
        for i, seg in enumerate(syl.segments or []):
            dur = seg.dur_us
            mk = marks.get((eid, i)) or marks.get((eid, None))
            if mk is not None and mk.kind == "break":
                overlap = -int(MAX_BREAK_MS * 1000 * mk.strength / 1000)
            elif mk is not None and mk.kind == "liaison":
                overlap = int(MAX_OVERLAP_MS * 1000 * mk.strength / 1000)
            else:
                overlap = int(dur * DEFAULT_OVERLAP) if i else 0
            start = syl.onset_us if i == 0 else max(prev_end - overlap, syl.onset_us)
            end = start + dur
            out.append({"syl": syl.char, "i": i, "kind": seg.kind,
                        "start_us": start, "end_us": end, "overlap_us": overlap,
                        "turn": 0 if overlap > 0 else 1,
                        "stress": 900 if i == 0 else 500})
            prev_end = end
    return out
