# -*- coding: utf-8 -*-
"""乐器总登记表（registry）：类型 → 能力。

三层结构中的第 ① 层：**不进 `.ms` 文件**，文件里只写 `P# 类型码 子类型码`。
本表是"乐器能力"的单一出处，被三处消费：

  · 渲染器：音域 / 踏板种类 / 谱表默认
  · MIDI  ：GM program / 通道策略 / 鼓组标记
  · 音频  ：SoundFont 预设

能力按**族**给默认值，只对例外写覆盖——避免 128 条重复。
"""
from __future__ import annotations

REGISTRY_VERSION = 1

# 人声语言（写谱侧 lang 字段的取值范围；通道实现见 docs/spec/MS_API.md）
from lang import LANGUAGES  # noqa: F401  （语言注册表在 lang.py）

# 族 → 默认能力
#   range  : (min, max) 半音（MIDI 键号）
#   poly   : 复音数（声明用，不拦截；数学结构不限制并发）
#   pedals : 可用踏板种类
#   dyn    : 力度标尺（对应 Dynamics.scale）
#   category: pitched | percussion | sfx | voice  ← 决定"要不要上谱 / 走不走鼓组通道"
FAMILIES = {
    "piano":      dict(range=(21, 108), poly=10, pedals=("sustain", "sostenuto", "una_corda"),
                       dyn="velocity_steps", category="pitched"),
    "mallet":     dict(range=(48, 96),  poly=4,  pedals=(), dyn="velocity_steps", category="pitched"),
    "organ":      dict(range=(36, 96),  poly=10, pedals=(), dyn="continuous",     category="pitched"),
    "guitar":     dict(range=(40, 88),  poly=6,  pedals=(), dyn="velocity_steps", category="pitched"),
    "bass":       dict(range=(28, 67),  poly=4,  pedals=(), dyn="velocity_steps", category="pitched"),
    "strings":    dict(range=(55, 103), poly=1,  pedals=("sordino",), dyn="continuous", category="pitched"),
    "ensemble":   dict(range=(48, 96),  poly=8,  pedals=(), dyn="continuous",     category="pitched"),
    "voice":      dict(range=(48, 84),  poly=1,  pedals=(), dyn="continuous",     category="voice"),
    "brass":      dict(range=(40, 84),  poly=1,  pedals=("sordino",), dyn="continuous", category="pitched"),
    "reed":       dict(range=(50, 90),  poly=1,  pedals=("sordino",), dyn="continuous", category="pitched"),
    "pipe":       dict(range=(60, 96),  poly=1,  pedals=(), dyn="continuous",     category="pitched"),
    "synth":      dict(range=(24, 108), poly=8,  pedals=(), dyn="continuous",     category="pitched"),
    "fx":         dict(range=(0, 127),  poly=8,  pedals=(), dyn="continuous",     category="sfx"),
    "ethnic":     dict(range=(40, 96),  poly=2,  pedals=(), dyn="velocity_steps", category="pitched"),
    "percussion": dict(range=(0, 127),  poly=8,  pedals=(), dyn="fixed_levels",   category="percussion"),
    "sfx":        dict(range=(0, 127),  poly=8,  pedals=(), dyn="fixed_levels",   category="sfx"),
}

# GM 128 音色：program(0-127) → (类型码, 族)
GM = (
    (0, "acoustic_grand_piano", "piano"), (1, "bright_acoustic_piano", "piano"),
    (2, "electric_grand_piano", "piano"), (3, "honky_tonk_piano", "piano"),
    (4, "electric_piano_1", "piano"), (5, "electric_piano_2", "piano"),
    (6, "harpsichord", "piano"), (7, "clavinet", "piano"),
    (8, "celesta", "mallet"), (9, "glockenspiel", "mallet"),
    (10, "music_box", "mallet"), (11, "vibraphone", "mallet"),
    (12, "marimba", "mallet"), (13, "xylophone", "mallet"),
    (14, "tubular_bells", "mallet"), (15, "dulcimer", "mallet"),
    (16, "drawbar_organ", "organ"), (17, "percussive_organ", "organ"),
    (18, "rock_organ", "organ"), (19, "church_organ", "organ"),
    (20, "reed_organ", "organ"), (21, "accordion", "organ"),
    (22, "harmonica", "organ"), (23, "tango_accordion", "organ"),
    (24, "acoustic_guitar_nylon", "guitar"), (25, "acoustic_guitar_steel", "guitar"),
    (26, "electric_guitar_jazz", "guitar"), (27, "electric_guitar_clean", "guitar"),
    (28, "electric_guitar_muted", "guitar"), (29, "overdriven_guitar", "guitar"),
    (30, "distortion_guitar", "guitar"), (31, "guitar_harmonics", "guitar"),
    (32, "acoustic_bass", "bass"), (33, "electric_bass_finger", "bass"),
    (34, "electric_bass_pick", "bass"), (35, "fretless_bass", "bass"),
    (36, "slap_bass_1", "bass"), (37, "slap_bass_2", "bass"),
    (38, "synth_bass_1", "bass"), (39, "synth_bass_2", "bass"),
    (40, "violin", "strings"), (41, "viola", "strings"),
    (42, "cello", "strings"), (43, "contrabass", "strings"),
    (44, "tremolo_strings", "strings"), (45, "pizzicato_strings", "strings"),
    (46, "orchestral_harp", "strings"), (47, "timpani", "percussion"),
    (48, "string_ensemble_1", "ensemble"), (49, "string_ensemble_2", "ensemble"),
    (50, "synth_strings_1", "ensemble"), (51, "synth_strings_2", "ensemble"),
    (52, "choir_aahs", "voice"), (53, "voice_oohs", "voice"),
    (54, "synth_voice", "voice"), (55, "orchestra_hit", "ensemble"),
    (56, "trumpet", "brass"), (57, "trombone", "brass"),
    (58, "tuba", "brass"), (59, "muted_trumpet", "brass"),
    (60, "french_horn", "brass"), (61, "brass_section", "brass"),
    (62, "synth_brass_1", "brass"), (63, "synth_brass_2", "brass"),
    (64, "soprano_sax", "reed"), (65, "alto_sax", "reed"),
    (66, "tenor_sax", "reed"), (67, "baritone_sax", "reed"),
    (68, "oboe", "reed"), (69, "english_horn", "reed"),
    (70, "bassoon", "reed"), (71, "clarinet", "reed"),
    (72, "piccolo", "pipe"), (73, "flute", "pipe"),
    (74, "recorder", "pipe"), (75, "pan_flute", "pipe"),
    (76, "blown_bottle", "pipe"), (77, "shakuhachi", "pipe"),
    (78, "whistle", "pipe"), (79, "ocarina", "pipe"),
    (80, "lead_1_square", "synth"), (81, "lead_2_sawtooth", "synth"),
    (82, "lead_3_calliope", "synth"), (83, "lead_4_chiff", "synth"),
    (84, "lead_5_charang", "synth"), (85, "lead_6_voice", "synth"),
    (86, "lead_7_fifths", "synth"), (87, "lead_8_bass_lead", "synth"),
    (88, "pad_1_new_age", "synth"), (89, "pad_2_warm", "synth"),
    (90, "pad_3_polysynth", "synth"), (91, "pad_4_choir", "synth"),
    (92, "pad_5_bowed", "synth"), (93, "pad_6_metallic", "synth"),
    (94, "pad_7_halo", "synth"), (95, "pad_8_sweep", "synth"),
    (96, "fx_1_rain", "fx"), (97, "fx_2_soundtrack", "fx"),
    (98, "fx_3_crystal", "fx"), (99, "fx_4_atmosphere", "fx"),
    (100, "fx_5_brightness", "fx"), (101, "fx_6_goblins", "fx"),
    (102, "fx_7_echoes", "fx"), (103, "fx_8_sci_fi", "fx"),
    (104, "sitar", "ethnic"), (105, "banjo", "ethnic"),
    (106, "shamisen", "ethnic"), (107, "koto", "ethnic"),
    (108, "kalimba", "ethnic"), (109, "bag_pipe", "ethnic"),
    (110, "fiddle", "ethnic"), (111, "shanai", "ethnic"),
    (112, "tinkle_bell", "percussion"), (113, "agogo", "percussion"),
    (114, "steel_drums", "percussion"), (115, "woodblock", "percussion"),
    (116, "taiko_drum", "percussion"), (117, "melodic_tom", "percussion"),
    (118, "synth_drum", "percussion"), (119, "reverse_cymbal", "percussion"),
    (120, "guitar_fret_noise", "sfx"), (121, "breath_noise", "sfx"),
    (122, "seashore", "sfx"), (123, "bird_tweet", "sfx"),
    (124, "telephone_ring", "sfx"), (125, "helicopter", "sfx"),
    (126, "applause", "sfx"), (127, "gunshot", "sfx"),
)

