# -*- coding: utf-8 -*-
"""MIDI 导出与回读。"""
from __future__ import annotations

import ms_events as ev

PPQ = 480                      # ticks per quarter
CC_SUSTAIN, CC_SOSTENUTO, CC_UNA_CORDA = 64, 66, 67
CC_SWELL, CC_HIHAT = 11, 4
PEDAL_CC = {"sustain": CC_SUSTAIN, "sostenuto": CC_SOSTENUTO, "una_corda": CC_UNA_CORDA,
            "swell": CC_SWELL, "hihat": CC_HIHAT}
# tuning（竖琴调音踏板）没有对应 CC：改变的是音高，不是控制量 → 记入报告，不静默丢
DYN_ANCHOR_VEL = 64            # 1000‰ ↔ velocity 64


# ── 基础编码 ────────────────────────────────────────────────

def _varlen(n: int) -> bytes:
    if n < 0:
        raise ValueError("delta 不能为负")
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.insert(0, 0x80 | (n & 0x7F))
        n >>= 7
    return bytes(out)


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


def velocity_of(permille: int | None) -> int:
    if permille is None:
        return DYN_ANCHOR_VEL
    v = round(permille * DYN_ANCHOR_VEL / 1000)
    return max(1, min(127, v))


def pedal_value(depth_permille: int) -> int:
    return max(0, min(127, round(depth_permille * 127 / 1000)))


def us_to_tick(us: int, time_base_us: int, ppq: int = PPQ) -> int:
    return int(round(us * ppq / time_base_us))


# ── 导出 ────────────────────────────────────────────────────

DRUM_CHANNEL = 9          # 0-based：MIDI 通道 10（GM 鼓组）
MELODIC_SLOTS = [c for c in range(16) if c != DRUM_CHANNEL]


def _spec_of(doc, iid: int) -> dict:
    """实例号 → 能力（按 **id** 取；未声明乐器时按单钢琴）。"""
    import ms_instruments as reg
    inst = ev.instrument_of(doc, iid)
    if inst is None:
        return reg.resolve("acoustic_grand_piano")
    try:
        return reg.resolve(inst.type, inst.subtype)
    except KeyError:
        return reg.resolve("acoustic_grand_piano")


def _groups(doc) -> list[dict]:
    """按通道策略分组：per_instance 每实例一组；per_section 按 section（无则类型+子类型）。"""
    n = len(doc.instruments) if doc.instruments else (doc.piano_count or 1)
    used = {e.instrument_id for e in doc.events} | {p.instrument_id for p in doc.pedals}
    declared = ev.declared_instrument_ids(doc)
    ids = sorted(x for x in used if isinstance(x, int) and x in declared) or [1]
    groups = {}
    for iid in ids:
        inst = ev.instrument_of(doc, iid)
        if doc.channels == "per_section":
            key = (getattr(inst, "section", None)
                   or f"{getattr(inst, 'type', 'acoustic_grand_piano')}/"
                      f"{getattr(inst, 'subtype', None) or '-'}")
        else:
            key = f"P{iid}"
        groups.setdefault(key, []).append(iid)
    out = []
    for key, members in groups.items():
        spec = _spec_of(doc, members[0])
        out.append({"key": key, "members": members, "spec": spec})
    return out


def _allocate(groups) -> tuple[list, list]:
    """分配 (文件号, 通道)。返回 (channels: {instrument_id: (file, ch)}, merges)。"""
    files = []          # 每个文件：{0..15}
    channels = {}
    merges = []
    for g in groups:
        ch = None
        for fi, slots in enumerate(files):
            if g["spec"]["category"] == "percussion":
                if DRUM_CHANNEL not in slots:
                    ch = DRUM_CHANNEL
            else:
                free = [c for c in MELODIC_SLOTS if c not in slots]
                if free:
                    ch = free[0]
            if ch is not None:
                slots.add(ch)
                break
        if ch is None:
            slots = set()
            ch = DRUM_CHANNEL if g["spec"]["category"] == "percussion" else MELODIC_SLOTS[0]
            slots.add(ch)
            files.append(slots)
        for iid in g["members"]:
            channels[iid] = (len(files) - 1, ch)
        if len(g["members"]) > 1:
            merges.append({"group": g["key"], "members": g["members"], "channel": ch})
    return channels, merges


def _program_change(ch: int, program: int) -> bytes:
    return bytes([0xC0 | ch, max(0, min(127, program))])


