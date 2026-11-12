# 兴趣雷达 · 参数目录（PARAMETERS）

> 参照 SurfCore-Life COVERAGE/PARAMETER-AUDIT 的治理思路整理（2026-11-02）。
> 目的：把雷达所有「可调的行为杠杆」列清楚——**归谁管、怎么生效、代码里到底有没有接线**。
> 权威口径：`charter.md` 为准；本文件是「参数地图」，两个运行时文件是唯一真值：
> - 运行配置：`state/config.json`（本文件不复制运行值，敏感项见该文件）
> - 规则口径：`state/charter.md` + 本仓库 `SKILL.md`

## 状态徽标

| 徽标 | 含义 |
|---|---|
| ✅ 已接线 | 代码确实读取（给出读取点），改 config 立即生效 |
| 📐 模型规则 | 不在代码里，真值在 SKILL.md/charter 文本，由模型执行 |
| ⚠️ 漂移 | 文档口径与实现/其他文档不一致，可能影响真实行为 |
| 💤 死配置 | config 里有键但全代码零引用，没人读 = 改了也白改 |
| 🔒 只读 | 代码常量或平台侧，不可配 |

## 权限分层（对齐 SurfCore-Life 的「自主/审批/只读」）

| 层级 | 谁 | 可动什么 |
|---|---|---|
| 维护者 | 老板 | 一切（含敏感项：频控上限、开关、白名单） |
| Agent 提议 | 我（爱莉希雅） | 可提议，**敏感项改动必须先经老板确认**；涉及账号安全/预算的默认不主动动 |
| 自动保护 | 代码 | 连续 3 次失败自动关闸、熔断、写冷却——不需要人管 |

---

## 总览（按生活场景分组）

| 组 | 参数数 | 已接线 | 模型规则 | 漂移 | 死配置 |
|---|---|---|---|---|---|
| A 平台互动（@ 主号推荐） | 9 | 4 | 1 | 2 | 2 |
| B 预算与阈值 | 9 | 0 | 4 | 1 | 4 |
| C 写操作闸（动态/私信/评论） | 14 | 14 | 0 | 0 | 0 |
| D 陌生人草稿审批 | 5 | 5 | 0 | 0 | 0 |
| E 评论区快筛 | 4 | 4 | 0 | 0 | 0 |
| F 调度与触发 | 4 | 3 | 1 | 0 | 0 |
| G 请求层（常量） | 4 | 4 | 0 | 0 | 0 |

**结论先行：38 个「生活中的」参数里，真正的死配置/漂移集中在 A、B 两组（共 9 处），C/D/E 三个安全相关组全部接线良好——安全闸比行为参数健康。** 详见下文明细与「问题清单」。

---

## A 组 · 平台互动（@ 主号推荐）— config `mention`

| 参数 | 运行值 | 权限 | 生效方式 | 状态 |
|---|---|---|---|---|
| `enabled` | true | 维护者/自动关闸 | 热加载 · 闸① | ✅ 接线（comment.py:49） |
| `name` / `mid` | 主号 | 维护者 | 热加载 · 闸① / notify | ✅ 接线（comment.py:48、notify.py:82） |
| `per_round` | 1 | 维护者 | —— | ⚠️ 漂移：SKILL.md 说「每轮 ≤1」（10-27 口径），**但代码闸没读它**（comment.py:63-74 只读 per_hour/per_day）；charter.md 39 行还停在 10-15 「每轮条数不限」——三处口径互不一致 |
| `per_hour` | 1 | 维护者 | 热加载 · 闸⑥ | ✅ 接线（comment.py:63）——当前实际由它兜底「每轮 ≤1」 |
| `per_day` | 0 | 维护者 | 热加载 · 闸⑥ | ✅ 接线（comment.py:64） |
| `min_score` | 17 | 维护者 | —— | 💤 死配置：全代码+tests 零引用；SKILL.md 只写「总分 ≥ min_score」**不写数值**——模型看不到 17，真值无人执行（实际生效的是 14，见 B 组） |
| `template` | 兜底文案 | 维护者 | —— | 💤 死配置：comment.py:80 用硬编码兜底「@{name} 这个值得看一眼」，template 从不被读 |
| `forbid` | 敏感词表 | 维护者 | 热加载 · 闸⑤ | ✅ 接线（comment.py:86） |
| 正文 ≤150 字 + 必须含 @ | —— | 代码 | 闸④ | ✅ 接线（comment.py:83-84，代码常量 🔒） |

