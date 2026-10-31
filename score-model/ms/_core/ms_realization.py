# -*- coding: utf-8 -*-
"""MS 演奏收束（R-1..R-4）：物理上能不能做到。"""
from __future__ import annotations

from ms_model import *  # noqa: F401,F403


def check_realization(doc: MSDocument, *, piano_count: int | None = None) -> list[str]:
    """**演奏收束**检查：把事件落到钢琴上时的物理不可能。

    与 `validate()` 分工：
      - `validate()` 管结构（数学上是否自洽）
      - 本函数管收束（能否在一架/多架琴上真正弹出）

    返回 `R-*` 前缀的违规；空列表表示可演奏。
    """
    errs: list[str] = []
    n_pianos = piano_count if piano_count is not None else doc.piano_count

    # R-1 同键同刻：同一架琴的同一个键不可能在同一微秒被击两次
    seen: dict = {}
    for e in doc.events:
        k = (e.instrument_id, e.key(), e.onset_us)
        if k in seen:
            errs.append(f"R-1 同键同刻无法击发两次：piano={e.instrument_id} key={e.key()} "
                        f"onset={e.onset_us}（{seen[k]} 与 {e.id}）")
        else:
            seen[k] = e.id

    # R-2 同键重击：一个键还在响（未释放）时不可能再被击发
    by_key: dict = {}
    for e in doc.events:
        by_key.setdefault((e.instrument_id, e.key()), []).append(e)
    for (pid, key), evs in by_key.items():
        evs = sorted(evs, key=lambda x: x.onset_us)
        for a, b in zip(evs, evs[1:]):
            a_end = a.release_us if a.release_us is not None else float("inf")
            if b.onset_us < a_end and b.onset_us != a.onset_us:
                errs.append(f"R-2 同键重击：piano={pid} key={key} "
                            f"{a.id}@{a.onset_us} 尚未释放即被 {b.id}@{b.onset_us} 再击")

    # R-3 琴数越界
    for e in doc.events:
        if not (1 <= e.instrument_id <= n_pianos):
            errs.append(f"R-3 instrument_id 越界：{e.id} piano={e.instrument_id}（声明 {n_pianos} 台）")
        if e.instrument_id is not None:
            pass
    for p in doc.pedals:
        if not (1 <= p.instrument_id <= n_pianos):
            errs.append(f"R-3 踏板 instrument_id 越界：{p.kind}@{p.start_us} piano={p.instrument_id}")

    # R-4 键域：落到真实钢琴的 88 键（MS 允许更宽，但钢琴物理上只有 A0..C8）
    # 更宽音域的检查位（默认配置下不会触发）。
    # 别当死代码删掉——放开音域时才接上线。
    for e in doc.events:
        if not (21 <= e.pitch.semitone <= 108):
            errs.append(f"R-4 超出 88 键：{e.id} key={e.pitch.semitone}")
    # R-5 严格对齐：附件（踏板/曲线）超出内容结尾时，渲染会按结尾截断
    content_end = sounding_end_us(doc)
    attach_end = content_end
    for p in doc.pedals:
        attach_end = max(attach_end, p.end_us or p.start_us)
    for c in getattr(doc, "curves", []):
        attach_end = max(attach_end, c.time_us)
    if attach_end > content_end + 100_000 and not getattr(doc, "trailing_silence_us", 0):
        errs.append(f"R-5 踏板/曲线比最后一个音晚结束 {(attach_end - content_end) / 1e6:.2f}s："
                    "渲染将按内容结尾对齐；若要留白请写 trailing_silence_us")

    return errs
