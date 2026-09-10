#!/usr/bin/env python3
"""秒懂 / JZ Insight 测试中心 (Agent Test Lab) 通用客户端。

零领域逻辑：不硬编码任何 bot / org / 场景 UUID / 表格列名。
用法见 SKILL.md；接口契约与踩坑见 references/api-contract.md。
"""
import json, time, sys
from collections import defaultdict
import requests


class MiaodongClient:
    def __init__(self, base_url, org_id, bot_id, token, timeout=90, verbose=True):
        self.base = base_url.rstrip("/").removesuffix("/api") + "/api"
        self.q = f"orgId={org_id}&botId={bot_id}"
        self.org_id, self.bot_id, self.timeout, self.verbose = org_id, bot_id, timeout, verbose
        self.h = {"Authorization": f"Bearer {token}", "accept": "application/json",
                  "content-type": "application/json"}
        self.s = requests.Session()
        self.s.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=16))

    def _log(self, *a):
        if self.verbose: print(*a, flush=True)

    def _get(self, path, extra=""):
        r = self.s.get(f"{self.base}{path}?{self.q}{extra}", headers=self.h, timeout=self.timeout)
        return self._unwrap(r, path)

    def _post(self, path, body):
        r = self.s.post(f"{self.base}{path}?{self.q}", headers=self.h, json=body, timeout=self.timeout)
        return self._unwrap(r, path)

    @staticmethod
    def _unwrap(r, path):
        try: j = r.json()
        except Exception: raise RuntimeError(f"{path} -> {r.status_code} 非 JSON: {r.text[:200]}")
        if r.status_code == 401:
            raise RuntimeError("401 Authentication failed —— 鉴权只认 Authorization 头里的 JWT，cookie 无效；token 也可能已过期，重新从浏览器取。")
        if r.status_code not in (200, 201) or j.get("code") not in (0, None):
            raise RuntimeError(f"{path} -> {r.status_code} {json.dumps(j, ensure_ascii=False)[:400]}")
        return j.get("data")

    def _paged(self, path, extra="", page_size=200):
        out, page = [], 1
        while True:
            d = self._get(path, f"{extra}&current={page}&pageSize={page_size}") or []
            out += d
            if len(d) < page_size: return out
            page += 1

    # ---------- 只读 ----------
    def scenario_tree(self):
        return (self._get("/test-center/scenario/tree") or {}).get("tree", [])

    def scenario_nodes(self):
        """扁平化场景树 -> [{id,name,path,ownCaseCount,totalCaseCount}]"""
        out = []
        def walk(ns):
            for n in ns or []:
                out.append({k: n.get(k) for k in
                            ("id", "name", "path", "source", "ownCaseCount", "totalCaseCount")})
                walk(n.get("children"))
        walk(self.scenario_tree())
        return out

    def scenario_map(self):
        """场景名 -> nodeId。同名节点取第一个，重名时请改用 path。"""
        m = {}
        for n in self.scenario_nodes(): m.setdefault(n["name"], n["id"])
        return m

    def session_memory(self):
        return self._get("/session-memory/list") or []

    def message_history_id(self):
        """「消息历史」会话属性的 id —— per-bot，禁止硬编码复用。"""
        for v in self.session_memory():
            if v.get("name") == "消息历史": return v["id"]
        raise RuntimeError("该 bot 没有名为「消息历史」的会话属性，请先用 session_memory() 人工确认变量名。")

    def list_test_sets(self):
        return self._paged("/test-center/test-set/list", page_size=100)

    def find_test_set(self, name):
        return next((x for x in self.list_test_sets() if x["name"] == name), None)

    def list_cases(self, test_set_id):
        return self._paged("/test-center/test-case/list", f"&testSetId={test_set_id}")

    def scenario_cases(self, node_id):
        return self._paged("/test-center/scenario/cases", f"&scenarioNodeId={node_id}")

    # ---------- 写 ----------
    def create_test_set(self, name):
        return self._post("/test-center/test-set/create", {"botId": self.bot_id, "name": name})["testSetId"]

    def create_cases(self, test_set_id, cases, batch=50, sleep=0.25):
        sent = 0
        for i in range(0, len(cases), batch):
            chunk = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cases[i:i + batch]]
            self._post("/test-center/test-case/create", {"testSetId": test_set_id, "testCases": chunk})
            sent += len(chunk)
            self._log(f"    批 {i // batch + 1:>3}: +{len(chunk):<4} 累计 {sent}/{len(cases)}")
            time.sleep(sleep)
        return sent   # 注意：create 不返回 testCaseId，要拿 id 必须回读

    def attach_scenario(self, node_id, case_ids, batch=100, sleep=0.2):
        n = 0
        for i in range(0, len(case_ids), batch):
            d = self._post("/test-center/scenario/attach-cases",
                           {"botId": self.bot_id, "testCaseIds": case_ids[i:i + batch],
                            "scenarioNodeId": node_id})
            n += (d or {}).get("attachedCount", 0)
            time.sleep(sleep)
        return n

    def update_case(self, case):
        """全量覆盖：未传的可写字段会被清空，必须回传完整对象。"""
        return self._post("/test-center/test-case/update", case)

    def delete_cases(self, case_ids, batch=100, sleep=0.2):
        for i in range(0, len(case_ids), batch):
            self._post("/test-center/test-case/batch-delete", {"testCaseIds": case_ids[i:i + batch]})
            time.sleep(sleep)
        return len(case_ids)

    def delete_test_set(self, test_set_id):
        return self._post("/test-center/test-set/delete", {"testSetId": test_set_id})

    # ---------- 组合 ----------
    def import_test_set(self, name, cases, scenario_map=None, batch=50, allow_existing=False):
        """建集 -> 分批灌入 -> 回读匹配 id -> 按 _scenario 挂场景。返回报告。

        cases: list[dict]，每条是 build_case() 的产物；可带 _scenario（场景名或 nodeId）。
        scenario_map: {场景名: nodeId}；省略则调 scenario_map() 自取。
        """
        if not cases: raise ValueError("cases 为空")
        names = [c["name"] for c in cases]
        if len(set(names)) != len(names):
            dup = [n for n in set(names) if names.count(n) > 1][:5]
            raise ValueError(f"name 必须在同一测试集内唯一（create 不返回 id，只能靠 name 回读匹配）。重复: {dup}")
        if not allow_existing and self.find_test_set(name):
            raise RuntimeError(f"测试集「{name}」已存在。改名，或传 allow_existing=True。")

        ts = self.create_test_set(name)
        self._log(f"  测试集「{name}」-> {ts}")
        self.create_cases(ts, cases, batch=batch)

        got = {c["name"]: c["testCaseId"] for c in self.list_cases(ts)}
        self._log(f"  回读 {len(got)} 条")

        smap = scenario_map if scenario_map is not None else self.scenario_map()
        by, missing = defaultdict(list), []
        for c in cases:
            cid = got.get(c["name"])
            if not cid: missing.append(c["name"]); continue
            sc = c.get("_scenario")
            if sc: by[smap.get(sc, sc)].append(cid)
        attached = {}
        for node_id, ids in by.items():
            attached[node_id] = self.attach_scenario(node_id, ids)
            self._log(f"  挂载 {node_id}: {attached[node_id]}/{len(ids)}")
        return {"testSetId": ts, "name": name, "submitted": len(cases),
                "readback": len(got), "attached": attached, "missing": missing}

    def drop_test_set(self, name_or_id):
        """删除测试集及其全部用例（先删用例再删集，避免场景树残留计数）。"""
        ts = name_or_id
        if not (len(str(ts)) == 36 and str(ts).count("-") == 4):
            found = self.find_test_set(name_or_id)
            if not found: raise RuntimeError(f"找不到测试集「{name_or_id}」")
            ts = found["testSetId"]
        ids = [c["testCaseId"] for c in self.list_cases(ts)]
        self.delete_cases(ids)
        self.delete_test_set(ts)
        return {"testSetId": ts, "deletedCases": len(ids)}


