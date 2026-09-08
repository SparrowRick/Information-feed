# Grok bot → Grok Build（仅复盘）

盘前简报仍由现有 ChatGPT Work 任务生成，本 bot **不管盘前**。

```
交易日 17:00 Asia/Shanghai
  Grok bot（触发器）
    → 启动 Grok Build
    → Grok Build 按 docs/REVIEW-JOB.md 跑 python -m review.build --out .
    → 只提交复盘文件到 main
服务器稍后拉：
  https://raw.githubusercontent.com/SparrowRick/Information-feed/main/review-feed.json
```

## Bot 职责

Bot 只负责叫醒 Grok Build，并回报结果。

- 不要自己写复盘正文或填涨停家数。
- 不要改 `feed.json`。
- 无法启动 Grok Build 时直接报失败，不要降级成聊天生成。

Bot 提示词快照见 `automation/grok-review.json`。修改该 JSON 不会自动改已创建的 Grok 自动化，需在 Grok 任务管理里同步。

## Grok Build 环境

- 能访问 GitHub 仓库 `SparrowRick/Information-feed`（写 `main`）。
- 环境变量 `HITHINK_FINANCE_API_KEY`（或 box-secrets）。请求头是 `X-api-key`。
- Python 3.10+，标准库即可，无第三方包。

## 调度

周一至周五 17:00（Asia/Shanghai）。节假日也会触发，由 `review.build` 判断交易日并跳过或回退，bot 不必自己维护休市表。
