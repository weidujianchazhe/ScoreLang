# -*- coding: utf-8 -*-
"""兼容转发：单字字典已移到 
otation/char_dict.py（字典层）。"""
from pinyin import CHAR_DICT, pinyin_of, tone_of, missing  # noqa: F401

VOCAB = {c: v[0] for c, v in CHAR_DICT.items()}
