# ScoreLang · 技能包

> 整个 `ScoreLang` 就是**技能包**；`score-model/` 是包内的工程本体。
> 平台入口：**[`SKILL.md`](SKILL.md)**；工程总览：**[`score-model/START_HERE.md`](score-model/START_HERE.md)**。

## 目录

| 路径 | 是什么 |
|---|---|
| `SKILL.md` | **技能入口**（平台用；只做路由） |
| `score-model/` | 工程本体：MS 模型、`.md`/`.py` 写作、S02、测试、`docs/`、`samples/`、`fixtures/` |
| `inbox/` | **正式产出区**：作品产物按 `<曲名>/` 放这里；打包只带 README + 示例 |
| `tools/` | 包级工具（如有） |
| `README.md` | 本页 |

## 入口怎么走

```
平台/外部 AI
   → SKILL.md
     → score-model/START_HERE.md
       → score-model/docs/reference/速查卡.md
         → score-model/docs/spec/写作手册.md
           → 写 .md / .py → 校验 → 导出 → S02/基线
```

## 交付

默认四件套：**PDF + MID + MD + WAV**（`song.save_delivery(...)`）；
PNG 仅预览；ABC 仅导入，不交付。

## 边界