## B 组 · 预算与阈值 — config `budget` + 打分规则

| 参数 | 运行值 | 权限 | 生效方式 | 状态 |
|---|---|---|---|---|
| `budget.max_subtitles_per_round` | — | 维护者 | —— | 🗑️ **B2 已删（2026-11-02）**：10-27 老板拍板「每轮字幕不限」后一直是死键，直接清除；历史注释保留在 config `_subtitle_note` |
| `budget.max_push_per_round` | 1 | 维护者 | —— | ⚠️ 漂移：config 是 1（10-27 老板拍板「每轮最多推 1 条」），但 **SKILL.md 第 9 步仍写「只推 0-3 条」且没写 1** → 模型看到的真值是 0-3，可能推超 1 条 |
| `budget.min_total_score` | 14 | 维护者 | —— | ✅ **B2 已接线（2026-11-02）**：`comment --score < 它` 会被代码拒发（硬闸）；日报最低分仍由 verify-params 对照 |
| 四维打分（相关/新奇/实操/新鲜 各 0-5） | —— | 模型规则 | 📐 | SKILL.md 76 + charter.md 18 |
| 新奇度 ≤1 直接砍 | —— | 模型规则 | 📐 | SKILL.md 76 |
| 粗筛 ≥8 条候选 | —— | 模型规则 | 📐 | SKILL.md 流程第 4 步（省 token 用，非硬闸） |
| 搜索默认 `--days 7 --order pubdate` | —— | CLI 默认 | 🔒 只读 | browse.py 参数默认 |
| 推送 0-3 条 / 0 条合法 | —— | 模型规则 | 📐 | SKILL.md 第 9 步（⚠️ 与 config=1 冲突，见上） |

## C 组 · 写操作闸（动态/私信/评论）— config `write`

**全部 ✅ 已接线**（安全闸最健康的一组）：

| 参数 | 运行值 | 读取点 |
|---|---|---|
| `write.cooldown_sec` | 120 | comment.py:99/269、dynamic.py:41、notify.py:51 |
| `write.dynamic.enabled / per_hour / per_day / forbid` | true / 0 / 3 / 词表 | dynamic.py:27、gates.py:79 |
| `write.message.enabled / per_hour / per_day / allow_mid / forbid` | true / 0 / 5 / [主号] / 词表 | gates.py:79、notify.py（白名单硬闸） |
| `write.comment.enabled / per_hour / per_day / same_video_once / forbid` | true / 3 / 0 / true / 词表 | gates.py:79、comment.py |
| `write.like.enabled / per_hour / per_day / same_video_once / forbid` | true / 6 / 0 / true / 词表 | gates.py:79、like.py |
| 动态/私信 ≤200 字、评论 ≤200 字 | —— | 代码常量 🔒 |

## D 组 · 陌生人草稿审批 — config `draft`（全部 ✅）

`enabled`(true) / `per_12h`(1) / `per_24h`(2) / `reply_interval_days`(30) / `forbid` —— 读取点 draft.py:61-73、131-148。24h 未审批自动作废、同人 30 天只回一次。

## E 组 · 评论区快筛 — config `comment_check`（全部 ✅）

`num`(10) / `warn_ratio`(0.3) / `name_keywords` / `ai_patterns` —— 读取点 comment.py:191-195、draft.py:66。只提示不拦截。

## F 组 · 调度与触发 — config `schedule` + DSH 定时任务

