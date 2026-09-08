# 服务器接入

生产端由ChatGPT Work定时检索、整理并提交GitHub。消费端只从公开仓库下载JSON，无需GitHub写权限。当前没有访问或修改用户服务器，本文件和deploy模板可直接用于接入。

## 最小接入

如果现有网站已读取原来的feed.json地址，旧的隔夜概况和重点新闻字段可继续使用。新加的行情、复盘、日历和来源需在前端读取相应字段。

服务器上的项目目录建议为`/opt/Information-feed`；可以克隆本仓库，或把`scripts`、`calendar`复制到同一项目目录。不要把下载的新闻JSON当作代码执行。

```bash
git clone https://github.com/SparrowRick/Information-feed.git /opt/Information-feed
python3 /opt/Information-feed/scripts/sync_feed.py --output /path/to/site/data/feed.json
```

将`/path/to/site/data/feed.json`替换为真实网站数据路径。执行用户须对该目录有写权限。脚本成功时退出0；错误时退出1并保留本地feed，同时写`sync-status.json`。最多立即重试三次，每次网络超时15秒。

脚本会拒绝：超过8MiB、JSON格式错误、不符合合约、时间在未来、比本地更旧、同一更新时间却内容不同的数据。会拒绝不在已核实日历内的版本，日历更新需要一并同步到服务器。

## 定时拉取

`deploy/information-feed.timer`使用明确的`Asia/Shanghai`时区，不依赖服务器系统时区。每周一到周五08:00—08:59每分钟拉取一次，09:00再拉取一次。休市日少量拉取也只会保留上一期并给出`market_closed`状态。

先修改`deploy/information-feed.service`里的`User`、`WorkingDirectory`、`ExecStart`，与网站实际目录和运行用户一致。确认手动拉取成功后，再安装模板：

```bash
sudo cp deploy/information-feed.service deploy/information-feed.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now information-feed.timer
systemctl list-timers information-feed.timer
```

查看执行结果：

```bash
journalctl -u information-feed.service -n 30 --no-pager
```

这里只安装数据拉取任务。生成任务在ChatGPT Work运行，目标08:30前提交；网页显示真实生成时间，不能写死“08:30已更新”。如果更换源地址，需要显式设置`--url`，只接受HTTPS。

## 网页呈现

| 条件/状态 | 页面文字 |
|---|---|
| 最新期`edition=retrospective` | 盘前回溯样稿，并显示真实生成时间 |
| `ready`且最新期为今天 | 今日盘前，显示信息截止时间及生成时间 |
| `awaiting_today` | 今日尚未更新；下方保留上一期日期 |
| `market_closed` | 今日休市；显示最近一期 |
| `sync_error` | 本次更新失败；显示最近成功时间和现有内容日期 |
| `calendar_unknown` | 交易日历待更新；保留现有内容日期 |
| `coverage.status=partial` | 部分资料未核实，可展开查看缺项 |

前端每次打开页面都应按北京时间检查最新期`date`，不能只依赖可能过期的status文件。`sync-status.json`的`checked_at`只代表服务器检查过，不能代表新一期已生成。数据文件可设较短缓存或使用条件请求；网络错误时不要用空数组覆盖页面。

展示新闻使用文本节点/转义输出；来源URL只渲染为普通外链。生产端只向JSON写简短事实概述、独立分析和来源链接，不提供付费新闻全文。

## 后续维护

日历覆盖2026年；新年度到来前同步官方日历和校验工具。如果当天有交易所临时调整，以最新公告更新。遇GitHub访问故障，脚本保留旧内容，日志会给出原因。来源、生成规则或格式更改后，先在本地执行测试，再更新服务器副本。
