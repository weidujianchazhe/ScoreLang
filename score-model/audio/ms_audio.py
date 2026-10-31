# -*- coding: utf-8 -*-
"""引擎 · 听觉参数（不合成音频，只出参数表）。

契约约束（SPEC §7.3）：
  - `dynamics_permille` 是**乘性系数**，`1000 = 1.0 = MIDI velocity 64`
  - 渲染函数 f 由 calibration 显式给出：须 `f(1000) = 1.0` 且**单调**
  - `NOT_PROVIDED` 按 1000 参与计算，但**必须留痕**（参数里带 state），不得静默当"确定中性"
  - 频率：十二平均律 `440 * 2^((semitone-69)/12)`；A4 = 69 = 440Hz

本模块只输出参数，**不含波形合成**（边界外）。
"""
from __future__ import annotations

import ms_events as ev
import ms_semantics as ms

A4_SEMITONE = 69
A4_HZ = 440.0


def frequency_hz(semitone: int) -> float:
    return A4_HZ * (2.0 ** ((semitone - A4_SEMITONE) / 12.0))


def default_calibration(permille: int) -> float:
    """线性近似标定：1000→1.0，且单调。真实标定应按乐器测量曲线替换。

    注意：这只是**一个可用的占位标定**，不是斯坦威实测曲线；
    换真实数据时应保持 f(1000)=1.0 与单调，并更新 calibration_ref。
    """
    return permille / ev.DYNAMICS_NEUTRAL


def event_parameters(doc: "ev.MSDocument", calibration=None) -> list:
    """事件 → 听觉参数表（每事件一条），供音频后端消费。"""
    f = calibration or default_calibration
    if abs(f(ev.DYNAMICS_NEUTRAL) - 1.0) > 1e-9:
        raise ValueError("calibration 必须满足 f(1000) = 1.0")
    # 单调性抽检（契约要求）
    probe = [ev.DYNAMICS_MIN, 250, 500, 1000, 2000, 4000, ev.DYNAMICS_MAX]
    vals = [f(p) for p in probe]
    if any(b < a - 1e-12 for a, b in zip(vals, vals[1:])):
        raise ValueError("calibration 必须单调不减")

    out = []
    for e in doc.events:
        d = e.dynamics
        if d.state == ms.VALUE and d.permille is not None:
            amp = f(d.permille)
            state = "VALUE"
            permille = d.permille
        elif d.state == ms.NOT_PROVIDED:
            amp = f(ev.DYNAMICS_NEUTRAL)      # 计算按中性
            state = ms.NOT_PROVIDED           # 但留痕
            permille = None
        else:
            raise ValueError(f"{e.id} dynamics 状态不可用于计算：{d.state}")

        release = e.release_us
        out.append({
            "id": e.id,
            "instrument_id": e.instrument_id,
            "semitone": e.pitch.semitone,
            "freq_hz": round(frequency_hz(e.pitch.semitone), 3),
            "onset_us": e.onset_us,
            "release_us": release,
            "duration_us": None if release is None else release - e.onset_us,
            "amplitude": amp,
            "dynamics_state": state,
            "dynamics_permille": permille,
            "excitation_type": e.excitation_type,
        })
    return out


def pedal_track_parameters(doc: "ev.MSDocument") -> dict:
    """踏板 → 每 (instrument_id, kind) 的段列表（供音频后端做制音/延音）。"""
    tracks: dict = {}
    for p in doc.pedals:
        tracks.setdefault((p.instrument_id, p.kind), []).append({
            "start_us": p.start_us,
            "end_us": p.end_us,
            "depth": p.depth_permille / 1000.0,
            "scope": p.scope,
        })
    for k in tracks:
        tracks[k].sort(key=lambda s: s["start_us"])
    return {f"{pid}:{kind}": v for (pid, kind), v in tracks.items()}

# ── 合并自 ms_audio_backend.py（2026-10-22 整理） ────────────────

# -*- coding: utf-8 -*-
"""音频后端适配层（排表 III-3）。

本项目**不合成音频**（边界外）。本模块只定义"后端接口"与两个参照实现：
  - `CommandBackend`：把参数翻译成"命令表"（类似 MIDI 事件），供任何合成器/MIDI 后端消费
  - `NullBackend`：明确拒绝，并指引走 MIDI 导出

设计约束：
  - 适配层**不做**音色/混响/采样规则（那是后端的事）
  - 力度→振幅必须经 `calibration`，且 `ms_audio` 已强制 `f(1000)=1.0` 与单调
  - `NOT_PROVIDED` 力度按锚点计算，但命令里保留 `dynamics_state`，不得丢失
"""

import ms_events as ev


class Backend:
    name = "abstract"

    def render(self, doc: "ev.MSDocument", calibration=None):
        raise NotImplementedError


class CommandBackend(Backend):
    """把 MS 翻译成"可执行命令表"（note on/off + 踏板），不产声音。"""
    name = "commands"

    def render(self, doc: "ev.MSDocument", calibration=None) -> dict:
        params = event_parameters(doc, calibration)
        commands = []
        for p in params:
            commands.append({
                "op": "note_on",
                "at_us": p["onset_us"],
                "piano": p["instrument_id"],
                "key": p["semitone"],
                "freq_hz": p["freq_hz"],
                "amplitude": p["amplitude"],
                "dynamics_state": p["dynamics_state"],
            })
            if p["release_us"] is not None:
                commands.append({
                    "op": "note_off", "at_us": p["release_us"],
                    "piano": p["instrument_id"], "key": p["semitone"],
                })
            else:
                commands.append({
                    "op": "sustain_until_end", "at_us": p["onset_us"],
                    "piano": p["instrument_id"], "key": p["semitone"],
                })
        for track, segs in pedal_track_parameters(doc).items():
            pid, kind = track.split(":")
            for s in segs:
                commands.append({"op": "pedal", "at_us": s["start_us"], "piano": int(pid),
                                 "kind": kind, "depth": s["depth"],
                                 "end_us": s["end_us"], "scope": s["scope"]})
        commands.sort(key=lambda c: (c["at_us"], 0 if c["op"] == "note_off" else 1))
        return {"backend": self.name, "commands": commands,
                "note_on_count": sum(1 for c in commands if c["op"] == "note_on")}


class NullBackend(Backend):
    """明确不做：本项目不含音频合成。"""
    name = "null"

    def render(self, doc: "ev.MSDocument", calibration=None):
        raise RuntimeError(
            "本项目不合成音频（边界外）。请改用 MIDI 导出：`mscli.py export <file> --time-base <µs>`，"
            "再用任意 MIDI 播放器试听。")


BACKENDS = {"commands": CommandBackend, "null": NullBackend}


def get_backend(name: str) -> Backend:
    if name not in BACKENDS:
        raise KeyError(f"未知后端：{name!r}（允许 {sorted(BACKENDS)}）")
    return BACKENDS[name]()


def available() -> list:
    return sorted(BACKENDS)