| 参数 | 运行值 | 生效方式 | 状态 |
|---|---|---|---|
| `schedule.mode` / `rrule` | night / `FREQ=DAILY;BYHOUR=0,1,2,3,4,5,22,23;BYMINUTE=43`（夜班保安 22:00–05:00 每小时一巡）；另有 all / valley / 间隔模式 `every<N>m` | 外部定时（DSH `schedule_create`，rrule 由 `schedule.py` 生成），**radar 代码不读** | ✅ 接线（外部） |
| 触发不落整点 | `BYMINUTE=17` | `schedule.py --minute`（DSH rrule 无 stagger，用分钟偏移等效） | ✅ 接线（外部） |
| 跑一轮的间隔（分钟） | 10 | `schedule.py --every-minutes`（`FREQ=MINUTELY;INTERVAL=N`，无 BY 部件） | ✅ 接线（外部） |
| 谷时口径（valley） | 工作日 9-12/14-18 高峰 | 📐 注释口径 | 📐 |

## G 组 · 请求层（代码常量，🔒 不可配）

退避 1.5s→60s cap · 429 尊重 Retry-After（≤5min）· -412/风控立即 die · 连续 3 败熔断本轮 —— client.py 写死，行为见 SKILL.md「请求层退避」节。

---

## 🚨 本次审计发现的问题清单（2026-11-02）

> **状态更新（同日 B 组落地后）**：（1）`radar.py verify-params` 参数采用对账已上线——
> 下表问题 1/2（drift）和 3/4/5/6（not-consumed）每次运行动态自检，conflict 才让退出码非零（可挂到定时任务做告警位）。
> （2）**B1/B2（2026-11-02）已处置 #3 与 #4 中的 `min_total_score`**：敏感参数加审批闸（`config propose/approve`）、
> `min_total_score` 接线为 `comment --score` 硬闸、`max_subtitles_per_round` 死键已删。
> （3）**口径裁决（11-02 老板拍板 AA）**：#1 统一「每轮 @ ≤1」（10-27）；#2 语义分层（@ ≤1 / 汇报候选 0-3）并加注；
> 模板 `max_push_per_round` 3→1 对齐；**cron 每时轮 prompt 的「每轮最多 3 条字幕」已修**（#7：10-27 的「字幕不限」此前 6 天从未生效，现已改「每轮不限（10-27 拍板）」）。
> 剩余处置（min_score=17 幽灵值是否下放硬闸）仍待老板拍板。
>
> （4）**11-07 老板拍板（治超时）**：单轮字幕上限从「不限」改回「每轮 ≤5 条」（+ 抽帧 ≤2、整轮 12 分钟内收尾）；cron `60d88f54` 超时 900s→1800s（单轮常跑到 14 分钟贴 900s 顶，11-07 连续 3 轮超时）。四处同步：charter.md / SKILL.md / state/config.json `_subtitle_note` / cron prompt；`budget.max_subtitles_per_round` 仍为已删死键（不恢复），上限只在文档/prompt 层约束模型。

按影响排序，**前两条是真实行为级问题，其余是卫生问题**：

| # | 级别 | 问题 | 影响 |
|---|---|---|---|
| 1 | ✅ 已处置 | charter.md 39 行「每轮条数不限」（10-15 口径）vs SKILL.md 126「每轮 ≤1」（10-27 口径）**互斥，而 charter 是「以它为准」** | **11-02 老板拍板 AA：统一 10-27 口径（每轮 ≤1）**，charter:39-40 已改写同步；SKILL.md/config/cron 本就是 10-27 → 四处统一 |
| 2 | ✅ 已澄清 | `max_push_per_round=1` 但 SKILL.md 说「只推 0-3 条」——**审计时误判：两处「推送」语义不同** | **11-02 老板拍板 AA：语义分层**——config `max_push` = @ 主号 ≤1（10-27 `_push_note`）；SKILL.md:84 / charter:24「0-3 条」= 汇报候选清单（≠ @）。两处已加注防再漂；模板 `max_push_per_round` 3→1 对齐（此前模板与真实 config 漂移） |
| 3 | 💤 卫生 | `budget.*` 三键一度全零引用 —— **目前已处置 2/3（B2）**：`max_subtitles_per_round` 已删；`min_total_score` 已接线为 `comment --score` 硬闸；剩 `max_push_per_round`（=1 vs SKILL.md 0-3）随 #2 一起裁 | 曾误导维护者；现 #2 待裁期间该键改写无效 |
| 4 | 💤 卫生 | `mention.min_score=17` 幽灵值：SKILL.md 只写「≥ min_score」不写数值，**没有任何执行者知道 17** | @ 阈值实际退化到 14 |
| 5 | 💤 卫生 | `mention.template` 死配置（fallback 硬编码） | 改模板不生效 |
| 6 | ⚠️ 语义 | `mention.per_round` 未入代码闸（真正生效的是 per_hour） | 改 per_round 无效；当前靠 per_hour=1 碰巧兜住 |

