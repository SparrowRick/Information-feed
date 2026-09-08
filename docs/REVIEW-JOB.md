# Grok Build 复盘任务卡

Grok bot 每次只把本文件交给 Grok Build。Grok Build 是唯一写手；bot 不编数字、不改盘前 feed。

仓库：`SparrowRick/Information-feed`，分支 `main`。每次从 GitHub 最新提交开始，不依赖本机旧状态。

最终供服务器拉取的是**润色后**的 `review-feed.json`。数字以脚本为准，文案由 Grok Build 按数据改写。

## 禁止

- 不要改盘前文件：`feed.json`、`config.json`、`sources.json`、`schema/feed.schema.json`、`scripts/feed_tool.py`、`docs/EDITORIAL.md`、`archive/YYYY-MM-DD.json`（盘前归档）。
- 不要手填涨停、炸板、成交额、晋级率等数字；必须先跑仓库 Python 管线。
- 不要打印 `HITHINK_FINANCE_API_KEY`。
- 不要把复盘条目写入 `feed.json`。
- 润色时不要改锁定字段，不要编造主力净流入、资金强度、价资双正。
- `audit.gaps` 写了缺的，正文只能承认缺失，不能假装有。
- 产业线按资格规则，不硬凑两条。

## 步骤

### 1. 拉数（唯一数据源）

1. 工作目录设为仓库根。
2. 确认 `HITHINK_FINANCE_API_KEY` 已在环境或 box-secrets 中。没有 key 就停止并如实说明，不要编造复盘。
3. 运行：

   ```bash
   python3 -m review.build --out .
   ```

   默认取 Asia/Shanghai 最近已收盘交易日。非交易日由管线跳过或回退上一交易日，不要另造数据。
4. 从输出或 `review-feed.json` 的 `latest_review_id` 得到日期 `YYYY-MM-DD`。若管线打印跳过且没有新条目，到「成功回报」写「非交易日已跳过」并结束。
5. **立刻**复制润色前底稿，不要提交这个副本：

   ```bash
   cp archive/review/YYYY-MM-DD.json /tmp/review-raw.json
   ```

### 2. 润色（只动文案）

只改这些字段：`title`、`summary`、`core_conflict`、`market_switches`、`risks`、`markdown`。

其它一律不动，包括：`core_metrics`、`volume_day`、`yesterday_themes`、`incremental_branch`、`ladder`、`structure_rows`、`broken_high_boards`、`sector_rotation`、`industry_lines`、`rotation`、`event_themes`、`dragon_tiger`、`audit.gaps`、日期与 id。

怎么写：

- 对照脚本 JSON 里的事实，把模板句改成接近「主线热度复盘」样例的判断口吻：盘面状态（加强 / 混沌 / 退潮）、主线是否成立、资格线够不够。
- `markdown` 保留十一节标题和**表格数字原样**；可改节前节后的解释段落。
- `summary` 仍要包含指数、成交、非 ST 涨停/炸板/跌停、封板率、名义/真实高度。
- 缺数据就写缺，不要补资金数字。

同时改三处，内容一致：

- `archive/review/YYYY-MM-DD.json`
- `review-feed.json` 里同 `id` 的那一条
- `samples/review/YYYY-MM-DD.md`（= `markdown` 全文）

润色失败（写不顺、不确定）就**保持脚本原文**，不要为了文采卡住发布。

### 3. 校验

```bash
python3 -m review.check_polish \
  --raw /tmp/review-raw.json \
  --polished archive/review/YYYY-MM-DD.json \
  --feed review-feed.json \
  --out . \
  --mark
```

失败则：用 `/tmp/review-raw.json` 覆盖回 archive，不要提交改坏的数字，并报告校验错误。通过后 `audit.polished=true`。

### 4. 提交

1. 检查 git diff，允许的写入只有：

   - `review-feed.json`
   - `archive/review/YYYY-MM-DD.json`
   - `samples/review/YYYY-MM-DD.md`

   若出现盘前文件或其它路径，不要提交，先报告。不要提交 `/tmp/review-raw.json`。
2. 一次 commit，说明 `review: YYYY-MM-DD 主线热度复盘`。同日重跑覆盖同一 `id`，不堆重复条目。
3. 非强制快进更新 `main`。冲突则拉最新再提交，最多两次。
4. 推送后读回 `review-feed.json` 的 `latest_review_id`，确认与本次日期一致。

## 成功回报

只回报：交易日、`review-YYYY-MM-DD`、commit 链接、是否已润色（`audit.polished`）、summary 前 120 字。休市跳过时写「非交易日已跳过」。

## 失败

GitHub 权限、API key、接口 429、润色校验失败或校验不通过必须说明，不能声称已发布。
