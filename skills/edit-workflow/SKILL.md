---
name: edit-workflow
description: |
  小空间机械编辑工作流。用户给出明确目标 + 明确动作（移动/删除/旋转/调整尺寸）时使用。
  单步几何修正，不做设计探索（探索归 design 链路）。
---

# Edit 工作流（机械编辑）

**触发**：明确目标 + 明确动作，如「把厨房台往左移 300」「删除那把凳子」「墨菲床转 90°」「衣柜改窄到 1200」。
**不属于本工作流**：含设计判断的模糊意图（「调整一下」无目标、「优化布局」、「哪样好看」）→ 归 design 链路。

## 步骤

1. 读当前项目 `README.md`。
2. **先读后写**：Read 目标设计区 `schemes/{zoneId}/modules.json`，确认目标模块存在（按 `moduleName` / `id` 定位）。
   - 目标不明确 / 命中多个 → `AskUserQuestion` 让用户锁定。
3. 按动作机械修改：
   - **移动**：平移 bounds 四顶点。
   - **旋转**：绕模块中心旋转 bounds，同步更新 facing。
   - **删除**：从 modules 数组移除该项。
   - **调整尺寸**：仅 parametric 件，在 `module_library.json` 的 limits 内、对齐 step 改 bounds。
4. **保留 `schemeMetadata.summary`** 写回 `modules.json`（`Write` / `Edit`）。
5. `mcp__canvas__validate_layout()`。有 error 按 `references/small_space_principles.md` §七修正优先级处理，重验到 0 error。
6. 简要汇报改动 + 验证结果。

## 边界

- 只做单步指定的几何动作，不顺便重新规划、不补放/换品。
- 改尺寸不越 limits；越界需求交 design / 用户决策。
- 编辑导致功能缺失或明显变差时，提示用户考虑走 design 重打包。