**处置进度（B1/B2 + 口径裁决已执行部分，2026-11-02）**
- ✅ **B2 已做**：`max_subtitles_per_round` 键已删（config+模板）；`min_total_score` 接线为 `comment --score` 硬闸（低于它 code 拒发，exit 14）；verify-params 文案同步
- ✅ **B1 已做**：敏感参数审批闸（`config propose/approve/reject`，25 键清单）
- ✅ **口径 AA 裁决已做（11-02）**：① #1 统一 10-27「每轮 @ ≤1」（charter:39-40 已同步）② #2 语义分层 + 加注（SKILL.md:84 / charter:24）③ 模板 `max_push_per_round` 3→1 ④ #7 cron prompt「最多 3 条字幕」→「每轮不限」——四改点到：charter / SKILL.md / 模板 / cron job 60d88f54
- ⏳ 待老板定：**#4 `min_score=17` 幽灵值是否也下放为代码硬闸**（参考 min_total_score 的做法）；#5/#6 死配置清理（template / per_round 键）

---

## 操作手册（怎么改、怎么验）

1. **改 config 参数** → 一律走 `radar.py config set <段.键> <值> [--yes]`（A3，2026-11-02）：**默认干跑**（打印 before→after，不写）；`--yes` 才写，**写前自动备份**（`config.json.bak-<ts>-<rand>`，保留最近 10 份）、写后重读校验；改错了 `config restore --list` 找备份 → `config restore <备份名> --yes` 一键还原（还原前会把当前值再备份一份，反悔可回）。敏感项（开关/白名单/频控）与死配置/漂移会显式提醒。`rate` 改 @ 频控同样自动备份。**每次变更自动写入参数变更账本**（A4，`state/param-history.jsonl`：谁/何时/为何改、前后值；restore 记回滚行与实际变动的参数）；顺手 `--reason "为什么改"`，事后 `config log` 看时间线、`config observe <变更id> --note "效果如何"` 补观察——**reason/观察只记人明说的，不编造**。热加载，下一轮立即生效。敏感项（频控/开关/白名单）改完**必须告诉我**，涉及账号安全的改动最好等我确认。
2. **改模型规则**（阈值/条数/流程）→ 改 `SKILL.md` + `charter.md` **两处一起**（本文件揭示：单改一处必漂移）。charter 是最终口径。
3. **改调度** → `scripts/schedule.py`（all / valley / `--every-minutes N`）打印 rrule + prompt，再用 DSH 的 `schedule_create` 建/改任务；`config.json` 的 `schedule` 段只是记录，不是权威。
4. **验证**：
   - `python scripts/radar.py verify-params` — **参数采用对账**（A2，2026-11-02）：config 保存值 vs 真实账本/日报逐项对账，五档判定（✅ adopted / ⏳ pending / ❌ conflict / ⚠️ drift / 💤 not-consumed）；**conflict>0 → exit 3**（可直接挂到定时任务做告警位，平时静默、漂移/冲突才开口）。`--json` 给脚本用
   - `python scripts/radar.py rate` — 看 @ 频控用量与参数
   - `radar.py mention --bv <BV> --dry-run`（默认干跑）— 验闸与文案
   - `cd scripts && python -m unittest discover tests -v` — 135 用例回归（零网络）
5. **审计口径**：本文件每次改参数后顺手核一遍「接线/漂移」列，保持地图与代码同步。

---

*生成方式：2026-11-02 对 `bili_radar/*.py` 全量 grep 读取点（`read_config`/`cfg.get` 溯源）+ SKILL.md/charter.md 口径比对。行号以当日 commit 7a1d9b7 为准。*