# 子类型：只加"真的需要区分"的（父类型 → 子类型 → 覆盖项）
SUBTYPES = {
    "acoustic_grand_piano": {
        "steinway_d": dict(soundfont="Steinway D", notes="卧式 88 键三角琴（本项目主用）"),
        "yamaha_c7": dict(soundfont="Yamaha C7", notes="卧式 88 键三角琴"),
        "digital": dict(program=2, soundfont="Electric Grand", notes="电子琴（88 键）"),
    },
    "acoustic_guitar_nylon": {"nylon": dict(soundfont="Nylon Guitar")},
    "acoustic_guitar_steel": {"steel": dict(soundfont="Steel Guitar")},
    "electric_guitar_clean": {"electric_clean": dict(soundfont="Clean Electric")},
    "string_ensemble_1": {"ensemble": dict(soundfont="String Ensemble")},
    "violin": {"solo": dict(soundfont="Solo Violin")},
}



# 扩展乐器（GM 之外的常用/民族/鼓组/人声声部）。program=None 表示需 SFZ 采样组。
EXTENDED = {
    # 中国民族乐器
    "guzheng":   dict(family="ethnic", program=None, range=(36, 96), notes="古筝"),
    "erhu":      dict(family="strings", program=None, range=(55, 100), notes="二胡"),
    "pipa":      dict(family="ethnic", program=None, range=(45, 98), notes="琵琶"),
    "dizi":      dict(family="pipe", program=None, range=(72, 96), notes="笛子"),
    "suona":     dict(family="reed", program=None, range=(60, 96), notes="唢呐"),
    "sheng":     dict(family="pipe", program=None, range=(55, 96), notes="笙"),
    "yangqin":   dict(family="mallet", program=None, range=(48, 96), notes="扬琴"),
    "xiao":      dict(family="pipe", program=None, range=(60, 91), notes="箫"),
    # 鼓组（GM 通道 10）
    "kit_standard":  dict(family="percussion", program=None, drum_kit=True, notes="GM 标准鼓组"),
    "kit_jazz":      dict(family="percussion", program=None, drum_kit=True, notes="爵士鼓组"),
    "kit_brush":     dict(family="percussion", program=None, drum_kit=True, notes="刷奏鼓组"),
    "kit_orchestra": dict(family="percussion", program=None, drum_kit=True, notes="管弦鼓组"),
    "kit_sfx":       dict(family="percussion", program=None, drum_kit=True, notes="音效鼓组"),
    # 人声声部（按音域区分）
    # MIDI 导出时映射到 GM 53（Voice Oohs）：否则默认 program 0 会变钢琴
    "soprano": dict(family="voice", program=53, range=(60, 84), notes="女高音"),
    "alto":    dict(family="voice", program=53, range=(55, 79), notes="女低音"),
    "tenor":   dict(family="voice", program=53, range=(48, 72), notes="男高音"),
    "bass":    dict(family="voice", program=53, range=(40, 64), notes="男低音"),
    "child":   dict(family="voice", program=53, range=(60, 84), notes="童声"),
    "voice_hum": dict(family="voice", program=53, range=(48, 84), notes="哼唱（闭口鼻音）"),
}



# 中国乐器目录（**预留**）：先有名录与分组，参数后续补。
#   group: 吹 / 拉 / 弹 / 打 / 古乐
#   status: 可用（已有音域） / 预留（仅目录）
ZH_CATALOG = {
    # 吹管
    "dizi":      dict(zh="笛子", group="吹", family="pipe", status="可用"),
    "xiao":      dict(zh="箫", group="吹", family="pipe", status="可用"),
    "sheng":     dict(zh="笙", group="吹", family="pipe", status="可用"),
    "suona":     dict(zh="唢呐", group="吹", family="reed", status="可用"),
    "guanzi":    dict(zh="管子", group="吹", family="reed", status="预留"),
    "bawu":      dict(zh="巴乌", group="吹", family="pipe", status="预留"),
    "hulusi":    dict(zh="葫芦丝", group="吹", family="pipe", status="预留"),
    "xun":       dict(zh="埙", group="古乐", family="pipe", status="预留"),
    "paixiao":   dict(zh="排箫", group="古乐", family="pipe", status="预留"),
    "bili":      dict(zh="筚篥", group="古乐", family="reed", status="预留"),
    # 拉弦
    "erhu":      dict(zh="二胡", group="拉", family="strings", status="可用"),
    "gaohu":     dict(zh="高胡", group="拉", family="strings", status="预留"),
    "zhonghu":   dict(zh="中胡", group="拉", family="strings", status="预留"),
    "banhu":     dict(zh="板胡", group="拉", family="strings", status="预留"),
    "jinghu":    dict(zh="京胡", group="拉", family="strings", status="预留"),
    "gehu":      dict(zh="革胡", group="拉", family="strings", status="预留"),
    "matouqin":  dict(zh="马头琴", group="拉", family="strings", status="预留"),
    # 弹拨
    "guzheng":   dict(zh="古筝", group="弹", family="ethnic", status="可用"),
    "pipa":      dict(zh="琵琶", group="弹", family="ethnic", status="可用"),
    "yangqin":   dict(zh="扬琴", group="弹", family="mallet", status="可用"),
    "liuqin":    dict(zh="柳琴", group="弹", family="ethnic", status="预留"),
    "ruan":      dict(zh="阮", group="弹", family="ethnic", status="预留"),
    "sanxian":   dict(zh="三弦", group="弹", family="ethnic", status="预留"),
    "guqin":     dict(zh="古琴", group="古乐", family="ethnic", status="预留"),
    "konghou":   dict(zh="箜篌", group="古乐", family="ethnic", status="预留"),
    "se":        dict(zh="瑟", group="古乐", family="ethnic", status="预留"),
    "zhu":       dict(zh="筑", group="古乐", family="ethnic", status="预留"),
    "dutar":     dict(zh="都塔尔", group="弹", family="ethnic", status="预留"),
    "rawap":     dict(zh="热瓦普", group="弹", family="ethnic", status="预留"),
    "dombra":    dict(zh="冬不拉", group="弹", family="ethnic", status="预留"),
    # 打击
    "bianzhong": dict(zh="编钟", group="古乐", family="percussion", status="预留"),
    "bianqing":  dict(zh="编磬", group="古乐", family="percussion", status="预留"),
    "jiangu":    dict(zh="建鼓", group="古乐", family="percussion", status="预留"),
    "jiegu":     dict(zh="羯鼓", group="古乐", family="percussion", status="预留"),
    "tanggu":    dict(zh="堂鼓", group="打", family="percussion", status="预留"),
    "paigu":     dict(zh="排鼓", group="打", family="percussion", status="预留"),
    "bangu":     dict(zh="板鼓", group="打", family="percussion", status="预留"),
    "daluo":     dict(zh="大锣", group="打", family="percussion", status="预留"),
    "xiaoluo":   dict(zh="小锣", group="打", family="percussion", status="预留"),
    "yunluo":    dict(zh="云锣", group="打", family="percussion", status="预留"),
    "naobo":     dict(zh="铙钹", group="打", family="percussion", status="预留"),
    "pengling":  dict(zh="碰铃", group="打", family="percussion", status="预留"),
    "muyu":      dict(zh="木鱼", group="打", family="percussion", status="预留"),
    "bangzi":    dict(zh="梆子", group="打", family="percussion", status="预留"),
    "shougu":    dict(zh="手鼓", group="打", family="percussion", status="预留"),
}