def write_midi_files(doc: "ev.MSDocument", *, time_base_us: int, ppq: int = PPQ,
                     strict: bool = False, tempo_map=None) -> tuple:
    """返回 (files: list[bytes], report)。每个文件最多 16 通道；超出自动开下一个。

    `tempo_map` = `[(tick, 微秒/四分音符), ...]`：给了就按点写 FF 51（支持渐快渐慢）。
    """
    if time_base_us <= 0:
        raise ValueError("time_base_us 必须为正（MIDI 需要把微秒换成 tick）")

    violations = ev.check_realization(doc)
    pedal_skipped: list = []
    import ms_playability as _pl
    play = _pl.check_playability(doc)
    if strict and (violations or play):
        raise ValueError("文档在演奏收束上不可弹：" + "；".join((violations + play)[:3]))

    groups = _groups(doc)
    chmap, merges = _allocate(groups)
    nfiles = max((f for f, _ in chmap.values()), default=0) + 1

    reports = []
    files = []
    for fi in range(nfiles):
        raw = []          # (tick, order, bytes)
        report = {"sustaining_note_offs": [], "not_provided_dynamics": [],
                  "channels": {}, "realization": list(violations),
                  "programs": {}, "drums": [], "actions_exported": []}
        # Program Change：每个用到的通道一条，tick 0
        for g in groups:
            members = [m for m in g["members"] if chmap.get(m, (None,))[0] == fi]
            if not members:
                continue
            _f, ch = chmap[members[0]]
            if g["spec"]["category"] == "percussion":
                report["drums"].append(ch)
            else:
                prog = g["spec"]["program"]
                if prog is not None:          # 人声声部（EXTENDED）无 GM program
                    report["programs"][ch] = prog
                    raw.append((0, 0, _program_change(ch, prog)))

        end_us = 0
        for e in doc.events:
            end_us = max(end_us, e.release_us if e.release_us is not None else e.onset_us)
        for p in doc.pedals:
            end_us = max(end_us, p.end_us if p.end_us is not None else p.start_us)

        for e in doc.events:
            f, ch = chmap.get(e.instrument_id, (None, None))
            if f != fi:
                continue
            report["channels"][e.instrument_id] = ch
            on = us_to_tick(e.onset_us, time_base_us, ppq)
            if e.release_us is None:
                off = us_to_tick(end_us, time_base_us, ppq)
                report["sustaining_note_offs"].append({"id": e.id, "off_tick": off})
            else:
                off = us_to_tick(e.release_us, time_base_us, ppq)
            d = e.dynamics
            if d.state == "NOT_PROVIDED" or d.permille is None:
                report["not_provided_dynamics"].append(e.id)
                vel = DYN_ANCHOR_VEL
            else:
                vel = velocity_of(d.permille)
            note = max(0, min(127, e.pitch.semitone))
            raw.append((on, 1, bytes([0x90 | ch, note, vel])))
            raw.append((max(off, on + 1), 0, bytes([0x80 | ch, note, 64])))

        for p in doc.pedals:
            f, ch = chmap.get(p.instrument_id, (None, None))
            if f != fi:
                continue
            if p.kind in PEDAL_CC:
                cc = PEDAL_CC[p.kind]
                t_on = us_to_tick(p.start_us, time_base_us, ppq)
                raw.append((t_on, 2, bytes([0xB0 | ch, cc, pedal_value(p.depth_permille)])))
                if p.end_us is not None:
                    t_off = us_to_tick(p.end_us, time_base_us, ppq)
                    raw.append((t_off, 2, bytes([0xB0 | ch, cc, 0])))
                continue
            # 没有 CC 的踏板：调音写 RPN（音分），弱音器写文本 meta——不静默丢
            t_on = us_to_tick(p.start_us, time_base_us, ppq)
            if p.kind == "tuning":
                cents = int(round((p.depth_permille - 500) / 5.0))
                val = max(0, min(16383, 8192 + cents * 8192 // 100))
                raw.append((t_on, 2, bytes([0xB0 | ch, 101, 0])))       # RPN 1 = fine tuning
                raw.append((t_on, 2, bytes([0xB0 | ch, 100, 1])))
                raw.append((t_on, 2, bytes([0xB0 | ch, 6, val >> 7])))
                raw.append((t_on, 2, bytes([0xB0 | ch, 38, val & 0x7F])))
                raw.append((t_on, 2, bytes([0xB0 | ch, 101, 127])))     # RPN null
                raw.append((t_on, 2, bytes([0xB0 | ch, 100, 127])))
                raw.append((t_on, 1, b"\xFF\x01" + _varlen(16) +
                            f"tuning {cents:+d}c".encode("ascii")))
            else:
                txt = f"{p.kind} on".encode("ascii")
                raw.append((t_on, 1, b"\xFF\x01" + _varlen(len(txt)) + txt))

        # 演奏动作：MIDI 没有对等控制量 → 写 FF 01 文本 meta（DAW 里可见、可核对）
        on_tick = {}
        for e in doc.events:
            f, _ch = chmap.get(e.instrument_id, (None, None))
            if f == fi:
                on_tick[e.id] = us_to_tick(e.onset_us, time_base_us, ppq)
        for t in getattr(doc, "turns", []):
            if t.event_id not in on_tick:
                continue
            txt = f"turn:{t.kind} {t.strength}".encode("ascii")
            raw.append((on_tick[t.event_id], 1, b"\xFF\x01" + _varlen(len(txt)) + txt))
            report["actions_exported"].append({"id": t.event_id, "kind": t.kind})

        # 速度：默认单 tempo；给了 tempo_map（[(tick, µs/四分音符)]）就按点写，支持渐快渐慢
        if not tempo_map:
            raw.append((0, 0, b"\xFF\x51\x03" + int(time_base_us).to_bytes(3, "big")))
        for tk, us in sorted(tempo_map or ()):
            raw.append((max(0, int(tk)), 0,
                        b"\xFF\x51\x03" + int(us).to_bytes(3, "big")))

        raw.sort(key=lambda x: (x[0], x[1]))
        body = bytearray()
        last = 0
        for tick, _order, payload in raw:
            body += _varlen(tick - last)
            body += payload
            last = tick
        # 严格对齐：EOT 落在「内容结尾 + 显式留白」，不留隐式空白
        total_us = ev.total_end_us(doc) if hasattr(ev, "total_end_us") else max(
            [e.release_us or e.onset_us for e in doc.events] + [0])
        end_tick = us_to_tick(total_us, time_base_us, ppq)
        body += _varlen(max(0, end_tick - last)) + b"\xFF\x2F\x00"
        header = _chunk(b"MThd", (1).to_bytes(2, "big") + (1).to_bytes(2, "big") + ppq.to_bytes(2, "big"))
        files.append(header + _chunk(b"MTrk", bytes(body)))
        reports.append(report)

    all_report = {
        "files": len(files),
        "channel_map": {iid: {"file": f + 1, "channel": ch} for iid, (f, ch) in chmap.items()},
        "channels": {iid: ch for iid, (_f, ch) in chmap.items()},
        "channel_merged": merges,
        "per_file": reports,
        "realization": list(violations),
        "playability": list(play),
        "pedal_skipped": pedal_skipped,
        "sustaining_note_offs": [x for r in reports for x in r["sustaining_note_offs"]],
        "not_provided_dynamics": [x for r in reports for x in r["not_provided_dynamics"]],
        "actions_exported": [x for r in reports for x in r.get("actions_exported", [])],
    }
    return files, all_report


def write_midi(doc: "ev.MSDocument", *, time_base_us: int, ppq: int = PPQ,
               strict: bool = False, tempo_map=None) -> tuple:
    """兼容包装：返回 (第一个文件的字节, report)。多文件时用 write_midi_files。"""
    files, report = write_midi_files(doc, time_base_us=time_base_us, ppq=ppq,
                                     strict=strict, tempo_map=tempo_map)
    return files[0], report


# ── 回读（III-2 用） ────────────────────────────────────────

def read_midi(data: bytes) -> dict:
    if data[:4] != b"MThd":
        raise ValueError("不是 SMF：缺少 MThd")
    fmt = int.from_bytes(data[8:10], "big")
    ntrks = int.from_bytes(data[10:12], "big")
    ppq = int.from_bytes(data[12:14], "big")
    pos = 14
    tempo_us = None
    notes, ccs = [], []
    skipped = 0
    for _ in range(ntrks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("轨道块缺失")
        length = int.from_bytes(data[pos + 4:pos + 8], "big")
        chunk = data[pos + 8:pos + 8 + length]
        pos += 8 + length
        i, tick, running = 0, 0, None
        while i < len(chunk):
            delta, i = _read_varlen(chunk, i)
            tick += delta
            status = chunk[i]
            if status == 0xFF:
                meta = chunk[i + 1]
                ln, i = _read_varlen(chunk, i + 2)
                payload = chunk[i:i + ln]
                i += ln
                if meta == 0x51 and ln == 3:
                    tempo_us = int.from_bytes(payload, "big")
                continue
            if status & 0x80:
                running = status
                i += 1
            elif running is None:
                raise ValueError("running status 缺失")
            kind = running & 0xF0
            ch = running & 0x0F
            if kind in (0x80, 0x90):
                note, vel = chunk[i], chunk[i + 1]
                i += 2
                notes.append({"tick": tick, "ch": ch, "note": note, "vel": vel,
                              "on": kind == 0x90 and vel > 0})
            elif kind == 0xB0:
                cc, val = chunk[i], chunk[i + 1]
                i += 2
                ccs.append({"tick": tick, "ch": ch, "cc": cc, "val": val})
            elif kind in (0xC0, 0xD0):          # 音色切换 / 通道触后：1 字节数据，跳过并记数
                i += 1
                skipped += 1
            elif kind == 0xE0:                  # 弯音：2 字节数据
                i += 2
                skipped += 1
            elif kind in (0xF0, 0xF7):          # SysEx：按长度跳过
                ln, i = _read_varlen(chunk, i)
                i += ln
                skipped += 1
            else:
                raise ValueError(f"不支持的 MIDI 事件：{hex(kind)}")
    return {"format": fmt, "ntrks": ntrks, "ppq": ppq, "tempo_us": tempo_us,
            "notes": notes, "ccs": ccs, "skipped": skipped}


def _read_varlen(buf: bytes, i: int) -> tuple:
    n = 0
    while True:
        b = buf[i]
        i += 1
        n = (n << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return n, i
