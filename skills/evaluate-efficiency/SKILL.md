---
name: evaluate-efficiency
description: |
  小空间效率评估工作流。调 evaluate_efficiency 拿五项指标，
  对照 space_efficiency.md rubric 解读，给改进建议。只读，不改 modules.json。
allowed-tools: Read, mcp__spacepack__evaluate_efficiency, mcp__canvas__request_background_screenshot
---

# 空间效率评估

> 触发：用户问「空间利用率 / 够不够省 / 评估 / 打分 / 还能更省吗」，或 design 收尾主动复核。
> 你在本 Skill 中是诊断师：读指标、解读、给方向。**不修改 `modules.json`**。

## 执行步骤

### Step 1 — 取指标

1. 确定目标设计区 `zoneId`（开放主间）。
2. 若能从用户需求得到期望功能清单，整理成 `requestedFunctions`（如 `["sleep","work","cook","relax","storage"]`），以便算功能覆盖率。
3. 调 `mcp__spacepack__evaluate_efficiency({zoneId, requestedFunctions?})`。
   - 用户明确要存档时才传 `save: true`。

### Step 2 — 解读

读 `references/space_efficiency.md`，对每项指标对照目标区间判断：

- 家具密度（目标 30%–65%）
- 动线/留白占比（目标 35%–70%）
- 多用途占比（目标 ≥30%）+ 复用红利
- 储物占地占比（目标 8%–30%）+ 储物模块数
- 功能覆盖率（若给了 requestedFunctions）

**【必须】**组合解读，不要单看一项（如「高密度+低多用途」= 用单功能件硬塞）。

### Step 3 — 截图复核（建议）

`mcp__canvas__request_background_screenshot` 看：主通道是否贯通≥800mm、有无 <600mm 死角窄缝、复用区是否真腾得出地面。指标衡量「量」，截图验证「质」。

### Step 4 — 给建议

按 `space_efficiency.md` 的「改进方向速查」给出**具体可执行**的改进项（哪件换成什么、加什么），并说明每条改哪个指标。

**【必须】**只给建议，不动 `modules.json`。用户认可后，由主控走 design（重打包）或 edit（单步调整）链路执行。
**【必须】**缺失功能要明确告知用户，确认是软分区阶段的有意取舍还是遗漏。
