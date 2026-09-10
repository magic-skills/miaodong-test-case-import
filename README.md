# miaodong-test-case-import

一个可移植的 **Agent Skill**：把任意外部数据（Excel 行、聊天记录、线上日志…）批量变成
**秒懂 / JZ Insight 测试中心**里可跑回归的测试用例。**同一份源在 Claude Code 和 OpenAI Codex 两端通用**。

> 核心立场：**用确定性脚本生成用例，不要让 agent 逐条生成。**
> 分类和字段映射通常是机械规则，脚本能保证 1:1 全覆盖；agent 会漏。
> 实测同一份 427 行的表格，平台自带的 Agent 生成器产出 410 条（漏 17 行，另有 23 条分类不稳定），
> 确定性脚本产出 427 条零误差。agent 该做的是**写规则**，不是**执行规则**。

## 快速开始

```bash
bash scripts/install.sh          # 装到 Claude Code + Codex（幂等，可反复跑）
pip3 install requests

export MD_BASE=https://<你的秒懂控制台域名>
export MD_ORG=<orgId>
export MD_BOT=<botId>
export MD_TOKEN=<JWT>            # 浏览器 Console: JSON.parse(localStorage.user).token

python3 scripts/md_client.py     # 打印场景树 / 测试集 / 「消息历史」变量 id
```

## 为什么需要这个 skill

秒懂测试中心的写入接口有几个**会静默出错**的地方，不知道就会导入成功但数据是错的：

| 坑 | 后果 | 对策 |
|---|---|---|
| `create` 丢弃 `scenarioNodeId` | 用例不挂场景树 | 创建后单独调 `attach-cases` |
| `create` 不返回 `testCaseId` | 拿不到 id，没法挂场景 | 回读按 `name` 匹配 → `name` 必须唯一 |
| `create`/`update` 丢弃 `dimensionDetail` | 溯源信息全空 | 溯源写进 `name` |
| `update` 是全量覆盖 | 漏传字段被清空 | 回传完整对象 |
| 鉴权只认 `Authorization` 头 | cookie 请求一律 401 | 从 `localStorage.user` 取 JWT |

**导入成功 ≠ 数据正确**，`{"code":0}` 骗人。所以本 skill 把「审计」做成流程的必经一步。

## 内容

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 主文档：五个坑 + 标准流程 + 可跑示例 |
| `references/data-model.md` | 测试用例完整数据结构、字段可写性四分类、10 种触发器字段表、断言结构 |
| `references/api-contract.md` | 接口清单、鉴权、契约探测技巧、回滚步骤 |
| `scripts/md_client.py` | 通用客户端 + `build_case()` + `import_test_set()` |
| `scripts/audit_cases.py` | 逐字段审计 + 场景树对账 |

两个脚本**零领域逻辑**，不含任何 bot / org / 场景 UUID / 表格列名——领域部分（怎么从你的数据造 case）
在 `SKILL.md` 里是一段标注清楚的可改示例。

## 用法骨架

```python
from md_client import client_from_env, build_case
from audit_cases import audit, reconcile_scenario_tree

c = client_from_env()
HIST = c.message_history_id()          # per-bot，禁止硬编码

cases = [build_case(
    name=f"{scene}_{i:03d}#第{i}行",                  # 唯一 + 带溯源
    trigger_type="receive-image-message",
    trigger_inputs={"imageUrl": row.img},
    history=[{"role": "user", "content": row.text}],  # 上下文都进 history
    history_var_id=HIST,
    expect="Bot 应识别图片并给出合理回复,不强制具体文案",
    scenario=scene,
) for i, row in enumerate(rows, 1)]

rep = c.import_test_set("我的测试集", cases)
audit(c, rep["testSetId"], cases)
reconcile_scenario_tree(c, expected_total=len(cases))
```

## 适用范围与免责

针对**秒懂控制台内部 API**（Agent Test Lab / 测试中心 / 场景树）。秒懂对外的 Insight Open API
完全不含测试中心，测试用例只能走内部 API——**该 API 无稳定性承诺**，平台升级后需重新核对契约。

契约实测于前端 `1.18.4`（2026-09-10），并以 1075 条真实用例验证。文档中所有 UUID、域名均为占位符。
`references/data-model.md` 对每个字段标注了证据等级（实测 / 双源交叉验证 / 单一来源），
没有可靠来源的部分明确写了「按探测法自取」，没有编造。
