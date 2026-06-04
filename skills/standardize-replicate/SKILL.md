---
name: standardize-replicate
description: |
  小空间户型标准化与复制工作流。存模板（save_unit_type）/ 套模板（跨 scene 读 + 几何适配 + 写 modules.json + validate）/ 比一致（check_unit_consistency）。
  v1 面向当前 active 单元逐个复制；多单元并行留 Phase 2。
---

# 户型标准化与复制

> 触发：用户说「存为标准间 / 套用 / 复制到 / 统一成 / 做成模板 / 对齐标准间」。
> 你在本 Skill 中是标准化执行者。先读 `references/standardization.md` 吃透 v1 边界（gate 禁止跨 scene 写）。

## 分支判断

用户意图分三类，先判断走哪条：

- **存模板**：把当前单元存成标准间 → 走 A。
- **套模板**：把某标准间套到当前单元 → 走 B。
- **比一致**：检查当前单元是否对齐某标准间 → 走 C。

---

## A. 存模板

1. 确认当前单元 `modules.json` 已通过 `validate_layout`（未过先让用户回 design 修）。
2. 与用户确认模板名 `unitTypeName`（如 `studio-A-32㎡`）。
3. `mcp__spacepack__save_unit_type({zoneId, unitTypeName})`。
4. 汇报：模板模块数、覆盖功能、落点路径。

---

## B. 套模板（核心流程）

1. **读标准间模板**：
   - 标准间在**当前项目另一 scene**：`mcp__canvas__list_project_scenes` 找到该 scene → `mcp__canvas__load_scene_artifact({sceneId, artifactKind: "unit_type", path: "<标准间 zoneId>"})`。
   - 标准间就在当前 scene 某 zone：`mcp__spacepack__load_unit_type({zoneId})`。
2. **读当前单元几何**：`mcp__spacepack__get_open_space({zoneIds: [当前 zoneId]})`。
3. **判断几何关系**（见 `references/standardization.md` §三）：一致 / 镜像 / 微调 / 超阈值。
   - **超阈值**（开间差 >1 档、门窗位置根本不同）→ `AskUserQuestion`：「硬套接受偏差」vs「退回走完整 design」。不要静默乱套。
4. **适配 + 写**：按几何关系适配模板的 bounds/facing（镜像翻转 / parametric 件按新墙长伸缩 / 固定件平移），`Write` 当前单元 `schemes/{zoneId}/modules.json`（保留 `schemeMetadata.summary`）。
5. **验证**：`mcp__canvas__validate_layout()` → 有 error 按 `small_space_principles.md` §七修正 → 重验到 0 error。
6. **比一致**（见 C）+ 截图复核。
7. 汇报：套用结果、适配方式、一致性、任何偏差。

**【必须】**只写当前 active 单元；不尝试跨 scene 写其他单元（gate 会 403）。
**【必须】**每次写 modules.json 后必调 validate_layout。

---

## C. 比一致

1. 拿到标准间模板的 `modules`（A 存的 / B 读的 / load_unit_type 返回的 structuredContent.modules）。
2. `mcp__spacepack__check_unit_consistency({zoneId, templateModules, templateFunctions?, unitTypeName?})`。
3. 解读：
   - **一致** → 复制成功。
   - **不一致** → 判断差异是「适配必要的合理偏离」（接受并说明）还是「套用出错」（漏/多放，需修）。
4. 汇报差异与判断。

---

## 边界

- **【禁止】**多单元并行复制（v1 不支持，gate 限制）；用户要批量时说明 v1 逐单元、可依次操作，批量留后续版本。
- **【禁止】**绕过 gate 写非 active scene。
- **【必须】**几何超阈值是战略选择点，交用户决定，不静默硬套。
