"""small-space-layout plugin 业务逻辑（namespace: spacepack）（纯函数，无 ctx / HTTP 依赖）。

设计纪律（对齐 interior-layout/lib/business.py）：
- 纯函数：输入 dict / list / str，输出 dict / list / str，或 raise BusinessError。
- 不依赖 ctx / aiohttp / Server URL —— 工具体负责 IO，本模块只做业务判定。
- 字段名 PascalCase：与平台通用 artifact 端点的落盘惯例一致
  （Entries / ZoneId / Tag / Content / Timestamp）。

文件格式契约：
- design_plan.json     = {"Entries": [<entry>...]}
- efficiency_report.json = <report dict>（Phase 2）
- unit_type.json       = <unit_type dict>（Phase 3）

本文件按 Phase 分段：
  §1 通用             —— BusinessError / utc_now_iso / is_design_zone_id
  §2 design_plan      —— Phase 1（软分区 / 打包简报）
  §3 open-space 格式化 —— Phase 1（开放主间边界呈现）
  §4 efficiency       —— Phase 2
  §5 unit_type        —— Phase 3
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ============================================================
# §1 通用
# ============================================================

class BusinessError(Exception):
    """业务校验失败。工具体捕获后转 {is_error: True} 返回给 LLM。"""


def utc_now_iso() -> str:
    """ISO 8601 + Z 时间戳（仅作记录，业务排序用 Tag 而非时间戳）。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_design_zone_id(zone_id: str | None) -> bool:
    """design_plan 只归属设计区，不归子分区（dz_ 前缀）。

    对齐 interior-layout：开放主间整体是一个设计区，
    软分区是设计语义而非几何子 zone，因此同样禁止把 design_plan 挂到 dz_ 上。
    """
    if not zone_id or not zone_id.strip():
        return False
    return not zone_id.lower().startswith("dz_")


# ============================================================
# §2 design_plan（Phase 1）
#
# 小空间的 design_plan 是两标签顺序链路：
#   soft-zoning   —— 开放主间的功能软分区（睡/工作/烹饪/休闲怎么叠、怎么复用）
#   packing-brief —— 据软分区选多用途模块的打包施工简报（placement 只读此标签）
# 比 interior-layout 的四标签简化：小空间无 multi-plan / 无 spatial-skeleton 独立阶段，
# 软分区本身即承担「读懂户型」与「定策略」双重职责。
# ============================================================

ALLOWED_DESIGN_PLAN_TAGS = (
    "soft-zoning",
    "packing-brief",
)

# packing-brief 是 placement 唯一生效图纸（对齐 interior-layout construction-brief 语义）。
EFFECTIVE_TAG = "packing-brief"


def validate_save_design_plan(zone_id: str, tag: str) -> None:
    """save_design_plan 前置校验；失败 raise BusinessError。

    顺序：1) IsDesignZoneId  2) tag 白名单。
    """
    if not is_design_zone_id(zone_id):
        raise BusinessError(
            "design_plan 只归属于设计区（开放主间），不归属于子分区。请传入父设计区 zoneId。"
        )
    if not tag or not tag.strip() or tag not in ALLOWED_DESIGN_PLAN_TAGS:
        allowed = ", ".join(ALLOWED_DESIGN_PLAN_TAGS)
        raise BusinessError(f"非法 tag: {tag or '(空)'}。合法值：{allowed}")


def build_design_plan_entry(zone_id: str, tag: str, content: str) -> dict[str, Any]:
    """构造 design_plan entry（PascalCase）。"""
    return {
        "ZoneId": zone_id,
        "Tag": tag,
        "Content": content,
        "Timestamp": utc_now_iso(),
    }


def upsert_entry(entries: list[dict[str, Any]], new_entry: dict[str, Any]) -> list[dict[str, Any]]:
    """同 Tag 替换 + append + 按 Tag 排序（对齐 interior-layout upsert_entry）。"""
    tag = new_entry.get("Tag")
    kept = [e for e in entries if e.get("Tag") != tag]
    kept.append(new_entry)
    kept.sort(key=lambda e: e.get("Tag") or "")
    return kept


