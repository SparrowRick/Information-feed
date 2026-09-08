# A股每日主线热度复盘

每个 A 股交易日收盘后（目标 17:00，Asia/Shanghai）生成一份「主线热度复盘」。本目录只新增复盘管线，不改盘前 `feed.json`。

## 运行

```bash
# 在仓库根目录 SparrowRick/Information-feed 执行
python3 -m review.build --date 2026-09-08 --out .
python3 -m review.build --out .          # 默认：上海时区最近已收盘交易日
python3 -m review --date 2026-09-08 --out .
```

| 参数 | 说明 |
| --- | --- |
| `--date YYYY-MM-DD` | 指定交易日。非交易日不造假数据：默认回退上一交易日；若日历窗口内没有上一交易日则 exit 0。 |
| `--out DIR` | 输出目录，默认 `out`。 |
| `--dry-run` | 只计算，不写文件。 |
| `--skip-non-trading` / `--no-skip-non-trading` | 默认 true。 |

鉴权：请求头 `X-api-key`（不是 Bearer）。Key 读取顺序：环境变量 `HITHINK_FINANCE_API_KEY` → `/home/box/agent-data/box-secrets.json` → `/home/box/sand-data/box-secrets.json`。禁止打印 Key。

## 输出

- `review-feed.json`（`--out .` 时写到仓库根）：Feed，新条目插到 `items` 最前，保留约 30 期；同日重跑覆盖同一 `id`。
- `archive/review/YYYY-MM-DD.json`：单期完整 JSON。
- `samples/review/YYYY-MM-DD.md`（可选）：可读中文 markdown。
- 仓库根目录 `review-feed.json` 是空骨架；`schema/review-feed.schema.json` 是字段约束。

发布到 GitHub 后，服务器可单独拉：

`https://raw.githubusercontent.com/SparrowRick/Information-feed/main/review-feed.json`

## 数据源（HiThink Financial-API）

Base：`https://fuyao.aicubes.cn`

特殊数据接口的官方日期参数是 `date_ms`（上海时区当日 00:00:00 的毫秒戳）。实测 `trade_date=YYYY-MM-DD` 会被忽略并回到「当日」，因此本管线只用 `date_ms`。交易日历接口无入参，返回近一年交易日后在本地过滤。

| 用途 | 路径 |
| --- | --- |
| 交易日历 | `GET /api/a-share/calendar/trading-days` |
| 涨停池 | `GET /api/a-share/special-data/limit-up-pool` |
| 跌停池 | `GET /api/a-share/special-data/limit-down-pool` |
| 炸板池 | `GET /api/a-share/special-data/limit-break-pool` |
| 连板天梯 | `GET /api/a-share/special-data/limit-up-ladder`（已接 client，报告以涨停池计算高度为主） |
| 龙虎榜 | `GET /api/a-share/special-data/dragon-tiger-list`（席位净额，不是主力净流入） |
| 异动原因 | `GET /api/a-share/special-data/anomaly-analysis-list` |
| 全市场快照 | `GET /api/a-share/prices/snapshot`（分页；无历史日期，仅最新交易日可用） |
| 指数快照 / 历史 | `/api/a-share-index/prices/snapshot`、`/historical` |
| 同花顺板块目录 / 成分 | `/api/a-share-index/catalog/ths-index-list`、`/constituents/ths-stock-list` |

调用间隔 1–2 秒；遇到 HTTP/业务 429 指数退避重试。

## 真实高度 MVP

名义高度 = 当日涨停池 `continue_day_cnt` 最大值（含 ST）。

真实高度在名义样本上再过滤，满足任一条件则剔除 / 降权：

1. `is_st=true`，或简称可识别为 ST / \*ST。
2. `is_new=true`（未开板新股）。
3. `open_times >= 3`（字段来自炸板池或池内字段，有则用）。
4. `turnover_ratio_pct >= 30`（有则用）。
5. 连板天数 ≥ 5 且快照成交额 ≥ 20 亿（涨停池没有换手率时的保守代理，对应「高换手水分高度」）。
6. 封单/成交额 < 1% 且（开板次数 ≥ 3 或连板 ≥ 5）→ 伪强势，不计入真实高度。

涨停池通常不含 `open_times` / `turnover_ratio_pct`；开板次数来自炸板池，成交额来自快照，封单比「有则用」。样例逻辑：深中华 A 一类名义高位因多次开板 / 高换手 / 封单占比过低不计入真实高度。

封板率 = 非 ST 涨停 / (非 ST 涨停 + 非 ST 炸板) × 100。炸板率 = 1 − 封板率（同一口径）。晋级率 = 昨日非 ST 涨停中今日连板天数增加的比例。

## 主线 / 题材 MVP

把 `limit_up_reason` 按 `+`、`、`、`,`、`/` 切词，按连板高度加权计热度。昨日 Top 簇与今日簇对比：

- **加强**：今日该簇涨停数与热度不掉。
- **走弱**：仍有涨停但热度下降。
- **证伪**：今日无涨停接力且成员回撤。
- **分化**：部分成员继续涨停、部分转弱。

若 `review-feed.json`（`--out .` 时写到仓库根） 已有上一交易日条目，则复用其 `core_metrics.today` 作为今日的「昨日盘面」；否则用昨日涨停/跌停/炸板池 + 上证/深证指数历史成交额做轻量结账。异动列表的 `keyword_list` / `tag_name` 只作概念切换备注，不替代 `limit_up_reason`。

## Markdown 结构

1. 标题 + 一句话总览 + 核心矛盾
2. 盘面全貌（五指数、非 ST 涨停/炸板/跌停、封板率、晋级率、名义/真实高度）
3. 从上次放量日到今日
4. 核心指数、成交与情绪
5. 昨主线与重点观察结账
6. 当日最大增量分支
7. 连板生死簿与高低结构
8. 行业/概念与相对配置（价量；无主力净流入则不编）
9. 产业线深拆（资格线，0–2 条，不硬凑）
10. 最大轮动与被证伪方向
11. 其他涨停原因暗线
12. 风险警示

盘前预判结账暂不生成，等盘前 feed 稳定后再接。次日互斥情形与数据审计章节不写入正文；缺口记在 JSON `audit.gaps`。

产业线选择：

- **次主线候选**：昨日结账不是「证伪」的最强昨主线，且今日仍有涨停接力或成员未全面转负。
- **新方向候选**：当日最大增量分支，且热度上升并有原因匹配首板（或热度增量 ≥ 2）。
- 两者同名则合并为一条。事件标签（中报增长等）不能成为产业线。

## 非交易日

不生成假复盘。指定日不是交易日时打印说明并回退上一交易日；若无法回退则 exit 0。

## Grok bot

每个交易日 17:00（Asia/Shanghai）由 Grok bot **只负责叫醒 Grok Build**。Grok Build 按 [REVIEW-JOB.md](REVIEW-JOB.md) 先跑本管线，再按数据润色 `title` / `summary` / `core_conflict` / `markdown` 等文案，经 `python -m review.check_polish` 锁住数字后提交。服务器拉到的是润色后的 feed。盘前不在此任务内。说明见 [GROK-BOT.md](GROK-BOT.md)。
