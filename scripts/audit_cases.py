#!/usr/bin/env python3
"""导入后审计：把服务端实际落库的用例逐字段对回本地构造的 cases。

导入成功 ≠ 数据正确。服务端会静默丢弃部分字段（见 references/api-contract.md），
不审计就会像「dimensionDetail 全空」那样直到很久以后才被发现。
"""
import json, sys
from collections import Counter

# 服务端只读/派生字段：本地不传，比对时跳过
DERIVED = {"testCaseId", "orgId", "testSetId", "status", "isReviewed", "rootCaseId",
           "sourceCaseId", "previousCaseId", "generatedCaseId", "createdBy", "createdAt",
           "updatedAt", "triggerContent", "scenarioPath", "scenarioNodeId", "revisionCount",
           "dimensionDetail"}


def audit(client, test_set_id, local_cases, *, expect_scenario=True, verbose=True):
    srv = {c["name"]: c for c in client.list_cases(test_set_id)}
    loc = {c["name"]: c for c in local_cases}
    problems = []

    for n in set(loc) - set(srv): problems.append((n, "服务端缺失"))
    for n in set(srv) - set(loc): problems.append((n, "服务端多出（非本次导入？）"))

    for n, lc in loc.items():
        sc = srv.get(n)
        if not sc: continue
        for k, lv in lc.items():
            if k.startswith("_") or k in DERIVED: continue
            sv = sc.get(k)
            if json.dumps(sv, sort_keys=True, ensure_ascii=False) != \
               json.dumps(lv, sort_keys=True, ensure_ascii=False):
                problems.append((n, f"{k}: 服务端={json.dumps(sv,ensure_ascii=False)[:80]} "
                                    f"本地={json.dumps(lv,ensure_ascii=False)[:80]}"))
        if expect_scenario and lc.get("_scenario") and not sc.get("scenarioNodeId"):
            problems.append((n, "未挂场景（create 会丢弃 scenarioNodeId，需 attach-cases）"))
        if sc.get("status") != "ready" or not sc.get("isReviewed"):
            problems.append((n, f"status={sc.get('status')}/isReviewed={sc.get('isReviewed')} 无法进回归"))

    rep = {"testSetId": test_set_id, "local": len(loc), "server": len(srv),
           "problems": problems,
           "scenarios": dict(Counter((c.get("scenarioPath") or "<未挂>").split("/")[-1]
                                     for c in srv.values()))}
    if verbose:
        print(f"  本地 {len(loc)} / 服务端 {len(srv)} | 问题 {len(problems)}")
        print(f"  场景分布: {rep['scenarios']}")
        for p in problems[:10]: print(f"    ⚠️  {p[0]}: {p[1]}")
        if len(problems) > 10: print(f"    …… 另有 {len(problems)-10} 项")
        print("  ✅ 通过" if not problems else "  ❌ 未通过")
    return rep


def reconcile_scenario_tree(client, expected_total=None, verbose=True):
    """场景树对账：各节点 ownCaseCount 之和应等于你导入的总数。"""
    nodes = [n for n in client.scenario_nodes() if n["ownCaseCount"]]
    total = sum(n["ownCaseCount"] for n in nodes)
    if verbose:
        for n in nodes: print(f"    {n['path']}: {n['ownCaseCount']}")
        print(f"    合计 {total}" + (f" / 期望 {expected_total}" if expected_total else ""))
        if expected_total is not None:
            print("    ✅ 对账一致" if total == expected_total
                  else f"    ❌ 差 {total - expected_total}（可能有旧批次重复挂在同一批节点上）")
    return {"total": total, "nodes": nodes}


if __name__ == "__main__":
    from md_client import client_from_env
    if len(sys.argv) < 3:
        sys.exit("用法: audit_cases.py <testSetId> <本地 cases.json>")
    c = client_from_env()
    audit(c, sys.argv[1], json.load(open(sys.argv[2])))
    print("\n=== 场景树对账 ===")
    reconcile_scenario_tree(c)
