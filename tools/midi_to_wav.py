# -*- coding: utf-8 -*-
"""MIDI → WAV（FluidSynth + 后期）。**工程外工具**：引擎只出 MIDI，出声在这里。

用法：
    python tools/midi_to_wav.py piece.mid -o out/piece_concert.wav
    python tools/midi_to_wav.py some/dir -o out/album.wav        # 多文件：分轨渲染后混音

选项：
    --sf2 PATH         音色库（默认 FluidR3 GM2）
    --reverb-room R    混响房间（默认 0.75；0.9 = 大厅）
    --eq-warm          温暖 EQ（<250Hz +2.5dB，~350Hz +1.5dB，>6.5k −2dB）
    --saturate         tanh 轻饱和（drive 1.15）
    --true-peak DB     归一化目标（默认 −1.5 dBFS，4 倍过采样估真峰值）
    --no-post          不做后期（只要 FluidSynth 原始输出）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

# 第三方工具/音色库放在工作区外的同级目录（约定：<workspace>/../tools）；
# 可用环境变量 MIDI_TO_WAV_TOOLS 覆盖，换机器/换目录不用改代码。
_TOOLS_ROOT = Path(os.environ.get("MIDI_TO_WAV_TOOLS")
                   or Path(__file__).resolve().parent.parent.parent / "tools")

FLUID = _TOOLS_ROOT / "fluidsynth" / "fluidsynth-v2.6.1-win10-x64-cpp11" / "bin" / "fluidsynth.exe"
SF2_CANDIDATES = [
    _TOOLS_ROOT / "soundfonts" / "arachno" / "Arachno SoundFont - Version 1.0.sf2",
    _TOOLS_ROOT / "soundfonts" / "generaluser" / "GeneralUserGS.sf2",
    _TOOLS_ROOT / "soundfonts" / "MuseScore_General.sf3",
    _TOOLS_ROOT / "soundfonts" / "fluid" / "FluidR3 GM2-2.SF2",
]
SFZ_CANDIDATES = [
    _TOOLS_ROOT / "soundfonts" / "salamander" / "SalamanderGrandPianoV3_44.1khz16bit"
    / "SalamanderGrandPianoV3.sfz",
    _TOOLS_ROOT / "soundfonts" / "salamander" / "SalamanderGrandPiano.sfz",
]
SFIZZ = _TOOLS_ROOT / "sfizz" / "bin" / "Release" / "sfizz_render.exe"
SR = 44100


def find_fluidsynth() -> Path:
    if FLUID.exists():
        return FLUID
    exe = shutil.which("fluidsynth")
    if not exe:
        raise SystemExit("找不到 fluidsynth（检查 --fluidsynth 或 PATH）")
    return Path(exe)


def render_one(mid: Path, sf2: Path, room: float, out_wav: Path, gain: float = 0.9) -> None:
    cmd = [str(find_fluidsynth()), "-ni", "-F", str(out_wav), "-r", str(SR), "-g", str(gain),
           "-o", "synth.reverb.active=1",
           "-o", f"synth.reverb.room-size={room}",
           "-o", "synth.reverb.width=0.9",
           "-o", "synth.reverb.level=0.7",
           "-o", "synth.reverb.damp=0.3",
           "-o", "synth.chorus.active=0",
           str(sf2), str(mid)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_wav.exists():
        raise SystemExit(f"FluidSynth 失败：{res.stderr[-400:]}")


def render_sfz(mid: Path, sfz: Path, out_wav: Path) -> None:
    """sfizz_render：SFZ + MIDI → WAV。

    必须带 --use-eot：sfizz_render 默认**不按 End of Track 停止**，会一直
    往下渲染（实测 4.5 分钟的曲子写到 772MB / 73 分钟仍在写，把构建挂死）。
    加了之后 266 秒的音频 25 秒渲染完并正常退出。
    """
    cmd = [str(SFIZZ), "--use-eot", "--sfz", str(sfz), "--midi", str(mid),
           "--wav", str(out_wav), "--samplerate", str(SR)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_wav.exists():
        raise SystemExit(f"sfizz 失败：{res.stderr[-300:]}")



def midi_programs(path: Path) -> set:
    """扫出 MIDI 里用到的 Program（音色号）。不依赖第三方库。"""
    data = path.read_bytes()
    if data[:4] != b"MThd":
        return set()
    programs = set()
    i = 14
    while i + 8 <= len(data):
        if data[i:i + 4] != b"MTrk":
            break
        length = int.from_bytes(data[i + 4:i + 8], "big")
        body = data[i + 8:i + 8 + length]
        i += 8 + length
        j = 0
        status = None
        while j < len(body):
            # delta
            while j < len(body) and body[j] & 0x80:
                j += 1
            j += 1
            if j >= len(body):
                break
            b = body[j]
            if b == 0xFF:
                j += 1
                if j >= len(body):
                    break
                mtype = body[j]; j += 1
                while j < len(body) and body[j] & 0x80:
                    j += 1
                ln = body[j]; j += 1
                j += ln
                continue
            if b in (0xF0, 0xF7):
                j += 1
                while j < len(body) and body[j] & 0x80:
                    j += 1
                ln = body[j]; j += 1
                j += ln
                continue
            if b & 0x80:
                status = b
                j += 1
            if status is None:
                break
            kind = status & 0xF0
            if kind == 0xC0:
                programs.add(body[j]); j += 1
            elif kind in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                j += 2
            else:
                j += 1
    return programs

def pick_engine(choice: str, midi: Path | None = None):
    """返回 (engine, sf2|sfz)。

    auto 规则：
      · 只有钢琴（Program 0 / 无 Program）+ Salamander 可用 → sfizz
      · 用到一个以上音色（如提琴 Program 40）→ FluidSynth（GM 音色库才能分辨乐器）
    """
    sfz = next((p for p in SFZ_CANDIDATES if p.exists()), None)
    sf2 = next((p for p in SF2_CANDIDATES if p.exists() and p.stat().st_size > 100_000), None)
    programs = midi_programs(midi) if midi else set()
    piano_only = not programs or programs <= {0}
    if choice == "auto" and not piano_only:
        choice = "fluid"
    if choice == "sfizz" or (choice == "auto" and sfz and SFIZZ.exists()):
        if not (sfz and SFIZZ.exists()):
            raise SystemExit("选了 sfizz，但缺少 sfizz_render.exe 或 Salamander .sfz")
        return "sfizz", sfz
    if not sf2:
        raise SystemExit("找不到可用的 SF2/SF3 音色库")
    return "fluid", sf2


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit(f"只支持 16-bit WAV：{path}")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch == 2:
        data = data.reshape(-1, 2)
    else:
        data = np.repeat(data[:, None], 2, axis=1)
    return data


def midi_end_seconds(mid: Path) -> float | None:
    """按 MIDI 的 tempo 与最后事件 tick 算出"应有长度"（秒）。用于严格对齐/剪尾。"""
    data = mid.read_bytes()
    if data[:4] != b"MThd":
        return None
    hlen = int.from_bytes(data[4:8], "big")
    ppq = int.from_bytes(data[12:14], "big")
    if not ppq:
        return None
    i = 8 + hlen
    tempo_us = 500_000
    max_tick = 0
    while i + 8 <= len(data):
        if data[i:i + 4] != b"MTrk":
            break
        length = int.from_bytes(data[i + 4:i + 8], "big")
        body = data[i + 8:i + 8 + length]
        i += 8 + length
        j = 0
        tick = 0
        status = None
        while j < len(body):
            delta = 0
            while j < len(body) and body[j] & 0x80:
                delta = (delta << 7) | (body[j] & 0x7F)
                j += 1
            if j >= len(body):
                break
            delta = (delta << 7) | body[j]
            j += 1
            tick += delta
            if j >= len(body):
                break
            b = body[j]
            if b == 0xFF:
                j += 1
                mtype = body[j]; j += 1
                ln = 0
                while j < len(body) and body[j] & 0x80:
                    ln = (ln << 7) | (body[j] & 0x7F)
                    j += 1
                ln = (ln << 7) | body[j]; j += 1
                if mtype == 0x51 and ln == 3:
                    tempo_us = int.from_bytes(body[j:j + 3], "big")
                elif mtype == 0x2F:
                    break
                j += ln
                continue
            if b in (0xF0, 0xF7):
                j += 1
                ln = 0
                while j < len(body) and body[j] & 0x80:
                    ln = (ln << 7) | (body[j] & 0x7F)
                    j += 1
                ln = (ln << 7) | body[j]; j += 1
                j += ln
                continue
            if b & 0x80:
                status = b
                j += 1
            max_tick = max(max_tick, tick)
            if status is None:
                break
            kind = status & 0xF0
            if kind == 0xC0:
                j += 1
            else:
                j += 2
    return max_tick * (tempo_us / ppq) / 1e6


def trim_tail(data: np.ndarray, keep: float = 0.7, floor: float = 2e-3) -> np.ndarray:
    """剪掉尾部静音，保留 keep 秒余量（防切掉自然衰减）。"""
    mono = np.abs(data).max(axis=1)
    idx = np.nonzero(mono > floor)[0]
    if len(idx) == 0:
        return data
    end = min(len(mono), idx[-1] + int(keep * SR))
    return data[:end]


def write_wav(path: Path, data: np.ndarray) -> None:
    pcm = np.clip(data, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm16.tobytes())


def eq_warm(x: np.ndarray) -> np.ndarray:
    """频域搁架式 EQ：低频抬、350Hz 微抬、>6.5k 削。"""
    n = len(x)
    if n == 0:
        return x
    spec = np.fft.rfft(x, axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    gain = np.ones_like(freqs, dtype=np.float32)
    gain += 2.5 / 20 * np.log(10) * (freqs < 250)
    gain += 1.5 / 20 * np.log(10) * ((freqs >= 250) & (freqs < 500))
    gain -= 2.0 / 20 * np.log(10) * (freqs > 6500)
    spec *= gain[:, None]
    return np.fft.irfft(spec, n=n, axis=0).astype(np.float32)


def true_peak(x: np.ndarray, factor: int = 4) -> float:
    """4 倍线性插值估真峰值。"""
    if len(x) < 2:
        return float(np.max(np.abs(x))) if len(x) else 0.0
    t = np.linspace(0, len(x) - 1, (len(x) - 1) * factor + 1)
    up = np.stack([np.interp(t, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1)
    return float(np.max(np.abs(up)))


def normalize(x: np.ndarray, db: float = -1.5) -> np.ndarray:
    peak = true_peak(x)
    if peak <= 1e-9:
        return x
    target = 10 ** (db / 20)
    return (x * (target / peak)).astype(np.float32)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MIDI → WAV（FluidSynth + 后期）")
    ap.add_argument("input", help=".mid 文件或目录")
    ap.add_argument("-o", "--out", required=True, help="输出 WAV")
    ap.add_argument("--engine", default="auto", choices=("auto", "fluid", "sfizz"),
                    help="auto：Salamander+sfizz > MuseScore_General > FluidR3")
    ap.add_argument("--sf2", default=None, help="指定 SF2/SF3（默认按优先级）")
    ap.add_argument("--reverb-room", type=float, default=0.75)
    ap.add_argument("--eq-warm", action="store_true")
    ap.add_argument("--saturate", action="store_true")
    ap.add_argument("--true-peak", type=float, default=-1.5)
    ap.add_argument("--no-post", action="store_true")
    ap.add_argument("--trim", action="store_true", default=True, help="剪掉尾部静音（默认开）")
    ap.add_argument("--no-trim", dest="trim", action="store_false")
    ap.add_argument("--trim-keep", type=float, default=0.7, help="剪尾后保留的余量秒数")
    args = ap.parse_args(argv)

    src = Path(args.input)
    mids = sorted(src.rglob("*.mid")) if src.is_dir() else [src]
    mids = [m for m in mids if m.suffix.lower() == ".mid"]
    if not mids:
        raise SystemExit("没有 .mid 文件")

    engine, lib = pick_engine(args.engine, Path(args.input) if Path(args.input).is_file() else None)
    if args.sf2:
        engine, lib = "fluid", Path(args.sf2)
    print(f"引擎 {engine} · 音色 {Path(lib).name}")

    out = Path(args.out)
    with tempfile.TemporaryDirectory() as td:
        tracks = []
        for i, mid in enumerate(mids):
            wav = Path(td) / f"track_{i}.wav"
            if engine == "sfizz":
                render_sfz(mid, lib, wav)
            else:
                render_one(mid, lib, args.reverb_room, wav)
            tracks.append(read_wav(wav))
            print(f"渲染 {mid.name} → {tracks[-1].shape[0] / SR:.1f}s")
        n = max(t.shape[0] for t in tracks)
        mix = np.zeros((n, 2), dtype=np.float32)
        for t in tracks:
            mix[: t.shape[0]] += t / max(1, len(tracks)) ** 0.5

    if not args.no_post:
        if args.eq_warm:
            mix = eq_warm(mix)
        if args.saturate:
            mix = np.tanh(mix * 1.15).astype(np.float32)
        mix = normalize(mix, args.true_peak)

    # 严格对齐：优先按 MIDI 的"应有长度"剪，剪不到再退回能量阈值
    if args.trim:
        declared = max([(midi_end_seconds(m) or 0.0) for m in mids] + [0.0])
        if declared > 0:
            end = min(mix.shape[0], int((declared + args.trim_keep) * SR))
            mix = mix[:end]
        else:
            mix = trim_tail(mix, keep=args.trim_keep)

    write_wav(out, mix)
    print(f"已写出 {out}（{mix.shape[0] / SR:.1f}s，{out.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