# 音色因子表（族 → 合成参数）。渲染器只读这张表，不再自己写死。
#   attack 起音(s) · tau 衰减常数(s) · roll 泛音衰减指数
#   bright 力度→亮度区间(最低,最高泛音数) · detune 失谐(音分) · noise 气声
#   vib_rate/vib_depth 颤音(Hz/音分)；0 表示无
TIMBRE = {
    # 卧式三角琴的物理线索（缺一样就会"电子味"）：
    #   reg_decay —— 衰减随音高变化：低音区弦长、能量大，余音拉得很长；高音区极短。
    #                0.85 指 tau_eff = tau * (C4/f)**0.85
    #   inharm    —— 钢丝有刚度，泛音不是精确整数倍（"拉伸八度"），这是钢琴听感的骨架
    #   hammer    —— 毡槌击弦的闷响（几十毫秒的低频瞬态），不是"嘶"而是"咚"
    "piano":      dict(attack=0.006, tau=1.15, roll=1.05, bright=(4, 12), detune=1.5, noise=0.0,
                       reg_decay=0.85, inharm=3.0e-4, hammer=0.030),
    "mallet":     dict(attack=0.002, tau=0.55, roll=1.40, bright=(6, 14), detune=0.0, noise=0.0),
    "organ":      dict(attack=0.010, tau=8.00, roll=1.00, bright=(8, 16), detune=0.0, noise=0.0),
    "guitar":     dict(attack=0.004, tau=0.85, roll=1.10, bright=(4, 12), detune=1.0, noise=0.0),
    "bass":       dict(attack=0.005, tau=0.90, roll=1.15, bright=(3, 9),  detune=1.0, noise=0.0),
    "strings":    dict(attack=0.050, tau=4.00, roll=1.30, bright=(3, 9),  detune=2.5, noise=0.010,
                       vib_rate=5.2, vib_depth=8),
    "ensemble":   dict(attack=0.060, tau=4.50, roll=1.30, bright=(3, 9),  detune=3.0, noise=0.008,
                       vib_rate=4.8, vib_depth=6),
    "voice":      dict(attack=0.040, tau=3.00, roll=1.35, bright=(2, 6),  detune=0.0, noise=0.006,
                       vib_rate=5.5, vib_depth=12),
    "brass":      dict(attack=0.030, tau=3.00, roll=1.20, bright=(5, 14), detune=0.8, noise=0.004),
    "reed":       dict(attack=0.040, tau=3.20, roll=1.25, bright=(4, 12), detune=0.5, noise=0.012,
                       vib_rate=4.5, vib_depth=5),
    "pipe":       dict(attack=0.045, tau=3.00, roll=1.25, bright=(4, 11), detune=0.5, noise=0.020,
                       vib_rate=5.0, vib_depth=6),
    "synth":      dict(attack=0.010, tau=3.00, roll=1.00, bright=(8, 18), detune=0.0, noise=0.0),
    "ethnic":     dict(attack=0.004, tau=1.00, roll=1.10, bright=(4, 12), detune=1.5, noise=0.0),
    "percussion": dict(attack=0.001, tau=0.45, roll=1.50, bright=(6, 16), detune=0.0, noise=0.30),
    "sfx":        dict(attack=0.002, tau=0.80, roll=1.50, bright=(6, 16), detune=0.0, noise=0.60),
}



# 发声机制：力怎么变成声音。族给默认，类型可覆盖。
MECHANISMS = {
    "piano": "hammered_string", "mallet": "struck_body", "organ": "electronic",
    "guitar": "plucked_string", "bass": "plucked_string", "strings": "bowed_string",
    "ensemble": "bowed_string", "voice": "vocal_fold", "brass": "lip_reed",
    "reed": "single_reed", "pipe": "air_jet", "synth": "electronic",
    "fx": "noise", "ethnic": "plucked_string", "percussion": "struck_body",
    "sfx": "noise",
}

# ── 止音（release）默认：不同乐器"怎么停"不一样，且都有缓冲，不是硬切 ──#   kind：damper 制音器落 / bow_lift 离弦 / breath_stop 收气 / pick_stop 手停 /
#         mallet_damp 手/毡止音 / electronic_off 断电式（最快）
#   ramp_ms：从 release_us 起衰减到无声的过程长度
OFF_KINDS = ("damper", "bow_lift", "breath_stop", "pick_stop", "mallet_damp", "electronic_off")
OFF_DEFAULTS = {
    "hammered_string": dict(kind="damper", ramp_ms=70),
    "bowed_string":    dict(kind="bow_lift", ramp_ms=45),
    "lip_reed":        dict(kind="breath_stop", ramp_ms=130),
    "single_reed":     dict(kind="breath_stop", ramp_ms=110),
    "air_jet":         dict(kind="breath_stop", ramp_ms=100),
    "vocal_fold":      dict(kind="breath_stop", ramp_ms=90),
    "plucked_string":  dict(kind="pick_stop", ramp_ms=60),
    "struck_body":     dict(kind="mallet_damp", ramp_ms=80),
    "electronic":      dict(kind="electronic_off", ramp_ms=15),
    "noise":           dict(kind="electronic_off", ramp_ms=20),
}


# ── 演奏动作：用**现有格式的 turns / curves / pedals** 表达，不新增区块 ──
#   · turns  = 逐音动作（音头方式）：`dict turn` 可扩，事件挂 event_id
#   · curves = 逐乐器连续参数：`dict curve` 可扩，按时间点
#   · pedals = 持续状态（装上/取下）：`dict kind` 可扩
#
# 每个动作声明"哪些机制能做"；值为 None 表示任何机制都可以。
ACTION_MECHS = {
    # —— 通用/原有 ——
    "retrigger":   None,
    "breath":      None,
    "restrike":    None,
    "mallet":      ("struck_body",),
    "bow_change":  ("bowed_string",),
    "liaison":     None,
    "break":       None,
    # —— 演奏动作（本轮补齐）——
    "bow_up":      ("bowed_string",),
    "bow_down":    ("bowed_string",),
    "pizz":        ("bowed_string",),
    "arco":        ("bowed_string",),
    "harmonic":    ("bowed_string", "plucked_string"),
    "mallet_soft": ("struck_body",),
    "mallet_hard": ("struck_body",),
    "inhale":      ("lip_reed", "single_reed", "air_jet", "vocal_fold"),
    "key_noise":   ("hammered_string",),
    "mute_on":     ("bowed_string", "lip_reed", "single_reed", "air_jet", "plucked_string"),
    "mute_off":    ("bowed_string", "lip_reed", "single_reed", "air_jet", "plucked_string"),
    # —— 教科书级的补充动作 ——
    "col_legno":   ("bowed_string",),                       # 用弓杆敲弦
    "tremolo":     ("bowed_string",),                       # 弦乐震音（快碎弓）
    "flutter":     ("lip_reed", "single_reed", "air_jet", "vocal_fold"),   # 花舌
    "key_click":   ("single_reed", "air_jet"),              # 按键/键孔声
    "roll":        ("struck_body",),                        # 滚奏（定音鼓等）
    "brush":       ("struck_body",),                        # 鼓刷
    "rim_shot":    ("struck_body",),                        # 敲鼓边
    # 铜管弱音器种类（straight = 普通 mute_on）
    "mute_cup":    ("lip_reed",),
    "mute_harmon": ("lip_reed",),
    "mute_plunger": ("lip_reed",),
    "half_valve":  ("lip_reed",),
    "growl":       ("lip_reed", "single_reed"),
}
TURN_KINDS = tuple(ACTION_MECHS)

