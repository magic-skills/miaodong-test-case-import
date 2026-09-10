# 秒懂测试用例数据结构

> 实测环境：X 区 `<你的秒懂控制台域名>`，前端 `1.18.4`，2026-09-10，1075 条真实用例验证。
> 字段可写性来自服务端 400 校验报错 + 写入后回读比对，不是猜的。

## 1. 完整字段

`GET /test-center/test-case/list?testSetId=..` 或 `/test-center/scenario/cases?scenarioNodeId=..`
返回 `{code, data:[...], page:{current,pageSize,total}}`，每条：

```json
{
  "testCaseId": "0a1b2c3d-0000-4000-8000-000000000001",
  "orgId": null,
  "testSetId": "0a1b2c3d-0000-4000-8000-000000000002",
  "name": "纯图片消息-单图_002",
  "dimension": "纯图片消息-单图",
  "dimensionDetail": "源表第2行",
  "scenarioNodeId": "0a1b2c3d-0000-4000-8000-000000000003",
  "scenarioPath": "图片消息识别与回复/纯图片消息-单图",
  "triggerType": "receive-image-message",
  "triggerInputs": { "imageUrl": "https://.../a.jpg" },
  "sessionMemoryCustomData": {},
  "pluginMockOutputs": [],
  "sqlDbMockOutputs": [],
  "testNodeOutputAssertions": [],
  "canvasActionOutputAssertions": [ /* 见 §5 */ ],
  "status": "ready",
  "isReviewed": true,
  "isStrictVerify": false,
  "rootCaseId": null,
  "sourceCaseId": null,
  "previousCaseId": null,
  "generatedCaseId": "0a1b2c3d-0000-4000-8000-000000000004",
  "revisionCount": 0,
  "createdBy": "<userId>",
  "createdAt": "2026-09-10T07:18:16.414Z",
  "updatedAt": "2026-09-10T07:18:16.414Z",
  "triggerContent": {
    "triggerType": "receive-image-message",
    "content": { "imageUrl": "https://.../a.jpg", "text": "" }
  }
}
```

## 2. 字段可写性（写入前必读）

| 类别 | 字段 | 说明 |
|---|---|---|
| **必填** | `triggerType`、`triggerInputs`、`sessionMemoryCustomData`、`testNodeOutputAssertions`、`canvasActionOutputAssertions` | `create` 强制校验，缺一个报 400。空值也要显式给 `{}` / `[]` |
| **可选、真正写入** | `name`、`dimension`、`isStrictVerify`、`pluginMockOutputs`、`sqlDbMockOutputs` | |
| ⚠️ **传了会被静默丢弃** | `scenarioNodeId`、`dimensionDetail` | 见下 |
| **服务端只读** | `testCaseId`、`orgId`、`status`、`isReviewed`、`rootCaseId`、`sourceCaseId`、`previousCaseId`、`generatedCaseId`、`revisionCount`、`createdBy`、`createdAt`、`updatedAt`、`triggerContent`、`scenarioPath` | 别传 |

**`scenarioNodeId`**：`create`/`update` 都丢弃，落库为 `null`。必须创建后再调
`POST /test-center/scenario/attach-cases {botId, testCaseIds[], scenarioNodeId}`。

**`dimensionDetail`**：`create`/`update` 都丢弃，落库为 `""`。Agent 生成器走内部路径能写，公开接口不能。
**要留数据溯源信息（源文件第几行等），写进 `name`** —— `name` 可写，且在用例列表页直接可见。

**`name` 必须在同一测试集内唯一**：`create` 只返回 `{"code":0}`，不返回 `testCaseId`；要拿 id（挂场景必需）只能创建后回读按 `name` 匹配。

**`status` / `isReviewed`**：接口创建的默认就是 `ready` / `true`，与 Agent 生成的一致，可直接进回归。不必额外审核。

## 3. `triggerType`（21 个，服务端权威枚举）

