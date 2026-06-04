"""small-space-layout plugin MCP 工具入口（namespace: spacepack）。

通过 `register(builder)` 范式注册小空间布局专属工具。按 Phase 分批实现：
- Phase 1：get_open_space / save_design_plan / load_design_plan
- Phase 2：evaluate_efficiency
- Phase 3：save_unit_type / load_unit_type / check_unit_consistency

⚠️ register 硬约束（详见 docs/BYO-Plugin.md §4）：
  1. register 体内严禁读 builder.context 字段做条件注册（probe 阶段是占位 context）。
  2. register 体内严禁 isinstance(builder, McpServerBuilder)（probe 用 _FakeBuilder）。
  所有 ctx 字段读取与副作用必须在 handler 内进行。

数据落点（复用 Server 通用 artifact 端点，scene-agnostic）：
- design_plan      : schemes/{zoneId}/design_plan.json
- efficiency_report: schemes/{zoneId}/efficiency_report.json（Phase 2）
- unit_type        : schemes/{zoneId}/unit_type.json（Phase 3）
端点：GET/POST /api/scheme/artifacts/{kind}?path=...
"""

from __future__ import annotations

import importlib.util as _importlib_util
import json
from pathlib import Path as _Path
from typing import Any

import aiohttp

from bimcanvas_plugin_sdk import McpServerBuilder


def _load_business_module() -> Any:
    """按路径加载 lib/business.py（唯一模块名，避免与其他 plugin 的 lib 冲突）。"""
    biz_path = _Path(__file__).resolve().parent / "lib" / "business.py"
    spec = _importlib_util.spec_from_file_location("small_space_layout_business", biz_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载业务模块: {biz_path}")
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


biz = _load_business_module()


# ============================================================
# 返回值 helper
# ============================================================

def _text(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}]}


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def _error_struct(status: str, message: str, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"status": status, "message": message}
    data.update(extra)
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": data,
        "is_error": True,
    }


# ============================================================
# Server 通用 artifact 端点 IO helper
# ============================================================

async def _load_artifact(ctx: Any, kind: str, path: str) -> tuple[int, Any, str]:
    """GET 精确读单文件 schemes/{path}/{kind}.json。返回 (status, parsed_or_none, raw)。"""
    url = f"{ctx.server_url}/api/scheme/artifacts/{kind}"
    try:
        async with ctx.session.get(url, params={"path": path}) as resp:
            raw = await resp.text()
            if resp.status == 200:
                try:
                    return 200, json.loads(raw), raw
                except json.JSONDecodeError:
                    return 200, None, raw
            return resp.status, None, raw
    except aiohttp.ClientError as e:
        return -1, None, f"无法连接 Server: {e}"


async def _save_artifact(ctx: Any, kind: str, path: str, content: Any) -> tuple[bool, str | None]:
    """POST 写单文件 schemes/{path}/{kind}.json。返回 (ok, error_text)。"""
    url = f"{ctx.server_url}/api/scheme/artifacts/{kind}"
    try:
        async with ctx.session.post(url, json={"path": path, "content": content}) as resp:
            if resp.status == 200:
                return True, None
            return False, await resp.text()
    except aiohttp.ClientError as e:
        return False, f"无法连接 Server: {e}"


# ============================================================
# 业务数据读取 helper（efficiency / standardize 用）
# ============================================================

