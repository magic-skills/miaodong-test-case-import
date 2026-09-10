# 秒懂测试中心接口契约

> 实测：某独立部署环境，前端 `1.18.4`，2026-09-10。
> 这是**控制台内部 API**，来源是前端 bundle，无稳定性承诺，升级后需重新核对。
> 秒懂分多个「区」(共用集群)和若干**独立部署**(单客户专属)，域名与版本各不相同，
> 同一套接口在不同环境未必都存在——先用 `capabilities()` 探测。目标域名向该客户的负责人确认。
> 秒懂对外的 Insight Open API（Apifox）**完全不含测试中心**，测试用例只能走内部 API。
>
> 触发器/动作字段另有一份独立来源：《秒懂 JSON结构规范》手册——那是**画布 JSON** 的规范
> （节点 data 结构），不是测试用例结构，但触发器节点的 `outputTypes` 正是 `triggerInputs` 该填的字段。
> 已交叉验证并并入 data-model.md §4.2。

## 1. 鉴权

```
POST/GET  <控制台域名>/api/<path>?orgId=<ORG_ID>&botId=<BOT_ID>
Header:   Authorization: Bearer <秒懂用户 JWT>
```

**只认 Authorization 头，不认 cookie。** 在已登录页面里 `fetch(url, {credentials:'include'})`
但不带该头，一律 `{"statusCode":401,"message":"Authentication failed"}`。

取 token：浏览器登录控制台 → Console 执行

```js
JSON.parse(localStorage.user).token
```

`orgId` 几乎所有请求都要带在 query 上（前端会自动补）。token 会过期，401 就重取。

## 2. 接口总表

| 用途 | Method | Path | 关键参数 |
|---|---|---|---|
| 场景树 | GET | `/test-center/scenario/tree` | `botId`,`orgId` |
| 场景下的用例 | GET | `/test-center/scenario/cases` | `scenarioNodeId`,`current`,`pageSize` |
| 测试集列表 | GET | `/test-center/test-set/list` | `current`,`pageSize` |
| 测试集内用例 | GET | `/test-center/test-case/list` | `testSetId`,`current`,`pageSize` |
| 会话属性列表 | GET | `/session-memory/list` | `botId`,`orgId` |
| 新建测试集 | POST | `/test-center/test-set/create` | body `{botId, name}` |
| 删除测试集 | POST | `/test-center/test-set/delete` | body `{testSetId}` |
| 批量新建用例 | POST | `/test-center/test-case/create` | body `{testSetId, testCases[]}` |
| 修改用例 | POST | `/test-center/test-case/update` | body `{testCaseId, ...全量}` |
| 批量删除用例 | POST | `/test-center/test-case/batch-delete` | body `{testCaseIds[]}` |
| **挂载到场景** | POST | `/test-center/scenario/attach-cases` | body `{botId, testCaseIds[], scenarioNodeId}` |
| 从画布执行历史导入 | POST | `/test-center/test-case/import` | body `{testSetId, canvasExecIds[], includeSessionMemory}` |
| 开始回归 | POST | `/test-center/test-task/regression-test` | 见旧版文档 |

分页返回 `{code, data:[...], page:{current,pageSize,total}}`；`pageSize` 实测可到 200。

## 3. 五个必踩的坑

### ① `create` 丢弃 `scenarioNodeId`
传了也白传，落库 `null`，场景树计数不变。必须创建后单独调 `attach-cases`。
返回 `{code:0, data:{attachedCount, scenarioPath}}`；不传 `scenarioNodeId` 时 `scenarioPath` 为空。
实测每批 100 个 id 可行，重复调用幂等。

### ② `create` 不返回 `testCaseId`
只返回 `{"code":0}`。要拿 id（挂场景必需）**只能创建后回读 `test-case/list` 按 `name` 匹配**
——所以 `name` 在同一测试集内必须唯一。

### ③ `create`/`update` 丢弃 `dimensionDetail`
落库恒为 `""`。Agent 生成器走内部路径能写，公开接口不能。
溯源信息（源文件第几行）写进 `name`。

### ④ `update` 是全量覆盖，不是 merge
未传的可写字段被清空——实测漏传 `name` 会把用例名写成空字符串。
改一个字段也要回传完整对象。好消息：`update` **不会**清掉已挂载的 `scenarioNodeId`。

### ⑤ Agent Test Lab 的会话流走 WebSocket
左侧会话列表、agent 思考/工具调用过程抓不到任何 HTTP 请求。
`/test-center/test-case/agent-changes?sessionId=..` 只是**本轮 agent 的临时 diff**，
会话结束后恒为 `{turns:[]}`——不是数据源，别拿它做导出。要用例数据走 `scenario/cases` 或 `test-case/list`。

## 4. `/test-case/import` 不是"导入文件"

名字有误导性。它的 body 是 `{testSetId(UUID), canvasExecIds[](UUID), includeSessionMemory(bool)}`
——**从画布的历史执行记录转成用例**。想从 Excel/外部数据灌用例，走 `create`。

## 5. 探测未知契约的两个技巧

**空 body 探必填字段**：`POST` 一个 `{}`，400 报错会列出全部必填字段名和类型；
非法枚举值会把完整枚举列出来。无副作用，不落库。

**探接口是否存在**：404 = 路径不存在，400 = 存在但参数不对。用这个快速试错路径名。

## 6. 回滚

```
POST /test-center/test-case/batch-delete  {testCaseIds[]}   # 先删用例
POST /test-center/test-set/delete         {testSetId}       # 再删测试集
```

顺序反了会在场景树上留下孤儿计数。实测按此顺序删除后 `ownCaseCount` 同步回落，无残留。
删之前先把 `test-case/list` 的完整结果存成 JSON 备份——用例删了不可恢复。
