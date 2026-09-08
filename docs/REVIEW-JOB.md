# Grok Build 复盘任务卡

Grok bot 每次只把本文件交给 Grok Build。Grok Build 是唯一写手；bot 不编数字、不改盘前 feed。

仓库：`SparrowRick/Information-feed`，分支 `main`。每次从 GitHub 最新提交开始，不依赖本机旧状态。

## 禁止

- 不要改盘前文件：`feed.json`、`config.json`、`sources.json`、`schema/feed.schema.json`、`scripts/feed_tool.py`、`docs/EDITORIAL.md`、`archive/YYYY-MM-DD.json`（盘前归档）。
- 不要手填涨停、炸板、成交额、晋级率等数字；必须跑仓库 Python 管线。
- 不要打印 `HITHINK_FINANCE_API_KEY`。
- 不要把复盘条目写入 `feed.json`。

## 步骤

1. 工作目录设为仓库根。
2. 确认 `HITHINK_FINANCE_API_KEY` 已在环境或 box-secrets 中。没有 key 就停止并如实说明，不要编造复盘。
3. 运行：

   ```bash
   python3 -m review.build --out .
   ```

   默认取 Asia/Shanghai 最近已收盘交易日。非交易日由管线跳过或回退上一交易日，不要另造数据。
4. 检查 git diff，允许的写入只有：

   - `review-feed.json`
   - `archive/review/YYYY-MM-DD.json`
   - `samples/review/YYYY-MM-DD.md`

   若出现盘前文件或其它路径，不要提交，先报告。
5. 一次 commit，说明 `review: YYYY-MM-DD 主线热度复盘`。同日重跑覆盖同一 `id`，不堆重复条目。
6. 非强制快进更新 `main`。冲突则拉最新再提交，最多两次。
7. 推送后读回 `review-feed.json` 的 `latest_review_id`，确认与本次日期一致。

## 成功回报

只回报：交易日、`review-YYYY-MM-DD`、commit 链接、summary 前 120 字。休市跳过时写「非交易日已跳过」。

## 失败

GitHub 权限、API key、接口 429 或校验失败必须说明，不能声称已发布。