async def _fetch_zone_ring(ctx: Any, zone_id: str) -> list | None:
    """取设计区边界外环 [[x,y], ...]。

    用 zone-boundaries 的段端点连成闭环（段已按边界顺序排列，取每段 start 即可）。
    取不到 / 无段 / 连接失败 → None。
    """
    try:
        async with ctx.session.post(
            f"{ctx.server_url}/api/validation/zone-boundaries",
            json={"zoneIds": [zone_id]},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except aiohttp.ClientError:
        return None
    if not isinstance(data, list):
        return None
    for zone_data in data:
        if zone_data.get("zoneId") != zone_id:
            continue
        segments = zone_data.get("segments") or []
        ring = [seg.get("start") for seg in segments if seg.get("start") is not None]
        if len(ring) >= 3:
            return ring
    return None


async def _fetch_modules(ctx: Any, zone_id: str) -> list | None:
    """取设计区 modules.json 的 modules 数组。404 / 连接失败 → None。

    开放主间是顶层叶子（designZoneId == leafZoneId == zone_id）。
    """
    url = f"{ctx.server_url}/api/scheme/modules"
    try:
        async with ctx.session.get(
            url, params={"designZoneId": zone_id, "leafZoneId": zone_id}
        ) as resp:
            if resp.status != 200:
                return None
            wrapper = await resp.json()
    except aiohttp.ClientError:
        return None
    if not isinstance(wrapper, dict):
        return None
    mods = wrapper.get("modules")
    return mods if isinstance(mods, list) else []


async def _fetch_library(ctx: Any) -> dict | None:
    """取当前项目模块库 module_library.json。失败 → None（业务降级，不报错）。"""
    try:
        async with ctx.session.get(f"{ctx.server_url}/api/modules/library") as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except aiohttp.ClientError:
        return None


def register(builder: McpServerBuilder) -> None:
    """small-space-layout plugin 注册入口（namespace: spacepack）。"""
    ctx = builder.context

    # ---------- get_open_space ----------
    @builder.tool(
        "get_open_space",
        "获取开放主间（及卫生间等）的边界语义：把每面墙拆成 实墙/窗/门/通道 段，"
        "并给出开放主间画像（采光面、入口墙、相邻通道、最长可用连续实墙）。"
        "软分区阶段的感知入口——理解小空间的物理骨架。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。指定要查询的 Zone ID 列表；不传则返回所有叶子 zone 的边界段数据。",
                }
            },
            "additionalProperties": False,
        },
    )
    async def get_open_space(args: dict[str, Any]) -> dict[str, Any]:
        zone_ids = args.get("zoneIds")
        body: dict[str, Any] | None = {"zoneIds": zone_ids} if zone_ids else None
        try:
            async with ctx.session.post(
                f"{ctx.server_url}/api/validation/zone-boundaries", json=body
            ) as resp:
                if resp.status == 400:
                    return _error("错误: 没有加载的项目")
                if resp.status != 200:
                    try:
                        error_data = await resp.json()
                        error_msg = error_data.get("message", f"HTTP {resp.status}")
                    except Exception:
                        error_msg = await resp.text()
                    return _error(f"获取边界数据失败: {error_msg}")
                data = await resp.json()
                return _text(biz.format_open_space(data))
        except aiohttp.ClientError as e:
            return _error(f"无法连接 Server: {e}")

    # ---------- save_design_plan ----------
    @builder.tool(
        "save_design_plan",
        "保存小空间设计方案标签。design 工作流两阶段：先 soft-zoning（功能软分区），"
        "再 packing-brief（打包施工简报，placement 只读此标签）。每阶段完成后调用。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {
                    "type": "string",
                    "description": "开放主间设计区 ID，如 'rz_1'。",
                },
                "tag": {
                    "type": "string",
                    "enum": ["soft-zoning", "packing-brief"],
                    "description": "soft-zoning=功能软分区方案；packing-brief=多用途模块打包施工简报。",
                },
                "content": {
                    "type": "string",
                    "description": "方案文本内容（markdown 格式）。",
                },
            },
            "required": ["zoneId", "tag", "content"],
            "additionalProperties": False,
        },
    )
    async def save_design_plan(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        tag = args["tag"]
        content = args["content"]

        try:
            biz.validate_save_design_plan(zone_id, tag)
        except biz.BusinessError as e:
            return _error(str(e))

        status, doc, raw = await _load_artifact(ctx, "design_plan", zone_id)
        if status not in (200, 404):
            return _error(f"读取现有设计方案失败: {raw}")
        if status == 404 or not isinstance(doc, dict):
            doc = {"Entries": []}

        entries = doc.get("Entries") or []
        entry = biz.build_design_plan_entry(zone_id, tag, content)
        doc["Entries"] = biz.upsert_entry(entries, entry)

        ok, err = await _save_artifact(ctx, "design_plan", zone_id, doc)
        if not ok:
            return _error(f"保存失败: {err}")
        return _text(f"设计方案 {tag} 已保存。" +
                     ("继续打包阶段。" if tag == "soft-zoning" else "可进入 placement 施工。"))

    # ---------- load_design_plan ----------
    @builder.tool(
        "load_design_plan",
        "加载当前开放主间的生效设计方案。默认按优先级返回（packing-brief > soft-zoning）；"
        "可选 tag 读取指定阶段。placement 进入前必调。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {
                    "type": "string",
                    "description": "开放主间设计区 ID，如 'rz_1'。",
                },
                "tag": {
                    "type": "string",
                    "enum": ["soft-zoning", "packing-brief"],
                    "description": "可选。指定阶段标签；不传则按优先级返回生效方案。",
                },
            },
            "required": ["zoneId"],
            "additionalProperties": False,
        },
    )
    async def load_design_plan(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        tag = args.get("tag")

        if not biz.is_design_zone_id(zone_id):
            return _error("design_plan 只归属于设计区（开放主间），不归属于子分区。请传入父设计区 zoneId。")

        status, doc, raw = await _load_artifact(ctx, "design_plan", zone_id)
        if status == 404 or not isinstance(doc, dict):
            return _error_struct("missing", f"未找到 {zone_id} 的设计方案", zoneId=zone_id)
        if status != 200:
            return _error(f"加载失败: {raw}")

        entries = doc.get("Entries") or []
        if not entries:
            return _error_struct("missing", f"{zone_id} 的设计方案为空", zoneId=zone_id)

        target = biz.resolve_design_plan_target(entries, tag)
        if target is None:
            label = f" {tag}" if tag else ""
            return _error_struct("missing", f"未找到 {zone_id} 的设计方案{label}",
                                 zoneId=zone_id, tag=tag)

        data = {
            "status": "ok",
            "zoneId": target.get("ZoneId"),
            "effectiveTag": target.get("Tag"),
            "content": target.get("Content"),
            "timestamp": target.get("Timestamp"),
        }
        text = "\n".join([
            f"status: {data['status']}",
            f"zoneId: {data['zoneId']}",
            f"effectiveTag: {data['effectiveTag']}",
            f"timestamp: {data['timestamp']}",
            "",
            data["content"] or "",
        ])
        return {"content": [{"type": "text", "text": text}], "structuredContent": data}

    # ---------- evaluate_efficiency ----------
    @builder.tool(
        "evaluate_efficiency",
        "评估开放主间的空间效率：家具密度 / 动线留白占比 / 多用途复用 / 储物 / 功能覆盖率。"
        "只读评估，不改 modules.json。建议在打包收尾或用户问「够不够省」时调用。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {
                    "type": "string",
                    "description": "开放主间设计区 ID，如 'rz_1'。",
                },
                "requestedFunctions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。用户期望的功能清单（如 ['sleep','work','cook','relax','storage']），"
                                   "给定后报告含功能覆盖率与缺失功能。",
                },
                "save": {
                    "type": "boolean",
                    "description": "可选。true 时把报告落盘到 schemes/{zoneId}/efficiency_report.json，默认 false。",
                },
            },
            "required": ["zoneId"],
            "additionalProperties": False,
        },
    )
    async def evaluate_efficiency(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        requested = args.get("requestedFunctions")
        do_save = bool(args.get("save"))

        if not biz.is_design_zone_id(zone_id):
            return _error("efficiency 只针对设计区（开放主间）。请传入父设计区 zoneId。")

        # 1) 设计区边界 ring（取 zone-boundaries 的段端点连成外环）
        zone_ring = await _fetch_zone_ring(ctx, zone_id)
        if zone_ring is None:
            return _error_struct("missing",
                f"无法获取 {zone_id} 的边界几何（请确认项目已加载、该设计区存在）。",
                zoneId=zone_id)

        # 2) 已放置模块
        modules = await _fetch_modules(ctx, zone_id)
        if modules is None:
            return _error_struct("missing",
                f"未找到 {zone_id} 的 modules.json，请先完成打包（generate-packing）。",
                zoneId=zone_id)

        # 3) 模块库索引（用于解析 functions / multipurpose / storage）
        library = await _fetch_library(ctx)
        lib_index = biz.build_library_index(library)

        report = biz.compute_efficiency(zone_ring, modules, lib_index, requested)
        report["zoneId"] = zone_id
        report["timestamp"] = biz.utc_now_iso()

        if do_save:
            ok, err = await _save_artifact(ctx, "efficiency_report", zone_id, report)
            if not ok:
                return _error(f"报告计算成功但保存失败: {err}")

        text = biz.format_efficiency_report(report)
        if do_save:
            text += "\n（已保存 efficiency_report.json）"
        return {"content": [{"type": "text", "text": text}], "structuredContent": report}

    # ---------- save_unit_type ----------
    @builder.tool(
        "save_unit_type",
        "把当前验过的单元布局打包成可复用户型模板 unit_type，落盘到 schemes/{zoneId}/unit_type.json。"
        "建议在 validate_layout 通过后调用。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {"type": "string", "description": "源单元设计区 ID。"},
                "unitTypeName": {"type": "string", "description": "户型模板名，如 'studio-A-32㎡'。"},
            },
            "required": ["zoneId", "unitTypeName"],
            "additionalProperties": False,
        },
    )
    async def save_unit_type(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        unit_type_name = args["unitTypeName"]
        if not biz.is_design_zone_id(zone_id):
            return _error("unit_type 只针对设计区（开放主间）。请传入父设计区 zoneId。")

        modules = await _fetch_modules(ctx, zone_id)
        if modules is None:
            return _error_struct("missing",
                f"未找到 {zone_id} 的 modules.json，无法打包模板。请先完成打包。", zoneId=zone_id)
        zone_ring = await _fetch_zone_ring(ctx, zone_id)
        lib_index = biz.build_library_index(await _fetch_library(ctx))

        unit_type = biz.build_unit_type(unit_type_name, zone_id, zone_ring or [], modules, lib_index)
        ok, err = await _save_artifact(ctx, "unit_type", zone_id, unit_type)
        if not ok:
            return _error(f"保存失败: {err}")
        return _text(
            f"户型模板 '{unit_type_name}' 已保存（{len(unit_type['modules'])} 个模块，"
            f"覆盖功能：{('、'.join(unit_type['functions']) or '无')}）。"
            f"\n落点：schemes/{zone_id}/unit_type.json"
        )

    # ---------- load_unit_type ----------
    @builder.tool(
        "load_unit_type",
        "读取户型模板 unit_type。默认读当前项目某 zone 的模板；跨 scene 套用「标准间」时，"
        "先用 mcp__canvas__list_project_scenes + mcp__canvas__load_scene_artifact 拿到标准间模板，再喂给打包。"
        "本工具读当前已加载项目的 schemes/{zoneId}/unit_type.json。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {"type": "string", "description": "存放 unit_type 的设计区 ID。"},
            },
            "required": ["zoneId"],
            "additionalProperties": False,
        },
    )
    async def load_unit_type(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        if not biz.is_design_zone_id(zone_id):
            return _error("unit_type 只针对设计区（开放主间）。请传入父设计区 zoneId。")
        status, doc, raw = await _load_artifact(ctx, "unit_type", zone_id)
        if status == 404 or not isinstance(doc, dict):
            return _error_struct("missing", f"未找到 {zone_id} 的户型模板", zoneId=zone_id)
        if status != 200:
            return _error(f"加载失败: {raw}")
        text = "\n".join([
            f"unitTypeName: {doc.get('unitTypeName')}",
            f"sourceZoneId: {doc.get('sourceZoneId')}",
            f"zoneAreaM2: {doc.get('zoneAreaM2')}",
            f"functions: {'、'.join(doc.get('functions') or []) or '无'}",
            f"moduleCount: {len(doc.get('modules') or [])}",
            "",
            json.dumps(doc.get("modules") or [], ensure_ascii=False, indent=2),
        ])
        return {"content": [{"type": "text", "text": text}], "structuredContent": doc}

    # ---------- check_unit_consistency ----------
    @builder.tool(
        "check_unit_consistency",
        "比对当前单元与标准间模板的一致性（模块组成 + 功能集差异）。"
        "传入标准间模板 templateModules（来自 load_unit_type 或跨 scene load_scene_artifact 的 modules 字段）。",
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "zoneId": {"type": "string", "description": "当前单元设计区 ID。"},
                "templateModules": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "标准间模板的 modules 数组（每项至少含 moduleId）。",
                },
                "templateFunctions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。标准间模板的功能集，用于功能一致性比对。",
                },
                "unitTypeName": {"type": "string", "description": "可选。标准间名称，仅用于报告显示。"},
            },
            "required": ["zoneId", "templateModules"],
            "additionalProperties": False,
        },
    )
    async def check_unit_consistency(args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args["zoneId"]
        template_modules = args["templateModules"]
        template_functions = args.get("templateFunctions")
        unit_type_name = args.get("unitTypeName")
        if not biz.is_design_zone_id(zone_id):
            return _error("一致性比对只针对设计区（开放主间）。请传入父设计区 zoneId。")

        current_modules = await _fetch_modules(ctx, zone_id)
        if current_modules is None:
            return _error_struct("missing",
                f"未找到 {zone_id} 的 modules.json，无法比对。请先完成套用打包。", zoneId=zone_id)

        current_functions = None
        if template_functions is not None:
            lib_index = biz.build_library_index(await _fetch_library(ctx))
            current_functions = []
            for m in current_modules:
                for f in biz._module_functions(m, lib_index):
                    if f not in current_functions:
                        current_functions.append(f)

        diff = biz.diff_units(template_modules, current_modules,
                              template_functions, current_functions)
        diff["zoneId"] = zone_id
        text = biz.format_consistency_report(diff, unit_type_name)
        return {"content": [{"type": "text", "text": text}], "structuredContent": diff}

    # PLACEHOLDER_PHASE3_TOOLS_END