# 连续参数（curves）：参数 → 值域
CURVE_PARAMS = {
    "dynamics": (0, 1000),
    "brightness": (0, 1000),
    "pitch_cents": (-2400, 2400),
    "vibrato": (0, 1000),        # 颤音深度（‰），频率取该乐器 timbre 默认
    "bow_position": (0, 1000),   # 0 = sul tasto（靠指板，暗）… 1000 = ponticello（靠桥，亮）
}

# 奏法：机制 → 允许的奏法（写谱侧据此拒绝不该有的记号）
ARTICULATIONS_BY_MECH = {
    "hammered_string": ("staccato", "staccatissimo", "tenuto", "marcato", "accent"),
    "plucked_string":  ("staccato", "tenuto", "marcato", "accent"),
    "bowed_string":    ("staccato", "staccatissimo", "tenuto", "marcato", "accent"),
    "lip_reed":        ("staccato", "tenuto", "marcato", "accent"),
    "single_reed":     ("staccato", "tenuto", "marcato", "accent"),
    "air_jet":         ("staccato", "tenuto", "marcato", "accent"),
    "vocal_fold":      ("tenuto", "marcato", "accent"),
    "struck_body":     ("staccato", "marcato", "accent"),
    "electronic":      ("staccato", "tenuto", "marcato", "accent"),
    "noise":           ("staccato", "accent"),
}

# 装饰音：机制 → 允许的装饰音
ORNAMENTS_BY_MECH = {
    "hammered_string": ("grace_short", "appoggiatura_long", "mordent", "turn", "trill"),
    "plucked_string":  ("grace_short", "appoggiatura_long", "mordent", "turn", "trill"),
    "bowed_string":    ("grace_short", "appoggiatura_long", "mordent", "turn", "trill"),
    "lip_reed":        ("grace_short", "trill"),
    "single_reed":     ("grace_short", "trill"),
    "air_jet":         ("grace_short", "trill"),
    "vocal_fold":      ("grace_short", "appoggiatura_long"),
    "struck_body":     ("grace_short",),
    "electronic":      ("grace_short", "trill"),
    "noise":           ("grace_short",),
}

# ── 鼓件映射：打击乐键号不是"音高"，是哪一件鼓 ──
#   GM 打击乐（channel 10）：键号 → (名称, 合成类型, 衰减秒, 亮度, 噪声比)
DRUM_MAP = {
    35: ("kick_2", "body", 0.45, 2.0, 0.05),
    36: ("kick_1", "body", 0.50, 2.2, 0.05),
    37: ("side_stick", "click", 0.06, 6.0, 0.60),
    38: ("snare_1", "noise_body", 0.22, 7.0, 0.55),
    39: ("hand_clap", "noise", 0.18, 8.0, 0.90),
    40: ("snare_2", "noise_body", 0.20, 7.5, 0.60),
    41: ("tom_low", "body", 0.40, 3.0, 0.10),
    42: ("hihat_closed", "noise", 0.07, 12.0, 0.95),
    43: ("tom_mid_low", "body", 0.36, 3.4, 0.10),
    44: ("hihat_pedal", "noise", 0.09, 11.0, 0.95),
    45: ("tom_mid", "body", 0.34, 3.8, 0.10),
    46: ("hihat_open", "noise", 0.45, 10.0, 0.95),
    47: ("tom_mid_high", "body", 0.32, 4.2, 0.10),
    48: ("tom_high", "body", 0.30, 4.6, 0.10),
    49: ("crash", "noise", 1.20, 9.0, 0.95),
    50: ("tom_floor_high", "body", 0.38, 3.2, 0.10),
    51: ("ride", "noise", 0.90, 11.0, 0.90),
    52: ("china", "noise", 1.00, 9.5, 0.95),
    53: ("ride_bell", "body", 0.70, 12.0, 0.30),
    54: ("tambourine", "noise", 0.25, 13.0, 0.90),
    55: ("splash", "noise", 0.70, 11.5, 0.95),
    56: ("cowbell", "body", 0.35, 9.0, 0.20),
    57: ("crash_2", "noise", 1.10, 9.2, 0.95),
    59: ("ride_2", "noise", 0.85, 10.5, 0.90),
    60: ("bongo_high", "body", 0.20, 5.5, 0.20),
    61: ("bongo_low", "body", 0.24, 5.0, 0.20),
    62: ("conga_high", "body", 0.26, 4.8, 0.20),
    63: ("conga_low", "body", 0.30, 4.4, 0.20),
    64: ("timbale_high", "body", 0.28, 5.2, 0.20),
    65: ("timbale_low", "body", 0.30, 4.8, 0.20),
    66: ("agogo_high", "body", 0.30, 8.0, 0.15),
    67: ("agogo_low", "body", 0.32, 7.4, 0.15),
    69: ("cabasa", "noise", 0.20, 12.0, 0.90),
    70: ("maracas", "noise", 0.18, 12.5, 0.92),
    75: ("claves", "click", 0.10, 9.0, 0.40),
    76: ("wood_block_high", "click", 0.10, 7.0, 0.45),
    77: ("wood_block_low", "click", 0.12, 6.0, 0.45),
    80: ("triangle_closed", "body", 0.50, 13.0, 0.20),
    81: ("triangle_open", "body", 0.90, 12.5, 0.20),
}
HIHAT_KEYS = (42, 44, 46)          # 闭/踩/开镲：受 hihat 踏板影响


# 乐器级覆盖：机制（harp/harpsichord 曾被归错）
TYPE_MECHANISMS = {
    "orchestral_harp": "plucked_string",
    "harpsichord": "plucked_string",
    "pizzicato_strings": "plucked_string",
}
# 乐器级覆盖：音域（族级音域只适用于代表乐器，不能一族人共用）
TYPE_RANGE = {
    "violin": (55, 103), "viola": (48, 88), "cello": (36, 76), "contrabass": (28, 67),
    "fiddle": (55, 103), "tremolo_strings": (55, 103), "pizzicato_strings": (55, 103),
    "string_ensemble_1": (36, 103), "string_ensemble_2": (36, 103),
    "orchestral_harp": (24, 103),
    "trumpet": (55, 82), "trombone": (40, 72), "tuba": (28, 58),
    "french_horn": (34, 77), "brass_section": (28, 82),
    "flute": (60, 96), "piccolo": (74, 108), "recorder": (72, 100),
    "soprano": (60, 84), "alto": (55, 79), "tenor": (48, 72), "bass": (40, 64),
}


