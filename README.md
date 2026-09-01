# Information-feed

投研台快报。服务器只爬这一个文件即可。

## 拉取地址

```
https://raw.githubusercontent.com/SparrowRick/Information-feed/main/feed.json
```

提交记录 Atom（可选）：

```
https://github.com/SparrowRick/Information-feed/commits/main.atom
```

## feed.json

`items` 新的在前。`type` 目前两种：

- `premarket`：工作日 8:00 A 股盘前（隔夜一段话 + 今天最多 5 条）
- `patrol`：周日到周四 22:00 晚班巡场（最多 5 条边际）

```json
{
  "updated_at": "2026-09-02T08:00:00+08:00",
  "items": [
    {
      "id": "premarket-2026-09-02",
      "type": "premarket",
      "date": "2026-09-02",
      "timezone": "Asia/Shanghai",
      "overnight": "隔夜重点一段话",
      "today": [
        { "title": "标题", "why": "为什么今天要看" }
      ]
    }
  ]
}
```
