---
name: interest-radar
description: 每日兴趣雷达——替你扫一轮 B站，读字幕挑出真正值得占用你一次注意力的东西，写成日报并推送到微信。当用户要求「跑一轮兴趣雷达 / 今天的雷达 / 每天帮我筛 B站 / 给我推值得看的东西 / 更新兴趣档案 / 记录反馈」时使用。判断口径与红线见 interests/charter.md。
---

# 兴趣雷达（interest-radar）

每天一轮：**读兴趣档案 → 搜 → 读字幕原文 → 四维打分 → 判重 → 写日报 → 推微信**。
不是搜索机器人：**"值不值得占用他一次注意力"是唯一的判据**，宁缺勿滥，**一天 0 条是合法输出**。

## 硬规则

- **写操作分档管**（2026-10-19 老板放开「发动态/私信」）：每档都有代码闸（开关 + `--yes` + 敏感词 + 频控 + 白名单 + 失败自动关）。口径不变：**只 @ 主号、只私信白名单、不发档案内容**。见「发动态 / 私信」节。
- **只 @ 主号，永远不理别人**（不回复、不引用、不 @ 第三人、不吵架）—— 目的就一个：**防账号被爆**。
  - ✅ **例外（2026-10-17 老板拍板）：主号（夜灬瞬）@ 我 = 指令，必须回一条**——**用楼中楼回**：`radar.py reply --bv <视频> --reply-to <at[].rpid> --text "@夜灬瞬 …"`（不占「同一视频一条」名额；楼中楼可见性查不准 → 记「未验证」）。**别人 @ 我 → 不理、不回**。
- **兴趣档案不出本机**：`interests/` 里的任何内容不进公开平台、不进外部日志。
- **不读 OpenClaw 的 memory 全文**（噪音源）。需要候选池时只看你自己的项目清单（别拿助手的长期记忆当兴趣源，那是噪音）。
- **不给档案灌历史数据**：档案只由本人明写 + 👍/👎 反馈生长，别自作聪明导入 star/收藏。
- 不确定的事**不编**，宁可写「没查到」。

## 状态目录（`~/.openclaw/workspace/interests/`）

| 文件 | 作用 |
|---|---|
| `profile.md` | 兴趣线（人写，空就开始跑） |
| `charter.md` | 章程：判据、红线、流程（**以它为准**，本文件只是操作手册） |
| `weights.json` | 反馈权重（脚本写） |
| `evidence.jsonl` | 反馈证据（脚本写） |
| `seen.md` | 判重表（脚本写） |
| `out/<日期>.md` | 每日报告 |

## 命令速查

```bash
R=~/.openclaw/workspace/skills/interest-radar/scripts/radar.py
python3 $R check                                    # 校验 cookie（读字幕必须登录）
python3 $R search --kw "关键词" --num 20 --days 7   # 搜（order: pubdate|click|totalrank）
python3 $R sub BV1xxxxxxxxx                         # 字幕全文；无字幕打印 NO_SUBTITLE
python3 $R seen check BV1xxx                        # SEEN / NEW
python3 $R seen add <日期> BV1xxx <verdict> 标题     # verdict: keep|skip
python3 $R feedback --topic "主题" --signal like|skip|note --bv BV1xxx --score 4
python3 $R stats                                    # 权重 + 已看条数（给"每周提议"用）
python3 $R reply --bv BV1xxx                        # 评论 @ 某人（默认干跑，只打印将要发什么）
python3 $R notify --new-only                         # 谁找我：@我的 / 回复我的（新于上次的）
python3 $R dm --new-only                            # 私信：主号会话里新于水位线的（只读不回）
python3 $R dynamic --text "…"                       # 发动态（≤200 字，默认千跑，--yes 真发）
python3 $R comment --bv BV1xxx --text "…" --yes     # 自发评论（≤200 字，无需 @；写操作闸）
python3 $R dynamic-del --dyn-id 1260… --yes          # 删掉发错的动态
python3 $R msg --mid 239028467 --text "…" --yes     # 私信（只准发 allow_mid 白名单）
python3 $R check-reply --bv BV1xxx --rpid 123456     # 匿名能不能看到这条评论（验阿瓦隆）
```

- cookie 文件：`~/.openclaw/secrets/bilibili-cookies.txt`（小号；**失效先跑 `scripts/bili_qr_login.py` 扫码自救**，见下节，不用手动导出）
- 脚本只做确定性的事；**判断一律由模型做**

## 一轮流程（严格按序）

0. **先读反馈**：`notify --new-only` → 主号在我评论下的**每一条回复**都用 `feedback` 记一条（like/skip/note），**一条都不许丢**；别人的回复不理也不记。
   - **主号 @ 我 → 必须回一条**（楼中楼：带 `--reply-to <at[].rpid>`；正文 ≤150 字）；**别人 @ 我 → 不理不回**。（`at[].text` 是正文、`at[].rpid` 是他那条评论）