# ---------- 用例构造 ----------
def build_case(name, trigger_type, trigger_inputs, *, dimension=None, history=None,
               history_var_id=None, expect=None, expect_type="llm", expect_action="send-text-message",
               threshold=None, session_memory=None, strict=False, scenario=None,
               plugin_mocks=None, sql_mocks=None, node_assertions=None):
    """构造一条符合服务端契约的测试用例。

    history: [{"role":"user","content":"文本 或 裸URL"}]，需同时给 history_var_id
             （= client.message_history_id()，per-bot）。
    expect:  期望描述/文案。expect_type: llm(自然语言判定) | similarity(需 threshold) | equal。
    """
    sm = dict(session_memory or {})
    if history:
        if not history_var_id:
            raise ValueError("给了 history 就必须给 history_var_id（client.message_history_id()）")
        sm[history_var_id] = history
    assertions = []
    if expect is not None:
        v = {"verifyType": expect_type}
        if expect_type == "llm": v["description"] = expect
        else: v["value"] = expect
        if threshold is not None: v["threshold"] = threshold
        payload = {"text": v}
        assertions = [{"verifyPayload": {"type": expect_action, **payload},
                       "actionContent": {"type": expect_action, "payload": payload}}]
    c = {"name": name, "triggerType": trigger_type, "triggerInputs": trigger_inputs,
         "sessionMemoryCustomData": sm, "pluginMockOutputs": plugin_mocks or [],
         "sqlDbMockOutputs": sql_mocks or [], "testNodeOutputAssertions": node_assertions or [],
         "canvasActionOutputAssertions": assertions, "isStrictVerify": bool(strict)}
    if dimension: c["dimension"] = dimension
    if scenario: c["_scenario"] = scenario
    return c


def client_from_env():
    """从环境变量建客户端：MD_BASE, MD_ORG, MD_BOT, MD_TOKEN。"""
    import os
    missing = [k for k in ("MD_BASE", "MD_ORG", "MD_BOT", "MD_TOKEN") if not os.environ.get(k)]
    if missing:
        sys.exit(f"缺少环境变量: {', '.join(missing)}\n"
                 "MD_TOKEN 取法：浏览器登录控制台後在 Console 执行 "
                 "JSON.parse(localStorage.user).token")
    return MiaodongClient(os.environ["MD_BASE"], os.environ["MD_ORG"],
                          os.environ["MD_BOT"], os.environ["MD_TOKEN"])


if __name__ == "__main__":
    c = client_from_env()
    print("=== 场景树 ===")
    for n in c.scenario_nodes():
        print(f"  {n['path']}  own={n['ownCaseCount']} total={n['totalCaseCount']}  {n['id']}")
    print("\n=== 测试集 ===")
    for s in c.list_test_sets():
        print(f"  {s['name']}: {s['testCaseCount']} 条  {s['testSetId']}")
    try: print(f"\n消息历史变量 id: {c.message_history_id()}")
    except Exception as e: print(f"\n{e}")
