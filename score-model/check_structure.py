# -*- coding: utf-8 -*-
"""结构门禁：防复发（根目录只放核心模块；文档进 docs；产物不进工程；无临时文件）。"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 根目录允许的核心模块（新增核心模块请在此登记，并同步 docs/CODEMAP.md）
CORE_ALLOWED = {
    "run_all", "check_consistency", "check_structure",
}
SUBDIRS = {"ms", "perform", "render", "audio", "analyze",
           "importers", "tools", "tests"}
ROOT_MD_ALLOWED = {"README.md", "START_HERE.md", "PERF.md"}
JUNK_SUFFIX = {".bak", ".tmp", ".orig", ".pyc"}

problems: list[str] = []
passed = 0


def ok(msg: str) -> None:
    global passed
    passed += 1


def bad(msg: str) -> None:
    problems.append(msg)


# 1. 根目录 .py 只允许门禁入口（业务模块在五层目录里）
for p in sorted(HERE.glob("*.py")):
    if p.stem not in CORE_ALLOWED:
        bad(f"根目录出现非门禁脚本：{p.name}（业务模块放 core/notation/render/audio/transform；工具放 tools/ 等）")
if not problems:
    ok("根目录 .py 全为门禁入口")

# 2. 根目录 .md 只允许三份
for p in sorted(HERE.glob("*.md")):
    if p.name not in ROOT_MD_ALLOWED:
        bad(f"根目录出现未登记文档：{p.name}（应放 docs/）")
ok("根目录 .md 白名单检查完成")

# 3. docs/ 之外不允许 .md（除根目录白名单与样例谱）
for p in sorted(HERE.rglob("*.md")):
    rel = p.relative_to(HERE)
    if rel.parts[0] in ("docs", "out"):
        continue
    if len(rel.parts) == 1 and p.name in ROOT_MD_ALLOWED:
        continue
    # samples/ 是写作样例（资产，就是给人抄的 .md），不是游离文档
    if rel.parts[0] == "samples" and p.suffix.lower() == ".md":
        continue
    bad(f"文档在 docs/ 之外：{rel}")
ok("docs/ 之外无游离文档")

# 4. 工程区不设 out/：产出一律写 ../inbox
if (HERE / "out").exists():
    bad("score-model/out/ 已取消——产出一律写 ../inbox/（临时产出区）")
ok("无 score-model/out/")

# 5. 无临时/备份/缓存文件
junk = [str(p.relative_to(HERE)) for p in HERE.rglob("*")
        if p.is_file() and (p.suffix in JUNK_SUFFIX or p.name.endswith("~"))]
if junk:
    bad(f"临时/备份文件：{junk[:5]}")
if (HERE / "__pycache__").exists():
    bad("工程根目录存在 __pycache__（应清理）")
ok("无临时/备份/缓存")

# 6. 一次性脚本不得常驻工程区
oneoff = [str(p.relative_to(HERE)) for p in HERE.rglob("*.py")
          if p.name.startswith(("fix_", "probe_", "patch_"))]
if oneoff:
    bad(f"一次性脚本常驻工程区：{oneoff[:5]}（应移入 archive/）")
ok("无一次性脚本常驻")

# 7. 子目录齐全
for d in sorted(SUBDIRS):
    if not (HERE / d).is_dir():
        bad(f"缺少角色目录：{d}/")
ok("角色目录齐全")

# 8. 工程区边界：产出只能进 inbox（临时产出区），不得自建成品目录
ENG = HERE.parent
if (ENG / "work").exists():
    bad("工程区出现 work/ —— 产出放 inbox/，由管理区分拣到 designs/_works/")
ok("工程区无自建成品目录 outputs/works")

AUDIO_OK = {(ENG / "inbox").resolve()}
stray_audio = []
for ext in ("*.wav", "*.mp3", "*.flac"):
    for p in ENG.rglob(ext):
        if any(parent in AUDIO_OK for parent in p.parents):
            continue
        stray_audio.append(str(p.relative_to(ENG)))
if stray_audio:
    bad(f"工程区散落音频：{stray_audio[:5]}（产出进 inbox/，临时垃圾用系统临时目录）")
ok("工程区无散落音频")

# 9. 产出区说明：inbox 是正式产出区，不判失败、不强制清空
inbox = ENG / "inbox"
count = sum(1 for _ in inbox.iterdir()) if inbox.exists() else 0
print(f"  [产出区] inbox/ 现有 {count} 项（正式产出区，打包只取 README + 示例）")
ok("inbox 产出区已检查")

# 10. 可搬迁：代码里不许写死绝对路径（换目录/换机器不能废）
ABSPATH_RE = re.compile(r"[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_\-]+[\\/]"
                        r"|/(?:home|Users|root|mnt)/")
hardcoded = []
for p in sorted(HERE.rglob("*.py")):
    rel = p.relative_to(HERE)
    try:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if ABSPATH_RE.search(code):
                hardcoded.append(f"{rel}:{i}")
    except Exception:
        continue
if hardcoded:
    bad(f"代码里有写死的绝对路径：{hardcoded[:5]}（用 Path(__file__) 推导或用参数传入）")
ok("代码不依赖绝对路径（可整体搬走）")

print(f"结构检查：通过 {passed} · 问题 {len(problems)}")
for p in problems:
    print("  [问题]", p)
raise SystemExit(0 if not problems else 1)