def resolve_design_plan_target(entries: list[dict[str, Any]],
                               tag: str | None) -> dict[str, Any] | None:
    """load 选择：
    - tag 指定 → 取该 tag 的最后一个（LastOrDefault）
    - tag 省略 → 按 effective 优先级：packing-brief > soft-zoning（每级 LastOrDefault）
    """
    if tag:
        target = None
        for e in entries:
            if e.get("Tag") == tag:
                target = e
        return target
    for preferred in (EFFECTIVE_TAG, "soft-zoning"):
        target = None
        for e in entries:
            if e.get("Tag") == preferred:
                target = e
        if target is not None:
            return target
    return None


# ============================================================
# §3 open-space 格式化（Phase 1）
#
# 复用平台 /api/validation/zone-boundaries 返回的 ZoneBoundaryData，
# 但呈现层换成小空间语义：把开放主间的每面墙按 实墙 / 窗 / 门 / 通道(→相邻)
# 标注，并在末尾给一段「开放主间画像」帮助 Agent 做软分区决策
# （哪面是采光面、入口在哪、卫生间贴哪面墙、最长可用连续实墙）。
# ============================================================

def _seg_direction_label(dx: float, dy: float) -> str:
    """方向向量 → 方位标签：东/南/西/北墙，或斜边。Y-Up 笛卡尔。"""
    if abs(dx) < 1e-3 and abs(dy) < 1e-3:
        return "斜边"
    if abs(dx) < 1e-3:
        return "东墙" if dy > 0 else "西墙"
    if abs(dy) < 1e-3:
        return "南墙" if dx > 0 else "北墙"
    return "斜边"


def _seg_length(start: list, end: list) -> int:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return round((dx * dx + dy * dy) ** 0.5)