# 收束结构（机制级默认）：**只描述"能不能弹"，不阻止写入**。
#   max_simultaneous 同刻最多几个音 · max_span 和弦最大跨度(半音)
#   max_polyphony 同时最多几个音在响 · max_hold_s 单音最长持续(秒)
#   strings 弦数 · max_double_stops 双音上限 · hands 手数
CONSTRAINTS = {
    "hammered_string": dict(max_simultaneous=10, max_span=12, max_polyphony=10, hands=2,
                            min_retrigger_ms=20),   # 同一键再击的最短间隔
    "plucked_string":  dict(max_simultaneous=6,  max_span=12, max_polyphony=6,  hands=2,
                            min_retrigger_ms=30, min_restrike_ms=25),
    "bowed_string":    dict(max_simultaneous=4,  max_span=12, max_polyphony=4,  strings=4,
                            max_double_stops=2, hands=2, max_bow_s=8,
                            min_bow_change_ms=20,   # 换弓（转折）最短间隔（连奏换弓可极短）
                            min_retrigger_ms=60),
    "lip_reed":        dict(max_simultaneous=1,  max_polyphony=1, max_hold_s=20, hands=2,
                            min_breath_ms=80),   # 换气/吐音
    "single_reed":     dict(max_simultaneous=1,  max_polyphony=1, max_hold_s=20, hands=2,
                            min_breath_ms=80),
    "air_jet":         dict(max_simultaneous=1,  max_polyphony=1, max_hold_s=20, hands=2,
                            min_breath_ms=80),
    "struck_body":     dict(max_simultaneous=4,  max_span=24, max_polyphony=8, hands=2,
                            min_retrigger_ms=40, min_mallet_ms=60),
    "vocal_fold":      dict(max_simultaneous=1,  max_polyphony=1, max_hold_s=15,
                            min_breath_ms=100),
    "electronic":      dict(max_simultaneous=10, max_span=24, max_polyphony=16, hands=2),
    "noise":           dict(max_simultaneous=8,  max_polyphony=8),
}


# 乐器级收束校准（覆盖机制默认）。只写与默认不同的项。
TYPE_CONSTRAINTS = {
    # 弓弦：弦数/双音差异很大
    "erhu": dict(strings=2, max_double_stops=0, max_bow_s=8),
    "gaohu": dict(strings=2, max_double_stops=0, max_bow_s=7),
    "zhonghu": dict(strings=2, max_double_stops=0, max_bow_s=9),
    "banhu": dict(strings=2, max_double_stops=0, max_bow_s=7),
    "jinghu": dict(strings=2, max_double_stops=0, max_bow_s=6),
    "matouqin": dict(strings=2, max_double_stops=0, max_bow_s=8),
    "fiddle": dict(strings=4, max_double_stops=2, max_bow_s=8),
    "tremolo_strings": dict(max_bow_s=8),
    "pizzicato_strings": dict(max_bow_s=8),
    "string_ensemble_1": dict(strings=4, max_double_stops=0, max_bow_s=10),
    "string_ensemble_2": dict(strings=4, max_double_stops=0, max_bow_s=10),
    "violin": dict(strings=4, max_double_stops=2, max_bow_s=8),
    "viola": dict(strings=4, max_double_stops=2, max_bow_s=10),
    "cello": dict(strings=4, max_double_stops=2, max_bow_s=12),
    "contrabass": dict(strings=4, max_double_stops=1, max_bow_s=10),
    "matouqin": dict(strings=2, max_double_stops=0),
    # 拨弦：弦数
    "guzheng": dict(strings=21, max_simultaneous=10, max_polyphony=10),
    "guqin": dict(strings=7, max_simultaneous=4, max_polyphony=4),
    "pipa": dict(strings=4, max_simultaneous=4, max_polyphony=4),
    "acoustic_guitar_nylon": dict(strings=6, max_simultaneous=6),
    "acoustic_guitar_steel": dict(strings=6, max_simultaneous=6),
    "electric_guitar_clean": dict(strings=6, max_simultaneous=6),
    # 击体：编钟/编磬多槌
    "bianzhong": dict(max_simultaneous=6, max_span=24),
    "bianqing": dict(max_simultaneous=4, max_span=24),
    # 铜管：按乐器给气息长度
    "trumpet": dict(max_hold_s=10), "muted_trumpet": dict(max_hold_s=10),
    "trombone": dict(max_hold_s=14), "tuba": dict(max_hold_s=16),
    "french_horn": dict(max_hold_s=14), "brass_section": dict(max_hold_s=14),
    # 人声：按声部给气息长度（低声部更长）
    "choir_aahs": dict(max_hold_s=14), "voice_oohs": dict(max_hold_s=14),
    "soprano": dict(max_hold_s=12), "alto": dict(max_hold_s=13),
    "tenor": dict(max_hold_s=15), "bass": dict(max_hold_s=18),
    "child": dict(max_hold_s=10),
    # 打击：按槌数
    "timpani": dict(max_simultaneous=2), "tubular_bells": dict(max_simultaneous=2),
    "glockenspiel": dict(max_simultaneous=2), "vibraphone": dict(max_simultaneous=4),
    "marimba": dict(max_simultaneous=4), "xylophone": dict(max_simultaneous=4),
    "celesta": dict(max_simultaneous=2),
    # 木管气息（按乐器给）
    "piccolo": dict(max_hold_s=10), "flute": dict(max_hold_s=14),
    "recorder": dict(max_hold_s=12), "pan_flute": dict(max_hold_s=12),
    "oboe": dict(max_hold_s=12), "english_horn": dict(max_hold_s=13),
    "clarinet": dict(max_hold_s=15), "bassoon": dict(max_hold_s=14),
    "soprano_sax": dict(max_hold_s=13), "alto_sax": dict(max_hold_s=14),
    "tenor_sax": dict(max_hold_s=15), "baritone_sax": dict(max_hold_s=16),
}

# 乘因说明（机制级）：同一因子在不同机制里怎么组合。S02/前端也可读这份说明。
COMBINE = {
    "hammered_string": dict(
        amp="f(permille) × 槌头硬度 × 制音器(踏板)",
        brightness="g(permille)（越重越亮）",
        duration="弦自由衰减 ⊕ 踏板延音",
        factors=["permille", "pedal", "subtype"]),
    "plucked_string": dict(
        amp="f(permille) × 拨点 × 弦阻尼",
        brightness="g(permille) × 拨点位置",
        duration="弦自由衰减 ⊕ 手/制音",
        factors=["permille", "subtype", "section"]),
    "bowed_string": dict(
        amp="弓压 × 弓速 × 弓位置",
        brightness="h(弓压, 弓速, 靠桥程度)",
        duration="弓持续；松弓才衰减",
        factors=["permille", "bow_length", "section"]),
    "lip_reed": dict(amp="气压 × 唇振效率", brightness="h(气压)", duration="持续；换气才断",
                     factors=["permille", "breath"]),
    "single_reed": dict(amp="气压 × 簧片效率", brightness="h(气压)", duration="持续；换气才断",
                        factors=["permille", "breath"]),
    "air_jet": dict(amp="气压 × 哨口效率", brightness="h(气压)", duration="持续；换气才断",
                    factors=["permille", "breath"]),
    "struck_body": dict(amp="槌重 × 槌速 × 击点", brightness="h(材质, 击点)", duration="体自由衰减",
                        factors=["permille", "mallets"]),
    "vocal_fold": dict(amp="气息压力 × 声带张力", brightness="h(张力, 共振峰)", duration="持续；换气才断",
                       factors=["permille", "tone", "lang"]),
    "electronic": dict(amp="f(permille)", brightness="g(permille)", duration="按包络参数",
                       factors=["permille", "subtype"]),
    "noise": dict(amp="f(permille)", brightness="h(类型)", duration="按包络参数", factors=["permille"]),
}


