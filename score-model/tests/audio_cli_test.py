# -*- coding: utf-8 -*-
"""音频 CLI（P8-2）：`mscli audio` 能直接出 wav。"""
from __future__ import annotations

import sys as _sys
import tempfile
import wave
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_io
import ms_semantics as ms
import mscli

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


tmp = _Path(tempfile.mkdtemp())
events = []
for i, semi in enumerate([60, 62, 64, 65, 67]):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    events.append(ev.Event(
        id=f"L{i + 1:08d}", instrument_id=1,
        onset_us=i * 500_000, release_us=(i + 1) * 500_000,
        pitch=ev.Pitch(step[0], 1 if "#" in step else 0, semi // 12 - 1, semi),
        release_state="given",
        dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured")))
src = tmp / "tiny.ms"
src.write_text(ms_io.dump(ev.MSDocument(events=events)), encoding="utf-8")

out = tmp / "tiny.wav"
rc = mscli.main(["audio", str(src), "-o", str(out)])
check("A1 命令返回 0", rc == 0, str(rc))
check("A2 wav 文件写出", out.exists() and out.stat().st_size > 1000,
      str(out.stat().st_size) if out.exists() else "缺失")

with wave.open(str(out), "rb") as w:
    frames, rate, channels = w.getnframes(), w.getframerate(), w.getnchannels()
    check("A3 是合法 wav（44.1k 采样）", rate == 44100 and channels >= 1,
          f"{rate}Hz/{channels}ch")
    secs = frames / rate
    check("A4 时长合理（5 音 × 0.5s + 尾音）", 2.0 <= secs <= 6.0, f"{secs:.2f}s")

rc2 = mscli.main(["audio", str(src)])
check("A5 不给 -o 时落在同名 .wav", rc2 == 0 and (tmp / "tiny.wav").exists())

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