def _group_walls(segments: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """把边界段按方位标签聚合成「墙」（连续同标签段合为一面墙）。"""
    seg_infos = []
    for seg in segments:
        start = seg.get("start", [0, 0])
        end = seg.get("end", [0, 0])
        seg_infos.append({
            "seg": seg,
            "label": _seg_direction_label(end[0] - start[0], end[1] - start[1]),
            "length": _seg_length(start, end),
            "start": start,
            "end": end,
        })
    if not seg_infos:
        return []
    walls: list[list[dict]] = []
    current: list[dict] = [seg_infos[0]]
    for i in range(1, len(seg_infos)):
        if seg_infos[i]["label"] != seg_infos[i - 1]["label"]:
            walls.append(current)
            current = [seg_infos[i]]
        else:
            current.append(seg_infos[i])
    walls.append(current)
    return walls


def _wall_solid_runs(wall: list[dict[str, Any]]) -> list[int]:
    """一面墙内的连续实墙段长度列表（被门/窗/通道打断处断开）。

    用于「最长可用连续实墙」——小空间靠墙打包的关键容量指标。
    """
    runs: list[int] = []
    cur = 0
    for s in wall:
        if s["seg"].get("type") == "wall":
            cur += s["length"]
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    return runs


def format_open_space(data: list[dict[str, Any]]) -> str:
    """将开放主间（+ 卫生间等）的 ZoneBoundaryData 渲染为小空间 AI 友好文本。"""
    if not data:
        return "没有找到 zone 边界数据。请确认当前项目已加载、开放主间设计区已存在。"

    out: list[str] = []
    for zone_data in data:
        zone_id = zone_data.get("zoneId", "?")
        segments = zone_data.get("segments", [])
        walls = _group_walls(segments)
        if not walls:
            out.append(f"=== {zone_id}（0 面墙，无边界数据）===\n")
            continue

        label_counts: dict[str, int] = {}
        for w in walls:
            lbl = w[0]["label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

        out.append(f"=== {zone_id} 开放空间边界（{len(walls)} 面墙）===")
        out.append("")

        # 画像收集
        longest_solid = 0
        window_walls: list[str] = []
        door_walls: list[str] = []
        passage_walls: list[tuple[str, str]] = []

        label_index: dict[str, int] = {}
        for wall in walls:
            lbl = wall[0]["label"]
            total_length = sum(s["length"] for s in wall)
            if label_counts[lbl] > 1:
                idx = label_index.get(lbl, 0) + 1
                label_index[lbl] = idx
                wall_name = f"{lbl}{chr(0x2080 + idx)}"
            else:
                wall_name = lbl

            types = {s["seg"].get("type") for s in wall}
            solid_runs = _wall_solid_runs(wall)
            wall_max_solid = max(solid_runs) if solid_runs else 0
            longest_solid = max(longest_solid, wall_max_solid)

            tags = []
            if "window" in types:
                tags.append("含窗")
                window_walls.append(wall_name)
            if "door" in types:
                tags.append("含门")
                door_walls.append(wall_name)
            if "passage" in types:
                adj = next((s["seg"].get("adjacent", "") for s in wall
                            if s["seg"].get("type") == "passage"), "")
                tags.append(f"通道→{adj}" if adj else "通道")
                passage_walls.append((wall_name, adj))
            if not tags:
                tags.append("完整实墙")
            solid_part = f"，可用连续实墙 {wall_max_solid}mm" if wall_max_solid else ""
            out.append(f"{wall_name} | 总长 {total_length}mm | {'/'.join(tags)}{solid_part}")

            for s in wall:
                seg = s["seg"]
                stype = seg.get("type", "?")
                sid = seg.get("id")
                st, en, length = s["start"], s["end"], s["length"]
                if stype == "wall":
                    out.append(f"  wall {length}mm [{st[0]},{st[1]}]→[{en[0]},{en[1]}]")
                else:
                    id_part = f"({sid})" if sid else ""
                    adj = seg.get("adjacent")
                    adj_part = f"→{adj}" if adj and stype == "passage" else ""
                    out.append(
                        f"  {stype}{id_part}{adj_part} {length}mm "
                        f"[{st[0]},{st[1]}]→[{en[0]},{en[1]}]"
                    )
            out.append("")

        # 开放主间画像
        out.append(f"【{zone_id} 画像】")
        out.append(f"- 采光面（含窗的墙）：{('、'.join(window_walls)) or '无明确窗墙'}")
        out.append(f"- 入口/门所在墙：{('、'.join(door_walls)) or '无（可能经通道进入）'}")
        if passage_walls:
            out.append("- 通往相邻空间的通道：" +
                       "、".join(f"{n}→{a or '相邻区'}" for n, a in passage_walls))
        out.append(f"- 最长可用连续实墙：{longest_solid}mm（靠墙打包的最大容量参考）")
        out.append("")

    return "\n".join(out)


# ============================================================
# §4 efficiency（Phase 2）
#
# 空间效率评估：给小空间打包质量打分。纯 Python（shoelace + 计数），不依赖 shapely。
# 关键前提：validate_layout 已保证模块两两不重叠，故占地面积 = 各模块 footprint 之和
# （互不重叠的精确并集），无需多边形布尔运算。
#
# 五项指标：
#   functionCoverage  功能覆盖率   —— 已覆盖功能 / 期望功能（给 requestedFunctions 时才有比率）
#   furnishingDensity 家具密度     —— 占地面积 / 设计区面积
#   circulationRatio  动线/留白占比 —— 1 - furnishingDensity（可走动的自由地面）
#   reuse             功能复用      —— multipurpose 模块数、复用红利（多赚的功能数）
#   storage           储物          —— 储物模块数与占地占比
# ============================================================

STORAGE_TAGS = ("generalStorage", "wardrobeStorage")


def polygon_area_mm2(ring: list) -> float:
    """shoelace 求多边形面积（mm²，取绝对值）。ring = [[x,y], ...]，自动闭合。"""
    pts = [(float(p[0]), float(p[1])) for p in ring]
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _module_functions(mod: dict, library_index: dict[str, dict]) -> list[str]:
    """解析一个已放置模块承担的功能列表。

    优先用库 entry 的 functions；缺失则退到库 tags；再退到模块自身 tags。
    """
    mid = (mod.get("moduleId") or "").lower()
    lib_entry = library_index.get(mid)
    if lib_entry:
        fns = lib_entry.get("functions")
        if isinstance(fns, list) and fns:
            return [str(f) for f in fns]
        tags = lib_entry.get("tags")
        if isinstance(tags, list) and tags:
            return [str(t) for t in tags if t != "multipurpose"]
    own = mod.get("tags")
    if isinstance(own, list) and own:
        return [str(t) for t in own if t != "multipurpose"]
    return []


def _is_multipurpose(mod: dict, library_index: dict[str, dict], functions: list[str]) -> bool:
    mid = (mod.get("moduleId") or "").lower()
    lib_entry = library_index.get(mid) or {}
    tags = lib_entry.get("tags") or mod.get("tags") or []
    if "multipurpose" in tags:
        return True
    return len(set(functions)) > 1


def _is_storage(mod: dict, library_index: dict[str, dict]) -> bool:
    mid = (mod.get("moduleId") or "").lower()
    lib_entry = library_index.get(mid) or {}
    tags = lib_entry.get("tags") or mod.get("tags") or []
    return any(t in STORAGE_TAGS for t in tags)


def build_library_index(library: dict | None) -> dict[str, dict]:
    """module_library → {lower(id): entry}。library 为 None / 异常时返回 {}。"""
    if not isinstance(library, dict):
        return {}
    mods = library.get("modules")
    if not isinstance(mods, list):
        return {}
    return {str(m.get("id", "")).lower(): m for m in mods if m.get("id")}


def compute_efficiency(zone_ring: list, modules: list[dict],
                       library_index: dict[str, dict],
                       requested_functions: list[str] | None = None) -> dict[str, Any]:
    """纯函数：算五项指标。所有面积单位 mm²，对外额外给 m² 便于阅读。"""
    zone_area = polygon_area_mm2(zone_ring) if zone_ring else 0.0

    occupied = 0.0
    storage_area = 0.0
    mp_count = 0
    storage_count = 0
    reuse_bonus = 0          # 多用途件多赚的功能数（sum of len(functions)-1）
    covered: list[str] = []  # 保序去重

    for mod in modules:
        bounds = mod.get("bounds")
        area = polygon_area_mm2(bounds) if bounds else 0.0
        occupied += area
        fns = _module_functions(mod, library_index)
        for f in fns:
            if f not in covered:
                covered.append(f)
        if _is_multipurpose(mod, library_index, fns):
            mp_count += 1
            reuse_bonus += max(0, len(set(fns)) - 1)
        if _is_storage(mod, library_index):
            storage_count += 1
            storage_area += area

    module_count = len(modules)
    furnishing_density = (occupied / zone_area) if zone_area > 0 else 0.0
    circulation_ratio = max(0.0, 1.0 - furnishing_density)

    coverage_ratio: float | None = None
    missing_functions: list[str] = []
    if requested_functions:
        req = [str(f) for f in requested_functions]
        req_unique = list(dict.fromkeys(req))
        covered_set = set(covered)
        hit = [f for f in req_unique if f in covered_set]
        missing_functions = [f for f in req_unique if f not in covered_set]
        coverage_ratio = (len(hit) / len(req_unique)) if req_unique else None

    return {
        "zoneAreaMm2": round(zone_area, 1),
        "zoneAreaM2": round(zone_area / 1_000_000, 2),
        "occupiedAreaMm2": round(occupied, 1),
        "occupiedAreaM2": round(occupied / 1_000_000, 2),
        "moduleCount": module_count,
        "furnishingDensity": round(furnishing_density, 3),
        "circulationRatio": round(circulation_ratio, 3),
        "functionsCovered": covered,
        "functionCoverage": (round(coverage_ratio, 3) if coverage_ratio is not None else None),
        "missingFunctions": missing_functions,
        "multipurposeModuleCount": mp_count,
        "multipurposeRatio": (round(mp_count / module_count, 3) if module_count else 0.0),
        "reuseBonus": reuse_bonus,
        "storageModuleCount": storage_count,
        "storageAreaRatio": (round(storage_area / zone_area, 3) if zone_area > 0 else 0.0),
    }


# 目标区间（与 references/space_efficiency.md 的 rubric 一致；仅作解读提示，不是硬阈值）
_EFFICIENCY_TARGETS = {
    "furnishingDensity": (0.30, 0.65),   # 低于 = 空旷未充分利用；高于 = 拥挤
    "circulationRatio": (0.35, 0.70),    # 低于 = 动线/留白不足
    "multipurposeRatio": (0.30, 1.0),    # 小空间应多用多用途件
    "storageAreaRatio": (0.08, 0.30),    # 储物太少 = 收纳不足
}


def _band(value: float, lo: float, hi: float) -> str:
    if value < lo:
        return "偏低"
    if value > hi:
        return "偏高"
    return "良好"


def format_efficiency_report(report: dict[str, Any]) -> str:
    """把指标 dict 渲染为 AI 友好文本（带目标区间解读）。"""
    lines = ["=== 空间效率评估 ==="]
    lines.append(f"设计区面积：{report['zoneAreaM2']} ㎡ | 家具占地：{report['occupiedAreaM2']} ㎡ "
                 f"| 模块数：{report['moduleCount']}")
    lines.append("")

    def line_with_band(label: str, key: str, value, pct=False):
        disp = f"{value*100:.1f}%" if pct and isinstance(value, (int, float)) else value
        target = _EFFICIENCY_TARGETS.get(key)
        if target and isinstance(value, (int, float)):
            lo, hi = target
            band = _band(value, lo, hi)
            rng = f"{lo*100:.0f}–{hi*100:.0f}%" if pct else f"{lo}–{hi}"
            lines.append(f"- {label}：{disp}（目标 {rng}，{band}）")
        else:
            lines.append(f"- {label}：{disp}")

    line_with_band("家具密度", "furnishingDensity", report["furnishingDensity"], pct=True)
    line_with_band("动线/留白占比", "circulationRatio", report["circulationRatio"], pct=True)
    line_with_band("多用途占比", "multipurposeRatio", report["multipurposeRatio"], pct=True)
    line_with_band("储物占地占比", "storageAreaRatio", report["storageAreaRatio"], pct=True)

    lines.append(f"- 多用途模块数：{report['multipurposeModuleCount']} | "
                 f"复用红利（多赚功能数）：{report['reuseBonus']}")
    lines.append(f"- 储物模块数：{report['storageModuleCount']}")

    covered = "、".join(report["functionsCovered"]) or "（无）"
    lines.append(f"- 已覆盖功能：{covered}")
    if report.get("functionCoverage") is not None:
        lines.append(f"- 功能覆盖率：{report['functionCoverage']*100:.1f}%")
        if report.get("missingFunctions"):
            lines.append(f"  缺失功能：{'、'.join(report['missingFunctions'])}")
    lines.append("")
    return "\n".join(lines)


# ============================================================
# §5 unit_type（Phase 3）
#
# 户型标准化复制：把验过的单元布局打包成可复用模板（unit_type），套用到目标单元，
# 再做一致性比对。纯函数只负责「打包」与「比对」；几何适配（镜像/微调）由 skill 引导
# Agent 在写 modules.json 时完成，并经 validate_layout 兜底。
#
# unit_type 文档结构：
#   {
#     "version": "1.0",
#     "unitTypeName": str,
#     "sourceZoneId": str,
#     "zoneAreaM2": float,
#     "functions": [str, ...],          # 该户型覆盖的功能集（保序去重）
#     "modules": [                       # 模板模块（仅保留可复制字段）
#       {"moduleId": str, "moduleName": str, "bounds": [[x,y]*4], "facing": {...}},
#       ...
#     ],
#     "timestamp": str
#   }
# ============================================================

def build_unit_type(unit_type_name: str, source_zone_id: str, zone_ring: list,
                    modules: list[dict], library_index: dict[str, dict]) -> dict[str, Any]:
    """把当前单元的 modules 打包成 unit_type 模板（纯函数）。"""
    tmpl_modules: list[dict] = []
    functions: list[str] = []
    for m in modules:
        tmpl_modules.append({
            "moduleId": m.get("moduleId"),
            "moduleName": m.get("moduleName"),
            "bounds": m.get("bounds"),
            "facing": m.get("facing"),
        })
        for f in _module_functions(m, library_index):
            if f not in functions:
                functions.append(f)
    zone_area = polygon_area_mm2(zone_ring) if zone_ring else 0.0
    return {
        "version": "1.0",
        "unitTypeName": unit_type_name,
        "sourceZoneId": source_zone_id,
        "zoneAreaM2": round(zone_area / 1_000_000, 2),
        "functions": functions,
        "modules": tmpl_modules,
        "timestamp": utc_now_iso(),
    }


def _module_id_counts(modules: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in modules:
        mid = m.get("moduleId") or "(无 moduleId)"
        counts[mid] = counts.get(mid, 0) + 1
    return counts


def diff_units(template_modules: list[dict], current_modules: list[dict],
               template_functions: list[str] | None = None,
               current_functions: list[str] | None = None) -> dict[str, Any]:
    """比对当前单元与标准间模板的一致性（纯函数）。

    返回模块组成差异（按 moduleId 计数）+ 功能集差异 + 一致性判定。
    """
    t_counts = _module_id_counts(template_modules)
    c_counts = _module_id_counts(current_modules)
    all_ids = sorted(set(t_counts) | set(c_counts))

    missing: list[dict] = []   # 模板有、当前缺（或少）
    extra: list[dict] = []     # 当前有、模板没（或多）
    for mid in all_ids:
        t = t_counts.get(mid, 0)
        c = c_counts.get(mid, 0)
        if c < t:
            missing.append({"moduleId": mid, "template": t, "current": c})
        elif c > t:
            extra.append({"moduleId": mid, "template": t, "current": c})

    func_diff: dict[str, Any] = {}
    if template_functions is not None and current_functions is not None:
        t_set = list(dict.fromkeys(template_functions))
        c_set = set(current_functions)
        func_diff = {
            "templateFunctions": t_set,
            "currentFunctions": list(dict.fromkeys(current_functions)),
            "missingFunctions": [f for f in t_set if f not in c_set],
        }

    module_consistent = not missing and not extra
    function_consistent = (not func_diff.get("missingFunctions")) if func_diff else True
    return {
        "moduleConsistent": module_consistent,
        "functionConsistent": function_consistent,
        "consistent": module_consistent and function_consistent,
        "templateModuleCount": len(template_modules),
        "currentModuleCount": len(current_modules),
        "missing": missing,
        "extra": extra,
        "functionDiff": func_diff,
    }


def format_consistency_report(diff: dict[str, Any], unit_type_name: str | None = None) -> str:
    """把 diff_units 结果渲染为 AI 友好文本。"""
    name = f"「{unit_type_name}」" if unit_type_name else "标准间模板"
    head = "一致" if diff["consistent"] else "不一致"
    lines = [f"=== 与{name}一致性比对：{head} ==="]
    lines.append(f"模板模块数 {diff['templateModuleCount']} | 当前模块数 {diff['currentModuleCount']}")
    if diff["missing"]:
        lines.append("缺少 / 数量不足（模板有、当前少）：")
        for d in diff["missing"]:
            lines.append(f"  - {d['moduleId']}：模板 {d['template']}，当前 {d['current']}")
    if diff["extra"]:
        lines.append("多出 / 数量超出（当前有、模板没）：")
        for d in diff["extra"]:
            lines.append(f"  - {d['moduleId']}：模板 {d['template']}，当前 {d['current']}")
    fd = diff.get("functionDiff") or {}
    if fd.get("missingFunctions"):
        lines.append(f"缺失功能：{'、'.join(fd['missingFunctions'])}")
    if diff["consistent"]:
        lines.append("模块组成与功能集与标准间一致。")
    return "\n".join(lines)
