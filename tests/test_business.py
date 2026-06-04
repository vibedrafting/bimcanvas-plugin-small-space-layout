"""small-space-layout business.py 纯函数单测。

运行：python tests/test_business.py
（不依赖 pytest；自带断言 + 计数，便于在无 pytest 环境跑。）

覆盖：
- §2 design_plan：校验链 / upsert / effective 优先级
- §3 open-space 格式化
- §4 efficiency：shoelace / 五项指标 / 功能覆盖率 / 多用途与储物识别
"""

from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BIZ = os.path.join(_HERE, "..", "mcp_tools", "lib", "business.py")
_spec = importlib.util.spec_from_file_location("ah_business_test", _BIZ)
biz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(biz)

_passed = 0
_failed = 0


def check(cond, msg):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print(f"  FAIL: {msg}")


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


# PLACEHOLDER_TESTS


def test_design_plan():
    check(biz.is_design_zone_id("rz_1") is True, "rz_1 is design zone")
    check(biz.is_design_zone_id("dz_1") is False, "dz_1 not design zone")
    check(biz.is_design_zone_id("") is False, "empty not design zone")

    raised = False
    try:
        biz.validate_save_design_plan("dz_1", "soft-zoning")
    except biz.BusinessError:
        raised = True
    check(raised, "dz_ zone rejected")

    raised = False
    try:
        biz.validate_save_design_plan("rz_1", "bogus")
    except biz.BusinessError:
        raised = True
    check(raised, "bad tag rejected")
    biz.validate_save_design_plan("rz_1", "soft-zoning")  # ok, no raise

    e1 = biz.build_design_plan_entry("rz_1", "soft-zoning", "v1")
    es = biz.upsert_entry([], e1)
    es = biz.upsert_entry(es, biz.build_design_plan_entry("rz_1", "soft-zoning", "v2"))
    check(len(es) == 1 and es[0]["Content"] == "v2", "same-tag upsert replaces")
    es = biz.upsert_entry(es, biz.build_design_plan_entry("rz_1", "packing-brief", "b1"))
    check(len(es) == 2, "different tag appends")
    check(biz.resolve_design_plan_target(es, None)["Tag"] == "packing-brief",
          "effective prefers packing-brief")
    check(biz.resolve_design_plan_target(es, "soft-zoning")["Tag"] == "soft-zoning",
          "explicit tag honored")
    check(biz.resolve_design_plan_target([e1], None)["Tag"] == "soft-zoning",
          "fallback to soft-zoning when no packing")
    check(biz.resolve_design_plan_target([], None) is None, "empty -> None")


def test_open_space():
    data = [{
        "zoneId": "rz_1",
        "segments": [
            {"type": "wall", "start": [0, 0], "end": [5000, 0]},
            {"type": "door", "id": "d1", "start": [5000, 0], "end": [5000, 900]},
            {"type": "wall", "start": [5000, 900], "end": [5000, 3000]},
            {"type": "window", "id": "w1", "start": [5000, 3000], "end": [2000, 3000]},
            {"type": "wall", "start": [2000, 3000], "end": [0, 3000]},
            {"type": "passage", "adjacent": "卫生间", "start": [0, 3000], "end": [0, 0]},
        ],
    }]
    out = biz.format_open_space(data)
    check("开放空间边界" in out, "header present")
    check("w1" in out and "采光面" in out, "window wall in portrait")
    check("最长可用连续实墙" in out, "longest solid wall reported")
    check(biz.format_open_space([]).startswith("没有找到"), "empty data handled")


def test_shoelace():
    check(biz.polygon_area_mm2(rect(0, 0, 1000, 2000)) == 2_000_000.0, "rect area")
    check(biz.polygon_area_mm2([[0, 0], [0, 1000], [1000, 1000], [1000, 0]]) == 1_000_000.0,
          "cw winding same area")
    check(biz.polygon_area_mm2([[0, 0], [1, 1]]) == 0.0, "degenerate -> 0")


