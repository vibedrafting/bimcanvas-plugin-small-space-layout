# 户型标准化与复制指引

> 本 plugin 的第三招牌能力。公寓酒店的商业价值在于**规模化**：一栋楼几十上百个相似单元，验过一个好布局就该能复制到其余单元。
> 标准化 = 把验过的单元布局打包成 `unit_type` 模板；复制 = 把模板套到目标单元并适配几何，再比对一致性。

## 一、三个动作

| 动作 | 工具 | 说明 |
|------|------|------|
| **存模板** | `save_unit_type` | 把当前验过的单元打包成 `unit_type`，落 `schemes/{zoneId}/unit_type.json` |
| **套模板** | `load_unit_type` / 跨 scene `load_scene_artifact` → 适配 → 写 modules.json | 读标准间模板，几何适配后写入当前单元 |
| **比一致** | `check_unit_consistency` | 比对当前单元与标准间的模块组成 + 功能差异 |

## 二、v1 边界（必读）

**【必须】**平台 gate 禁止写非 active scene 的项目数据（写会 403）。因此 v1 的复制是**面向当前 active 单元逐个进行**的：

- **跨 scene 读**：用 `mcp__canvas__list_project_scenes` 找到标准间所在 scene，`mcp__canvas__load_scene_artifact({sceneId, artifactKind: "unit_type", path: "<标准间 zoneId>"})` 读出模板。`load_scene_artifact` 是 scene-agnostic 的，按 `schemes/{path}/` 读，能拿到任意单元存的模板。
- **只写当前**：适配后的 modules.json 只能写进**当前 active 单元**。

**【说明】**多单元并行复制（一次把模板刷到 N 个单元）需要跨 scene 写，被 gate 挡住，留待 Phase 2 解决（届时可能用 SubAgent + 逐 scene 切换 active）。v1 不要尝试绕过 gate。

## 三、几何适配（套模板的核心难点）

标准间与目标单元的几何很少完全相同。套用时按以下顺序适配：

1. **尺寸一致**：直接套用模板坐标。
2. **镜像**：目标单元是标准间的镜像（门/窗在对侧）→ 沿对称轴翻转所有模块的 bounds 与 facing。这是公寓楼最常见的情况（走廊两侧户型互为镜像）。
3. **微调**：目标单元尺寸略有出入（±一档开间/进深）→ parametric 件（厨房台/到顶柜/吧台/搁板）按新可用墙长在 limits 内伸缩；固定件平移贴位。
4. **冲突超阈值**：目标单元与标准间差异过大（开间差 >1 档、门窗位置根本不同）→ **这是战略选择点**，用 `AskUserQuestion` 让用户决定「按模板硬套并接受偏差 / 退回走完整 design 重新打包」，不要静默乱套。

**【必须】**每次写完适配后的 modules.json 必调 `validate_layout`；适配后的几何冲突按 `small_space_principles.md` §七修正优先级解决。

## 四、一致性比对

套用后调 `check_unit_consistency`：

- 传入标准间模板的 `templateModules`（+ 可选 `templateFunctions`）。
- 工具报告：模块组成差异（缺/多哪些 moduleId）+ 功能集差异。
- **一致**：模块组成与功能集和标准间对齐——复制成功。
- **不一致**：列出差异。判断差异是「适配必要的合理偏离」（如镜像后某件换了对称位置的 parametric 尺寸）还是「套用出错」（漏放/多放）。前者可接受并向用户说明，后者要修。

## 五、典型流程

```
1. 在标准间单元（scene A）完成 design + validate_layout → save_unit_type("studio-A-32㎡")
2. 切到目标单元（scene B，当前 active）
3. list_project_scenes 找到 scene A → load_scene_artifact 读 unit_type 模板
4. 判断几何关系（一致 / 镜像 / 微调 / 超阈值）→ 适配 → Write modules.json
5. validate_layout → 修正到 0 error
6. check_unit_consistency（喂模板 modules）→ 解读差异
7. 向用户汇报：套用结果、适配方式、一致性、任何偏差
```
