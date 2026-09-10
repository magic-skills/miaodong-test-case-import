#!/usr/bin/env python3
"""秒懂 / JZ Insight 测试中心 (Agent Test Lab) 通用客户端。

零领域逻辑：不硬编码任何 bot / org / 场景 UUID / 表格列名。
用法见 SKILL.md；接口契约与踩坑见 references/api-contract.md。
"""
import json, os, time, sys
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


# ---------- 多客户 profile ----------
# 一个人常同时对接多个客户的私有部署。域名/org/bot 是稳定的，存成 profile；
# token 会过期且是个人凭证，**不存盘**，每次从环境变量给。
PROFILE_PATH = os.path.join(os.path.expanduser("~"), ".miaodong", "profiles.json")


def load_profiles():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return {}
    except Exception as e: sys.exit(f"profiles.json 读取失败: {e}")


def save_profile(name, base, org, bot, note=""):
    ps = load_profiles()
    ps[name] = {"base": base, "org": org, "bot": bot, "note": note}
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(ps, f, ensure_ascii=False, indent=2)
    os.chmod(PROFILE_PATH, 0o600)
    return PROFILE_PATH


# ---------- 环境地图 ----------
# 秒懂分「标准区」(多客户共用集群) 和「独立部署」(单客户专属)。
# ⚠️ 内部拓扑，勿外传；本仓库为私有仓库。
STANDARD_ZONES = {
    "A": "insight.juzibot.com",
    "B": "lighthouse-insight.juzibot.com",
    "C": "echo-insight.juzibot.com",
    "D": "lantern-insight.juzibot.com",
    "E": "horizon-insight.juzibot.com",
    "F": "grove-insight.juzibot.com",
    "G": "fireside-insight.juzibot.com",
    "H": "glimmer-insight.juzibot.com",
    "I": "stride-md.dpclouds.com",          # 唯一不在 juzibot.com 上的
    "J": "journey-insight.juzibot.com",
    "X": "willow-insight.juzibot.com",
    "Z": "az-insight.juzibot.com",
}
DEDICATED = {                                # 独立部署，key 是客户名
    "量子之歌": "inkwell-insight.juzibot.com",
    "有赞":     "petal-insight.juzibot.com",
    "网易":     "cloudweave-insight.juzibot.com",
    "兴趣岛":   "xlink-insight.juzibot.com",
}
# ⚠️ xlink-insight 是【兴趣岛独立部署】，不是「X 区」——X 区是 willow-insight。
ZONES = {**STANDARD_ZONES, **DEDICATED}


def resolve_zone(key):
    """区代号(A~Z) 或 客户名 -> https://域名。认不出就返回 None。"""
    if not key: return None
    k = key.strip()
    for cand in (k, k.upper()):
        if cand in ZONES: return "https://" + ZONES[cand]
    if "." in k:                              # 直接给了域名
        return k if k.startswith("http") else "https://" + k
    return None


SHARE_PREFIX = "md-profile:"

JS_SNIPPET = r"""(()=>{try{const u=JSON.parse(localStorage.user);const b=location.pathname.match(/\/agents\/([0-9a-f-]{36})/);if(!u?.token)return'❌ 没读到登录态,先登录控制台';if(!b)return'❌ 请先打开目标智能体页面(地址栏含 /agents/<id>/)再执行';const s=`export MD_BASE=${location.origin} MD_ORG=${u.currentOrg.id} MD_BOT=${b[1]} MD_TOKEN=${u.token}`;try{copy(s)}catch(e){};console.log(s);return'✅ 已复制到剪贴板,粘到终端即可'}catch(e){return'❌ '+e.message}})()"""


def share_profile(name):
    """把一个 profile 编成单行串，便于发给同事。**不含 token**，只是环境坐标。"""
    import base64
    ps = load_profiles()
    if name not in ps: sys.exit(f"没有 profile「{name}」。已有: {sorted(ps) or '（空）'}")
    p = dict(ps[name]); p["name"] = name
    p.pop("token", None)   # 防御：任何情况下都不外传 token
    return SHARE_PREFIX + base64.urlsafe_b64encode(
        json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode()).decode()


