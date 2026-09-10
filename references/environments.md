# 秒懂环境地图

> ⚠️ **内部部署拓扑与客户名单，勿外传。** 本仓库为私有仓库。

秒懂分两类环境，域名与平台版本各不相同，**同一套接口在不同环境未必都存在**。

## 标准区（12 个，多客户共用集群）

| 区 | 域名 |
|---|---|
| A | `insight.juzibot.com` |
| B | `lighthouse-insight.juzibot.com` |
| C | `echo-insight.juzibot.com` |
| D | `lantern-insight.juzibot.com` |
| E | `horizon-insight.juzibot.com` |
| F | `grove-insight.juzibot.com` |
| G | `fireside-insight.juzibot.com` |
| H | `glimmer-insight.juzibot.com` |
| I | `stride-md.dpclouds.com` |
| J | `journey-insight.juzibot.com` |
| X | `willow-insight.juzibot.com` |
| Z | `az-insight.juzibot.com` |

## 独立部署（4 个，单客户专属）

| 客户 | 域名 |
|---|---|
| 量子之歌 | `inkwell-insight.juzibot.com` |
| 有赞 | `petal-insight.juzibot.com` |
| 网易 | `cloudweave-insight.juzibot.com` |
| 兴趣岛 | `xlink-insight.juzibot.com` |

## 两个易错点

1. **`xlink-insight` 是「兴趣岛」的独立部署，不是「X 区」。X 区是 `willow-insight`。**
   光看域名分不出区还是独立部署——除了 I 区用 `dpclouds.com`，其余全是 `*-insight.juzibot.com`。
2. **版本不齐。** 独立部署与各区升级节奏不同：见过 I 区还是 `1.17.3`（旧测试中心，**无场景树**），
   而某独立部署已是 `1.18.4`（有 Agent Test Lab + 场景树）。别假设接口都在。

## 用法

不用记域名，直接给区代号或客户名：

```bash
MD_ZONE=X       ...    # 标准区，大小写不敏感
MD_ZONE=兴趣岛   ...    # 独立部署，用客户名
MD_ZONE=some-host.example.com  ...   # 含 "." 时按域名直传（新环境未收录时用）

python3 scripts/md_client.py zones     # 查全表
```

`MD_ZONE` 只解析出 `MD_BASE`。**`MD_ORG` / `MD_BOT` / `MD_TOKEN` 仍需各自提供**——
它们是每个企业、每个智能体、每个人各不相同的。

新增环境时改 `scripts/md_client.py` 顶部的 `STANDARD_ZONES` / `DEDICATED` 两个字典。
