# 盘前简报生成规则

用户已授权在 SparrowRick/Information-feed 的 main 分支发布每日 A 股盘前 feed。面向 1—5 个交易日的短期交易，全市场筛选，无固定行业或自选股。北京时间 08:00 启动，目标 08:30 前可读。只在 A 股交易日发布。不要恢复其他每日简报、晚班巡场或再通胀任务。

## 每次执行

1. 从 GitHub 读取本文件、config.json、sources.json、schema/feed.schema.json、feed.json、scripts/feed_tool.py，以及覆盖本次前后五个交易日的 calendar/YYYY.json；需要回溯时读 archive 中最近五个交易日的原版。按仓库目录结构保存校验脚本和日历，以便直接运行。不要依赖上次运行的本地文件。读取最新 main 的 commit 和 tree，避免覆盖并发更改。
2. 查阅上交所/深交所当年休市安排与最近临时休市公告；核实今天是否交易日。周末调休上班不等于证券交易日。calendar 文件仅在其覆盖期内作为已核实的基础，新的或超出覆盖期的安排须查官方原文后更新。休市静默结束，不改变 feed.updated_at；无法确定则明确报告失败并保留上一期。
3. 每次运行以实际采集结束时刻为截止，最晚 08:20，不能把尚未到达的 08:20 填进 cutoff_at。优先检索上一交易日收盘至截止时刻的新信息；如前期断档，补查遗漏的重要事件并注明首次发布时间。节后覆盖整个休市期。盘中已公布的信息可以入选，但必须写清楚当时已发生的价格反应。
4. 用联网搜索发现线索，打开原文核实。先扫公告、政策、国内财经快讯，再补海外与事件日历。看到搜索日期与原文不一致，以原文为准；搜索摘要不能单独支撑价格、公告数字或发布时间。不得把旧闻当成新消息。
5. 查昨日 A 股市场与相关板块表现。先用固定的可信行情来源；没有稳定接口时允许引用带日期、时点、口径的可信收盘报道，必须在 coverage.gaps 说明获取方式及缺项。核对隔夜市场的实际交易日，遇海外休市，不生成不存在的昨夜涨跌。现货/期货、在岸/离岸、盘中/收盘不可混用。无法取得可靠行情就留空，不填 0、不估算。禁止生成尚未发生的当日竞价、开盘、收盘表现。
6. 合并同一事件，优先选择真正新增且与未来五个交易日相关的变化。一般 3—5 条，没有足够重要消息可少写。不得用多年规划目标冒充近期订单、用研究预测冒充实际数据、用市场传闻冒充公告。风险事件和利好按重要性共同排序。
7. 生成一份 version=2 的 premarket 对象，字段按 schema/feed.schema.json 和脚本样例。正文 overnight + today.why + review.what_happened + calendar.why 目标 600—1000 字；其他细节用于网页展开。自然、具体、克制，不写“开盘易被资金扫一眼”“有望全面提振”等空话，不机械重复“事实/判断/A股映射”。
8. 调用 scripts/feed_tool.py validate/merge 做结构、来源引用和时间校验。一次 Git commit 同时写 feed.json 和 archive/YYYY-MM-DD.json，并保留原有历史条目（含 patrol）。同日已存在的归档不覆盖，避免重跑改变盘前判断；修订另存 archive/YYYY-MM-DD.revision-时间.json，需显式说明修正内容和原版引用。
9. 更新 main 必须使用非强制快进。冲突时重新读取最新 feed 和 base commit、重新合并校验，最多重试两次。成功后重新读取 main 的归档核对 id、生成时间与内容，再报告提交链接。GitHub 报错或权限失败必须说明，不能声称已上传；不要降低校验要求来发布。

## 内容字段

- overnight：约 100 字，今天最主要的影响因素、隔夜变化和不确定性。用 overview_source_ids 指向依据。
- market_snapshot：有把握的数字才填，包含 name、value、unit、as_of、session 和 source_ids。change_pct 可为 null；债券收益率变化若写，用 bp 单位，不能混同百分比。market_note 解释指标缺失或休市。
- today：最多五条。title 和 why 供旧页面直接读取。what_changed 写新增事实；priced_in 写截至截稿时已知的市场反应，缺行情明确说无法判断；watch 写接下来要验证的条件；invalidates 写会削弱该判断的证据。kind 为 catalyst/risk；novelty 为 new/update/known。sectors 为直接相关行业，companies 最多三家，必须有代码、交易所、业务关系及来源；关系无法核实就不列公司。不得给出保证涨跌、未经计算的预期收益率或伪精确评分。
- 每条事件 id 使用稳定、唯一、可读的英文/数字短名；follow_until 为第五个后续交易日，用交易日历计算。
- review：对前一/三/五个交易日归档中的判断做跟踪，最多两条。原文逐字引用，original_report_id + original_event_id 可以定位。区分消息是否兑现与股价是否上涨；相关性不证明因果。没有符合条件的记录时留空并解释。旧版无来源的记录不能据此评“命中”。本次回溯样稿不得被未来复盘计入实时判断表现。
- calendar：未来五个后续交易日内的重要日程，最多三条；精确时间用北京时间。只确定日期则 scheduled_at=null、time_precision=day；标明不确定性，不把待公布的数据写成已公布。
- sources：每个引用有 id、原文标题、URL、发布者、类型、retrieved_at、published_at（可空）、published_date（可空）、time_precision、timing_note。只有日期不得编造整点时间。只有当天日期且采集发生在截稿后，不能证明盘前可见，不可单独支撑新闻。静态日历或用于补充核实的公告可设 reference_only=true，并在 timing_note 解释限制；每条新闻仍须至少一个已证明在截稿前公开的非 reference_only 来源。不得用该标记收录截稿后新消息。
- coverage.status：complete 或 partial，gaps 列出无法核实的关键数据、未取得的来源、回溯限制。只有检索和数据均充分才用 complete；重要消息完全无法核实则不发布。

## 时间与归档

所有时间使用带 +08:00 的 ISO 8601，并填 timezone=Asia/Shanghai。generated_at 是实际生成时刻；updated_at 是本次 feed 更新时刻；target_publish_at 固定该交易日 08:30，不能当作真实生成时间。cutoff_at 不晚于实际生成或当日 08:20。

09:00 后启动或完成的运行不得装作当日实时盘前：自动任务应保留此前已发布版本，明确报告延迟；用户明确要求补发/样稿时可用 edition=retrospective，title 和 overnight 均标注“盘前回溯样稿”，新闻仍须证明截稿前公开。回溯不具备严格历史网页快照，不作为回测样本。

初次发布保留旧 feed 原文于 archive/legacy-feed-2026-09-04.json。所有历史原文不改写。feed 持续保留历史项目；后续体积需要调整时先确保归档完整并明确记录保留策略，不能自动悄悄删除历史。

## 发布操作（GitHub 连接器）

用 git/ref/heads/main 得到 commit；用 git/commits/{sha} 得到 tree.sha（不要把 commit SHA 当作 tree SHA）。create_tree 基于原 tree，用 content 写入修改后的文本；create_commit 的 parent_sha 为刚读到的 main；update_ref(main, force=false)。缺工具时发现对应 GitHub 能力，禁止凭工具名称猜成功。优先一个 commit 发布整组文件。

手工测试命令：

```bash
python scripts/feed_tool.py validate feed.json
python scripts/feed_tool.py merge archive/2026-09-08.json --feed feed.json --archive-dir archive --check
python -m unittest discover -s tests -v
```

以上 2026-09-08 仅为已提交的样稿例子，日常运行必须使用当日日期。