```
input                              receive-text-message
receive-image-message              receive-audio-message
receive-video-message              receive-file-message
receive-other-message              receive-intent-comment
receive-note-message               receive-share-note-comment-message
receive-email-message              custom-attr-event
tag-event                          join-room
new-friend                         canvas-event-trigger
bot-receive-text-message           write-message
contact-lead-filled                wecom-contact-bind
```

来源：给 `create` 发一个非法 `triggerType`，400 报错会把完整枚举列出来。这是探测枚举最快的办法。

## 4. `triggerInputs` —— 结构随 `triggerType` 变

`triggerInputs` 就是给该触发器的**输出字段**赋值。不同触发器字段完全不同，**没有统一 schema**。

### 4.1 拿到确切结构的可靠办法（推荐，100% 准确）

> 在 UI 上手工建一条该类型的用例 → `GET /test-center/test-case/list?testSetId=..`
> → 抄回来的 `triggerInputs`，只替换业务值。

猜字段名会静默失败（多余字段被丢弃，缺字段可能触发不了画布），别猜。

### 4.2 已知触发器字段表

证据等级：**[实测]** = 1075 条真实用例验证；**[双源]** = 前端 `registerNode` chunk 与
《秒懂 JSON结构规范》手册独立吻合；**[手册]** = 仅《JSON结构规范》第四章（该手册自述已与官方 Open API 交叉验证）。

**公共字段**（消息类触发器共有）：
`roomId`(可空)、`contactId`(必填)、`receiverId`(必填)、`messageId`、`isCoworker`(bool)、
`contactTags`(tag)、`senderName`。

| triggerType | 特有/完整字段 | 证据 |
|---|---|---|
| `receive-image-message` | 公共 + **`imageUrl`**(必填, type=`image`)、`imageUrls`(数组)、`text` | [实测] |
| `receive-text-message` | `roomId`、`contactId`、`receiverId`、**`text`**(必填)、`messageId`、`isCoworker`、`mentionSelf`、`mentionCoworker`、`mentionCustomer`、`isMentionAll`、`contactTags`、`senderName`、`quoteMessageId` | [双源] |
| `receive-audio-message` | 公共 + **`audioUrl`**(必填, type=`audio`) | [手册] |
| `receive-video-message` | 公共 + **`videoUrl`**(必填, type=`video`) | [手册] |
| `receive-file-message` | 公共 + **`fileUrl`**(必填)、`text` | [手册] |
| `receive-other-message` | `roomId`、`contactId`、`receiverId`、**`rawContent`**(必填)、`messageId`、`isCoworker`、`contactTags`、`senderName` | [手册] |
| `receive-email-message` | `fromAddress`、`toAddress`、`subject`、`text`、`html`、`attachments`、`contactId`、`receiverId`、`messageId`、`quoteMessageId` | [手册] |
| `tag-event` | **`tagId`**(必填, type=`tag`)、**`operation`**(必填, `"ADD"`/`"REMOVE"`)、`contactId`、`receiverId` | [双源] |
| `new-friend` | `contactId`、`receiverId` | [手册] |
| `canvas-event-trigger` | `receiverId`、`contactId` + 该事件自定义的 `variables` | [手册] |

⚠️ 媒体字段的 `type.type` 是媒体关键词（`image`/`audio`/`video`），不是 `string`。

以下触发器还会自动带企微身份字段 `externalUserId` / `wecomUserId` / `imBotId`：
`receive-text/image/audio/video/file/other-message`、`tag-event`、`new-friend`、
`bot-receive-text-message`、`custom-attr-event`。

**剩余 11 种**（`input`、`receive-intent-comment`、`receive-note-message`、
`receive-share-note-comment-message`、`custom-attr-event`、`join-room`、
`bot-receive-text-message`、`write-message`、`contact-lead-filled`、`wecom-contact-bind`）
没有可靠来源，按 §4.1 探测。

**`triggerContent` 是回显**：服务端从 `triggerType` + `triggerInputs` 归一化生成，会把 `text` 补成 `""`，即使你没传。别拿它当输入。

