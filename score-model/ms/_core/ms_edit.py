# -*- coding: utf-8 -*-
"""引擎 · 编辑通道（六铁律 E1–E6）。

设计（`RENDERER_AND_EDITOR_SCOPE.md`）：
  E1 纯函数：旧文档 → 新文档；**不修改入参**、不写文件
  E2 提交前校验：每次操作后 `ms_events.validate()`；失败返回**原文档 + 错误**
  E3 不得伪造来源：手动编辑只能用 `notated_inferred`，禁 `measured` / `midi_inverted`
  E4 id 不复用：update 不改 id；delete 把 id 记入 `gaps.retired_id`，分配器永不复用
  E5 不得仅为显示改结构：不提供自动吸附/自动修正
  E6 撤销：丢弃新文档即可；旧文档本身必须仍合法（纯函数保证）
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import ms_dynamics_levels as dl
import ms_events as ev
import ms_semantics as ms

MANUAL_SRC = "notated_inferred"
_FORBIDDEN_MANUAL_SRCS = ("measured", "midi_inverted")


@dataclass(frozen=True)
class EditResult:
    ok: bool
    doc: "ev.MSDocument"          # 失败时即原文档（同一对象，未被修改）
    errors: tuple = ()
    changed_id: str | None = None


def _copy_doc(doc: "ev.MSDocument") -> "ev.MSDocument":
    """复制 MSDocument 的**全部**字段（编辑/撤销不得静默丢数据）。"""
    return ev.MSDocument(
        piano_count=doc.piano_count,
        constraint_mode=doc.constraint_mode,
        events=list(doc.events),
        pedals=list(doc.pedals),
        gaps=[dict(g) if isinstance(g, dict) else g for g in doc.gaps],
        retired_ids=list(getattr(doc, "retired_ids", ())),
        channels=getattr(doc, "channels", "per_instance"),
        instruments=list(getattr(doc, "instruments", ()) or ()),
        curves=list(getattr(doc, "curves", ()) or ()),
        turns=list(getattr(doc, "turns", ()) or ()),
        trailing_silence_us=int(getattr(doc, "trailing_silence_us", 0) or 0),
        segments=list(getattr(doc, "segments", ()) or ()),
    )


def _clone(doc: "ev.MSDocument") -> "ev.MSDocument":
    return _copy_doc(doc)


def _reject(doc, msg) -> EditResult:
    return EditResult(ok=False, doc=doc, errors=(msg,))


def _commit(old, new, changed_id=None) -> EditResult:
    errs = ev.validate(new)
    if errs:
        return EditResult(ok=False, doc=old, errors=tuple(errs))
    return EditResult(ok=True, doc=new, errors=(), changed_id=changed_id)


def alloc_id(doc: "ev.MSDocument", prefix: str = "e") -> str:
    """分配新 id：扫描现存 id 与已作废 id（E4：永不复用）。"""
    used = {e.id for e in doc.events}
    used.update(getattr(doc, "retired_ids", ()))
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


# ── 事件 ─────────────────────────────────────────────────────

def add_event(doc, *, pitch, onset_us, release_us=None, release_state="given",
              dynamics=None, instrument_id=1, excitation_type="impulse",
              is_grace=False, event_id=None) -> EditResult:
    new = _clone(doc)
    eid = event_id or alloc_id(new)
    if any(e.id == eid for e in new.events):
        return _reject(doc, f"E4 id 已存在：{eid}")
    new.events.append(ev.Event(id=eid, instrument_id=instrument_id, onset_us=onset_us,
                               pitch=pitch, excitation_type=excitation_type,
                               release_us=release_us, release_state=release_state,
                               dynamics=dynamics or ev.Dynamics(ms.NOT_PROVIDED),
                               is_grace=is_grace))
    return _commit(doc, new, eid)


def update_event(doc, event_id: str, **changes) -> EditResult:
    if "id" in changes:
        return _reject(doc, "不允许修改事件 id（引用会断链）")
    idx = next((i for i, e in enumerate(doc.events) if e.id == event_id), None)
    if idx is None:
        return _reject(doc, f"事件不存在：{event_id}")
    new = _clone(doc)
    new.events[idx] = replace(doc.events[idx], **changes)
    return _commit(doc, new, event_id)


def delete_event(doc, event_id: str) -> EditResult:
    if not any(e.id == event_id for e in doc.events):
        return _reject(doc, f"事件不存在：{event_id}")
    new = _clone(doc)
    new.events = [e for e in new.events if e.id != event_id]
    new.retired_ids.append(event_id)          # E4：作废簿记（不再借用 gaps）
    return _commit(doc, new, event_id)


def set_dynamics(doc, event_id: str, permille: int, *, src: str | None = None,
                 scale: str = "relative_permille", calibration_ref: str = "manual") -> EditResult:
    """直接给定数值。

    `src=None` 表示"直接给定的数值，无推导过程"（推导/来源属渲染或写谱层，
    不由模型承载；见 FIRST_PRINCIPLES P3）。显式传 `measured`/`midi_inverted`
    仍会被拒——那两者意味着"测出来的"，只能由测量管线写入。
    """
    if src in _FORBIDDEN_MANUAL_SRCS:
        return _reject(doc, f"E3 手动编辑不得标 {src}（那表示'测出来的'）")
    if src is not None and src not in ev.DYNAMICS_SRCS:
        return _reject(doc, f"E3 src 非法：{src}")
    dyn = ev.Dynamics(ms.VALUE, permille, scale, calibration_ref, src)
    return update_event(doc, event_id, dynamics=dyn)


def set_dynamics_level(doc, event_id: str, level: str,
                       calibration_ref: str = "dyn-levels-v1") -> EditResult:
    """写谱侧：等级 → 数值（经默认等级表），来源记 notated_inferred。

    第一原理 P3：换算只发生在写谱侧；MS 里存的是**数值**，不是等级。
    """
    try:
        permille = dl.level_to_permille(level)
    except KeyError as e:
        return _reject(doc, f"P3 等级非法：{e}")
    return set_dynamics(doc, event_id, permille, src=MANUAL_SRC,
                        calibration_ref=calibration_ref)


# ── 踏板 ─────────────────────────────────────────────────────

def add_pedal(doc, *, kind, start_us, end_us=None, depth_permille=1000,
              instrument_id=None, scope="mechanical", targets=None) -> EditResult:
    """加踏板段。`instrument_id` **必须给出**，且必须是本曲声明过的乐器 id。

    一个踏板只属于一台乐器；不给乐器就是要靠猜——直接拒绝，不默认 1。
    """
    if instrument_id is None:
        return _reject(doc, "P2 加踏板必须指明 instrument_id（本曲声明过的乐器 id）")
    if instrument_id not in ev.declared_instrument_ids(doc):
        return _reject(doc, f"P2 本曲没有声明乐器 P{instrument_id}")
    new = _clone(doc)
    seg = ev.PedalSegment(instrument_id=instrument_id, kind=kind, start_us=start_us,
                          end_us=end_us, depth_permille=depth_permille,
                          scope=scope, targets=targets)
    # 新段按现有踏板 id 续编（D+8 位），不和已有 id 撞
    seg = ev.assign_pedal_ids(list(new.pedals) + [seg])[-1]
    new.pedals.append(seg)
    return _commit(doc, new, seg.id)


def update_pedal(doc, index: int, **changes) -> EditResult:
    if not (0 <= index < len(doc.pedals)):
        return _reject(doc, f"踏板段不存在：index={index}")
    new = _clone(doc)
    new.pedals[index] = replace(doc.pedals[index], **changes)
    return _commit(doc, new)


def delete_pedal(doc, index: int) -> EditResult:
    if not (0 <= index < len(doc.pedals)):
        return _reject(doc, f"踏板段不存在：index={index}")
    new = _clone(doc)
    new.pedals.pop(index)
    return _commit(doc, new)


# ── 约束档 ───────────────────────────────────────────────────

def set_constraint(doc, mode: str, piano_count: int | None = None) -> EditResult:
    new = _clone(doc)
    new.constraint_mode = mode
    if piano_count is not None:
        new.piano_count = piano_count
    return _commit(doc, new)


# ── 批量编辑（IV-2） ─────────────────────────────────────────

_SHARP_SPELL = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
                6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def _spell(semitone: int) -> "ev.Pitch":
    step, alter = _SHARP_SPELL[semitone % 12]
    return ev.Pitch(step, alter, semitone // 12 - 1, semitone)


def transpose(doc, semitones: int) -> EditResult:
    """整体移调。

    注意：**拼写会被重新按升号规范化**（E♭ 移调后可能变 D♯）——这是编辑带来的
    表示变化，不是事实丢失；若需保留原拼写风格，应在调用方另行处理。
    """
    if not isinstance(semitones, int) or isinstance(semitones, bool):
        return _reject(doc, "semitones 必须是整数")
    new = _clone(doc)
    new.events = []
    for e in doc.events:
        target = e.pitch.semitone + semitones
        if not (ev.KEY_MIN <= target <= ev.KEY_MAX):
            return _reject(doc, f"移调越界：{e.id} {e.pitch.semitone}{semitones:+d}={target} "
                                f"（不在 {ev.KEY_MIN}..{ev.KEY_MAX}）")
        new.events.append(replace(e, pitch=_spell(target)))
    return _commit(doc, new)


def quantize(doc, grid_us: int, *, snap_release: bool = True) -> EditResult:
    """把起点（可选：终点）吸附到网格。吸附后若终点 ≤ 起点，终点顺延一格。"""
    if not isinstance(grid_us, int) or grid_us <= 0:
        return _reject(doc, "grid_us 必须是正整数")
    new = _clone(doc)
    new.events = []
    for e in doc.events:
        onset = int(round(e.onset_us / grid_us)) * grid_us
        release = e.release_us
        if release is not None and snap_release:
            release = int(round(release / grid_us)) * grid_us
        if release is not None and release <= onset:
            release = onset + grid_us
        new.events.append(replace(e, onset_us=onset, release_us=release))
    return _commit(doc, new)


def set_all_dynamics(doc, *, level: str | None = None, permille: int | None = None) -> EditResult:
    """批量设置力度：等级经 `dyn-levels-v1` 换算（notated_inferred）；或直接给数值。"""
    if (level is None) == (permille is None):
        return _reject(doc, "level 与 permille 必须且只能给一个")
    if level is not None:
        try:
            pm = dl.level_to_permille(level)
        except KeyError as e:
            return _reject(doc, f"等级非法：{e}")
        dyn = ev.Dynamics(ms.VALUE, pm, "relative_permille", dl.LEVELS_VERSION, MANUAL_SRC)
    else:
        if not (ev.DYNAMICS_MIN <= permille <= ev.DYNAMICS_MAX):
            return _reject(doc, f"permille 越界：{permille}")
        dyn = ev.Dynamics(ms.VALUE, permille, "relative_permille", "manual", None)
    new = _clone(doc)
    new.events = [replace(e, dynamics=dyn) for e in doc.events]
    return _commit(doc, new)

# ── 合并自 ms_undo.py（2026-10-22 整理） ────────────────

# -*- coding: utf-8 -*-
"""撤销/重做栈（排表 IV-1）。

