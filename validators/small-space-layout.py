"""small-space-layout 布局校验器（被平台 PluginValidatorRuntime 子进程调用）。

定位：几何安全是 domain-agnostic 的，本校验器复用 interior-layout 的几何安全内核
（bounds 结构 / 越界 / 墙·柱·禁区重叠 / 模块两两重叠 / facing 规范化），但**去掉**
interior-layout 里强「靠墙锚定」语义——小空间是开放主间，家具不必靠墙。

死角窄缝不在此处报：validate 只判几何安全（硬错误）；窄缝是否「死角」依赖功能意图
（使用间隙 vs 卫生死角），无法在几何层无歧义判定，故归 evaluate_efficiency 的
碎片化质量指标（Phase 2），不在 validate 里产生噪声 warning。

入口：`run(request) -> result`
  request = {mode: "normalize"|"validate", projectPath, zoneIds?: [..], variantId?: str}
  result  = {report: {...}, writeback: [{path, wrapper}, ...]}

几何走 bimcanvas_plugin_sdk.geometry（shapely），阈值/噪声地板对齐平台原语。
本文件刻意只保留单层 modules.json（schemes/{zoneId}/modules.json）的扫描，
不实现 interior-layout 的多级 zones.json 拓扑——开放主间是单设计区，无嵌套子分区文件。
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Optional

from bimcanvas_plugin_sdk import geometry

# ── 常量（对齐平台原语）─────────────────────────────────────────
ZONE_EXCLUSION = 0
ZONE_ROOM = 1
ZONE_DESIGNABLE = 2

ERROR_THRESHOLD_MM = 10.0      # 穿透深度 > 此值为 error
BOUNDS_TOL_MM = 0.001
WITHIN_TOLERANCE_MM = 10.0

# DiagnosticCodes（对齐 interior-layout 的几何安全码；窄缝/碎片化归 efficiency 报告）
E_OUT_OF_BOUNDS = "E001_OUT_OF_BOUNDS"
E_WALL_OVERLAP = "E002_WALL_OVERLAP"
E_COLUMN_OVERLAP = "E003_COLUMN_OVERLAP"
E_EXCLUSION_OVERLAP = "E004_EXCLUSION_OVERLAP"
E_MODULE_OVERLAP = "E005_MODULE_OVERLAP"
E_MISSING_BOUNDS = "E006_MISSING_BOUNDS"
E_INVALID_FACING_SEMANTIC = "E007_INVALID_FACING_SEMANTIC"
E_MISSING_FACING_VALUE = "E008_MISSING_FACING_VALUE"
E_INVALID_FACING_VALUE = "E009_INVALID_FACING_VALUE"
E_INVALID_MODULE_ID = "E011_INVALID_MODULE_ID"
E_INVALID_BOUNDS = "E012_INVALID_BOUNDS"

_ZONE_TYPE_ALIASES = {
    "exclusion": ZONE_EXCLUSION,
    "room": ZONE_ROOM,
    "designable": ZONE_DESIGNABLE,
}


def _zone_type(z: dict):
    t = z.get("type")
    if isinstance(t, str):
        return _ZONE_TYPE_ALIASES.get(t.strip().lower())
    if isinstance(t, bool):
        return None
    if isinstance(t, int):
        return t if t in (ZONE_EXCLUSION, ZONE_ROOM, ZONE_DESIGNABLE) else None
    return None


# ── 入口 ────────────────────────────────────────────────────────
def run(request: dict) -> dict:
    mode = request.get("mode")
    project_path = request.get("projectPath")
    zone_ids = request.get("zoneIds") or None
    variant_id = request.get("variantId") or None

    if not project_path:
        raise ValueError("缺少 projectPath")
    if variant_id and not zone_ids:
        raise ValueError("variantId 非空时必须显式指定 zoneIds")

    target = set(zone_ids) if zone_ids else None

    if mode == "normalize":
        return _run_normalize(project_path, target, variant_id)
    if mode == "validate":
        return _run_validate(project_path, target, variant_id)
    raise ValueError(f"未知 mode: {mode}")


# ── normalize ───────────────────────────────────────────────────
def _run_normalize(project_path: str, target: Optional[set], variant_id: Optional[str]) -> dict:
    t0 = time.perf_counter()
    schemes_path = os.path.join(project_path, "schemes")
    files = _module_files(schemes_path, target, variant_id)

    diagnostics: list[dict] = []
    normalized_count = 0
    total_modules = 0
    writeback: list[dict] = []

    for abs_path, _zone_id in files:
        wrapper = _read_modules_wrapper(abs_path)
        if wrapper is None:
            continue
        modules = wrapper["modules"]
        diags, n = _normalize_facings(modules)
        diagnostics.extend(diags)
        normalized_count += n
        total_modules += len(modules)
        writeback.append(_writeback_entry(project_path, abs_path, wrapper))

    elapsed = int((time.perf_counter() - t0) * 1000)
    report = {
        "isValid": _count(diagnostics, "error") == 0,
        "totalModules": total_modules,
        "normalizedCount": normalized_count,
        "errorCount": _count(diagnostics, "error"),
        "warningCount": _count(diagnostics, "warning"),
        "diagnostics": diagnostics,
        "elapsedMs": elapsed,
    }
    return {"report": report, "writeback": writeback}


# ── validate ────────────────────────────────────────────────────
def _run_validate(project_path: str, target: Optional[set], variant_id: Optional[str]) -> dict:
    t0 = time.perf_counter()
    schemes_path = os.path.join(project_path, "schemes")

    walls, columns = _load_architecture(project_path)
    design_zones, exclusion_zones = _load_zone_data(project_path, schemes_path)

    all_diags: list[dict] = []
    files = _module_files(schemes_path, target, variant_id)
    writeback: list[dict] = []
    loaded: list[tuple[str, list[dict]]] = []
    for abs_path, zone_id in files:
        wrapper = _read_modules_wrapper(abs_path)
        if wrapper is None:
            continue
        modules = wrapper["modules"]
        diags, _ = _normalize_facings(modules)
        all_diags.extend(diags)
        for m in modules:
            if m.get("zoneId") is None:
                m["zoneId"] = zone_id
        loaded.append((zone_id, modules))
        writeback.append(_writeback_entry(project_path, abs_path, wrapper))

    # bounds 结构预检（E006/E012，剔除非法 bounds）
    valid_modules: list[dict] = []
    skipped = 0
    for _zone_id, modules in loaded:
        for m in modules:
            err = _bounds_structure_error(m)
            if err is not None:
                code, detail = err
                all_diags.append(_diag(code, "error",
                    f"模块 {m.get('id', '')} ({_name(m)}) 的 bounds 结构非法：{detail}",
                    m.get("id", ""), _name_or_none(m)))
                skipped += 1
            else:
                valid_modules.append(m)

    all_diags.extend(_validate_module_facings(valid_modules))
    all_diags.extend(_validate_scheme(valid_modules, design_zones, exclusion_zones,
                                      walls, columns, target))

    total_modules = len(valid_modules) + skipped
    elapsed = int((time.perf_counter() - t0) * 1000)
    report = {
        "isValid": _count(all_diags, "error") == 0,
        "totalModules": total_modules,
        "errorCount": _count(all_diags, "error"),
        "warningCount": _count(all_diags, "warning"),
        "diagnostics": all_diags,
        "elapsedMs": elapsed,
    }
    return {"report": report, "writeback": writeback}


# ── facing 规范化 ───────────────────────────────────────────────
def _normalize_facings(modules: list[dict]) -> tuple[list[dict], int]:
    diags: list[dict] = []
    normalized = 0
    for m in modules:
        if "items" not in m or m.get("items") is None:
            m["items"] = []
        facing = m.get("facing") or {}
        value = facing.get("value")
        semantic = facing.get("semantic")

        sv = geometry.semantic_to_vector(semantic) if _has_semantic(semantic) else None
        if sv is not None:
            m["facing"] = {"value": [sv[0], sv[1]], "semantic": None}
            normalized += 1
            continue
        if _has_semantic(semantic):
            diags.append(_diag(E_INVALID_FACING_SEMANTIC, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 的 facing.semantic '{semantic}' 无效",
                m.get("id", ""), _name_or_none(m)))
            continue
        if not _value_present(value):
            diags.append(_diag(E_MISSING_FACING_VALUE, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 缺少 facing.value",
                m.get("id", ""), _name_or_none(m)))
            continue
        norm = _normalize_value(value)
        if norm is None:
            diags.append(_diag(E_INVALID_FACING_VALUE, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 的 facing.value 不是有效单位向量",
                m.get("id", ""), _name_or_none(m)))
            continue
        if not _same_vector(value, norm):
            normalized += 1
        m["facing"] = {"value": [norm[0], norm[1]], "semantic": None}
    return diags, normalized


def _validate_module_facings(modules: list[dict]) -> list[dict]:
    diags: list[dict] = []
    for m in modules:
        facing = m.get("facing") or {}
        value = facing.get("value")
        if not _value_present(value):
            diags.append(_diag(E_MISSING_FACING_VALUE, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 缺少 facing.value",
                m.get("id", ""), _name_or_none(m)))
            continue
        if _normalize_value(value) is None:
            diags.append(_diag(E_INVALID_FACING_VALUE, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 的 facing.value 不是有效单位向量",
                m.get("id", ""), _name_or_none(m)))
    return diags


# ── 几何校验 ────────────────────────────────────────────────────
def _validate_scheme(modules: list[dict], design_zones: list[dict], exclusion_zones: list[dict],
                     walls: list[dict], columns: list[dict], target: Optional[set]) -> list[dict]:
    diags: list[dict] = []

    zone_cache = []
    for z in design_zones:
        if _zone_type(z) not in (ZONE_ROOM, ZONE_DESIGNABLE):
            continue
        if target is not None and z.get("id") not in target:
            continue
        b = z.get("computedBoundary") or z.get("rawBoundary")
        if b is not None:
            zone_cache.append((z, b))

    excl_cache = []
    for z in exclusion_zones:
        if _zone_type(z) != ZONE_EXCLUSION:
            continue
        b = z.get("rawBoundary") or z.get("computedBoundary")
        if b is not None:
            excl_cache.append((z, b))

    wall_cache = [w for w in walls if w.get("polygon") is not None]
    col_cache = [c for c in columns if c.get("polygon") is not None]
    valid = [(m, m["bounds"]) for m in modules]

    for m, mb in valid:
        in_any = False
        for _z, zb in zone_cache:
            if geometry.aabb_intersects(mb, zb) and geometry.within_tolerant(mb, zb, WITHIN_TOLERANCE_MM):
                in_any = True
                break
        if not in_any:
            diags.append(_diag(E_OUT_OF_BOUNDS, "error",
                f"模块 {m.get('id', '')} ({_name(m)}) 不在任何设计区域内",
                m.get("id", ""), _name_or_none(m)))

        for w in wall_cache:
            _overlap_diag(diags, m, mb, w["polygon"], E_WALL_OVERLAP, w.get("id"), "wall",
                f"模块 {m.get('id', '')} ({_name(m)}) 与墙体 {w.get('id')} 重叠")
        for c in col_cache:
            _overlap_diag(diags, m, mb, c["polygon"], E_COLUMN_OVERLAP, c.get("id"), "column",
                f"模块 {m.get('id', '')} ({_name(m)}) 与柱子 {c.get('id')} 重叠")
        for z, zb in excl_cache:
            _overlap_diag(diags, m, mb, zb, E_EXCLUSION_OVERLAP, z.get("id"), "exclusion",
                f"模块 {m.get('id', '')} ({_name(m)}) 与禁区 {z.get('id')} 重叠 ({z.get('reason', '')})")

    # 模块两两重叠（双向记录）
    for i in range(len(valid)):
        ma, ba = valid[i]
        for j in range(i + 1, len(valid)):
            mb_, bb = valid[j]
            if not geometry.aabb_intersects(ba, bb):
                continue
            info = geometry.overlap_info(ba, bb)
            if not info["has_overlap"]:
                continue
            severity = "error" if info["depth_mm"] > ERROR_THRESHOLD_MM else "warning"
            rev = _reverse_dir(info["direction"])
            diags.append(_diag(E_MODULE_OVERLAP, severity,
                f"模块 {ma.get('id', '')} ({_name(ma)}) 与模块 {mb_.get('id', '')} ({_name(mb_)}) 重叠",
                ma.get("id", ""), _name_or_none(ma), mb_.get("id"), "module",
                info["area_mm2"], info["depth_mm"], info["direction"]))
            diags.append(_diag(E_MODULE_OVERLAP, severity,
                f"模块 {mb_.get('id', '')} ({_name(mb_)}) 与模块 {ma.get('id', '')} ({_name(ma)}) 重叠",
                mb_.get("id", ""), _name_or_none(mb_), ma.get("id"), "module",
                info["area_mm2"], info["depth_mm"], rev))
    return diags


def _overlap_diag(diags: list[dict], m: dict, mb, obstacle, code: str,
                  conflict_id, conflict_type: str, message: str) -> None:
    if not geometry.aabb_intersects(mb, obstacle):
        return
    info = geometry.overlap_info(mb, obstacle)
    if not info["has_overlap"]:
        return
    severity = "error" if info["depth_mm"] > ERROR_THRESHOLD_MM else "warning"
    diags.append(_diag(code, severity, message,
        m.get("id", ""), _name_or_none(m), conflict_id, conflict_type,
        info["area_mm2"], info["depth_mm"], info["direction"]))


# ── bounds 结构预检 ─────────────────────────────────────────────
def _bounds_structure_error(m: dict) -> Optional[tuple]:
    bounds = m.get("bounds")
    if bounds is None:
        return (E_MISSING_BOUNDS, "缺少 bounds 定义")
    shell, _holes = geometry._coerce_rings(bounds)
    verts = [(float(p[0]), float(p[1])) for p in shell]
    if len(verts) != 4:
        return (E_INVALID_BOUNDS, f"顶点数不符合模块规范（{len(verts)} 个，需要 4 个矩形顶点）")
    for x, y in verts:
        if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
            return (E_INVALID_BOUNDS, "包含非法坐标值（NaN 或 Infinity）")
    if _count_distinct(verts) != 4:
        return (E_INVALID_BOUNDS, "包含重复顶点，需要 4 个互不重复的矩形顶点")
    if abs(_signed_area(verts)) <= BOUNDS_TOL_MM:
        return (E_INVALID_BOUNDS, "面积为 0，无法形成有效模块轮廓")
    return None


def _count_distinct(verts: list[tuple]) -> int:
    distinct: list[tuple] = []
    for v in verts:
        if not any(abs(v[0] - e[0]) <= BOUNDS_TOL_MM and abs(v[1] - e[1]) <= BOUNDS_TOL_MM
                   for e in distinct):
            distinct.append(v)
    return len(distinct)


def _signed_area(verts: list[tuple]) -> float:
    s = 0.0
    n = len(verts)
    for i in range(n):
        cur = verts[i]
        nxt = verts[(i + 1) % n]
        s += cur[0] * nxt[1] - nxt[0] * cur[1]
    return s / 2.0


# ── facing 值工具 ───────────────────────────────────────────────
def _has_semantic(semantic) -> bool:
    return isinstance(semantic, str) and semantic.strip() != ""


def _value_present(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and value[0] is not None and value[1] is not None


def _normalize_value(value) -> Optional[tuple]:
    if not _value_present(value):
        return None
    try:
        x = float(value[0]); y = float(value[1])
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
        return None
    length = math.hypot(x, y)
    if length < 1e-10:
        return None
    return (x / length, y / length)


def _same_vector(a, b) -> bool:
    try:
        return abs(float(a[0]) - b[0]) <= 1e-9 and abs(float(a[1]) - b[1]) <= 1e-9
    except (TypeError, ValueError, IndexError):
        return False


def _reverse_dir(d: Optional[str]) -> Optional[str]:
    return {"north": "south", "south": "north", "east": "west", "west": "east"}.get(d, d)


# ── 区域 / 建筑读取 ─────────────────────────────────────────────
def _load_architecture(project_path: str) -> tuple[list[dict], list[dict]]:
    arch = _read_json(os.path.join(project_path, "baseline", "architecture.json"))
    if not isinstance(arch, dict):
        return [], []
    return arch.get("walls") or [], arch.get("columns") or []


def _load_zone_data(project_path: str, schemes_path: str) -> tuple[list[dict], list[dict]]:
    design: list[dict] = []
    room_zones = _read_json(os.path.join(project_path, "computed", "room_zones.json"))
    if isinstance(room_zones, list):
        design.extend(room_zones)
    scheme_zones = _read_json(os.path.join(schemes_path, "zones.json"))
    if isinstance(scheme_zones, list):
        design.extend(_flatten_leaves(scheme_zones))
    exclusions = _read_json(os.path.join(project_path, "computed", "exclusions.json"))
    excl = exclusions if isinstance(exclusions, list) else []
    return design, excl


def _flatten_leaves(zones: list[dict]) -> list[dict]:
    out: list[dict] = []
    for z in zones:
        subs = z.get("subZones")
        if subs:
            out.extend(_flatten_leaves(subs))
        else:
            out.append(z)
    return out


# ── modules 文件扫描（单层，开放主间无嵌套子分区文件）────────────
def _module_files(schemes_path: str, target: Optional[set],
                  variant_id: Optional[str]) -> list[tuple[str, str]]:
    """扫描 schemes/{zoneId}/modules.json。variant_id 时切到 variants/{variantId}/。

    开放主间是单设计区，故不复刻 interior-layout 的多级拓扑：
    直接遍历 schemes 下含 modules.json 的一级目录。
    """
    out: list[tuple[str, str]] = []
    if not os.path.isdir(schemes_path):
        return out
    for name in sorted(os.listdir(schemes_path)):
        zone_dir = os.path.join(schemes_path, name)
        if not os.path.isdir(zone_dir):
            continue
        if target is not None and name not in target:
            continue
        if variant_id:
            path = os.path.join(zone_dir, "variants", variant_id, "modules.json")
        else:
            path = os.path.join(zone_dir, "modules.json")
        if os.path.exists(path):
            out.append((path, name))
    return out


def _read_modules_wrapper(abs_path: str) -> Optional[dict]:
    """仅认 wrapper {schemeMetadata, modules}；裸数组抛错。"""
    if not os.path.exists(abs_path):
        return None
    with open(abs_path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    if not raw.strip():
        return {"schemeMetadata": {"summary": ""}, "modules": []}
    token = json.loads(raw)
    if isinstance(token, list):
        raise ValueError(f"modules.json 是裸数组格式，已不支持：{abs_path}")
    if not isinstance(token, dict):
        raise ValueError(f"modules.json 既不是 wrapper 也不是数组：{abs_path}")
    token.setdefault("schemeMetadata", {"summary": ""})
    if token.get("schemeMetadata") is None:
        token["schemeMetadata"] = {"summary": ""}
    token.setdefault("modules", [])
    if token.get("modules") is None:
        token["modules"] = []
    return token


def _writeback_entry(project_path: str, abs_path: str, wrapper: dict) -> dict:
    out_modules = []
    for m in wrapper["modules"]:
        mm = dict(m)
        mm["zoneId"] = None
        out_modules.append(mm)
    rel = os.path.relpath(abs_path, project_path).replace("\\", "/")
    return {
        "path": rel,
        "wrapper": {
            "schemeMetadata": wrapper.get("schemeMetadata") or {"summary": ""},
            "modules": out_modules,
        },
    }


# ── 通用工具 ────────────────────────────────────────────────────
def _read_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _name(m: dict) -> str:
    mn = m.get("moduleName")
    return mn if mn is not None else "未命名"


def _name_or_none(m: dict) -> Optional[str]:
    return m.get("moduleName")


def _count(diags: list[dict], severity: str) -> int:
    return sum(1 for d in diags if d.get("severity") == severity)


def _diag(code: str, severity: str, message: str, module_id: str,
          module_name: Optional[str], conflict_id: Optional[str] = None,
          conflict_type: Optional[str] = None, overlap_area: Optional[float] = None,
          penetration_depth: Optional[float] = None, penetration_dir: Optional[str] = None) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "moduleId": module_id,
        "moduleName": module_name,
        "conflictId": conflict_id,
        "conflictType": conflict_type,
        "overlapAreaMm2": overlap_area,
        "penetrationDepthMm": penetration_depth,
        "penetrationDirection": penetration_dir,
    }



