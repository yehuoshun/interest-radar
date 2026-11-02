# 兴趣雷达 · 参数目录（PARAMETERS）

> 参照 SurfCore-Life COVERAGE/PARAMETER-AUDIT 的治理思路整理（2026-11-02）。
> 目的：把雷达所有「可调的行为杠杆」列清楚——**归谁管、怎么生效、代码里到底有没有接线**。
> 权威口径：`charter.md` 为准；本文件是「参数地图」，两个运行时文件是唯一真值：
> - 运行配置：`~/.openclaw/workspace/interests/config.json`（本文件不复制运行值，敏感项见该文件）
> - 规则口径：`~/.openclaw/workspace/interests/charter.md` + 本仓库 `SKILL.md`

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
| `budget.max_subtitles_per_round` | 0 | 维护者 | —— | 💤 死配置：代码零引用。10-27 老板拍板「每轮字幕不限」时此键**本来就没被代码读过**（上限一直是模型按 SKILL.md 执行） |
| `budget.max_push_per_round` | 1 | 维护者 | —— | ⚠️ 漂移：config 是 1（10-27 老板拍板「每轮最多推 1 条」），但 **SKILL.md 第 9 步仍写「只推 0-3 条」且没写 1** → 模型看到的真值是 0-3，可能推超 1 条 |
| `budget.min_total_score` | 14 | 维护者 | —— | 💤 死配置：代码零引用。好在它只是镜像——真值在 SKILL.md 76「默认 ≥ 14/20」📐，模型看得见，**数值恰好一致** |
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
| 动态/私信 ≤200 字、评论 ≤200 字 | —— | 代码常量 🔒 |

## D 组 · 陌生人草稿审批 — config `draft`（全部 ✅）

`enabled`(true) / `per_12h`(1) / `per_24h`(2) / `reply_interval_days`(30) / `forbid` —— 读取点 draft.py:61-73、131-148。24h 未审批自动作废、同人 30 天只回一次。

## E 组 · 评论区快筛 — config `comment_check`（全部 ✅）

`num`(10) / `warn_ratio`(0.3) / `name_keywords` / `ai_patterns` —— 读取点 comment.py:191-195、draft.py:66。只提示不拦截。

## F 组 · 调度与触发 — config `schedule` + cron

| 参数 | 运行值 | 生效方式 | 状态 |
|---|---|---|---|
| `schedule.mode` / `cron` | all / `0 * * * *` | 平台 cron（openclaw cron + apply-cron.py），**radar 代码不读** | ✅ 接线（外部） |
| 触发随机化 staggerMs | 120000 | cron 配置侧 | ✅ 接线（外部） |
| 谷时口径（valley） | 工作日 9-12/14-18 高峰 | 📐 注释口径 | 📐 |

## G 组 · 请求层（代码常量，🔒 不可配）

退避 1.5s→60s cap · 429 尊重 Retry-After（≤5min）· -412/风控立即 die · 连续 3 败熔断本轮 —— client.py 写死，行为见 SKILL.md「请求层退避」节。

---

## 🚨 本次审计发现的问题清单（2026-11-02）

> **状态更新（同日晚些时候，A2 落地）**：新增 `radar.py verify-params` 参数采用对账，
> 下表问题的 1/2（drift）和 3/4/5/6（not-consumed）已能**每次运行动态自检**、
> conflict 才会让退出码非零（cron 可挂告警）。处置（对齐口径/清理）仍待老板拍板。

按影响排序，**前两条是真实行为级问题，其余是卫生问题**：

| # | 级别 | 问题 | 影响 |
|---|---|---|---|
| 1 | ⚠️ 行为 | charter.md 39 行「每轮条数不限」（10-15 口径）vs SKILL.md 126「每轮 ≤1」（10-27 口径）**互斥，而 charter 是「以它为准」** | @ 推荐每轮 1 条还是不限，执行者无所适从 |
| 2 | ⚠️ 行为 | `max_push_per_round=1` 但 SKILL.md 说「只推 0-3 条」 | 模型可能每轮推 3 条，超老板 10-27 定的「1 条」 |
| 3 | 💤 卫生 | `budget.*` 三键全零引用（死配置） | 改配置无效果，误导维护者 |
| 4 | 💤 卫生 | `mention.min_score=17` 幽灵值：SKILL.md 只写「≥ min_score」不写数值，**没有任何执行者知道 17** | @ 阈值实际退化到 14 |
| 5 | 💤 卫生 | `mention.template` 死配置（fallback 硬编码） | 改模板不生效 |
| 6 | ⚠️ 语义 | `mention.per_round` 未入代码闸（真正生效的是 per_hour） | 改 per_round 无效；当前靠 per_hour=1 碰巧兜住 |

**处置建议（未动手，等老板定）**
- **A. 对齐口径**（推荐先做，改动小）：SKILL.md / charter.md / config 三处统一「每轮 ≤1」「推送 ≤1」「min_score 数值写明 17」，并决定 min_score 是否下放为代码硬闸
- **B. 清理死配置**：budget 段要么接线（代码读 + 推送时执行），要么删键留注释说明「模型规则，不在 config」
- C/D/E 组无需动。

---

## 操作手册（怎么改、怎么验）

1. **改 config 参数** → 一律走 `radar.py config set <段.键> <值> [--yes]`（A3，2026-11-02）：**默认干跑**（打印 before→after，不写）；`--yes` 才写，**写前自动备份**（`config.json.bak-<ts>-<rand>`，保留最近 10 份）、写后重读校验；改错了 `config restore --list` 找备份 → `config restore <备份名> --yes` 一键还原（还原前会把当前值再备份一份，反悔可回）。敏感项（开关/白名单/频控）与死配置/漂移会显式提醒。`rate` 改 @ 频控同样自动备份。热加载，下一轮立即生效。敏感项（频控/开关/白名单）改完**必须告诉我**，涉及账号安全的改动最好等我确认。
2. **改模型规则**（阈值/条数/流程）→ 改 `SKILL.md` + `charter.md` **两处一起**（本文件揭示：单改一处必漂移）。charter 是最终口径。
3. **改 cron/schedule** → 走 `scripts/apply-cron.py`（all/valley），不是 config.json 说了算。
4. **验证**：
   - `python3 scripts/radar.py verify-params` — **参数采用对账**（A2，2026-11-02）：config 保存值 vs 真实账本/日报逐项对账，五档判定（✅ adopted / ⏳ pending / ❌ conflict / ⚠️ drift / 💤 not-consumed）；**conflict>0 → exit 3**（可直接挂 cron 做告警位，平时静默、漂移/冲突才开口）。`--json` 给脚本用
   - `python3 scripts/radar.py rate` — 看 @ 频控用量与参数
   - `radar.py mention --bv <BV> --dry-run`（默认干跑）— 验闸与文案
   - `cd scripts && python3 -m unittest discover tests -v` — 52 用例回归（零网络）
5. **审计口径**：本文件每次改参数后顺手核一遍「接线/漂移」列，保持地图与代码同步。

---

*生成方式：2026-11-02 对 `bili_radar/*.py` 全量 grep 读取点（`read_config`/`cfg.get` 溯源）+ SKILL.md/charter.md 口径比对。行号以当日 commit 7a1d9b7 为准。*