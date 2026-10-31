# MD 写作约束（静态）

> 写给 AI/人看的写作规则；解析时会校验，但**写之前**先按这里避免踩坑。

## 1. 文件骨架

```markdown
# 曲名
- BPM: 87
- Meter: 4/4

## 乐器
- 1: piano
- 2: violin

## 乐谱
```notes
[n1] 1: C5 @0+1 mf
[n2] 1: E5 @1+1
```

## 动作
- turn: n2 retrigger
- pedal: 1 sustain 0 2
- curve: 1 dynamics 0 500 8 950
```

## 2. 音符行

```
[标签] 乐器号: 音高 @起始拍+时值拍 [力度]
```

- 标签：`[A-Za-z_][A-Za-z0-9_]*`，必须唯一（转折/踏板引用它）；
- 乐器号：`1..N`，必须在“## 乐器”里声明；
- 音高：`C4 / F#5 / Bb3`，范围 **21..108**（A0–C8）；
- 起始拍/时值：拍，不是微秒；时值必须 > 0；
- 力度：`ppp…fff` 或 `0..1000` 的 permille（可省略）；
- 奏法/装饰音：写在该行行尾会与力度冲突——当前格式只支持力度；
  奏法/装饰音请用 Python DSL 或 JSON。

## 3. 动作行

| 写法 | 约束 |
|---|---|
| `- turn: 标签 种类 [强度]` | 钢琴可用 retrigger/restrike/…；同音高重击需前一个同音高音、间隔 ≥60ms |
| `- pedal: 乐器号 种类 起始拍 结束拍` | 乐器必须支持该踏板；连续踏板间隔 ≥0.25 拍 |
| `- curve: 乐器号 参数 拍 值 …（成对）` | 参数：dynamics/tempo/pedal/brightness/expression；值在范围内 |

## 4. 校验链

1. `ms_md.lint(text)` —— 写之前快速检查（返回行号+原因）；
2. `ms_md.loads_authoring(text)` —— 编译时完整校验（V1–V19）；
3. `ms.export_check(spec)` / `mscli ms export-check` —— 导出前门禁；
4. `ms.report(song)` —— 结构/演奏测量。

## 5. 常见错误

- 乐器号没声明 → 编译报错；
- 音高越界（C0/C9）→ `UNSUPPORTED_PITCH_RANGE`；
- 踏板不被乐器支持（小提琴 sustain）→ V14；
- 连续踏板间隔太小 → 被合并/校验失败；
- 标签重复 → 转折引用错位。
