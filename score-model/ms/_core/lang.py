# -*- coding: utf-8 -*-
"""语言框架：语言注册、各语言默认参数、按语言取参数。

各语言实现放在独立脚本：lang_en.py / lang_ja.py / lang_fr.py / lang_ru.py；
中文的语音细节在 pinyin.py（拼音表/声母特征/声调曲线）。
"""
from __future__ import annotations

LANGUAGES = {"zh": "中文", "en": "英语", "fr": "法语",
             "ja": "日语", "ru": "俄语"}

LANG_DEFAULTS = {
    "zh": dict(breathiness=0.35, vibrato=(5.5, 6.0)),
    "en": dict(breathiness=0.30, vibrato=(5.2, 5.0)),
    "ja": dict(breathiness=0.32, vibrato=(5.4, 5.5)),
    "fr": dict(breathiness=0.28, vibrato=(5.0, 5.0)),
    "ru": dict(breathiness=0.30, vibrato=(5.3, 5.5)),
}

# 段时长权重（相对）
def lang(code: str | None) -> dict:
    """取语言参数；语言未实现时直接拒绝。"""
    c = code or "zh"
    require_ready(c)
    return LANG_DEFAULTS.get(c, LANG_DEFAULTS["zh"])


def available() -> dict:
    """各语言是否可用（当前只有中文可用）。"""
    return dict(READY)


def register_language(code: str, name: str) -> dict:
    LANGUAGES[code] = name
    LANG_DEFAULTS.setdefault(code, dict(breathiness=0.30, vibrato=(5.3, 5.5)))
    return dict(LANGUAGES)


__all__ = ["LANGUAGES", "LANG_DEFAULTS", "READY", "lang", "available",
           "is_ready", "require_ready", "register_language"]

import lang_en  # noqa: E402,F401
import lang_ja  # noqa: E402,F401
import lang_fr  # noqa: E402,F401
import lang_ru  # noqa: E402,F401

IMPLS = {"en": lang_en, "ja": lang_ja, "fr": lang_fr, "ru": lang_ru}

# 实现状态：中文可用；其他语言脚本已占位但未实现（READY=False）
READY = {"zh": True}
READY.update({k: bool(getattr(m, "READY", False)) for k, m in IMPLS.items()})


def is_ready(code: str | None) -> bool:
    return bool(READY.get(code or "zh", False))


def require_ready(code: str | None) -> None:
    """语言未实现时拒绝使用（不把未实现的声音混进音乐）。"""
    if not is_ready(code):
        raise NotImplementedError(
            f"{code} 语言的演唱通道未实现（当前仅支持中文 zh）")
