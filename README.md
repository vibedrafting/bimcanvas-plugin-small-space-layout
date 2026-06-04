# 🏠 bimcanvas-plugin-small-space-layout

BIMCanvas 小空间布局 domain plugin（MCP namespace：`spacepack`）。

## 定位

studio、微公寓、公寓酒店、长租 loft 这类小空间（25–60㎡）的设计问题与普通住宅布置根本不同：一个开放主间内睡眠 / 工作 / 烹饪 / 休闲多功能叠加共存，唯一封闭空间是卫生间。本 plugin 围绕小空间的真实价值——**功能复用、空间效率、标准化复制**——提供三个一等能力：

| 能力 | 解决什么 |
|------|---------|
| **功能软分区** | 在开放主间内用家具群组 / 视线 / 动线切出可重叠、可转换的功能区，不靠内墙 |
| **空间效率评估** | 给小空间打包质量打分（功能覆盖率 / 面积效率 / 复用率 / 储物密度 / 动线占比）|
| **户型标准化复制** | 把验过的单元布局存成可复用模板，套用到目标单元并自动适配几何，再做一致性比对 |

## 工作流

```
design:       get_open_space → soft-zoning → packing(modules.json) → validate_layout
efficiency:   evaluate_efficiency → 对照 rubric 解读
standardize:  save_unit_type / load_unit_type(跨 scene) → 适配 → check_unit_consistency
```

详见 `BIMCANVAS.md`（domain 系统提示词）与 `skills/`。

## 结构

| 路径 | 内容 |
|------|------|
| `bimcanvas-plugin.json` | manifest（工具权限 / sceneId 模板）|
| `BIMCANVAS.md` | domain 系统提示词 |
| `mcp_tools/spacepack.py` | 7 个 MCP 工具入口（namespace = 文件名 stem = `spacepack`）|
| `mcp_tools/lib/business.py` | 效率指标 / unit_type diff 纯函数 |
| `validators/small-space-layout.py` | 几何安全校验（文件名必须 = manifest `name`，平台硬绑）|
| `projectMount/` | 物化到项目的家具库 + 参考规则 |
| `skills/` | 软分区 / 打包 / 效率 / 标准化 / query / edit |

> **命名说明**：manifest `name`、目录名、validator 文件名三者 = `small-space-layout`（其中 validator 文件名被平台硬绑定为 manifest name）；但 **MCP namespace 独立命名为 `spacepack`**（取自 `mcp_tools/spacepack.py` 的 stem），刻意与业态/仓库名解耦，便于能力将来迁移到其他业态仓库。

## 安装

作为 BIMCanvas domain plugin 安装：放入 `BIMCANVAS_HOME/plugins/small-space-layout/`（开发态用 junction 软链到本仓库根），Server 启动后在 Web 设置页「信任并激活」。

> 本仓库根**绝不能**有 `CLAUDE.md` / `.claude/` / `settings.local.json` / `.bimcanvas/`——`StaticPluginValidator` 会在安装阶段拒绝（已由 `.gitignore` 预禁）。

## 状态

Phase 0–5 全部完成：三招牌能力（软分区 / 效率评估 / 标准化复制）+ query/edit + atlas studio 示例场景。
代码层验证通过（45 项单测 / validator fixture / register 探针 / manifest schema）。
运行时端到端「信任并激活」验证见 `docs/manual-verification-checklist.md`。
