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

## 报告结构（对齐样例，按批注裁剪）
生成 markdown + 结构化 JSON：
1. 标题 + 一句话总览 + 核心矛盾
2. 盘面全貌
3. 从上次放量日到今日
4. 核心指数、成交与情绪（非 ST 口径、晋级率、系统/真实高度）
5. 昨主线与重点观察结账
6. 当日最大增量分支
7. 连板生死簿与高低结构
8. 行业/概念相对配置（价量；无主力净流入则不编资金强度）
9. 产业线深拆：资格线 0–2 条（次主线候选 + 新方向候选，同名合并，不硬凑）
10. 最大轮动与被证伪方向
11. 其他涨停原因暗线
12. 风险警示

盘前预判结账等盘前 feed 稳定后再接。次日互斥情形、数据审计章节不写入正文。

「真实高度」规则：排除 ST / 未开板新股；开板次数过多、换手过高、或封单/成交额 < 1% 且高位多次开板的标的不计入真实高度。字段没有就跳过该条，不把成交额启发式误标成换手。

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
