# -*- coding: utf-8 -*-
"""S02 索引：动机签名 + 关系边 + 特征。"""
from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE note(id TEXT PRIMARY KEY, inst INTEGER, voice TEXT, staff TEXT,
                  onset INTEGER, dur INTEGER, semi INTEGER, vel INTEGER, bar INTEGER);
CREATE TABLE edge(src TEXT, dst TEXT, kind TEXT, w REAL, PRIMARY KEY(src, dst, kind));
CREATE TABLE motif(id TEXT PRIMARY KEY, signature TEXT, length INTEGER, first_note TEXT,
                   variant_of TEXT, transform TEXT);
CREATE TABLE occurrence(motif TEXT, start_note TEXT, end_note TEXT,
                        transposed_by INTEGER, voice TEXT, bar INTEGER,
                        PRIMARY KEY(motif, start_note));
CREATE TABLE variant(motif TEXT, transform TEXT, start_note TEXT, end_note TEXT,
                     voice TEXT, bar INTEGER, PRIMARY KEY(motif, start_note));
CREATE TABLE feature(scope TEXT, scope_id INTEGER, name TEXT, value REAL,
                     PRIMARY KEY(scope, scope_id, name));
CREATE TABLE section(id TEXT PRIMARY KEY, start_bar INTEGER, end_bar INTEGER,
                     label TEXT, why TEXT, notes INTEGER,
                     density REAL, tension REAL, centroid REAL);
CREATE TABLE phrase(id TEXT PRIMARY KEY, section TEXT, start_bar INTEGER,
                    end_bar INTEGER, reason TEXT);
