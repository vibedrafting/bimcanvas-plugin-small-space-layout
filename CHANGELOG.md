# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