1. **`check`**：cookie 失效 → 直接停，**别硬跑**，报「cookie 失效，需要重新导出」。
2. 读 `profile.md`：兴趣线 0 条 → 只按「明确不要的」过滤，**不自造兴趣**。
3. **广撒网**：每条兴趣线搜 1-2 轮（主题 + 邻域各一次），`--days 7 --order pubdate`。
4. **粗筛（先省 token）**：按标题/简介/时长/播放量砍掉明显不值的（入门教程、标题党、吵架场）→ **剩 ≤ 8 条候选**。
   ⚠️ **字幕预算：每轮不限**（2026-10-27 老板拍板取消，账号交 AI 运营；`config.json` → `budget.max_subtitles_per_round=0`）。粗筛仍做（省 token），但不再卡条数——够格就都读。
5. **逐条 `sub` 读原文**（不看摘要下判断）。`NO_SUBTITLE` → 跳过（除非本人开了转写，那就另说）。
6. **四维打分**（各 0-5，写在报告里）：**相关性 / 新奇度 / 实操价值 / 新鲜度**
   - 总分 ≥ 阈值（默认 **≥ 14/20**）才留；**新奇度 ≤ 1 的直接砍**（只是重复他已知道的）。
7. **判重**：`seen check`，SEEN 的跳过；每条处理完 `seen add`。
8. **写报告** `out/<YYYY-MM-DD>.md`（格式见下）。
9. **推送**：只推总分最高的 **0-3 条**到你的渠道（按渠道配置解析 target）。**0 条就别推、别凑数**。
10. **（可选）谁找我**：`notify --new-only`，有新 @/回复就在推送里附一行；`dm --new-only` 看私信里有没有新话（**只读不回**）。
11. **结尾**：报告后加一行「本轮扫了 N 条、读了 M 条字幕、留下 K 条」。

## cookie 失效自救（扫码登录，2026-10-27 起）

`check` 报 `-101 账号未登录`（服务端判定登录态失效；文件在 ≠ 登录在）时：

```bash
python3 scripts/bili_qr_login.py   # 生成二维码 → 轮询 180s → 跟随 crossDomain 拿 Set-Cookie → 覆写 cookie 文件（自动备份 .bak-qr）
```

- 二维码 PNG 输出到 `tmp/bili-qr-login-<ts>.png`（**文件名带时间戳**，防浏览器缓存旧图），发给本人用**小号 B站 App** 扫码并点确认
- 新版 poll 成功后返回的是 **crossDomain 跳转 URL**（`passport.biligame.com/.../crossDomain?ticket=...`），不是直接 SESSDATA —— 脚本必须**跟随跳转**从 Set-Cookie 提取登录态（第一次踩坑：只解析 query 拿不到）
- 状态码：`86101` = 等待扫码（正常）、`86090` = 已扫待确认、`CONFIRMED` 后 `LOGIN_OK` = 成功；二维码 3 分钟有效，超时重跑
- 成功后 `radar.py check` 验证；`~/.openclaw/secrets/` 里没有其它 B站凭据可自愈，扫码是唯一免手动导出的路径
- 历史：10-23 01:00 ~ 10-27 14:00 连续 **110 轮停摆**后靠此法恢复（2026-10-27）

## 评论与 @（**默认关**）

目的只有一个：让使用者自己能上 B站 看到「今天有什么值得看」。**不互动、不吵架、不带档案内容**。

四道闸全在**代码里**（不靠提示词），缺一不发：

1. `config.json` 里 `mention.enabled = true` **且** `mention.name` 非空
2. 命令行必须显式加 `--yes`（**默认干跑**，只打印将要发的内容）
3. 同一 BV 只发一次（查 `seen.md` 的 `mentioned` 记录）
4. 正文 ≤ 150 字，必须包含 `@昵称`，**正文就是结论**：`@昵称` + 一句「为什么值得」（不是"值得看一眼"这种空话）
5. 敏感词闸：正文命中 `config.json` 的 `mention.forbid` 里任一词 → 拒发（防档案/项目名漏进公开评论）
6. 频控（可配，`config.json` → `mention`）：**2026-10-27 老板拍板：每轮 ≤1、每小时 ≤1、每天不限**（雷达照旧每小时跑，但一小时只给主号一条，多了看不过来）· 硬闸仍 = 「同一视频只发一条」+ 总分 ≥ min_score。用 `radar.py rate` 看用量、改参数
7. **发完自检**：自动用**匿名请求**回查这条评论可不可见（阿瓦隆拦了就记一行；别人看不到 = 没真发出去）
   - ⚠️ **visible_anon=false 不一定是永久隐藏**（2026-10-27 实证）：新号/新登录态发首评后会有一段**审核延迟**，当时查看不到、半小时后老板主号确认可见。判定「被拦」前至少隔 30min+ 复查一次。