CREATE INDEX idx_edge_src ON edge(src);
CREATE INDEX idx_occ_motif ON occurrence(motif);
CREATE INDEX idx_note_onset ON note(onset);
CREATE INDEX idx_phrase_sec ON phrase(section);
"""

MIN_TOKENS = 2          # 至少 3 个音才算动机（2 个 token）
MAX_TOKENS = 8


@dataclass
class Motif:
    id: str
    signature: str
    length: int                 # 音数
    first_note: str
    occurrences: list = field(default_factory=list)   # [(start_id, end_id, transposed_by, voice, bar)]
    ivs: tuple = ()             # 音程序列（移调不变）
    rhs: tuple = ()             # 时值比例序列
    variant_of: str | None = None    # 变体所属的母动机
    transform: str | None = None     # inversion / retrograde / rhythmic
    line: tuple = ()                 # 所属旋律线 (乐器, 声部)

    @property
    def count(self) -> int:
        return len(self.occurrences)


VARIANTS = ("inversion", "retrograde", "rhythmic")


def classify_variant(a: "Motif", b: "Motif"):
    """b 是 a 的哪种变体；不是变体返回 None。

    倒影：音程取反、节奏不变
    逆行：音程倒序取反、节奏倒序
    节奏变形：音程相同、节奏不同
    """
    if len(a.ivs) != len(b.ivs) or not a.ivs:
        return None
    if tuple(b.ivs) == tuple(-x for x in a.ivs) and tuple(b.rhs) == tuple(a.rhs):
        return "inversion"
    if tuple(b.ivs) == tuple(-x for x in reversed(a.ivs)) \
            and tuple(b.rhs) == tuple(reversed(a.rhs)):
        return "retrograde"
    if tuple(b.ivs) == tuple(a.ivs) and tuple(b.rhs) != tuple(a.rhs):
        return "rhythmic"
    return None


# ── 旋律线切分 ───────────────────────────────────────────

def _lines(score) -> dict:
    """按 (乐器, 声部) 切成旋律线：动机是"一条线上的连续音"。"""
    lines = {}
    for n in sorted(score.notes, key=lambda x: (x.onset, x.id)):
        lines.setdefault((n.instrument_id, n.voice), []).append(n)
    return lines


def _tokens(notes) -> list:
    """相邻音 → (音程, 时值比例)。比例以本线最短时值为单位。"""
    durs = [n.duration for n in notes if n.duration > 0]
    if not durs:
        return []
    unit = 0
    for d in durs:
        unit = d if unit == 0 else _gcd(unit, d)
    toks = []
    for a, b in zip(notes, notes[1:]):
        toks.append((b.pitch.semitone - a.pitch.semitone,
                     max(1, a.duration // unit), max(1, b.duration // unit)))
    return toks


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


# ── 动机发现：最长重复子串（签名分组，不做两两比较）────────

def _discover(tokens: list, *, min_tokens=MIN_TOKENS, max_tokens=MAX_TOKENS) -> list:
    """返回 [(start, length_tokens, [positions...])]，按最长优先、互不重叠覆盖。"""
    n = len(tokens)
    used = set()
    found = []
    for L in range(min(max_tokens, n), min_tokens - 1, -1):
        groups = {}
        for i in range(n - L + 1):
            if any(j in used for j in range(i, i + L)):
                continue
            groups.setdefault(tuple(tokens[i:i + L]), []).append(i)
        for key, starts in sorted(groups.items(), key=lambda kv: kv[1][0]):
            occ = [s for s in starts if not any(j in used for j in range(s, s + L))]
            if len(occ) < 2:
                continue
            # 尽量向右扩（所有出现处下一个 token 都相同才能扩）
            cur = L
            while cur < max_tokens and all(s + cur < n for s in occ):
                nxt = tokens[occ[0] + cur]
                if any(tokens[s + cur] != nxt for s in occ):
                    break
                cur += 1
            # 扩完若与已用冲突，退回原长
            if any(j in used for s in occ for j in range(s, s + cur)):
                cur = L
            for s in occ:
                used.update(range(s, s + cur))
            found.append((occ[0], cur, occ))
    return _drop_contained(found)


def _drop_contained(found: list) -> list:
    """去掉"整体落在更长动机的每次出现之内"的碎片（避免 3 音碎片淹没长动机）。"""
    def covers(a, b) -> bool:
        a0, al = a[0], a[1]
        b0, bl = b[0], b[1]
        return b0 <= a0 and a0 + al <= b0 + bl

    keep = []
    for i, item in enumerate(found):
        inside = False
        for j, other in enumerate(found):
            if i == j or other[1] <= item[1]:
                continue
            # 该动机的**每次**出现都被同一个更长动机覆盖 → 视为碎片
            if all(any(covers(rng(item, o), rng(other, p)) for p in other[2])
                   for o in item[2]):
                inside = True
                break
        if not inside:
            keep.append(item)
    return keep


def rng(item: tuple, start: int) -> tuple:
    return (start, item[1])


def _sig(tokens: list, start: int, length: int) -> str:
    iv = [t[0] for t in tokens[start:start + length]]
    rh = [f"{t[1]}:{t[2]}" for t in tokens[start:start + length]]
    return "iv=" + ",".join(f"{x:+d}" for x in iv) + " rh=" + ",".join(rh)


def parse_sig(sig: str) -> tuple:
    """`iv=+2,+2,+1 rh=9:9,9:9` → (ivs, rhs)。用于从 `.s02x` 还原动机。"""
    left, _, right = sig.partition(" rh=")
    ivs = tuple(int(x) for x in left.replace("iv=", "").split(",") if x)
    rhs = tuple(tuple(int(y) for y in x.split(":")) for x in right.split(",") if x)
    return ivs, rhs


def line_sig_of(notes) -> str:
    """一条线的签名：token 序列的 sha1（与 `s02_incremental.line_sigs` 同口径）。"""
    import hashlib
    import json as _json
    raw = _json.dumps(_tokens(notes), ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


# ── 建索引 ───────────────────────────────────────────────

def build(score, *, probe=None, prev=None) -> dict:
    """ScoreV02 → 索引（notes/edges/motifs/occurrences/features）。

    `prev`（可选）：上一版 idx dict。给了就**按旋律线增量**：线签名没变的线
    直接复用其动机（id 保持不变），只重算改过的线；边/特征/段落仍整体重算。
    """
    motifs: list = []
    edges: list = []
    lines = _lines(score)
    sigs = {f"{k[0]}|{k[1]}": line_sig_of(notes) for k, notes in lines.items()}

    prev_sigs = (prev or {}).get("line_sig") or {}
    prev_motifs = (prev or {}).get("motifs") or []
    prev_variants = (prev or {}).get("variants") or []
    prev_by_line: dict = {}
    for m in prev_motifs:
        prev_by_line.setdefault(tuple(m.line) if m.line else (), []).append(m)

    used_ids = set()
    for m in prev_motifs:
        used_ids.add(m.id)
    next_id = max((int(m.id[1:]) for m in prev_motifs if m.id[1:].isdigit()), default=0) + 1

    reused_lines = rebuilt_lines = reused_motifs = 0
    reused_motif_ids = set()

    for key, notes in lines.items():
        toks = _tokens(notes)
        toks_key = f"{key[0]}|{key[1]}"
        for a, b in zip(notes, notes[1:]):                       # 带状：相邻关系
            edges.append((a.id, b.id, "next", float(b.pitch.semitone - a.pitch.semitone)))
        if not toks:
            continue
        if prev_sigs.get(toks_key) == sigs[toks_key]:
            reused_lines += 1
            for m in prev_by_line.get(key, []):
                m2 = copy.deepcopy(m)
                m2.line = key
                motifs.append(m2)
                reused_motifs += 1
                reused_motif_ids.add(m2.id)
                for i in range(len(m2.occurrences)):
                    for j in range(i + 1, len(m2.occurrences)):
                        edges.append((m2.occurrences[i][0], m2.occurrences[j][0],
                                      "similar", float(len(m2.ivs))))
            continue
        rebuilt_lines += 1
        for start, length, occ in _discover(toks):
            ivs = [t[0] for t in toks[start:start + length]]
            if all(iv == 0 for iv in ivs):
                continue          # 纯同音反复（震音/持续音）不算旋律动机
            mid = f"M{next_id:04d}"
            next_id += 1
            first = notes[occ[0]]
            occ_rows = []
            for s in occ:
                st, en = notes[s], notes[min(s + length, len(notes) - 1)]
                occ_rows.append((st.id, en.id, st.pitch.semitone - first.pitch.semitone,
                                 key[1], st.measure))
            motifs.append(Motif(id=mid, signature=_sig(toks, start, length),
                                length=length + 1, first_note=first.id,
                                occurrences=occ_rows,
                                ivs=tuple(ivs),
                                rhs=tuple((t[1], t[2]) for t in toks[start:start + length]),
                                line=key))
            # 同动机各出现之间建立 similar 边（长程关系）
            for i in range(len(occ_rows)):
                for j in range(i + 1, len(occ_rows)):
                    a_, b_ = occ_rows[i][0], occ_rows[j][0]
                    edges.append((a_, b_, "similar", float(length)))

    # ── 变体扫描：在全曲里找每个动机的倒影/逆行/节奏变形出现 ──
    #   按"动机的连续子段"匹配（不要求整段），因为段落交界处的连接音程会拉长动机。
    variant_rows = []
    for m in motifs:
        if len(m.ivs) < 4:
            continue                    # 太短的动机谈"变体"没意义
        if m.id in reused_motif_ids:    # 线没变 → 变体也不变，直接复用（连边一起补回）
            for v in prev_variants:
                if v[0] == m.id:
                    variant_rows.append(v)
                    edges.append((v[2], m.first_note, "variant", float(len(m.ivs) + 1)))
            continue
        exact = {(o[0], o[1]) for o in m.occurrences}
        lines_to_scan = [m.line] if m.line in lines else list(lines)
        for key in lines_to_scan:
            notes = lines[key]
            voice = key[1]
            toks = _tokens(notes)
            best = {}          # start → (k, kind)
            kmin = max(3, len(m.ivs) - 2)   # 变体要覆盖动机的大部分，否则短碎片会刷屏
            for k in range(kmin, len(m.ivs) + 1):
                subs = [m.ivs[j:j + k] for j in range(len(m.ivs) - k + 1)]
                rhsubs = {tuple(m.rhs[j:j + k]) for j in range(len(m.rhs) - k + 1)}
                inv = {tuple(-x for x in s) for s in subs}
                ret = {tuple(-x for x in reversed(s)) for s in subs}
                same = set(subs)
                for i in range(len(toks) - k + 1):
                    iv = tuple(t[0] for t in toks[i:i + k])
                    rh = tuple((t[1], t[2]) for t in toks[i:i + k])
                    if iv in inv:
                        kind = "inversion"
                    elif iv in ret:
                        kind = "retrograde"
                    elif iv in same and rh not in rhsubs:
                        kind = "rhythmic"
                    else:
                        continue
                    if i not in best or k > best[i][0]:
                        best[i] = (k, kind)
            kept, last_end = [], -1
            for i, (k, kind) in sorted(best.items()):
                if kind == "rhythmic" and k < 4:
                    continue          # 节奏变形要求更长，否则 3 音到处都能"变形"
                if i < last_end:
                    continue          # 重叠窗口只留最早的一个
                kept.append((i, k, kind))
                last_end = i + k
                if len(kept) >= 200:  # 防御：极端重复的曲子不让变体边爆炸
                    break
            for i, k, kind in kept:
                st, en = notes[i], notes[min(i + k, len(notes) - 1)]
                if (st.id, en.id) in exact:
                    continue
                variant_rows.append((m.id, kind, st.id, en.id, voice, st.measure))
                edges.append((st.id, m.first_note, "variant", float(k + 1)))

    # 同刻关系（和弦/干涉）：同一乐器的同 onset 音两两相连
    by_onset = {}
    for n in score.notes:
        by_onset.setdefault((n.instrument_id, n.onset), []).append(n)
    for (_inst, _on), group in by_onset.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                edges.append((group[i].id, group[j].id, "simult",
                              float(abs(group[i].pitch.semitone - group[j].pitch.semitone))))

    features = _features(score, probe)

    # 段落 / 句读 / 标签（L4）：写进索引，前端可直接查
    sections, phrases = [], []
    try:
        import s02_segment
        sg = s02_segment.segment(score)
        for x in sg.get("sections", []):
            f = x.get("features") or {}
            sections.append((x["id"], x["start_bar"], x["end_bar"], x["label"],
                             x.get("why", ""), int(x.get("notes") or 0),
                             float(f.get("density") or 0), float(f.get("v_tension_mean") or 0),
                             float(f.get("centroid") or 0)))
        for p in sg.get("phrases", []):
            phrases.append((p["id"], p["section"], p["start_bar"], p["end_bar"],
                            p.get("reason", "")))
    except Exception:
        pass

    return {"notes": score.notes, "edges": edges, "motifs": motifs,
            "features": features, "sections": sections, "phrases": phrases,
            "variants": variant_rows, "line_sig": sigs,
            "_reused_lines": reused_lines, "_rebuilt_lines": rebuilt_lines,
            "_reused_motifs": reused_motifs}


def _features(score, probe) -> list:
    if probe is None:
        try:
            import s02_probe
            probe = s02_probe.analyze(score)
        except Exception:
            return []
    rows = []
    for b in probe.get("bars", []):
        for name in ("notes", "density", "vel_mean", "vel_std", "centroid", "span", "poly"):
            v = b.get(name)
            if v is not None:
                rows.append(("window", int(b["window"]), name, float(v)))
    s = probe.get("summary", {})
    for name in ("notes", "windows", "repeat_ratio"):
        if name in s:
            rows.append(("song", 0, name, float(s[name])))
    # 张力/协和/声部干涉（固定常数，零权重）
    try:
        import s02_harmony
        h = s02_harmony.analyze(score)
        for w in h.get("windows", []):
            for name in ("v_tension_mean", "v_tension_max", "leap_mean", "leap_max",
                         "chromatic"):
                rows.append(("window", int(w["window"]), name, float(w[name])))
        for name, v in h.get("overall", {}).items():
            rows.append(("song", 0, name, float(v)))
    except Exception:
        pass
    # 指法/物理可行性（P2）：手部跨度、手位移动、难度
    try:
        import s02_fingering
        fg = s02_fingering.analyze(score)
        for w in fg.get("windows", []):
            for name in ("hand_span", "hand_jump", "stretch", "hard"):
                rows.append(("window", int(w["window"]), name, float(w[name])))
        for name in ("max_span", "max_jump", "stretch_bars"):
            rows.append(("song", 0, name, float(fg["overall"][name])))
    except Exception:
        pass
    # 局部扰动（P3）
    try:
        import s02_perturb
        pb = s02_perturb.analyze(score)
        for w in pb.get("windows", []):
            rows.append(("window", int(w["window"]), "perturb", float(w["perturb"])))
            rows.append(("window", int(w["window"]), "perturb_count", float(w["count"])))
        rows.append(("song", 0, "perturb_events", float(pb["overall"]["events"])))
    except Exception:
        pass
    return rows


# ── 落盘 / 读取 ──────────────────────────────────────────

def save(idx: dict, path, *, meta: dict | None = None) -> Path:
    p = Path(path)
    if p.exists():
        p.unlink()
    con = sqlite3.connect(str(p))
    try:
        con.executescript(SCHEMA)
        for n in idx["notes"]:
            con.execute("INSERT INTO note VALUES (?,?,?,?,?,?,?,?,?)",
                        (n.id, n.instrument_id, n.voice, n.staff, n.onset, n.duration,
                         n.pitch.semitone, n.dynamics_permille, n.measure))
        con.executemany("INSERT OR REPLACE INTO edge VALUES (?,?,?,?)", idx["edges"])
        for m in idx["motifs"]:
            con.execute("INSERT INTO motif VALUES (?,?,?,?,?,?)",
                        (m.id, m.signature, m.length, m.first_note,
                         m.variant_of, m.transform))
            con.executemany("INSERT OR REPLACE INTO occurrence VALUES (?,?,?,?,?,?)",
                            [(m.id, *row) for row in m.occurrences])
        con.executemany("INSERT OR REPLACE INTO feature VALUES (?,?,?,?)", idx["features"])
        con.executemany("INSERT OR REPLACE INTO section VALUES (?,?,?,?,?,?,?,?,?)",
                        idx.get("sections") or [])
        con.executemany("INSERT OR REPLACE INTO phrase VALUES (?,?,?,?,?)",
                        idx.get("phrases") or [])
        con.executemany("INSERT OR REPLACE INTO variant VALUES (?,?,?,?,?,?)",
                        idx.get("variants") or [])
        for k, v in (meta or {}).items():
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(v)))
        if idx.get("line_sig") is not None and "line_sig" not in (meta or {}):
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                        ("line_sig", json.dumps(idx["line_sig"], ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return p


def open_index(path) -> sqlite3.Connection:
    return sqlite3.connect(str(Path(path)))


def read_index(path) -> dict:
    """从 `.s02x` 还原出增量所需的 prev 结构（motifs/variants/line_sig）。"""
    con = sqlite3.connect(str(Path(path)))
    try:
        sig_row = con.execute("SELECT value FROM meta WHERE key='line_sig'").fetchone()
        line_sig = json.loads(sig_row[0]) if sig_row else {}
        occ = {}
        for mid, sn, en, tr, voice, bar in con.execute(
                "SELECT motif, start_note, end_note, transposed_by, voice, bar"
                "  FROM occurrence"):
            occ.setdefault(mid, []).append((sn, en, tr, voice, bar))
        voice_of = {}
        for mid, voice in con.execute("SELECT motif, voice FROM occurrence"):
            voice_of.setdefault(mid, voice)
        inst_of = {}
        for mid, sn in con.execute("SELECT motif, start_note FROM occurrence"):
            row = con.execute("SELECT inst FROM note WHERE id=?", (sn,)).fetchone()
            if row:
                inst_of.setdefault(mid, row[0])
        motifs = []
        for mid, sig, length, first, _vof, _tr in con.execute(
                "SELECT id, signature, length, first_note, variant_of, transform FROM motif"):
            ivs, rhs = parse_sig(sig)
            line = (inst_of.get(mid, 1), voice_of.get(mid, "RH"))
            motifs.append(Motif(id=mid, signature=sig, length=length, first_note=first,
                                occurrences=occ.get(mid, []), ivs=ivs, rhs=rhs, line=line))
        variants = [tuple(r) for r in con.execute(
            "SELECT motif, transform, start_note, end_note, voice, bar FROM variant")]
        return {"notes": [], "edges": [], "motifs": motifs, "features": [],
                "sections": [], "phrases": [], "variants": variants,
                "line_sig": line_sig}
    finally:
        con.close()


# ── 查询 API（固定一组，不做任意 SQL 注入面）──────────────

def stats(con) -> dict:
    q = lambda sql: con.execute(sql).fetchone()[0]
    return {"notes": q("SELECT count(*) FROM note"),
            "edges": q("SELECT count(*) FROM edge"),
            "motifs": q("SELECT count(*) FROM motif"),
            "occurrences": q("SELECT count(*) FROM occurrence"),
            "features": q("SELECT count(*) FROM feature"),
            "sections": q("SELECT count(*) FROM section"),
            "phrases": q("SELECT count(*) FROM phrase")}


def sections(con) -> list:
    """段落列表：[(id, start_bar, end_bar, label, notes, density, tension, centroid)]。"""
    return con.execute("SELECT id, start_bar, end_bar, label, notes, density, tension, centroid"
                       "  FROM section ORDER BY start_bar").fetchall()


def phrases(con, section_id: str | None = None) -> list:
    if section_id:
        return con.execute("SELECT id, section, start_bar, end_bar, reason FROM phrase"
                           "  WHERE section = ? ORDER BY start_bar", (section_id,)).fetchall()
    return con.execute("SELECT id, section, start_bar, end_bar, reason FROM phrase"
                       "  ORDER BY start_bar").fetchall()


def section_at(con, bar: int):
    """第 bar 小节属于哪一段（bar 从 1 开始）。"""
    return con.execute("SELECT id, start_bar, end_bar, label FROM section"
                       "  WHERE start_bar <= ? AND ? <= end_bar", (bar, bar)).fetchone()


def variants(con) -> list:
    """变体出现：[(motif, transform, start_note, end_note, voice, bar)]。"""
    return con.execute("SELECT motif, transform, start_note, end_note, voice, bar"
                       "  FROM variant ORDER BY motif, start_note").fetchall()


def variant_summary(con) -> list:
    """每个动机的变体计数：[(motif, transform, count)]。"""
    return con.execute("SELECT motif, transform, count(*) FROM variant"
                       "  GROUP BY motif, transform ORDER BY motif, transform").fetchall()


def motif_detail(con, motif_id: str):
    return con.execute("SELECT id, signature, length, first_note, variant_of, transform"
                       "  FROM motif WHERE id = ?", (motif_id,)).fetchone()


def motif_of(con, note_id: str) -> list:
    """这个音落在哪些动机里（按动机覆盖区间判断）。"""
    rows = con.execute(
        "SELECT o.motif, m.signature, o.start_note, o.end_note, o.transposed_by"
        "  FROM occurrence o JOIN motif m ON m.id = o.motif"
        " WHERE o.start_note = ? OR o.end_note = ?", (note_id, note_id)).fetchall()
    if rows:
        return rows
    # 区间中间的音：按 onset 落在 [start.onset, end.onset] 判定
    return con.execute(
        "SELECT o.motif, m.signature, o.start_note, o.end_note, o.transposed_by"
        "  FROM occurrence o JOIN motif m ON m.id = o.motif"
        "  JOIN note s ON s.id = o.start_note JOIN note e ON e.id = o.end_note"
        "  JOIN note x ON x.id = ?"
        " WHERE x.onset BETWEEN s.onset AND e.onset", (note_id,)).fetchall()


def occurrences(con, motif_id: str) -> list:
    return con.execute("SELECT start_note, end_note, transposed_by, voice, bar"
                       "  FROM occurrence WHERE motif = ? ORDER BY start_note",
                       (motif_id,)).fetchall()


def feature(con, scope: str, scope_id: int = 0) -> dict:
    rows = con.execute("SELECT name, value FROM feature WHERE scope=? AND scope_id=?",
                       (scope, scope_id)).fetchall()
    return {k: v for k, v in rows}


def motifs(con) -> list:
    """[(id, signature, length, 出现次数, 变体数)]。"""
    return con.execute(
        "SELECT m.id, m.signature, m.length,"
        "       (SELECT count(*) FROM occurrence o WHERE o.motif = m.id),"
        "       (SELECT count(*) FROM variant v WHERE v.motif = m.id)"
        "  FROM motif m ORDER BY m.id").fetchall()


def to_json(con) -> str:
    data = {"stats": stats(con),
            "sections": [{"id": r[0], "start_bar": r[1], "end_bar": r[2], "label": r[3]}
                         for r in sections(con)],
            "motifs": [{"id": r[0], "signature": r[1], "length": r[2], "count": r[3],
                        "variants": r[4]}
                       for r in motifs(con)],
            "variants": [{"motif": r[0], "transform": r[1], "start": r[2],
                          "end": r[3], "voice": r[4], "bar": r[5]}
                         for r in variants(con)]}
    return json.dumps(data, ensure_ascii=False, indent=2)