依据：编辑层是纯函数（E1/E6），因此撤销＝**回到之前的快照**，不需要反向操作。

铁律：
  - 只有**合法文档**能进入栈（E6：撤销后的状态也必须通过 `validate()`）
  - 快照必须**与外部隔离**（容器里的 list 会被就地追加，必须复制）
  - 栈有上限；超限丢最旧的，并显式告知（不静默）
"""

import ms_events as ev


def snapshot(doc: "ev.MSDocument") -> "ev.MSDocument":
    """深一层复制：事件/踏板/缺口/作废 id 各自复制列表（元素不可变，无需再深）。"""
    return _copy_doc(doc)


class UndoStack:
    def __init__(self, initial: "ev.MSDocument", limit: int = 100):
        if limit < 2:
            raise ValueError("limit 至少为 2（需要能容纳当前与上一步）")
        errs = ev.validate(initial)
        if errs:
            raise ValueError("初始文档不合法：" + "；".join(errs))
        self._limit = limit
        self._frames = [snapshot(initial)]
        self._i = 0
        self.dropped = 0          # 因超限被丢弃的快照数（显式记录）

    # ── 查询 ──
    @property
    def depth(self) -> int:
        return len(self._frames)

    @property
    def position(self) -> int:
        return self._i

    @property
    def can_undo(self) -> bool:
        return self._i > 0

    @property
    def can_redo(self) -> bool:
        return self._i < len(self._frames) - 1

    def current(self) -> "ev.MSDocument":
        return snapshot(self._frames[self._i])

    # ── 变更 ──
    def push(self, doc: "ev.MSDocument") -> None:
        errs = ev.validate(doc)
        if errs:
            raise ValueError("不能把非法文档推入撤销栈：" + "；".join(errs))
        # 丢弃当前点之后的重做分支
        self._frames = self._frames[: self._i + 1]
        self._frames.append(snapshot(doc))
        self._i = len(self._frames) - 1
        while len(self._frames) > self._limit:
            self._frames.pop(0)
            self._i -= 1
            self.dropped += 1

    def apply(self, result, *, require_ok: bool = True) -> bool:
        """便捷：接受 `ms_edit.EditResult`；成功则入栈并返回 True。"""
        ok = getattr(result, "ok", False)
        if not ok:
            return False
        self.push(result.doc)
        return True

    def undo(self) -> "ev.MSDocument | None":
        if not self.can_undo:
            return None
        self._i -= 1
        return snapshot(self._frames[self._i])

    def redo(self) -> "ev.MSDocument | None":
        if not self.can_redo:
            return None
        self._i += 1
        return snapshot(self._frames[self._i])

    def history(self) -> list:
        """返回每帧的摘要（不含完整文档），便于日志。"""
        return [{"index": i, "events": len(d.events), "pedals": len(d.pedals),
                 "retired": len(getattr(d, "retired_ids", ()))}
                for i, d in enumerate(self._frames)]
