---
name: query-workflow
description: |
  小空间查询/统计工作流（只读）。
  用户「统计 / 查看 / 列出 / 有多少 / 当前状态」等只读操作时使用。
allowed-tools: Read, Glob, Grep, mcp__spacepack__get_open_space, mcp__spacepack__load_design_plan, mcp__spacepack__evaluate_efficiency, mcp__canvas__request_background_screenshot
---

# Query 工作流（只读）

**触发**：关键词「统计 / 查看 / 列出 / 有多少 / 当前状态」。
**禁止工具**：Write、Edit。

## 步骤

1. 读当前项目 `README.md` 理解意图与材料定位。
2. 如需空间/布局判断，先 `mcp__canvas__request_background_screenshot` 看截图。
3. Read `schemes/zones.json` 定位开放主间设计区 ID（小空间通常单设计区，无嵌套子分区）。
4. Read `schemes/{zoneId}/modules.json` 看已放置模块。
   - ⚠️ `modules.json` 不存在 = 尚未打包，视作 0 个模块，**不报错**。
5. 需要时叠加：
   - `mcp__spacepack__get_open_space` 看户型骨架（采光面/入口/实墙）。
   - `mcp__spacepack__load_design_plan` 看软分区/打包简报。
   - `mcp__spacepack__evaluate_efficiency` 看效率指标（也是只读）。
6. 仅基于实际读到的数据统计/分析，报告内容必须与文件一致。

## 禁止

- 根据房间信息推断/编造不存在的模块。
- 空数据时自动创建示例数据。

## 示例

- 「这个 studio 放了几件家具」→ 读 zones.json 找开放主间 → 读其 modules.json → 数模块。
- 「当前空间利用率多少」→ `evaluate_efficiency`（只读）→ 报指标，不改任何文件。