# 逐类型音色覆盖（族默认之上）。只写与族不同的项。
TYPE_TIMBRE = {
    # 木管：亮度与气声差异
    "piccolo":   dict(bright=(7, 16), roll=1.15, tau=2.6, noise=0.020),
    "flute":     dict(bright=(4, 11), roll=1.25, noise=0.018),
    "recorder":  dict(bright=(3, 9),  roll=1.30, noise=0.030),
    "pan_flute": dict(bright=(3, 10), roll=1.30, noise=0.035),
    "shakuhachi": dict(bright=(3, 9), roll=1.32, noise=0.040),
    "oboe":      dict(bright=(5, 13), roll=1.20, noise=0.008),
    "english_horn": dict(bright=(4, 11), roll=1.28, noise=0.010),
    "clarinet":  dict(bright=(3, 9),  roll=1.35, noise=0.006),
    "bassoon":   dict(bright=(3, 10), roll=1.30, noise=0.010),
    # 萨克斯
    "soprano_sax": dict(bright=(5, 13), roll=1.20),
    "alto_sax":    dict(bright=(4, 12), roll=1.24),
    "tenor_sax":   dict(bright=(3, 11), roll=1.28),
    "baritone_sax": dict(bright=(3, 10), roll=1.32),
    # 铜管
    "trumpet":     dict(bright=(6, 15), roll=1.15, attack=0.020),
    "muted_trumpet": dict(bright=(4, 10), roll=1.30, attack=0.020),
    "trombone":    dict(bright=(5, 13), roll=1.20, attack=0.035),
    "tuba":        dict(bright=(3, 9),  roll=1.25, attack=0.045),
    "french_horn": dict(bright=(4, 11), roll=1.30, attack=0.040),
    "brass_section": dict(bright=(5, 13), roll=1.22, detune=2.0),
    # 槌击
    "marimba":     dict(bright=(4, 10), tau=0.90),
    "vibraphone":  dict(bright=(5, 12), tau=2.50),
    "xylophone":   dict(bright=(7, 16), tau=0.45),
    "glockenspiel": dict(bright=(8, 18), tau=0.60),
    "celesta":     dict(bright=(6, 14), tau=0.80),
    "tubular_bells": dict(bright=(6, 14), tau=3.50),
    # 键盘/拨弦
    "harpsichord": dict(bright=(5, 13), tau=0.90, detune=0.0),
    "clavinet":    dict(bright=(6, 15), tau=0.70, detune=0.0),
    "church_organ": dict(bright=(7, 15), tau=9.00),
    "orchestral_harp": dict(bright=(4, 12), roll=1.20, tau=3.00),
    # 弓弦独奏更干净（少失谐）
    "violin":   dict(detune=0.8),
    "viola":    dict(detune=0.8),
    "cello":    dict(detune=0.8),
    "contrabass": dict(detune=1.0),
    # 打击
    "timpani":  dict(bright=(5, 14), tau=0.70, noise=0.10),
    # 中国民族乐器（逐件）
    "guzheng":  dict(bright=(5, 13), roll=1.15, tau=1.40, detune=2.0, noise=0.010),
    "guqin":    dict(bright=(3, 9),  roll=1.30, tau=2.00, detune=1.5, noise=0.015),
    "pipa":     dict(bright=(6, 15), roll=1.10, tau=0.90, detune=1.0, noise=0.020),
    "yangqin":  dict(bright=(6, 14), roll=1.30, tau=0.70, detune=1.0, noise=0.012),
    "liuqin":   dict(bright=(7, 16), roll=1.20, tau=0.60, detune=0.8, noise=0.015),
    "erhu":     dict(bright=(3, 9),  roll=1.30, tau=3.50, detune=1.0, noise=0.012),
    "gaohu":    dict(bright=(4, 11), roll=1.28, tau=3.20, detune=1.0, noise=0.012),
    "zhonghu":  dict(bright=(3, 9),  roll=1.32, tau=3.60, detune=1.0, noise=0.012),
    "banhu":    dict(bright=(5, 13), roll=1.25, tau=3.00, detune=1.2, noise=0.018),
    "jinghu":   dict(bright=(6, 15), roll=1.20, tau=2.60, detune=1.2, noise=0.020),
    "dizi":     dict(bright=(5, 13), roll=1.20, tau=3.00, detune=0.5, noise=0.025),
    "xiao":     dict(bright=(3, 9),  roll=1.30, tau=3.20, detune=0.5, noise=0.030),
    "sheng":    dict(bright=(4, 11), roll=1.20, tau=3.30, detune=1.0, noise=0.020),
    "suona":    dict(bright=(7, 16), roll=1.15, tau=2.50, detune=0.5, noise=0.010),
    "guanzi":   dict(bright=(4, 11), roll=1.25, tau=3.10, detune=0.5, noise=0.015),
    "bawu":     dict(bright=(3, 10), roll=1.28, tau=3.00, detune=0.5, noise=0.022),
    "hulusi":   dict(bright=(4, 11), roll=1.26, tau=2.80, detune=0.8, noise=0.018),

    # 风琴系
    "drawbar_organ":   dict(bright=(8, 16), tau=9.00, attack=0.008),
    "percussive_organ": dict(bright=(7, 14), tau=4.00, attack=0.006),
    "rock_organ":      dict(bright=(7, 15), tau=8.00, attack=0.010),
    "reed_organ":      dict(bright=(5, 12), tau=7.00, attack=0.015, noise=0.006),
    "accordion":       dict(bright=(5, 13), tau=6.00, attack=0.020, noise=0.008),
    "harmonica":       dict(bright=(5, 14), tau=5.00, attack=0.015, noise=0.020),
    "tango_accordion": dict(bright=(5, 13), tau=5.50, attack=0.018, noise=0.010),
    # 民族（非中国）
    "sitar":    dict(bright=(5, 14), roll=1.20, tau=1.60, detune=3.0, noise=0.015),
    "banjo":    dict(bright=(7, 16), roll=1.10, tau=0.70, detune=1.0, noise=0.020),
    "shamisen": dict(bright=(6, 15), roll=1.15, tau=0.80, detune=1.5, noise=0.020),
    "koto":     dict(bright=(5, 13), roll=1.20, tau=1.50, detune=2.0, noise=0.012),
    "kalimba":  dict(bright=(6, 14), roll=1.40, tau=0.70, noise=0.010),
    "bag_pipe": dict(bright=(4, 11), roll=1.28, tau=3.40, noise=0.030),
    "shanai":   dict(bright=(7, 16), roll=1.18, tau=2.40, noise=0.012),
    # 鼓组
    "kit_standard":  dict(bright=(6, 16), tau=0.40, noise=0.35),
    "kit_jazz":      dict(bright=(5, 14), tau=0.35, noise=0.40),
    "kit_brush":     dict(bright=(4, 12), tau=0.45, noise=0.50),
    "kit_orchestra": dict(bright=(4, 13), tau=0.60, noise=0.30),
    "kit_sfx":       dict(bright=(6, 16), tau=0.70, noise=0.60),
}