def adopt_profile(blob, rename=None):
    import base64
    blob = blob.strip()
    if not blob.startswith(SHARE_PREFIX): sys.exit(f"不是有效的分享串（应以 {SHARE_PREFIX} 开头）")
    try: p = json.loads(base64.urlsafe_b64decode(blob[len(SHARE_PREFIX):]).decode())
    except Exception as e: sys.exit(f"分享串解析失败: {e}")
    name = rename or p.get("name") or "imported"
    for k in ("base", "org", "bot"):
        if not p.get(k): sys.exit(f"分享串缺少 {k}")
    save_profile(name, p["base"], p["org"], p["bot"], p.get("note", ""))
    return name, p


def client_from_env():
    """建客户端。两种方式：

    1) 直接给环境变量 MD_BASE / MD_ORG / MD_BOT / MD_TOKEN
    2) MD_PROFILE=<客户名> + MD_TOKEN   （前三项从 ~/.miaodong/profiles.json 读）

    token 永远只从环境变量取，不落盘。
    """
    prof = os.environ.get("MD_PROFILE")
    if prof:
        ps = load_profiles()
        if prof not in ps:
            sys.exit(f"没有名为「{prof}」的 profile。已有: {sorted(ps) or '（空）'}\n"
                     f"新增: MD_BASE=.. MD_ORG=.. MD_BOT=.. python3 md_client.py save {prof}")
        p = ps[prof]
        base, org, bot = p["base"], p["org"], p["bot"]
        if not os.environ.get("MD_TOKEN"):
            sys.exit("profile 只存环境坐标，不存 token。请另外给 MD_TOKEN=<JWT>")
        print(f"  profile「{prof}」{p.get('note') or ''}")
        return MiaodongClient(base, org, bot, os.environ["MD_TOKEN"])

    # MD_ZONE=X 或 MD_ZONE=兴趣岛 可代替 MD_BASE
    zone = os.environ.get("MD_ZONE")
    if zone and not os.environ.get("MD_BASE"):
        base = resolve_zone(zone)
        if not base:
            sys.exit(f"认不出 MD_ZONE=「{zone}」。可用: 标准区 {'/'.join(STANDARD_ZONES)} | "
                     f"独立部署 {'/'.join(DEDICATED)}\n跑 `python3 md_client.py zones` 看全表")
        os.environ["MD_BASE"] = base

    missing = [k for k in ("MD_BASE", "MD_ORG", "MD_BOT", "MD_TOKEN") if not os.environ.get(k)]
    if missing:
        ps = load_profiles()
        sys.exit(
            f"缺少环境变量: {', '.join(missing)}\n"
            "取法（浏览器登录控制台后，在目标智能体页面打开 Console）：\n"
            "  MD_BASE  = 控制台域名；或用 MD_ZONE=<区代号|客户名> 自动解析\n"
            "             （区代号见 `python3 md_client.py zones`）\n"
            "  MD_BOT   = 地址栏 /main/agents/<botId>/... 里的那段 UUID\n"
            "  MD_ORG   = JSON.parse(localStorage.user).currentOrg.id\n"
            "  MD_TOKEN = JSON.parse(localStorage.user).token\n"
            + (f"\n或用已存的 profile: MD_PROFILE=<{'|'.join(sorted(ps))}> MD_TOKEN=.." if ps else
               "\n多客户可存 profile: MD_BASE=.. MD_ORG=.. MD_BOT=.. python3 md_client.py save <客户名>"))
    return MiaodongClient(os.environ["MD_BASE"], os.environ["MD_ORG"],
                          os.environ["MD_BOT"], os.environ["MD_TOKEN"])


