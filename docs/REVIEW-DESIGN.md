# A股每日主线热度复盘 — 设计说明（交工程师）

## 目标
每天 A股交易日 **17:00（Asia/Shanghai）** 自动生成一份「主线热度复盘」类收盘报告，观感对齐用户样例（2026-08-28 主线热度复盘），并发布到 GitHub：

- 仓库：`SparrowRick/Information-feed`（公开）
- **新文件**：`review-feed.json`
- 归档：`archive/review/YYYY-MM-DD.json`
- Schema：`schema/review-feed.schema.json`
- 服务器爬取：`https://raw.githubusercontent.com/SparrowRick/Information-feed/main/review-feed.json`

## 严禁
- **禁止覆盖/改写** 现有盘前工程：`feed.json`、`config.json`、`sources.json`、`schema/feed.schema.json`、`scripts/feed_tool.py`、`scripts/sync_feed.py`、`docs/*`（盘前相关）、根 `README.md` 主体内容等用户已改文件。
- 若需在 README 提及复盘，只**追加**一小节，或另写 `docs/REVIEW.md`，不要重写盘前说明。
- 不要把复盘条目混进 `feed.json`。

## 数据源
- **主**：HiThink Financial-API（同花顺）`https://fuyao.aicubes.cn`
  - Key：环境变量 `HITHINK_FINANCE_API_KEY`；若空，可从 `/home/box/sand-data/box-secrets.json` 的 `secrets.HITHINK_FINANCE_API_KEY` 读取。**禁止打印 Key。**
  - 已验证可用：calendar、prices snapshot、special-data 系列。
  - 重点接口：
    - `/api/a-share/calendar/trading-days`
    - `/api/a-share/prices/snapshot`
    - `/api/a-share/special-data/limit-up-pool`
    - `/api/a-share/special-data/limit-up-ladder`
    - `/api/a-share/special-data/limit-down-pool`
    - `/api/a-share/special-data/limit-break-pool`
    - `/api/a-share/special-data/anomaly-analysis-list`
    - 指数/板块：`/api/a-share-index/...`（按官方 docs）
- **辅**：问财（iwencai）仅补概念归因等；能用 HiThink 的 `limit_up_reason` 就不要强依赖问财。

## 报告结构（对齐样例，MVP）
生成 markdown + 结构化 JSON，尽量覆盖：
1. 标题 + 一句话总览 + 核心矛盾
2. 盘面开关：指数均涨跌、成交额及环比、涨跌家数、涨停/炸板/跌停、炸板率、名义连板高度 / 真实高度
3. 昨主线今日结账（加强/走弱/证伪）
4. 连板生死簿：名义 vs 真实高度代表、低位强首板
5. 行业/概念切换表（涨跌、资金强度若可得、资格状态）
6. 风险警示
7. 次日 2–3 个互斥情形
8. 数据审计：数据截止时间、来源、生成时间

「真实高度」MVP 规则（可后续精修）：排除 ST；连板天数高但换手过高/开板次数过多的标的降权或剔除出真实高度（样例逻辑：深中华A 名义7板因高换手/多次开板不计入真实高度）。封单额、换手等字段能拿到就用。

## review-feed.json 约定
```json
{
  "schema_version": "1.0",
  "updated_at": "...+08:00",
  "latest_review_id": "review-YYYY-MM-DD",
  "items": [ { "id": "review-YYYY-MM-DD", "type": "review", ... } ]
}
```
- 新条目插到 `items` 最前；保留最近约 30 期。
- 同日重跑更新同一 `id`，不堆重复。
- 另存 `archive/review/YYYY-MM-DD.json` 完整一期。

## 工程交付物
优先用 **Grok Build / Codex / Cursor cloud agent** 完成，控制本对话 token：
1. 可运行的 Python 管线（建议放在仓库新目录，如 `review/` 或 `scripts/review_*.py`，只新增）
2. `schema/review-feed.schema.json`
3. CLI：`python -m review.build --date YYYY-MM-DD`（默认上一交易日或当日收盘后）
4. 发布：用已连接 GitHub（SparrowRick）**只提交新增/更新的 review 相关文件**
5. README/文档：`docs/REVIEW.md` 说明 raw URL 与字段
6. 本地跑通至少一期样例（可用最近交易日）

## 验收
- 非交易日跳过
- 输出观感接近样例（主线/结账/连板/行业/次日情形）
- `review-feed.json` raw 可被服务器单独拉取
- 盘前 `feed.json` 内容与 sha 不被误改