# 逐类型踏板声明（覆盖族默认）。空元组 = 该乐器没有踏板。
# 说明：调音踏板/表情踏板/踩镲踏板不属于 MS 的三种踏板语义（见 KNOWN_LIMITS）。
TYPE_PEDALS = {
    "harpsichord": (), "clavinet": (), "honky_tonk_piano": (),
    "celesta": ("sustain",), "vibraphone": ("sustain",),
    "marimba": (), "xylophone": (), "glockenspiel": (), "tubular_bells": (),
    "timpani": (), "kit_standard": ("hihat",), "kit_jazz": ("hihat",),
    "kit_brush": ("hihat",), "kit_orchestra": ("hihat",), "kit_sfx": ("hihat",),
    "church_organ": ("swell",), "drawbar_organ": (), "rock_organ": (), "reed_organ": (),
    "orchestral_harp": ("tuning",),   # 7 个调音踏板（targets 指音级，depth 三档）
    "acoustic_guitar_nylon": (), "acoustic_guitar_steel": (),
    # 电吉他/电贝斯：外接效果器属演奏/制作动作，不做成踏板 kind
    "electric_guitar_clean": (), "electric_guitar_muted": (),
    "overdriven_guitar": (), "distortion_guitar": (), "guitar_harmonics": (),
    "electric_bass_finger": (), "electric_bass_pick": (),
    "slap_bass_1": (), "slap_bass_2": (),
    "synth_bass_1": (), "synth_bass_2": (),
}

# 踏板响应因子：una_corda_darken=弱音时高次泛音保留比例（1.0=不变暗）
PEDAL_FACTORS = {
    "acoustic_grand_piano": dict(una_corda_darken=0.55, sustain_resonance=1.00),
    "electric_piano_1": dict(una_corda_darken=0.75, sustain_resonance=0.60),
    "electric_piano_2": dict(una_corda_darken=0.75, sustain_resonance=0.60),
    "celesta": dict(una_corda_darken=0.85, sustain_resonance=0.50),
    "vibraphone": dict(una_corda_darken=0.80, sustain_resonance=0.70),
}

_BY_CODE = {code: (program, family) for program, code, family in GM}


_RESOLVE_CACHE: dict = {}


def _resolve_uncached(type_code: str, subtype: str | None = None) -> dict:
    """把（类型码, 子类型码）解析成完整能力。

    返回 dict：program / family / range / poly / pedals / dyn / category / soundfont / notes。
    类型码不存在 → KeyError；子类型不存在 → KeyError。
    """
    if type_code in ZH_CATALOG:
        zh = ZH_CATALOG[type_code]
        family = zh["family"]
        spec = dict(FAMILIES[family])
        spec.update(type_code=type_code, family=family, program=None,
                    zh=zh["zh"], group=zh["group"], reserved=(zh["status"] == "预留"))
        spec.setdefault("soundfont", type_code)
        spec.setdefault("notes", zh["zh"])
        spec["subtype"] = subtype
        spec["timbre"] = dict(TIMBRE.get(family, TIMBRE["piano"]))
        spec["timbre"].update(TYPE_TIMBRE.get(type_code, {}))
        spec["mechanism"] = TYPE_MECHANISMS.get(type_code) or MECHANISMS.get(family, "hammered_string")
        spec["pedals"] = TYPE_PEDALS.get(type_code, spec.get("pedals"))
        spec.setdefault("pedal_factors", {}).update(PEDAL_FACTORS.get(type_code, {}))
        spec["constraints"] = dict(CONSTRAINTS.get(spec["mechanism"], CONSTRAINTS["hammered_string"]))
        spec["constraints"].update(TYPE_CONSTRAINTS.get(type_code, {}))
        spec["constraints"].setdefault("max_polyphony", spec.get("poly", 1))
        spec["off"] = dict(OFF_DEFAULTS.get(spec["mechanism"], OFF_DEFAULTS["hammered_string"]))
        spec["combine"] = dict(COMBINE.get(spec["mechanism"], COMBINE["hammered_string"]))
        return spec
    if type_code in EXTENDED:
        ext = EXTENDED[type_code]
        family = ext["family"]
        spec = dict(FAMILIES[family])
        spec.update(type_code=type_code, family=family, program=ext.get("program"))
        if "range" in ext:
            spec["range"] = ext["range"]
        if ext.get("drum_kit"):
            spec["drum_kit"] = True
        spec.setdefault("soundfont", type_code)
        spec.setdefault("notes", ext.get("notes", ""))
        spec["subtype"] = subtype
        spec["timbre"] = dict(TIMBRE.get(family, TIMBRE["piano"]))
        spec["timbre"].update(TYPE_TIMBRE.get(type_code, {}))
        spec["mechanism"] = MECHANISMS.get(family, "hammered_string")
        spec["pedals"] = TYPE_PEDALS.get(type_code, spec.get("pedals"))
        spec.setdefault("pedal_factors", {}).update(PEDAL_FACTORS.get(type_code, {}))
        spec["constraints"] = dict(CONSTRAINTS.get(spec["mechanism"], CONSTRAINTS["hammered_string"]))
        spec["constraints"].update(TYPE_CONSTRAINTS.get(type_code, {}))
        spec["combine"] = dict(COMBINE.get(spec["mechanism"], COMBINE["hammered_string"]))
        return spec
    if type_code not in _BY_CODE:
        raise KeyError(f"未登记的乐器类型：{type_code!r}（共 {len(_BY_CODE)} 种 + {len(EXTENDED)} 扩展）")
    program, family = _BY_CODE[type_code]
    spec = dict(FAMILIES[family])
    spec.update(type_code=type_code, family=family, program=program)
    if subtype is not None:
        subs = SUBTYPES.get(type_code, {})
        if subtype not in subs:
            raise KeyError(f"类型 {type_code!r} 没有子类型 {subtype!r}（可用：{sorted(subs) or '无'}）")
        spec.update(subs[subtype])
    spec.setdefault("soundfont", type_code)
    spec.setdefault("notes", "")
    spec["subtype"] = subtype
    spec["timbre"] = dict(TIMBRE.get(family, TIMBRE["piano"]))
    spec["timbre"].update(TYPE_TIMBRE.get(type_code, {}))
    # 机制：先看乐器级覆盖，再看族（harp/harpsichord 曾被族归错）
    spec["mechanism"] = TYPE_MECHANISMS.get(type_code) or MECHANISMS.get(family, "hammered_string")
    # 音域：乐器级覆盖优先（族级只适用于代表乐器）
    spec["range"] = TYPE_RANGE.get(type_code, spec.get("range"))
    spec["pedals"] = TYPE_PEDALS.get(type_code, spec.get("pedals"))
    spec.setdefault("pedal_factors", {}).update(PEDAL_FACTORS.get(type_code, {}))
    spec["constraints"] = dict(CONSTRAINTS.get(spec["mechanism"], CONSTRAINTS["hammered_string"]))
    spec["constraints"].update(TYPE_CONSTRAINTS.get(type_code, {}))
    # 族声明的复音数（poly）作为收束默认，避免两套数字并存
    spec["constraints"].setdefault("max_polyphony", spec.get("poly", 1))
    spec["off"] = dict(OFF_DEFAULTS.get(spec["mechanism"], OFF_DEFAULTS["hammered_string"]))
    spec["combine"] = dict(COMBINE.get(spec["mechanism"], COMBINE["hammered_string"]))
    return spec


def resolve(type_code: str, subtype: str | None = None) -> dict:
    """带缓存的解析入口（S02 会大量查询同一乐器）。"""
    key = (type_code, subtype)
    hit = _RESOLVE_CACHE.get(key)
    if hit is None:
        hit = _resolve_uncached(type_code, subtype)
        _RESOLVE_CACHE[key] = hit
    return dict(hit)


def resolve_many(instances) -> list[dict]:
    """批量解析乐器实例（list[Instrument]），返回与之一一对应的能力表。"""
    out = []
    for inst in instances:
        out.append(resolve(getattr(inst, "type", ""), getattr(inst, "subtype", None)))
    return out


def list_types() -> list[tuple]:
    """全部类型：(program|None, type_code, family)，GM 在前、扩展在后。"""
    rows = sorted(GM) + [(None, k, v["family"]) for k, v in sorted(EXTENDED.items())]
    rows += [(None, k, v["family"]) for k, v in sorted(ZH_CATALOG.items())
             if k not in EXTENDED]
    return rows


