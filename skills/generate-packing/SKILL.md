---
name: generate-packing
description: |
  小空间 design 工作流第二阶段：按软分区方案选多用途模块打包施工。
  load_design_plan(soft-zoning) → 选模块 + 坐标化 → 写 packing-brief → 写 modules.json → validate_layout → 必要修正 → 品质复核。
---

# 打包施工

> 你在本 Skill 中是施工方兼品质把关人。你把软分区策略转成精确坐标的 `modules.json`，并验证、修正、复核。

## 路径约定

- 相对路径均以当前项目目录为根。
- `references/furniture_rules.md`、`references/small_space_principles.md` 是选品与间距依据。
- `modules/module_library.json` 是唯一允许的家具尺寸来源。

## 最重要的规则

1. **进入施工前必须先 `load_design_plan`（取 soft-zoning）——不读策略不施工。**
2. **`modules.json` 形态 `{schemeMetadata: {summary}, modules: [...]}`，编辑时必须保留 `schemeMetadata.summary`。**
3. **每次 `Write modules.json` 后必调 `validate_layout`。**
4. **不编造家具尺寸——只用 `module_library.json` 的尺寸或其 parametric limits 内取值，对齐 step。**
5. **多用途件的 bounds 按展开态算（墨菲床 deployedSize、折叠桌展开态），并在 summary 记录复用关系。**

---

## 执行步骤

### Step 1 — 加载策略

1. `mcp__spacepack__load_design_plan({zoneId})` 取生效软分区（soft-zoning）。
2. 读 `references/furniture_rules.md` + `references/small_space_principles.md`（间距/选品/修正优先级）。
3. 调 `mcp__spacepack__get_open_space` 复核几何边界（墙段坐标，供靠墙件定位）。

### Step 2 — 选模块 + 坐标化

1. 对每个软区，按 `furniture_rules.md` 的优先级选模块（多用途 > 单用途，可折叠 > 固定，壁挂/到顶 > 落地矮件）。
2. parametric 件（厨房台/到顶柜/吧台/搁板/鞋柜）按可用连续实墙长度在 limits 内调宽度，对齐 step。
3. 坐标化每个模块的 4 顶点矩形 `bounds`（Y-Up 笛卡尔，单位 mm）与 `facing`（可用 semantic 或单位向量 value）。
4. **成套件顺序累加**：同组家具（如吧台+凳）从锚点坐标依次累加尺寸，gap=0，避免逐件估算引入缝隙。
5. **多用途件按展开态占地**：墨菲床用 `deployedSize`、折叠桌用展开 depth；复用区的"另一功能"不要再放与之冲突的固定件。

### Step 3 — 写 packing-brief + modules.json

1. 先把「每个模块选型 + 位置 + 复用声明」写成施工简报：
   `mcp__spacepack__save_design_plan({zoneId, tag: "packing-brief", content})`
2. 再 `Write` 当前设计区 `schemes/{zoneId}/modules.json`：
   - wrapper：`{schemeMetadata: {summary: "<本方案 + 复用关系一句话>"}, modules: [...]}`
   - 每个 module：`id` / `moduleId`（库 id）/ `moduleName` / `bounds`（4 顶点）/ `facing`。

### Step 4 — 验证 + 修正

1. `mcp__canvas__validate_layout()`。
2. 有 error 按 `small_space_principles.md` §七 修正优先级处理：
   **平移 → 旋转 → 换更小/可折叠模块 → 拆附属件（凳/边几）→ 改用多用途件合并功能 → 移除可选件**。
3. 每次改 `modules.json` 后重跑 `validate_layout`，直到 0 error。

### Step 5 — 品质复核

1. `mcp__canvas__request_background_screenshot` 截图抽检：主通道是否贯通≥800mm、采光面是否被堵、复用区是否真的腾得出地面、有无 <600mm 死角窄缝。
2. **【建议】**调 `mcp__spacepack__evaluate_efficiency` 看空间效率指标（功能覆盖率/复用率/动线占比），作收尾参考。
3. 向主控汇报：放置模块清单、复用关系、validate 结果、截图发现的品质点、任何对用户需求的偏离。

---

## 边界

- 不在本 Skill 做软分区（那是 `generate-soft-zoning`）。若 `load_design_plan` 取不到 soft-zoning，停止并告知主控需先做软分区。
- 不自动改图纸尺寸越过 limits；越界需求是战略选择点，交主控/用户。
