# miaodong-test-case-import

一个可移植的 **Agent Skill**：把任意外部数据（Excel 行、聊天记录、线上日志…）批量变成
**秒懂 / JZ Insight 测试中心**里可跑回归的测试用例。**同一份源在 Claude Code 和 OpenAI Codex 两端通用**。

> 核心立场：**用确定性脚本生成用例，不要让 agent 逐条生成。**
> 分类和字段映射通常是机械规则，脚本能保证 1:1 全覆盖；agent 会漏。
> 实测同一份 427 行的表格，平台自带的 Agent 生成器产出 410 条（漏 17 行，另有 23 条分类不稳定），
> 确定性脚本产出 427 条零误差。agent 该做的是**写规则**，不是**执行规则**。

## 快速开始

```bash
bash scripts/install.sh          # 装到 Claude Code / Codex / ~/.agents（幂等，可反复跑）
pip3 install requests

# 登录控制台，进到目标智能体页面，打开浏览器 Console
export MD_BASE=https://<你的秒懂控制台域名>
export MD_BOT=<botId>            # 地址栏 /main/agents/<botId>/... 里那段 UUID
export MD_ORG=<orgId>            # JSON.parse(localStorage.user).currentOrg.id
export MD_TOKEN=<JWT>            # JSON.parse(localStorage.user).token

python3 scripts/md_client.py     # 打印目标智能体 / 场景树 / 测试集 / 「消息历史」变量 id
```

⚠️ **用例落在哪由 `MD_BOT` 决定**。弄错就会灌进别人的智能体，还会挂上那个 bot 的场景树、
污染它的回归集。所以 `import_test_set()` 每次都先打印目标智能体的名字，跑之前看一眼。

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

## 在 Claude Code / Codex 里用

装完重启会话即可：

| Runtime | 触发方式 |
|---|---|
| Claude Code | 描述需求自动触发（如「把这个 Excel 导成秒懂测试用例」），或打 `/miaodong-test-case-import` |
| Codex | `$miaodong-test-case-import`，或 `/skills` 里选 |

`install.sh` 用 symlink 装到三个位置（`~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`），
以后 `git pull` 一下就更新，不用重装。

## 凭证与多客户

**你交代「哪个区/客户 + 哪个智能体」；token 由同事本人提供（自己取，不能用你的）**
——JWT 里编着身份，转交等于共享账号，且会过期。

```bash
python3 scripts/md_client.py zones      # 12 个标准区 + 4 个独立部署，见 references/environments.md
MD_ZONE=X ...        # 或 MD_ZONE=兴趣岛 ...，代替 MD_BASE
```

```bash
# 拿全四个变量：打印一段 JS，在目标客户控制台的智能体页面 Console 里执行，
# 自动把 export MD_BASE=.. MD_ORG=.. MD_BOT=.. MD_TOKEN=.. 复制到剪贴板
python3 scripts/md_client.py bootstrap

# 存起来：之后同机的脚本 / Claude Code / Codex 都能直接读到（~/.miaodong/session, 600）
# agent 新开的 shell 不继承你终端的环境变量，这一步让你不必把 token 贴进对话
python3 scripts/md_client.py login
python3 scripts/md_client.py logout     # 用完或换客户

# 多客户：存成 profile（只存 base/org/bot，绝不存 token）
MD_BASE=.. MD_ORG=.. MD_BOT=.. MD_TOKEN=.. python3 scripts/md_client.py save 客户A
python3 scripts/md_client.py profiles
MD_PROFILE=客户A MD_TOKEN=<JWT> python3 scripts/md_client.py

# 交接给同事：发一个不含 token 的环境坐标串
python3 scripts/md_client.py share 客户A     # -> md-profile:eyJ...
python3 scripts/md_client.py adopt 'md-profile:eyJ...'
```

profile 存 `~/.miaodong/profiles.json`（权限 600，不在仓库里）。
`localStorage` 按域名隔离，换客户要重新取 token；报 401 就是过期了，重取。

## 换客户 / 换部署

秒懂多为私有部署，环境差异很大。换环境先跑 `python3 scripts/md_client.py`，
`capabilities()` 会探测目标属于哪一代：**新一代**有场景树（全流程可用），
**老一代**只有测试集+用例（`scenario/tree` 404）。

老环境下即使传了 `_scenario`，导入也会**降级跳过挂载而不是报错**，用例照常写入。

要重新取的（都别硬编码）：4 个环境变量、场景节点 id（`scenario_map()`）、
「消息历史」变量 id（`message_history_id()`，per-bot 且变量名可能不同）。

要重写的：**用例生成逻辑**（源数据 → `build_case()` 那段循环）是领域相关的。
导入 / 回读 / 挂场景 / 审计四步通用。

详见 `SKILL.md` 的「换客户 / 换部署」一节。

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