## 5. `sessionMemoryCustomData` —— 多轮历史藏在这里

**没有 `history` 字段。** 会话上下文和自定义会话变量都写在这个 map：

```
{ "<会话属性变量的 UUID>": <该变量的值> }
```

「消息历史」是系统默认会话属性（`isDefault: true`），类型：

```json
{"type":"array","items":{"type":"object",
 "properties":{"role":{"type":"string"},"content":{"type":"string"}}}}
```

```json
"sessionMemoryCustomData": {
  "0a1b2c3d-0000-4000-8000-0000000000ff": [
    { "role": "user", "content": "老师这个动作对吗" },
    { "role": "user", "content": "https://xxx.com/a.jpg" }
  ]
}
```

**这个 UUID 是 per-bot 的，禁止硬编码跨 bot 复用。** 每次先调
`GET /session-memory/list?botId=..&orgId=..`，找 `name === "消息历史"` 取 `id`
（`md_client.message_history_id()` 就是干这个的）。同一个 map 里也可以塞业务变量
（`nickname`、各种标识位……），key 同样是该变量的 UUID。

历史里的图片**直接放裸 URL 字符串**，不要包成 `{"type":"image","url":...}`。

## 6. 断言

### 6.1 `canvasActionOutputAssertions`（校验 Bot 的输出动作）

每个元素**同时带 `verifyPayload` 和 `actionContent` 两份，内容重复**——
`actionContent.payload` = `verifyPayload` 去掉 `type`。两份都要给，照抄。

```json
{
  "verifyPayload": {
    "type": "send-text-message",
    "text": { "verifyType": "llm", "description": "Bot 应识别图片并给出合理回复,不强制具体文案" }
  },
  "actionContent": {
    "type": "send-text-message",
    "payload": { "text": { "verifyType": "llm", "description": "同上" } }
  }
}
```

| `verifyType` | 配套字段 | 用途 |
|---|---|---|
| `llm` | `description` | 自然语言判定，适合开放式回复 |
| `similarity` | `value` + `threshold`（如 `0.9`） | 语义相似度 |
| `equal` | `value` | 严格相等 |

`type` 是画布动作类型。可选值（来自《JSON结构规范》第三章动作节点表）：

```
send-text-message   send-image-message   send-combination-message   send-audio-message
send-material       tag-user             invite-room                canvas-event-action
update-data         update-custom-attr   handover                   plugin-action
```

⚠️ **断言的字段名 ≠ 画布节点的配置字段名。** 断言校验的是**运行时实际输出**：
`send-text-message` 的画布节点配置字段叫 `template`，但断言里实测是 **`text`**。
所以其他动作类型的断言字段（如 `send-image-message` 是不是 `imageUrl`）**不能从画布节点结构推**，
必须按 §4.1 在 UI 建一条同类断言再抄。实测样本仅覆盖 `send-text-message` + `text`。
顶层 `isStrictVerify`（布尔）控制整条用例是否严格校验。

### 6.2 `testNodeOutputAssertions`（校验画布中间节点的输出）

必填但可以是 `[]`。1075 条实测样本里全为空，未取到真实形态。
测试集的 `testNodes` 字段里有对应结构（`{nodeId, outputTests:[{verifyType, output:{name,type}}]}`），
要用先在 UI 配一条再抄。

## 7. 场景树

```
GET /test-center/scenario/tree?botId=..&orgId=..
```

节点：`id`、`name`、`description`、`path`（`父/子`）、`source`（`agent` = AI 建的）、
`excluded`、`ownCaseCount`（挂本节点的）、`totalCaseCount`（含子节点）、`ranCount`、`passedCount`、`children`。

场景树是 **bot 级共享**的：不同测试集的用例会挂到同一批节点上，`ownCaseCount` 会累加。
导入新批次前先看一眼各节点计数，导完对账（各节点之和 == 本次导入总数，否则说明有旧批次重复挂着）。
