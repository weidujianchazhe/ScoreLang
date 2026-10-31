# -*- coding: utf-8 -*-
"""人声通道（预留接口；通道尚未实现，写谱侧的段结构已存在）。

现状：
  · ✅ 写谱侧：`ms.author.write_vocal` 能写声母/韵母段（V18 校验段结构）；
  · ⚠️ 音频通道：`audio/ms_sing.py` 有合成实验，但**未接入 `flow run`/`make_audio`**；
  · 🔜 多语言：`register_language()` 可先登记（zh/en/fr/ja/ru 已登记），
    真正支持某语言还缺音素表与演唱模型。

以后接通道时的入口（不改解析器）：
    from ms import vocal
    vocal.register_language("ko", "韩语")
    vocal.languages()          # 当前可选语言
    vocal.available()          # 通道是否已实现（现在 False）
"""
from __future__ import annotations

from ms_instruments import LANGUAGES, register_language  # noqa: F401


def languages() -> dict:
    """当前登记的语言：{code: 名称}。"""
    return dict(LANGUAGES)


def available() -> bool:
    """人声**演唱通道**是否已实现（现在还没有；段结构可写、可校验）。"""
    return False


def require_ready() -> None:
    """需要演唱通道的地方调用它：未实现时明确报错，不静默降级。"""
    if not available():
        raise NotImplementedError(
            "人声演唱通道尚未实现：当前只能写段结构（write_vocal → events/segments），"
            "音频仍由 MS 的乐器通道负责；接入计划见 docs/spec/MS_API.md")


__all__ = ["languages", "available", "require_ready", "register_language"]
