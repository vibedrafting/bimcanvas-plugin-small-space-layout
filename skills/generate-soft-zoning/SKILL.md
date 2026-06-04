---
name: generate-soft-zoning
description: |
  小空间 design 工作流第一阶段：把开放主间切成功能软分区。
  读户型几何 → 功能取舍 → 软区划分（并置/复用/共享）→ save_design_plan(soft-zoning)。
  不写 modules.json，不定精确坐标。
---

# 功能软分区

> 你在本 Skill 中是空间策略师。你的职责是把一个开放主间「读懂」，并切成有意图的功能软区，
> 为下一阶段 `generate-packing` 提供可施工的策略合同。

## 路径约定

- 相对路径均以当前项目目录为根。
- `references/small_space_principles.md`、`references/soft_zoning.md`、`references/furniture_rules.md` 是项目级运行时参考规则。
- `modules/module_library.json`、`schemes/` 是当前项目业务数据。

## 最重要的规则

1. **软分区只定「哪块地是什么功能、家具大概在哪、怎么复用」，不定精确坐标。**
2. **软分区记录在 `design_plan` 的 `soft-zoning` 标签，不在 `zones.json` 造几何子 zone。**
3. **每个功能区必须显式声明与相邻区的关系：并置 / 复用 / 共享 + WHY。**
4. **空间放不下全部功能时，取舍是战略选择点——必要时 `AskUserQuestion`，不要静默砍功能。**
5. **本 Skill 不写 `modules.json`。**

**WHY**：小空间的核心矛盾是「功能塞不下」，软分区就是用复用/共享关系把矛盾化解掉的设计层；跳过它直接摆家具，会丢掉时分复用这个小空间最大的杠杆。

---

## 执行步骤

### Step 1 — 读懂开放主间

1. 读当前项目 `README.md`（意图与材料定位）。
2. 调 `mcp__spacepack__get_open_space`，拿到开放主间画像：采光面、入口墙、卫生间侧、最长可用连续实墙、各墙段。
3. 读 `references/small_space_principles.md` + `references/soft_zoning.md`。
4. 估算开放主间净面积（设计区边界），心里有「这点地大概能塞几个功能」的预算。

### Step 2 — 功能清单与取舍（战略选择点）

1. 从用户需求列出期望功能（睡 / 工作 / 烹饪 / 休闲 / 储物 / 餐 …）。
2. 对照面积预算判断能否全部独立放下。
3. **放不下时**：用 `AskUserQuestion` 让用户在「保留哪些独立功能 / 哪些走复用（如墨菲床白天变休闲）/ 哪些走共享（如餐桌兼工作台）」之间做战略选择。给出每个选项的空间代价。
4. **【必须】**不要自己静默砍掉用户要的功能；复用/共享是优先于删除的解法。

### Step 3 — 切软区

按 `references/soft_zoning.md` 的「无墙划分手法」切区：

- **采光轴定主区**：窗墙留给高频/需光功能。
- **入口定过渡区**：进门第一块地是过渡/收纳，隐私向深处递进。
- **卫生间墙定服务带**：厨房/储物沿卫生间外墙排（管线集中）。
- **家具背做软隔断**：沙发背/矮柜背/开放书架暗示区界。
- **动线穿缝不穿区**：主通道（≥800mm）走区与区之间。

对每个功能区确定：区名 / 大致位置（靠哪面墙、哪个角）/ 锚点家具（参考 `module_library.json` 与 `furniture_rules.md` 的选品优先级，优先多用途件）/ 与相邻区的关系（并置/复用/共享 + WHY）。

### Step 4 — 写软分区方案并提交

按 `references/soft_zoning.md` §4 的结构组织 markdown（开放主间画像 / 功能清单与取舍 / 软区划分 / 设计目标），然后：

`mcp__spacepack__save_design_plan({zoneId, tag: "soft-zoning", content})`

**【必须】**`save_design_plan(soft-zoning)` 成功返回 = 本阶段完成。未提交不得进入 `generate-packing`。

---

## 输出交接

软分区提交后，把控制权交回主控：主控将加载 `generate-packing` 用本方案施工。本 Skill 不调 `validate_layout`、不写 `modules.json`。
