# A股盘前简报

运行状态与服务器接入进度见[实施状态](docs/STATUS.md)。

每天用三五分钟了解新增事件、此前市场反应及接下来需要验证的条件。面向 **1—5个交易日** 的短期交易，全市场筛选，无固定行业或自选股。

**服务器继续拉取原地址：**

[feed.json 原始数据](https://raw.githubusercontent.com/SparrowRick/Information-feed/main/feed.json)

## 运行方式

ChatGPT Work 定时任务在北京时间 **08:00** 启动，核实 A 股交易日，检索并生成内容，目标 **08:30前** 上传 GitHub。实际截稿时间是完成采集的时刻，最晚08:20；不保证整点到达。09:00后不再冒充当日实时盘前发布。周末、交易所休市日跳过，调休上班的周末也跳过。新闻源或GitHub失败时保留上一期并报告错误。

生成规则在 [docs/EDITORIAL.md](docs/EDITORIAL.md)，信息源入口在 [sources.json](sources.json)。每次任务重新从仓库读取规则和历史，不依赖本地会话记忆。旧的每日重点简报、再通胀任务不由本项目启用。

## 内容

| 模块 | 字段 | 说明 |
|---|---|---|
| 开盘前心里有数 | `overnight` | 约100字概括主要变化，含关键不确定性 |
| 行情概览 | `market_snapshot` / `market_note` | 数字带交易日、时点和来源；缺数据明确留空 |
| 今天值得盯 | `today` | 通常3—5条，不凑数；`title`、`why`兼容旧页面 |
| 最近判断跟踪 | `review` / `review_note` | 原版判断第1、3、5个交易日跟踪，最多2条 |
| 未来五个交易日 | `calendar` | 最多3项；只有日期就不编造时刻 |
| 依据与缺项 | `sources` / `coverage` | 原文链接、发布时间、采集时间及未核实内容 |

`today`的展开内容包括`what_changed`、`priced_in`、`watch`、`invalidates`、`sectors`、`companies`。公司最多三家，明确业务关系与来源；没有依据不列。

首版尚未接通专用行情API，使用带明确交易日和口径的可信报道/行情页；不会把它显示为实时行情。样稿缺少的数据已在`coverage.gaps`标注。

## 样稿与历史

- [2026-09-08 阅读版](samples/2026-09-08.md)
- [2026-09-08 JSON归档](archive/2026-09-08.json)
- [旧版原始feed备份](archive/legacy-feed-2026-09-04.json)

9月8日为开盘后制作的**盘前回溯样稿**，根据公开发布时间筛选08:20前的事件，不计入实时判断复盘或回测。没有严格的历史网页快照。

新数据采用`schema_version: "2.0"`，每期`version: 2`，保留`items`、`overnight`及`today[].title/why`。原有premarket/patrol历史保持原文。`latest_premarket_id`定位最新一期。前端应通过这个ID查找，或先按`type`过滤；不要把旧patrol当盘前。

每个交易日有唯一ID`premarket-YYYY-MM-DD`。同次提交同时更新feed与日期归档；同日重跑不新增重复项或改写原稿。历史保存于`archive`，修正应另存版本并说明。

时间均带`+08:00`：`generated_at`是真实生成时间，`cutoff_at`是信息截止时间，`target_publish_at`只是08:30的目标时间，不能用来宣称已在该时刻发布。

## 校验与服务器接入

脚本只依赖Python 3.10以上的标准库，无需API密钥。

```bash
python3 scripts/feed_tool.py validate feed.json
python3 -m unittest discover -s tests -v
```

每次生成一份新条目JSON后：

```bash
python3 scripts/feed_tool.py merge /tmp/new-premarket.json --feed feed.json --archive-dir archive
```

校验通过后，通过GitHub一次提交`feed.json`与对应`archive`。该脚本只准备本地文件；自动任务使用已连接的GitHub工具提交，不要求用户在仓库中保存Token。

服务器执行：

```bash
python3 scripts/sync_feed.py --output /path/to/site/data/feed.json
```

会同时生成`sync-status.json`，供网页显示“今日未更新”“回溯样稿”“拉取失败”等状态。下载失败、格式错误或收到旧版本时保留本地有效feed。详见 [服务器接入说明](docs/SERVER.md)。

正式接入后，网页只需读取服务器本地JSON，展示层无需每天重新部署。新增复盘/日历等模块需要页面读取对应新字段。

## 文件约定

| 文件 | 用途 |
|---|---|
| `config.json` | 时间、篇幅、条数及发布约定 |
| `calendar/2026.json` | 已核实的2026年交易所休市安排；每次运行补查临时公告 |
| `schema/feed.schema.json` | JSON结构合约；语义校验由`feed_tool.py`完成 |
| `scripts/feed_tool.py` | 校验、交易日计算、不可变归档、兼容合并 |
| `scripts/sync_feed.py` | 服务器下载、检查、原子替换和状态文件 |
| `deploy/` | 服务器systemd定时拉取模板 |
| `tests/` | 时间边界、休市、来源、原文保留和失败保护检查 |

新年度日历未核实时，程序明确失败，不能自动把所有工作日当交易日。生成任务应先查官方当年安排并更新日历。服务器使用的本项目代码和日历也需同步升级；如果只有旧日历，会保留现有数据并提示错误。
