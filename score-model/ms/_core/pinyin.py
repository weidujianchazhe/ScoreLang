# -*- coding: utf-8 -*-
"""拼音 → 发声段（声母/介音/主元音/韵尾）。

只做普通话。规则来自拼音拼写本身，不引入音素表以外的体系。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 声母（21 个；不含零声母）
INITIALS = ("b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
            "j", "q", "x", "zh", "ch", "sh", "r", "z", "c", "s")

# 声母发音特征：(方式, 部位, 浊, 送气)
INITIAL_FEATURES = {
    "b": ("plosive", "bilabial", False, False),
    "p": ("plosive", "bilabial", False, True),
    "m": ("nasal", "bilabial", True, False),
    "f": ("fricative", "labiodental", False, False),
    "d": ("plosive", "alveolar", False, False),
    "t": ("plosive", "alveolar", False, True),
    "n": ("nasal", "alveolar", True, False),
    "l": ("lateral", "alveolar", True, False),
    "g": ("plosive", "velar", False, False),
    "k": ("plosive", "velar", False, True),
    "h": ("fricative", "velar", False, False),
    "j": ("affricate", "palatal", False, False),
    "q": ("affricate", "palatal", False, True),
    "x": ("fricative", "palatal", False, False),
    "zh": ("affricate", "retroflex", False, False),
    "ch": ("affricate", "retroflex", False, True),
    "sh": ("fricative", "retroflex", False, False),
    "r": ("approximant", "retroflex", True, False),
    "z": ("affricate", "alveolar", False, False),
    "c": ("affricate", "alveolar", False, True),
    "s": ("fricative", "alveolar", False, False),
}

# 韵母 → (介音, 主元音, 韵尾)
FINALS = {
    "a": ("", "a", ""), "o": ("", "o", ""), "e": ("", "e", ""),
    "i": ("", "i", ""), "u": ("", "u", ""), "v": ("", "v", ""), "ü": ("", "v", ""),
    "er": ("", "er", ""),
    "m": ("", "m", ""), "n": ("", "n", ""), "ng": ("", "ng", ""),
    "ai": ("", "a", "i"), "ei": ("", "e", "i"), "ao": ("", "a", "o"), "ou": ("", "o", "u"),
    "an": ("", "a", "n"), "en": ("", "e", "n"), "ang": ("", "a", "ng"), "eng": ("", "e", "ng"),
    "ong": ("", "o", "ng"),
    "ia": ("i", "a", ""), "ie": ("i", "e", ""), "iao": ("i", "a", "o"),
    "iou": ("i", "o", "u"), "iu": ("i", "o", "u"),
    "ian": ("i", "a", "n"), "in": ("i", "e", "n"), "iang": ("i", "a", "ng"),
    "ing": ("i", "e", "ng"), "iong": ("v", "o", "ng"),
    "ua": ("u", "a", ""), "uo": ("u", "o", ""), "uai": ("u", "a", "i"),
    "uei": ("u", "e", "i"), "ui": ("u", "e", "i"),
    "uan": ("u", "a", "n"), "uen": ("u", "e", "n"), "un": ("u", "e", "n"),
    "uang": ("u", "a", "ng"), "ueng": ("u", "e", "ng"),
    "ve": ("v", "e", ""), "üe": ("v", "e", ""),
    "van": ("v", "a", "n"), "üan": ("v", "a", "n"),
    "vn": ("v", "e", "n"), "ün": ("v", "e", "n"),
}

# 共振峰目标（F1, F2, F3），单位 Hz
VOWEL_FORMANTS = {
    "a": (800, 1200, 2500),
    "o": (500, 900, 2400),
    "e": (500, 1800, 2500),
    "i": (300, 2300, 3000),
    "u": (320, 800, 2300),
    "v": (300, 1800, 2200),
    "er": (500, 1400, 2500),
    # 哼唱鼻音：低 F1 + 鼻腔共振
    "m": (250, 1000, 2200),
    "n": (250, 1500, 2500),
    "ng": (250, 2000, 2600),
}


@dataclass
class Segment:
    kind: str            # initial | medial | nucleus | coda | inhale
    text: str
    voiced: bool = True
    manner: str = ""     # 声母方式
    place: str = ""
    aspirated: bool = False
    formants: tuple = ()  # 元音的共振峰目标


@dataclass
class Syllable:
    """一个字的拼音解析结果。"""
    char: str
    pinyin: str
    normalized: str
    initial: str
    final: str
    tone: int
    segments: list = field(default_factory=list)


def normalize(pinyin: str) -> str:
    """y/w 拼写与 ü 的规范化。"""
    p = pinyin.strip().lower().replace("ü", "v")
    if p.startswith("yu"):
        p = "v" + p[2:]
    elif p.startswith("yi"):
        p = "i" + p[2:]
    elif p.startswith("y"):
        p = "i" + p[1:]
    elif p.startswith("wu"):
        p = "u" + p[2:]
    elif p.startswith("w"):
        p = "u" + p[1:]
    # j/q/x + u 实为 ü
    if p[:1] in ("j", "q", "x"):
        if p[1:2] == "u":
            p = p[0] + "v" + p[2:]
        elif p[1:2] == "v":
            p = p[0] + "v" + p[2:]
    return p


def split_initial(p: str) -> tuple[str, str]:
    """返回 (声母, 韵母)；零声母时声母为空串。"""
    if len(p) >= 2 and p[:2] in INITIALS:
        return p[:2], p[2:]
    if p[:1] in INITIALS:
        return p[0], p[1:]
    # 规范化后 y/w 已处理；剩余视为零声母
    if p.startswith("v"):
        return "", p          # ü / üe / üan / ün
    return "", p


def parse(char: str, pinyin: str, tone: int = 1) -> Syllable:
    norm = normalize(pinyin)
    if norm in ("m", "n", "ng"):        # 成音节鼻音：零声母
        ini, fin = "", norm
    else:
        ini, fin = split_initial(norm)
    if fin in ("v", "ve", "van", "vn"):
        fin = "ü" + fin[1:]
    if fin not in FINALS:
        raise ValueError(f"不认识的韵母：{pinyin!r}（规范化后 {norm!r}）")
    medial, nucleus, coda = FINALS[fin]
    segs: list[Segment] = []
    if ini:
        manner, place, voiced, asp = INITIAL_FEATURES[ini]
        segs.append(Segment("initial", ini, voiced, manner, place, asp))
    if medial:
        segs.append(Segment("medial", medial, True, formants=VOWEL_FORMANTS[medial]))
    if nucleus:
        segs.append(Segment("nucleus", nucleus, True, formants=VOWEL_FORMANTS[nucleus]))
    if coda:
        segs.append(Segment("coda", coda, True))
    return Syllable(char=char, pinyin=pinyin, normalized=norm, initial=ini,
                    final=fin, tone=tone, segments=segs)


# 声调轮廓：归一化音高（0..1 相对音域），按时间 0→1 采样点
TONE_CONTOURS = {
    1: ((0.0, 0.95), (1.0, 0.95)),
    2: ((0.0, 0.55), (1.0, 1.0)),
    3: ((0.0, 0.75), (0.45, 0.35), (1.0, 0.85)),
    4: ((0.0, 1.0), (1.0, 0.35)),
    5: ((0.0, 0.55), (1.0, 0.5)),
    0: ((0.0, 0.7), (1.0, 0.7)),
}

# 段时长占比（长音时主元音更多）
DURATION_TEMPLATE = {
    "initial": 0.18,
    "medial": 0.08,
    "nucleus": 0.58,
    "coda": 0.16,
}


# ── 合法音节表（声母→允许韵母、编号） ──

# 每个声母允许的韵母（按普通话拼写规则整理）
_TABLE = {
    "": ("a o e ai ei ao ou an en ang eng er yi ya ye yao you yan yin yang ying yong wu wa wo wai wei wan wen wang weng yu yue yuan yun",
         "a o e ai ei ao ou an en ang eng er i ia ie iao iou ian in iang ing iong u ua uo uai uei uan uen uang ueng v ve van vn"),
    "b": ("a o ai ei ao an en ang eng i ie iao ian in ing u", "a o ai ei ao an en ang eng i ie iao ian in ing u"),
    "p": ("a o ai ei ao ou an en ang eng i ie iao ian in ing u", "a o ai ei ao ou an en ang eng i ie iao ian in ing u"),
    "m": ("a o e ai ei ao ou an en ang eng i ie iao iou ian in ing u", "a o e ai ei ao ou an en ang eng i ie iao iou ian in ing u"),
    "f": ("a o ei ou an en ang eng u", "a o ei ou an en ang eng u"),
    "d": ("a e ai ei ao ou an en ang eng ong i ia ie iao iou ian ing u uo uai uei uan uen ong", "a e ai ei ao ou an en ang eng ong i ia ie iao iou ian ing u uo uai uei uan uen"),
    "t": ("a e ai ao ou an ang eng ong i ie iao ian ing u uo uai uei uan uen ong", "a e ai ao ou an ang eng ong i ie iao ian ing u uo uai uei uan uen"),
    "n": ("a e ai ei ao ou an en ang eng ong i ie iao iou ian in iang ing iong u uo uan uen v ve van vn", "a e ai ei ao ou an en ang eng ong i ie iao iou ian in iang ing iong u uo uan uen v ve van vn"),
    "l": ("a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u uo uan uen v ve van vn", "a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u uo uan uen v ve van vn"),
    "g": ("a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang", "a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang"),
    "k": ("a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang", "a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang"),
    "h": ("a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang", "a e ai ei ao ou an en ang eng ong u ua uo uai uei uan uen uang"),
    "j": ("i ia ie iao iou ian in iang ing iong v ve van vn", "i ia ie iao iou ian in iang ing iong v ve van vn"),
    "q": ("i ia ie iao iou ian in iang ing iong v ve van vn", "i ia ie iao iou ian in iang ing iong v ve van vn"),
    "x": ("i ia ie iao iou ian in iang ing iong v ve van vn", "i ia ie iao iou ian in iang ing iong v ve van vn"),
    "zh": ("a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u ua uo uai uei uan uen uang", "a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u ua uo uai uei uan uen uang"),
    "ch": ("a e ai ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u ua uo uai uei uan uen uang", "a e ai ao ou an en ang eng ong i ia ie iao iou ian in iang ing iong u ua uo uai uei uan uen uang"),
    "sh": ("a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing u ua uo uai uei uan uen uang", "a e ai ei ao ou an en ang eng ong i ia ie iao iou ian in iang ing u ua uo uai uei uan uen uang"),
    "r": ("e en eng ong i iao iou ian in iang ing u ua uo uai uei uan uen", "e en eng ong i iao iou ian in iang ing u ua uo uai uei uan uen"),
    "z": ("a e ai ei ao ou an en ang eng ong i u uo uai uei uan uen", "a e ai ei ao ou an en ang eng ong i u uo uai uei uan uen"),
    "c": ("a e ai ao ou an en ang eng ong i u uo uai uei uan uen", "a e ai ao ou an en ang eng ong i u uo uai uei uan uen"),
    "s": ("a e ai ao ou an en ang eng ong i u uo uai uei uan uen", "a e ai ao ou an en ang eng ong i u uo uai uei uan uen"),
}


def _split(pair: str) -> tuple:
    parts = pair.split()
    return parts[0], parts[1:]


LEGAL = {}
for ini, (_raw, _canon) in _TABLE.items():
    LEGAL[ini] = set(_canon.split())


def is_legal(initial: str, final: str) -> bool:
    return final in LEGAL.get(initial, set())


def all_syllables() -> list:
    out = []
    for ini, finals in LEGAL.items():
        for f in sorted(finals):
            out.append((ini + f) if ini else f)
    return out


def count() -> int:
    return len(all_syllables())


# 带调音节：声母 + 韵母 + 声调（1–5）构成一个完整发音结构。
# 本表是**数学结构全集**：任何 (声母, 韵母, 声调) 组合都合法。
# 现实中某音节没有某调属于**收束层**规则，不在这里剔除。
TONES = (1, 2, 3, 4, 5)   # 5 = 轻声


# 特殊：成音节鼻音（嗯/呣/哼）——零声母，独立成音节
NASAL_SYLLABLES = ("m", "n", "ng")
for _ns in NASAL_SYLLABLES:
    LEGAL[""].add(_ns)


def legal_tones(initial: str, final: str) -> tuple:
    return TONES if is_legal(initial, final) else ()


def is_legal_toned(initial: str, final: str, tone: int) -> bool:
    return is_legal(initial, final) and tone in TONES


def toned_syllables() -> list:
    out = []
    for ini, finals in LEGAL.items():
        for f in sorted(finals):
            for t in TONES:
                out.append((ini, f, t))
    return out


def count_toned() -> int:
    return len(toned_syllables())


# ── 组合编号：每个 (声母, 韵母) 一个稳定编号，MS 用它做结构绑定 ──
_COMBOS = sorted(((ini, f) for ini, fs in LEGAL.items() for f in fs))
SYLLABLE_ID = {combo: f"S{i:04d}" for i, combo in enumerate(_COMBOS, 1)}
ID_TO_SYLLABLE = {v: k for k, v in SYLLABLE_ID.items()}


def syllable_id(initial: str, final: str) -> str | None:
    return SYLLABLE_ID.get((initial, final))


def syllable_by_id(sid: str):
    return ID_TO_SYLLABLE.get(sid)


# ── 声母/韵母发音特征与时长分配 ──

INITIAL_FACTORS = {
    "b": dict(manner="plosive", place="bilabial", voiced=False, aspiration=0.3,
              noise_center=900, noise_bw=700, dur_ratio=0.17),
    "p": dict(manner="plosive", place="bilabial", voiced=False, aspiration=1.0,
              noise_center=900, noise_bw=900, dur_ratio=0.19),
    "m": dict(manner="nasal", place="bilabial", voiced=True, aspiration=0.0,
              noise_center=0, noise_bw=0, dur_ratio=0.19),
    "f": dict(manner="fricative", place="labiodental", voiced=False, aspiration=0.8,
              noise_center=4000, noise_bw=2500, dur_ratio=0.20),
    "d": dict(manner="plosive", place="alveolar", voiced=False, aspiration=0.3,
              noise_center=3500, noise_bw=2000, dur_ratio=0.16),
    "t": dict(manner="plosive", place="alveolar", voiced=False, aspiration=1.0,
              noise_center=4000, noise_bw=2500, dur_ratio=0.18),
    "n": dict(manner="nasal", place="alveolar", voiced=True, aspiration=0.0,
              noise_center=0, noise_bw=0, dur_ratio=0.18),
    "l": dict(manner="lateral", place="alveolar", voiced=True, aspiration=0.0,
              noise_center=0, noise_bw=0, dur_ratio=0.16),
    "g": dict(manner="plosive", place="velar", voiced=False, aspiration=0.3,
              noise_center=1800, noise_bw=1200, dur_ratio=0.16),
    "k": dict(manner="plosive", place="velar", voiced=False, aspiration=1.0,
              noise_center=2000, noise_bw=1500, dur_ratio=0.18),
    "h": dict(manner="fricative", place="velar", voiced=False, aspiration=0.9,
              noise_center=1800, noise_bw=1500, dur_ratio=0.20),
    "j": dict(manner="affricate", place="palatal", voiced=False, aspiration=0.5,
              noise_center=4500, noise_bw=2500, dur_ratio=0.19),
    "q": dict(manner="affricate", place="palatal", voiced=False, aspiration=1.0,
              noise_center=4800, noise_bw=2600, dur_ratio=0.20),
    "x": dict(manner="fricative", place="palatal", voiced=False, aspiration=0.8,
              noise_center=4500, noise_bw=2500, dur_ratio=0.19),
    "zh": dict(manner="affricate", place="retroflex", voiced=False, aspiration=0.5,
               noise_center=3500, noise_bw=2000, dur_ratio=0.19),
    "ch": dict(manner="affricate", place="retroflex", voiced=False, aspiration=1.0,
               noise_center=3500, noise_bw=2000, dur_ratio=0.20),
    "sh": dict(manner="fricative", place="retroflex", voiced=False, aspiration=0.8,
               noise_center=3500, noise_bw=2000, dur_ratio=0.19),
    "r": dict(manner="approximant", place="retroflex", voiced=True, aspiration=0.1,
              noise_center=0, noise_bw=0, dur_ratio=0.17),
    "z": dict(manner="affricate", place="alveolar", voiced=False, aspiration=0.4,
              noise_center=6000, noise_bw=3000, dur_ratio=0.18),
    "c": dict(manner="affricate", place="alveolar", voiced=False, aspiration=1.0,
              noise_center=6000, noise_bw=3000, dur_ratio=0.20),
    "s": dict(manner="fricative", place="alveolar", voiced=False, aspiration=0.8,
              noise_center=6000, noise_bw=3000, dur_ratio=0.19),
}

# 元音共振峰 + 韵尾（coda 决定鼻音/滑音收束）
FINAL_FACTORS = {
    "a": dict(formants=(800, 1200, 2500), coda=""),
    "o": dict(formants=(500, 900, 2400), coda=""),
    "e": dict(formants=(500, 1800, 2500), coda=""),
    "i": dict(formants=(300, 2300, 3000), coda=""),
    "u": dict(formants=(320, 800, 2300), coda=""),
    "v": dict(formants=(300, 1800, 2200), coda=""),
    "er": dict(formants=(500, 1400, 2500), coda="r"),
    "m": dict(formants=(250, 1000, 2200), coda=""),
    "n": dict(formants=(250, 1500, 2500), coda=""),
    "ng": dict(formants=(250, 2000, 2600), coda=""),
}

# 声调：相对音高采样点（0..1 时间 → 0..1 高度）
TONE_FACTORS = {
    1: ((0.0, 0.95), (1.0, 0.95)),
    2: ((0.0, 0.55), (1.0, 1.00)),
    3: ((0.0, 0.75), (0.45, 0.35), (1.0, 0.85)),
    4: ((0.0, 1.00), (1.0, 0.35)),
    5: ((0.0, 0.55), (1.0, 0.50)),
    0: ((0.0, 0.70), (1.0, 0.70)),
}

DUR_WEIGHTS = {"initial": 0.18, "medial": 0.08, "nucleus": 0.60, "coda": 0.14}


def spread_durations(kinds, note_us: int) -> list:
    kinds = list(kinds)
    weights = [float(DUR_WEIGHTS.get(k, 0.1)) for k in kinds]
    nuc = next((i for i, k in enumerate(kinds) if k == "nucleus"), 0)
    if note_us >= 1_000_000:
        k = 0.20
        weights = [w * (1 - k) if i != nuc else w * (1 + k * (len(kinds) - 1))
                   for i, w in enumerate(weights)]
    elif note_us < 150_000:
        for i, kind in enumerate(kinds):
            if kind == "coda":
                weights[i] *= 0.5
    total = sum(weights) or 1.0
    return [max(1, int(note_us * w / total)) for w in weights]


def initial(name: str) -> dict:
    return INITIAL_FACTORS.get(name, {})


def final(name: str) -> dict:
    return FINAL_FACTORS.get(name, {"formants": (500, 1500, 2500), "coda": ""})


def tone(number: int):
    return TONE_FACTORS.get(number, TONE_FACTORS[0])

def check() -> list:
    errs = []
    for k, v in INITIAL_FACTORS.items():
        for f in ("manner", "place", "dur_ratio"):
            if f not in v:
                errs.append(f"{k} 缺 {f}")
        if not (0 < v.get("dur_ratio", 0) < 0.5):
            errs.append(f"{k} dur_ratio 越界")
    for k, v in FINAL_FACTORS.items():
        if len(v.get("formants", ())) != 3:
            errs.append(f"{k} 共振峰不足 3 个")
    return errs


def noise_center(place: str) -> int:
    for v in INITIAL_FACTORS.values():
        if v["place"] == place and v["noise_center"]:
            return v["noise_center"]
    return 3000


def nasal_formants(place: str) -> tuple:
    return {"bilabial": (250, 1000, 2200), "alveolar": (250, 1500, 2500),
            "velar": (250, 2000, 2600)}.get(place, (250, 1200, 2400))


# ── 汉字 → 拼音/声调 ──

# 常用字（按主题分组，便于扩充）
CHAR_DICT: dict[str, tuple[str, int]] = {}

_GROUPS = {
    "长夜行天未明晨雾风雨雪月光影静远近深": [
        ("长", "chang", 2), ("夜", "ye", 4), ("行", "xing", 2), ("天", "tian", 1),
        ("未", "wei", 4), ("明", "ming", 2), ("晨", "chen", 2), ("雾", "wu", 4),
        ("风", "feng", 1), ("雨", "yu", 3), ("雪", "xue", 3), ("月", "yue", 4),
        ("光", "guang", 1), ("影", "ying", 3), ("静", "jing", 4), ("远", "yuan", 3),
        ("近", "jin", 4), ("深", "shen", 1),
    ],
    "人称常用": [
        ("我", "wo", 3), ("你", "ni", 3), ("他", "ta", 1), ("她", "ta", 1),
        ("们", "men", 5), ("人", "ren", 2), ("心", "xin", 1), ("手", "shou", 3),
        ("眼", "yan", 3), ("声", "sheng", 1), ("音", "yin", 1), ("歌", "ge", 1),
        ("唱", "chang", 4), ("听", "ting", 1), ("看", "kan", 4), ("来", "lai", 2),
        ("去", "qu", 4), ("走", "zou", 3), ("回", "hui", 2), ("在", "zai", 4),
        ("有", "you", 3), ("是", "shi", 4), ("不", "bu", 4), ("一", "yi", 1),
        ("的", "de", 5), ("了", "le", 5), ("个", "ge", 4), ("这", "zhe", 4),
        ("那", "na", 4), ("和", "he", 2), ("与", "yu", 3), ("为", "wei", 4),
        ("被", "bei", 4), ("把", "ba", 3), ("从", "cong", 2), ("向", "xiang", 4),
        ("到", "dao", 4), ("过", "guo", 4), ("着", "zhe", 5), ("就", "jiu", 4),
        ("也", "ye", 3), ("都", "dou", 1), ("很", "hen", 3), ("太", "tai", 4),
        ("最", "zui", 4), ("更", "geng", 4), ("又", "you", 4), ("还", "hai", 2),
        ("会", "hui", 4), ("能", "neng", 2), ("要", "yao", 4), ("想", "xiang", 3),
        ("说", "shuo", 1), ("问", "wen", 4), ("答", "da", 2), ("笑", "xiao", 4),
        ("哭", "ku", 1), ("等", "deng", 3), ("找", "zhao", 3), ("忘", "wang", 4),
        ("记", "ji", 4), ("知", "zhi", 1), ("道", "dao", 4), ("别", "bie", 2),
        ("再", "zai", 4), ("已", "yi", 3), ("曾", "ceng", 2), ("将", "jiang", 1),
        ("正", "zheng", 4), ("总", "zong", 3), ("只", "zhi", 3), ("每", "mei", 3),
        ("些", "xie", 1), ("什", "shen", 2), ("么", "me", 5), ("怎", "zen", 3),
        ("样", "yang", 4), ("如", "ru", 2), ("若", "ruo", 4), ("因", "yin", 1),
        ("所", "suo", 3), ("以", "yi", 3), ("但", "dan", 4), ("而", "er", 2),
        ("却", "que", 4), ("虽", "sui", 1), ("然", "ran", 2), ("此", "ci", 3),
    ],
    "自然时间": [
        ("山", "shan", 1), ("水", "shui", 3), ("河", "he", 2), ("海", "hai", 3),
        ("云", "yun", 2), ("星", "xing", 1), ("日", "ri", 4), ("年", "nian", 2),
        ("春", "chun", 1), ("夏", "xia", 4), ("秋", "qiu", 1), ("冬", "dong", 1),
        ("早", "zao", 3), ("晚", "wan", 3), ("今", "jin", 1), ("昨", "zuo", 2),
        ("时", "shi", 2), ("间", "jian", 1),
    ],
    "动作状态": [
        ("开", "kai", 1), ("关", "guan", 1), ("起", "qi", 3), ("落", "luo", 4),
        ("飞", "fei", 1), ("停", "ting", 2), ("留", "liu", 2), ("送", "song", 4),
        ("带", "dai", 4), ("给", "gei", 3), ("让", "rang", 4), ("使", "shi", 3),
        ("得", "de", 5), ("成", "cheng", 2), ("变", "bian", 4), ("化", "hua", 4),
        ("生", "sheng", 1), ("死", "si", 3), ("活", "huo", 2), ("醒", "xing", 3),
        ("睡", "shui", 4), ("梦", "meng", 4), ("见", "jian", 4),
    ],
    "情绪字面": [
        ("悲", "bei", 1), ("欢", "huan", 1), ("喜", "xi", 3), ("怒", "nu", 4),
        ("哀", "ai", 1), ("乐", "le", 4), ("孤", "gu", 1), ("独", "du", 2),
        ("寂", "ji", 4), ("寞", "mo", 4), ("安", "an", 1), ("宁", "ning", 2),
    ],
}

for rows in _GROUPS.values():
    for ch, py, tone in rows:
        CHAR_DICT[ch] = (py, tone)


def pinyin_of(char: str) -> str | None:
    hit = CHAR_DICT.get(char)
    return hit[0] if hit else None


def tone_of(char: str) -> int | None:
    hit = CHAR_DICT.get(char)
    return hit[1] if hit else None


def missing(chars: str) -> list:
    return [c for c in chars if c not in CHAR_DICT and not c.isspace()]
