---
name: miaodong-test-case-import
description: Use when creating, importing, exporting, auditing or bulk-editing test cases in a 秒懂 / JZ Insight 测试中心 (test-center, Agent Test Lab, 测试集, 测试用例, 场景树/scenario tree), or when scripting against its API — including turning Excel/CSV rows, chat logs or other external data into 回归测试 cases, wiring multi-turn history, or debugging why imported cases came back empty, unassigned to a scenario, or 401.
---

# 秒懂测试用例批量导入

把任意外部数据（Excel 行、聊天记录、线上日志……）变成秒懂测试中心里可跑回归的用例。

**核心立场：用确定性脚本生成用例，不要让 agent 逐条生成。** 分类和字段映射通常是机械规则，脚本能保证 1:1 全覆盖；agent 会漏。实测同一份 427 行的 Excel，Agent Test Lab 生成出 410 条（漏 17 行，另有 23 条分类不稳定），脚本生成 427 条零误差。agent 该做的是**写规则**，不是**执行规则**。

**动手前先读 `references/data-model.md`**（用例数据结构、字段可写性、triggerInputs、history）和 `references/api-contract.md`（接口清单、鉴权、五个坑）。下面只是摘要。

## 五个坑（不知道就会静默出错）

| 坑 | 后果 | 对策 |
|---|---|---|
| `create` 丢弃 `scenarioNodeId` | 用例不挂场景树，UI 上看不见分类 | 创建后单独调 `attach-cases` |
| `create` 不返回 `testCaseId` | 拿不到 id，没法挂场景 | 回读 `test-case/list` 按 `name` 匹配 → **`name` 必须唯一** |
| `create`/`update` 丢弃 `dimensionDetail` | 溯源信息全空 | 溯源写进 `name` |
| `update` 是全量覆盖 | 漏传字段被清空（漏 `name` → 用例名变空串） | 回传完整对象 |
| 鉴权只认 `Authorization` 头 | cookie 请求一律 401 | `JSON.parse(localStorage.user).token` |

**导入成功 ≠ 数据正确。** 服务端静默丢字段，`{"code":0}` 骗人。每次导完必须审计。

## 标准流程

```
1. 建测试集      POST /test-center/test-set/create   {botId, name}
2. 分批灌入      POST /test-center/test-case/create  {testSetId, testCases[]}   每批 50
3. 回读匹配 id   GET  /test-center/test-case/list    ?testSetId=..&pageSize=200
4. 挂场景        POST /test-center/scenario/attach-cases {botId, testCaseIds[], scenarioNodeId}
5. 审计对账      逐字段对回本地 + 场景树各节点之和 == 本次导入总数
```

`scripts/md_client.py` 把 1–4 封装成 `import_test_set()`，`scripts/audit_cases.py` 是第 5 步。
两个脚本零领域逻辑，不含任何 bot / org / 场景 UUID / 列名。

## 用法

```bash
export MD_BASE=https://<控制台域名>  MD_ORG=<orgId>  MD_BOT=<botId>  MD_TOKEN=<JWT>
python3 scripts/md_client.py          # 先看场景树、测试集、消息历史变量 id
```

```python
from md_client import MiaodongClient, build_case, client_from_env
from audit_cases import audit, reconcile_scenario_tree

c = client_from_env()
HIST = c.message_history_id()          # per-bot，禁止硬编码

cases = []
for i, row in enumerate(rows, 1):      # ← 这段是领域逻辑，按你的数据改
    cases.append(build_case(
        name=f"{scene}_{i:03d}#第{i}行",          # 唯一 + 带溯源
        trigger_type="receive-image-message",
        trigger_inputs={"imageUrl": row.img},
        dimension=scene,
        history=[{"role": "user", "content": row.text}],   # 上下文都进 history
        history_var_id=HIST,
        expect="Bot 应识别图片并给出合理回复,不强制具体文案",
        scenario=scene,                                     # 场景名，用于 attach
    ))

rep = c.import_test_set("我的测试集", cases)
audit(c, rep["testSetId"], cases)
reconcile_scenario_tree(c, expected_total=len(cases))
```

## 建模：什么进 `triggerInputs`，什么进 history

`triggerInputs` 只放**触发这一轮的那条消息**，此前的所有上下文进 history。

IM 里文字和图片是**两条独立消息**（靠输入缓冲区事件聚合），所以用户先说的话属于历史，
不要塞进 `triggerInputs.text`——那个字段只表示图片自带的说明文字（caption）。
一行数据里有 N 张图 + 一段文字时：最后一张图作触发输入，文字和前 N-1 张图按时间序进 history，
history 里的图片直接放**裸 URL 字符串**。

`triggerInputs` 的字段随 `triggerType` 变（21 种，无统一 schema）。**别猜字段名**——
在 UI 手工建一条同类型用例，读 `test-case/list` 抄回来的结构，只替换业务值。

## 常见错误

- **拿 `agent-changes` 当数据源** —— 那是 agent 会话的临时 diff，会话结束恒为空。用 `scenario/cases`。
- **以为 `/test-case/import` 能导 Excel** —— 它是从画布执行历史导入，参数是 `canvasExecIds[]`。
- **场景树重复挂载** —— 场景树是 bot 级共享的，重复导入同一批数据会让 `ownCaseCount` 翻倍，回归会跑重复用例。导入前先看计数，导入后对账。
- **删除顺序反了** —— 先 `batch-delete` 用例再 `test-set/delete`，否则场景树留孤儿计数。删前先把 `test-case/list` 结果存成 JSON 备份，用例删了不可恢复。
- **在生产 bot 上直接全量导** —— 先建一个临时测试集灌 1–2 条，回读确认字段没被丢，再全量。验证完删掉临时集。