def list_subtypes(type_code: str) -> list[str]:
    return sorted(SUBTYPES.get(type_code, {}))


def check_registry() -> list[str]:
    """自检：program 连续 0..127、类型码唯一、每个类型有族、族有能力定义。"""
    errs = []
    programs = [p for p, _, _ in GM]
    if programs != list(range(128)):
        errs.append("GM program 不是完整 0..127")
    codes = [c for _, c, _ in GM]
    if len(set(codes)) != len(codes):
        errs.append("类型码重复")
    for _, code, fam in GM:
        if fam not in FAMILIES:
            errs.append(f"{code}: 未知族 {fam}")
    for fam, spec in FAMILIES.items():
        if not isinstance(spec.get("range"), tuple) or len(spec["range"]) != 2:
            errs.append(f"{fam}: range 非法")
        if spec.get("category") not in ("pitched", "percussion", "sfx", "voice"):
            errs.append(f"{fam}: category 非法")
    for code, subs in SUBTYPES.items():
        if code not in _BY_CODE and code not in EXTENDED:
            errs.append(f"子类型挂在未知类型上：{code}")
    for code, ext in EXTENDED.items():
        if ext["family"] not in FAMILIES:
            errs.append(f"扩展 {code}: 未知族 {ext['family']}")
    for code, zh in ZH_CATALOG.items():
        if zh["family"] not in FAMILIES:
            errs.append(f"目录 {code}: 未知族 {zh['family']}")
        if zh["group"] not in ("吹", "拉", "弹", "打", "古乐"):
            errs.append(f"目录 {code}: 未知分组 {zh['group']}")
        if zh["status"] not in ("可用", "预留"):
            errs.append(f"目录 {code}: 未知状态 {zh['status']}")
    return errs


# ── 扩展 / 补录接口（打包后由 `ms.registry` 转发；这里只做数据层） ──────
# 目的：以后补新人声语言、新乐器、新演奏动作/奏法/踏板时，不改解析器、只登记。

def register_instrument(type_code: str, *, family: str, mechanism: str | None = None,
                        pitch_range: tuple | None = None, poly: int | None = None,
                        pedals: tuple | None = None, subtypes: dict | None = None,
                        program: int | None = None, soundfont: str | None = None,
                        notes: str = "", replace: bool = False) -> dict:
    """补录一件乐器（扩展接口）。

    · `family` 必须是已登记的族（FAMILIES）；`mechanism` 缺省用族机制；
    · `program` 为 GM 音色号（0..127），没有就用 None（扩展乐器）；
    · 重复登记同一类型默认拒绝（`replace=True` 才覆盖）——避免静默改名。
    """
    if not type_code or not isinstance(type_code, str):
        raise ValueError("type_code 必须是非空字符串")
    if family not in FAMILIES:
        raise KeyError(f"未知族 {family!r}；可用：{sorted(FAMILIES)}")
    if (type_code in _BY_CODE or type_code in EXTENDED) and not replace:
        raise ValueError(f"乐器 {type_code!r} 已登记（replace=True 才覆盖）")
    if program is not None and not (0 <= int(program) <= 127):
        raise ValueError(f"program 必须在 0..127：{program}")
    if mechanism is not None and mechanism not in MECHANISMS.values():
        raise KeyError(f"未知发声机制 {mechanism!r}；可用：{sorted(set(MECHANISMS.values()))}")
    if pitch_range is not None and (len(tuple(pitch_range)) != 2
                                    or not (21 <= pitch_range[0] <= pitch_range[1] <= 108)):
        raise ValueError(f"pitch_range 必须落在 21..108 且升序：{pitch_range}")

    _BY_CODE[type_code] = (program, family)
    if mechanism:
        TYPE_MECHANISMS[type_code] = mechanism
    if pitch_range:
        TYPE_RANGE[type_code] = tuple(pitch_range)
    if poly is not None:
        TYPE_CONSTRAINTS.setdefault(type_code, {})["max_polyphony"] = int(poly)
    if pedals:
        TYPE_PEDALS[type_code] = tuple(pedals)
    if subtypes:
        SUBTYPES[type_code] = dict(subtypes)
    if soundfont or notes:
        EXTENDED.setdefault(type_code, {"family": family})
        EXTENDED[type_code]["family"] = family
        if soundfont:
            EXTENDED[type_code]["soundfont"] = soundfont
        if notes:
            EXTENDED[type_code]["notes"] = notes
    _RESOLVE_CACHE.clear()
    return resolve(type_code)


def register_turn_kind(mechanism: str, kind: str) -> tuple:
    """给某个发声机制补一个演奏转折（如以后加"泛音滑奏"）。"""
    if mechanism not in ACTION_MECHS:
        raise KeyError(f"未知机制 {mechanism!r}；可用：{sorted(ACTION_MECHS)}")
    if kind in ACTION_MECHS[mechanism]:
        return ACTION_MECHS[mechanism]
    ACTION_MECHS[mechanism] = tuple(ACTION_MECHS[mechanism]) + (kind,)
    if kind not in TURN_KINDS:
        globals()["TURN_KINDS"] = tuple(TURN_KINDS) + (kind,)
    return ACTION_MECHS[mechanism]


def register_articulation(mechanism: str, name: str) -> tuple:
    """给某个机制补奏法。"""
    if mechanism not in ARTICULATIONS_BY_MECH:
        raise KeyError(f"未知机制 {mechanism!r}；可用：{sorted(ARTICULATIONS_BY_MECH)}")
    ARTICULATIONS_BY_MECH[mechanism] = tuple(ARTICULATIONS_BY_MECH[mechanism]) + (name,)
    return ARTICULATIONS_BY_MECH[mechanism]


def register_ornament(mechanism: str, name: str) -> tuple:
    """给某个机制补装饰音。"""
    if mechanism not in ORNAMENTS_BY_MECH:
        raise KeyError(f"未知机制 {mechanism!r}；可用：{sorted(ORNAMENTS_BY_MECH)}")
    ORNAMENTS_BY_MECH[mechanism] = tuple(ORNAMENTS_BY_MECH[mechanism]) + (name,)
    return ORNAMENTS_BY_MECH[mechanism]


def register_pedal(type_code: str, kind: str) -> tuple:
    """给某类乐器补一种踏板。"""
    if type_code not in _BY_CODE and type_code not in EXTENDED:
        raise KeyError(f"未登记的乐器类型：{type_code!r}")
    TYPE_PEDALS[type_code] = tuple(TYPE_PEDALS.get(type_code, ())) + (kind,)
    _RESOLVE_CACHE.clear()
    return TYPE_PEDALS[type_code]


def register_language(code: str, name: str) -> dict:
    """补一门人声语言（写谱侧 lang 字段）。"""
    if not code or not isinstance(code, str):
        raise ValueError("语言码必须是非空字符串")
    LANGUAGES[code] = name
    return dict(LANGUAGES)


def unregister_instrument(type_code: str) -> None:
    """撤销一件补录的乐器（只允许撤销扩展表里、且没有子类型挂着的）。"""
    if type_code not in _BY_CODE:
        raise KeyError(f"未登记：{type_code!r}")
    _BY_CODE.pop(type_code, None)
    for tbl in (TYPE_MECHANISMS, TYPE_RANGE, TYPE_PEDALS, TYPE_CONSTRAINTS):
        tbl.pop(type_code, None)
    SUBTYPES.pop(type_code, None)
    EXTENDED.pop(type_code, None)
    _RESOLVE_CACHE.clear()