def test_efficiency_basic():
    # 40 m2 open room: 8000 x 5000 = 40,000,000 mm2
    zone = rect(0, 0, 8000, 5000)
    lib = {"modules": [
        {"id": "mod_murphy_bed", "tags": ["sleep", "multipurpose"], "functions": ["sleep", "relax"]},
        {"id": "mod_kitchen_counter", "tags": ["cook"], "functions": ["cook"]},
        {"id": "mod_tall_cabinet", "tags": ["generalStorage", "wardrobeStorage"], "functions": ["storage"]},
    ]}
    idx = biz.build_library_index(lib)
    check(len(idx) == 3 and "mod_murphy_bed" in idx, "library index built")

    modules = [
        {"moduleId": "mod_murphy_bed", "bounds": rect(0, 0, 1600, 2100)},   # 3.36 m2
        {"moduleId": "mod_kitchen_counter", "bounds": rect(2000, 0, 1800, 600)},  # 1.08 m2
        {"moduleId": "mod_tall_cabinet", "bounds": rect(4000, 0, 2000, 600)},     # 1.2 m2
    ]
    r = biz.compute_efficiency(zone, modules, idx)
    check(r["zoneAreaM2"] == 40.0, f"zone area 40 got {r['zoneAreaM2']}")
    check(abs(r["occupiedAreaM2"] - 5.64) < 0.01, f"occupied 5.64 got {r['occupiedAreaM2']}")
    check(abs(r["furnishingDensity"] - 0.141) < 0.005, f"density got {r['furnishingDensity']}")
    check(abs(r["circulationRatio"] - 0.859) < 0.005, "circulation = 1-density")
    check(r["multipurposeModuleCount"] == 1, "1 multipurpose (murphy)")
    check(r["reuseBonus"] == 1, "murphy reuse bonus = 1 (sleep+relax)")
    check(r["storageModuleCount"] == 1, "1 storage module")
    check(set(r["functionsCovered"]) == {"sleep", "relax", "cook", "storage"},
          f"functions covered got {r['functionsCovered']}")
    check(r["functionCoverage"] is None, "no requested -> coverage None")
    # storage area ratio: 1.2/40 = 0.03
    check(abs(r["storageAreaRatio"] - 0.03) < 0.005, f"storage ratio got {r['storageAreaRatio']}")


def test_efficiency_coverage():
    zone = rect(0, 0, 5000, 5000)
    lib = {"modules": [
        {"id": "mod_sofa_bed", "tags": ["relax", "sleep", "multipurpose"], "functions": ["relax", "sleep"]},
    ]}
    idx = biz.build_library_index(lib)
    modules = [{"moduleId": "mod_sofa_bed", "bounds": rect(0, 0, 1900, 900)}]
    r = biz.compute_efficiency(zone, modules, idx,
                              requested_functions=["sleep", "relax", "cook", "storage"])
    check(r["functionCoverage"] == 0.5, f"coverage 0.5 got {r['functionCoverage']}")
    check(set(r["missingFunctions"]) == {"cook", "storage"},
          f"missing got {r['missingFunctions']}")
    # module with no library entry falls back to its own tags
    r2 = biz.compute_efficiency(zone, [{"moduleId": "unknown", "tags": ["work"],
                                        "bounds": rect(0, 0, 1000, 500)}], {})
    check(r2["functionsCovered"] == ["work"], "fallback to own tags when no lib entry")
    # report formatting smoke
    txt = biz.format_efficiency_report(r)
    check("空间效率评估" in txt and "功能覆盖率" in txt, "report renders")


def test_unit_type():
    zone = rect(0, 0, 8000, 4000)  # 32 m2
    lib = {"modules": [
        {"id": "mod_murphy_bed", "tags": ["sleep", "multipurpose"], "functions": ["sleep", "relax"]},
        {"id": "mod_kitchen_counter", "tags": ["cook"], "functions": ["cook"]},
    ]}
    idx = biz.build_library_index(lib)
    modules = [
        {"moduleId": "mod_murphy_bed", "moduleName": "墨菲床",
         "bounds": rect(0, 0, 1600, 400), "facing": {"value": [0, 1], "semantic": None}},
        {"moduleId": "mod_kitchen_counter", "moduleName": "厨台",
         "bounds": rect(2000, 0, 1800, 600), "facing": {"value": [0, 1], "semantic": None}},
    ]
    ut = biz.build_unit_type("studio-A-32㎡", "rz_1", zone, modules, idx)
    check(ut["unitTypeName"] == "studio-A-32㎡", "name kept")
    check(ut["zoneAreaM2"] == 32.0, f"area 32 got {ut['zoneAreaM2']}")
    check(len(ut["modules"]) == 2, "2 template modules")
    check(ut["modules"][0]["bounds"] is not None, "bounds preserved")
    check(set(ut["functions"]) == {"sleep", "relax", "cook"}, f"functions {ut['functions']}")

    # consistency: identical -> consistent
    d = biz.diff_units(ut["modules"], modules, ut["functions"], ["sleep", "relax", "cook"])
    check(d["consistent"] is True, "identical units consistent")
    check(not d["missing"] and not d["extra"], "no diffs")

    # current missing the kitchen -> missing reported, not consistent
    d2 = biz.diff_units(ut["modules"], [modules[0]], ut["functions"], ["sleep", "relax"])
    check(d2["consistent"] is False, "missing module -> inconsistent")
    check(any(x["moduleId"] == "mod_kitchen_counter" for x in d2["missing"]), "kitchen missing")
    check("cook" in d2["functionDiff"]["missingFunctions"], "cook function missing")

    # current has an extra module -> extra reported
    extra_mod = dict(modules[1]);
    d3 = biz.diff_units([ut["modules"][0]], modules)
    check(any(x["moduleId"] == "mod_kitchen_counter" for x in d3["extra"]), "extra kitchen reported")
    check("一致性比对" in biz.format_consistency_report(d, "studio-A-32㎡"), "consistency report renders")


def main():
    test_design_plan()
    test_open_space()
    test_shoelace()
    test_efficiency_basic()
    test_efficiency_coverage()
    test_unit_type()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