def _cli():
    args = sys.argv[1:]
    if args and args[0] == "profiles":
        ps = load_profiles()
        if not ps: print(f"（空）{PROFILE_PATH} 还没有 profile"); return True
        print(f"{PROFILE_PATH}:")
        for k, v in ps.items():
            print(f"  {k:<16} {v['base']}  bot={v['bot']}  {v.get('note','')}")
        print("\n用法: MD_PROFILE=<名字> MD_TOKEN=<JWT> python3 md_client.py")
        return True
    if args and args[0] == "zones":
        print("标准区（多客户共用集群）:")
        for k, v in STANDARD_ZONES.items(): print(f"  {k:<8} https://{v}")
        print("\n独立部署（单客户专属）:")
        for k, v in DEDICATED.items(): print(f"  {k:<8} https://{v}")
        print("\n用法: MD_ZONE=X ...  或  MD_ZONE=兴趣岛 ...   （代替 MD_BASE）")
        print("⚠️ xlink-insight 是【兴趣岛独立部署】，不是 X 区（X 区是 willow-insight）")
        print("⚠️ 内部拓扑，勿外传")
        return True
    if args and args[0] == "bootstrap":
        print("""在【目标客户的控制台】里做（每个客户各做一次）：

  1. 浏览器登录该客户控制台，打开你要导入的那个智能体页面
     （地址栏形如 https://<域名>/main/agents/<botId>/...）
  2. 打开开发者工具 Console：Chrome/Edge  Cmd+Option+J (mac) / F12 (win)
     ⚠️ 首次可能提示不允许粘贴，按提示输入 allow pasting 后回车
  3. 粘贴下面整行并回车：

""" + JS_SNIPPET + """

  4. 会自动复制好一整行 export 命令，直接粘到终端执行。

注意：
  · 这一行里含你的 JWT，等同于你的账号——**不要发到群里/工单/文档**。
  · token 会过期，脚本报 401 就回来重做一次。
  · localStorage 按域名隔离：必须在【该客户】的控制台页面执行，换客户要重做。""")
        return True
    if args and args[0] == "share":
        if len(args) < 2: sys.exit("用法: python3 md_client.py share <客户名>")
        print(share_profile(args[1]))
        print("\n↑ 发给同事，对方执行: python3 md_client.py adopt '<上面这串>'", file=sys.stderr)
        print("   串里只有 域名/orgId/botId/备注，**没有 token**；对方仍需自己的账号。", file=sys.stderr)
        return True
    if args and args[0] == "adopt":
        if len(args) < 2: sys.exit("用法: python3 md_client.py adopt '<md-profile:...>' [改名]")
        name, p = adopt_profile(args[1], args[2] if len(args) > 2 else None)
        print(f"已导入 profile「{name}」: {p['base']}  bot={p['bot']}  {p.get('note','')}")
        print(f"用法: MD_PROFILE={name} MD_TOKEN=<你自己的JWT> python3 md_client.py")
        return True
    if args and args[0] == "save":
        if len(args) < 2: sys.exit("用法: MD_BASE=.. MD_ORG=.. MD_BOT=.. python3 md_client.py save <客户名> [备注]")
        miss = [k for k in ("MD_BASE", "MD_ORG", "MD_BOT") if not os.environ.get(k)]
        if miss: sys.exit(f"缺少 {', '.join(miss)}")
        note = " ".join(args[2:])
        # 有 token 就顺手把 bot 名存进备注，方便日后辨认
        if not note and os.environ.get("MD_TOKEN"):
            try:
                note = (MiaodongClient(os.environ["MD_BASE"], os.environ["MD_ORG"],
                                       os.environ["MD_BOT"], os.environ["MD_TOKEN"],
                                       verbose=False).bot_info() or {}).get("name", "")
            except Exception: pass
        print(f"已保存 profile「{args[1]}」-> {save_profile(args[1], os.environ['MD_BASE'], os.environ['MD_ORG'], os.environ['MD_BOT'], note)}")
        return True
    return False


if __name__ == "__main__":
    if _cli(): sys.exit(0)
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
