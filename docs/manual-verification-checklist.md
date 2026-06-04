# 手动验证清单 — small-space-layout plugin

> 自动化已覆盖：Python 编译、45 项 business 单测、validator fixture、register 探针（7 工具 + 两条硬约束）、
> manifest schema 校验、三处命名一致性、repo 纯净度、projectMount 物化目标、atlas studio 场景完整性。
> 以下是需要**人工在运行中的 Server** 里跑的端到端验证（自动化触不到交互式启动链路）。

## 一、安装与激活

1. 建 junction 把 plugin 仓库挂进 dev-home（与 CLAUDE.md 一致）：
   ```powershell
   New-Item -ItemType Junction `
     -Path C:\CodingProject\vibedrafting\bimcanvas-plugin-interior-layout\.dev-home\plugins\small-space-layout `
     -Target C:\CodingProject\vibedrafting\bimcanvas-plugin-small-space-layout
   ```
2. 启动 Server（交互终端）：
   ```powershell
   $env:BIMCANVAS_HOME = "C:\CodingProject\vibedrafting\bimcanvas-plugin-interior-layout\.dev-home"
   cd C:\CodingProject\vibedrafting\bimcanvas
   dotnet run --project BIMCanvas.Server
   ```
3. Web 设置页 → 插件管理：应看到 `small-space-layout [未信任]`。
   - [ ] `StaticPluginValidator` 通过（仓库根无 CLAUDE.md/.claude/settings.local.json/.bimcanvas）
   - [ ] 点「信任并激活」→ 二次确认 → `ExecutablePluginProbe` 通过（register 干跑无副作用）→ 重启
   - [ ] 顶部 active plugin 标签显示「🏠 小空间布局」

## 二、从场景新建（atlas studio-31）

- [ ] 首页「从场景新建」列表出现 `Studio 31㎡`（tag：公寓酒店）
- [ ] 选它建项目：画布渲染出 L 形开放主间 + 角卫，南墙入口门、北墙采光窗、卫生间门可见
- [ ] 激活 small-space-layout scene 后，projectMount 物化：项目目录出现 `modules/module_library.json`（12 件）+ `references/*.md`（5 份）

## 三、design 工作流端到端

- [ ] 对 Agent 说「帮我设计这个 studio，要睡、工作、做饭、休闲、储物」
- [ ] 主控走 design：先 `generate-soft-zoning` → `save_design_plan(soft-zoning)` 成功
- [ ] 功能塞不下时触发 `AskUserQuestion`（复用/共享取舍），不静默砍功能
- [ ] 再 `generate-packing` → `load_design_plan` → 写 `modules.json` → `validate_layout` 通过（0 error）
- [ ] 截图复核：主通道贯通、采光窗不被堵、墨菲床/沙发床等多用途件入选
- [ ] `modules.json` 的 `moduleId` 全部能在 `module_library.json` 查到（validate 无 E011 warning）

## 四、efficiency

- [ ] 「评估一下空间利用率」→ `evaluate_efficiency` 返回五项指标 + 目标区间解读
- [ ] 传期望功能时报告含功能覆盖率与缺失功能
- [ ] 工具只读：不修改 `modules.json`

## 五、standardize

- [ ] 「把这个存成标准间」→ `save_unit_type` 落 `schemes/{zoneId}/unit_type.json`
- [ ] 新建第二个 studio 项目/scene → 「套用标准间」→ 跨 scene `list_project_scenes` + `load_scene_artifact` 读模板 → 适配写入 → `validate_layout` 通过
- [ ] `check_unit_consistency` 报告模块组成 + 功能差异
- [ ] 几何差异超阈值时触发 `AskUserQuestion`（硬套 vs 重做）

## 六、query / edit

- [ ] 「这个 studio 放了几件家具」→ query-workflow 只读统计，与文件一致
- [ ] 「把厨房台往左移 300」→ edit-workflow 单步平移 → `validate_layout` 通过

## 七、回归（不破坏现网）

- [ ] 未激活 small-space-layout 时，interior-layout / core-base 流程不受影响
- [ ] atlas 其余 5 个住宅场景仍正常「从场景新建」