正文默认用 `config.json` 里的 `template`；**模板里不许出现档案、项目名、私人信息**。
撤除：`/x/v2/reply/del`（带 `csrf`）可删，实测 code=0。

- ⚠️ 发评论失败（`-107 账号未转正` / 风控 / -412）→ **不重试、不刷屏**：这一轮就只推微信，报告里记一行原因。
> 风险自担：评论是**公开**的；小号 @ 主号等于把两个号公开关联；新号发言有风控概率。
> 防爆措施：只 @ 主号 / **同一视频只发一条** / 频控三参数（当前 0/0/0 = 全不限，可配）/ **连续 3 次发失败自动关掉 mention.enabled** 并喊人。

## 发动态 / 私信（**2026-10-19 老板放开**）

能力开了，口径没开。闸全在**代码里**（`radar.py`），缺一发不出去：

1. `config.json` 里 `write.<kind>.enabled = true`（`kind` = `dynamic` | `message`）
2. 命令行必须显式 `--yes`（**默认千跑**）
3. 正文非空；动态/私信都 ≤ 200 字
4. 敏感词闸：命中 `write.<kind>.forbid` 里任一词 → 拒发（防档案/项目名/路径漏上公开平台）
5. 频控（可配）：`per_hour` / `per_day`（按 kind 各算；**删动态不受限制**）
6. **私信白名单**：收件人必须在 `write.message.allow_mid` 里（当前只有主号 239028467）——防私信陌生人
7. 连续 3 次失败 → **自动关掉该 kind 的开关**并喊人

- 实测接口（2026-10-19）：动态 `POST /x/dynamic/feed/create/dyn`，**只吃 JSON body** `{"dyn_req":{...}}`（form 编码会 -400）；删动态走 `dynamic_svr/rm_dynamic`；私信走 `web_im/send_msg`（form + csrf）
- 日志：所有写入落 `interests/write-log.jsonl`；失败计数 `interests/write-fails-<kind>.json`
- **动态不发档案**：只发「今天读到/干了什么」这种本体视角的话。**私信不群发、不催回复**
- 📌 **身份已公开关联**（2026-10-19）：小号签名写着「夜灬瞬 的 AI 助手」——两号关联是本人主动公开的；**档案/私人偏好/主号私信内容依旧一条不许上公开面**（限制更严，因为已经实名挂上去了）

## 自发评论（**2026-10-27 老板放权**）

老板原话：「你看到你感兴趣的视频可以发评论，这个权限我给你放开，你自发评论（不属于兴趣雷达）可以不用艾特我」。

- 用途：刷到真正感兴趣的视频，以小号身份正常发一条评论；**不强制 @ 主号**、不计入雷达「同一视频一条」闸（那道闸只管 @ 推荐）
- 闸（代码里，`write.comment`）：`enabled` → `--yes` → 正文 ≤200 字 → 敏感词 fail-closed → 频控（**小时 ≤3、天不限**，2026-10-27 老板调：当个正常人，防高频风控）→ 同一视频只发一条 → 连续失败 3 次自动关
- 红线不变：评论里**不许带**兴趣档案/项目名/路径/私人信息（forbid 兜底）；不吵架、不引战、不 @ 第三人
- 账本：`write-log.jsonl`（kind=comment，含 bv/rpid/visible_anon）；发完自动匿名回查可见性
- 用法：`radar.py comment --bv BV1xxx --text "…" --yes`（默认干跑）

## 报告格式（`interests/out/<日期>.md`）

```markdown
# 兴趣雷达 · 2026-10-15

## 1. 标题（BV号）
- UP / 时长 / 播放量 / 发布：`YYYY-MM-DD` / 链接
- 打分：相关性 4 · 新奇度 3 · 实操价值 3 · 新鲜度 4（= 14）
- 为什么值得：（两三句，具体到"他为什么会在意"，不许空话）
- 一句话：（如果推给他，就这一句）

---
扫了 N 条 · 读了 M 条字幕 · 留下 K 条 · 本轮到 X 点停
```

## 反馈

- 本人说「第 2 条不错 / 那条没用」→ `feedback --topic <兴趣线主题> --signal like|skip --bv <BV号> [--score N]`
- **每周一次**：`stats` 汇总 → **提议**增删兴趣线，等本人点头才改 `profile.md`
- 别自己改 `profile.md`，那是本人的地盘

## 定时（cron）
按 `openclaw cron` 配置，建议：独立 session + 便宜模型 + `delivery.mode=announce`（正常回 NO_REPLY = 静默，异常才开口）。
模式用 `scripts/apply-cron.py` 一键切：
- **all**：全天每小时（`0 * * * *`）
- **valley（梁文谷）**：只在 DeepSeek 谷时的小时跑（`0 0-8,12,13,18-23 * * *`）—— 工作日 9-12/14-18 是高峰，其余含周末都是谷时
创建/修改 cron 的投递参数按你的渠道配置解析（微信类渠道通常要 `channel` + `to` + `accountId`）。
