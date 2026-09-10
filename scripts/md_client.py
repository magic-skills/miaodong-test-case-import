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

    # ---------- 目标确认 ----------
    def bot_info(self):
        """当前 MD_BOT 指向的智能体基本信息（name / botStatus / canvasName …）。"""
        return self._get("/bot/basic-info")   # botId 已在 self.q 里，重复传会被解析成数组 -> 400

    def whoami(self, echo=True):
        """导入前务必确认：这批用例到底会落到哪个环境的哪个智能体上。"""
        try: bot = self.bot_info() or {}
        except Exception as e: bot = {"name": f"<取不到: {e}>"}
        who = {"console": self.base.removesuffix("/api"), "orgId": self.org_id,
               "botId": self.bot_id, "botName": bot.get("name"),
               "canvas": bot.get("canvasName"), "botStatus": bot.get("botStatus")}
        if echo:
            self._log(f"  目标 → {who['console']}")
            self._log(f"         智能体「{who['botName']}」 ({self.bot_id})")
            self._log(f"         orgId {self.org_id}")
        return who

    def capabilities(self, echo=True):
        """探测目标环境支持哪一代测试中心。换客户/换部署的第一步。

        新一代(Agent Test Lab)有场景树；老一代只有 测试集 + 测试用例。
        404 = 该接口不存在（老版本），200 = 支持。
        """
        probe = {"test_set": "/test-center/test-set/list",
                 "scenario_tree": "/test-center/scenario/tree",
                 "session_memory": "/session-memory/list"}
        caps = {}
        for k, path in probe.items():
            try: self._get(path, "&current=1&pageSize=1"); caps[k] = True
            except Exception as e: caps[k] = False if "404" in str(e) else f"? {str(e)[:60]}"
        caps["generation"] = "new (Agent Test Lab, 有场景树)" if caps.get("scenario_tree") is True \
                             else "old (仅测试集+用例，无场景树)"
        if echo:
            self._log(f"  能力: {caps['generation']}")
            for k in ("test_set", "scenario_tree", "session_memory"):
                self._log(f"    {k}: {caps[k]}")
            if caps.get("test_set") is not True:
                self._log("    ⚠️ 连测试集列表都取不到——域名/orgId/token 可能不对，先别继续。")
        return caps

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
        names = [v.get("name") for v in self.session_memory()]
        raise RuntimeError(f"该 bot 没有名为「消息历史」的会话属性。现有: {names[:20]}"
                           " —— 换环境时变量名可能不同，用 session_memory() 人工确认后直接传 history_var_id。")

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
        self.whoami()   # 用例会落到这个 bot 的测试集 + 该 bot 的场景树上，导错 bot 很难清理
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

        # 挂场景是可选步骤：老版本部署没有场景树，取不到就降级跳过，
        # 绝不能因此让「用例已写入但脚本报错退出」。
        smap, attached, skipped = scenario_map, {}, None
        wants = [c for c in cases if c.get("_scenario")]
        if wants and smap is None:
            try: smap = self.scenario_map()
            except Exception as e:
                skipped = f"取不到场景树({str(e)[:80]})"
                self._log(f"  ⚠️ {skipped} —— 跳过挂载。用例已在测试集里，可用不带 _scenario 的方式使用。")
        if wants and smap is not None:
            by, unknown = defaultdict(list), set()
            for c in wants:
                cid = got.get(c["name"])
                if not cid: continue
                sc = c["_scenario"]
                if sc not in smap and not (len(sc) == 36 and sc.count("-") == 4):
                    unknown.add(sc); continue
                by[smap.get(sc, sc)].append(cid)
            if unknown:
                self._log(f"  ⚠️ 场景树里没有这些节点，未挂载: {sorted(unknown)}")
                self._log(f"     该 bot 现有场景: {sorted(smap)}")
            for node_id, ids in by.items():
                attached[node_id] = self.attach_scenario(node_id, ids)
                self._log(f"  挂载 {node_id}: {attached[node_id]}/{len(ids)}")
        missing = [c["name"] for c in cases if not got.get(c["name"])]
        return {"testSetId": ts, "name": name, "submitted": len(cases),
                "readback": len(got), "attached": attached, "missing": missing,
                "scenarioSkipped": skipped}

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
        sys.exit(
            f"缺少环境变量: {', '.join(missing)}\n"
            "取法（浏览器登录控制台后，在目标智能体页面打开 Console）：\n"
            "  MD_BASE  = 控制台域名，如 https://xxx-insight.example.com\n"
            "  MD_BOT   = 地址栏 /main/agents/<botId>/... 里的那段 UUID\n"
            "  MD_ORG   = JSON.parse(localStorage.user).currentOrg.id\n"
            "  MD_TOKEN = JSON.parse(localStorage.user).token")
    return MiaodongClient(os.environ["MD_BASE"], os.environ["MD_ORG"],
                          os.environ["MD_BOT"], os.environ["MD_TOKEN"])


if __name__ == "__main__":
    c = client_from_env()
    print("=== 目标 ===")
    c.whoami()
    print("\n=== 环境能力 ===")
    caps = c.capabilities()
    print("\n=== 场景树 ===")
    for n in c.scenario_nodes():
        print(f"  {n['path']}  own={n['ownCaseCount']} total={n['totalCaseCount']}  {n['id']}")
    print("\n=== 测试集 ===")
    for s in c.list_test_sets():
        print(f"  {s['name']}: {s['testCaseCount']} 条  {s['testSetId']}")
    try: print(f"\n消息历史变量 id: {c.message_history_id()}")
    except Exception as e: print(f"\n{e}")
