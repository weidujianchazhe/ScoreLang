# -*- coding: utf-8 -*-
"""MS 数据结构（门面 re-export）。真正的定义在 `core/ms_model.py`。"""
from __future__ import annotations

from ms_model import (  # noqa: F401
    MSDocument, Event, Instrument, PedalSegment, TurnPoint, CurvePoint,
    VoiceSegment, Dynamics, Pitch,
    content_end_us, sustain_end_us, pedal_applies,
    PEDAL_REPRESS_TOL_US, KEY_MIN, KEY_MAX, CONSTRAINT_MODES, PEDAL_KINDS,
    PEDAL_SCOPES,
)

__all__ = ["MSDocument", "Event", "Instrument", "PedalSegment", "TurnPoint",
           "CurvePoint", "VoiceSegment", "Dynamics", "Pitch",
           "content_end_us", "sustain_end_us", "pedal_applies",
           "PEDAL_REPRESS_TOL_US", "KEY_MIN", "KEY_MAX", "CONSTRAINT_MODES",
           "PEDAL_KINDS", "PEDAL_SCOPES"]
