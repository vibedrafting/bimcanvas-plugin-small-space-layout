# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.2.0] - 2026-06-04

### Added
- 模块库扩充（4 个新模块）：
  - `mod_tv_wall`：壁挂电视（media 功能，parametric 宽度 800–1600mm，深度仅 80mm 不占地面）
  - `mod_compact_fridge`：嵌入式冰箱（cook 功能，厨房打包固定锚点，parametric 550–700mm）
  - `mod_work_chair`：折叠工作椅（work + seating + multipurpose，折叠后仅 100mm 深）
  - `mod_washer`：滚筒洗衣机（laundry 功能，600×600 固定，紧靠水路）
- 对应 4 个 SVG 平面图资产（`assets/mod_tv_wall.svg` 等）
- `furniture_rules.md` 更新「工作」「烹饪」条目，新增「休闲/媒体」条目，引用新模块

### Changed
- **重命名 + 命名解耦**：仓库 `apartment-hotel` → `small-space-layout`（去业态化，覆盖 studio/微公寓/公寓酒店/loft）。
  manifest `name` / 目录 / `validators/<name>.py` = `small-space-layout`（validator 文件名被平台硬绑为 manifest name）；
  **MCP namespace 独立解耦为 `spacepack`**（`mcp_tools/spacepack.py` stem），调用 `mcp__spacepack__<tool>`。
  依据：平台只硬绑 validator 文件名，namespace 自由（见 workspace CLAUDE.md 红线 #2 已同步改写）。

### Added
- Phase 0：仓库脚手架——manifest / plugin.json / projectMount manifest / BIMCANVAS.md domain 契约骨架。
- Phase 1：软分区引擎——`get_open_space` / `save_design_plan` / `load_design_plan` MCP 工具，几何安全 validator，小空间家具库，`generate-soft-zoning` + `generate-packing` skill。
- Phase 2：空间效率评估——`evaluate_efficiency` MCP 工具 + `lib/business.py` 五项指标（shoelace 纯 Python），`space_efficiency.md` rubric，`evaluate-efficiency` skill，business.py 单测（33 项）。
- Phase 3：户型标准化复制——`save_unit_type` / `load_unit_type` / `check_unit_consistency` MCP 工具，`standardization.md`，`standardize-replicate` skill（跨 scene 读标准间），单测扩至 45 项。
- Phase 4：query/edit skill + 示例场景——`query-workflow` / `edit-workflow` skill；atlas 仓库新增 `studio-31` 示例场景（31㎡ 开放主间 + 角卫，tag「公寓酒店」），接入首页「从场景新建」。
- Phase 5：验证——45 项 business 单测、validator fixture、register 探针（7 工具 + 两条硬约束）、manifest schema 校验、三处命名一致性、repo 纯净度全部通过；`docs/manual-verification-checklist.md` 手动激活清单。
