---
name: interest-radar
description: 每日兴趣雷达——替你扫一轮 B站，读字幕挑出真正值得占用你一次注意力的东西，写成日报，并把够格的 0-3 条在对话里回报。当用户要求「跑一轮兴趣雷达 / 今天的雷达 / 每天帮我筛 B站 / 给我推值得看的东西 / 更新兴趣档案 / 记录反馈」时使用。判断口径与红线见 state/charter.md。
---

# 兴趣雷达（interest-radar）

每天一轮：**读兴趣档案 → 搜 → 读字幕原文 → 四维打分 → 判重 → 写日报 → 对话里回报 0-3 条**。
不是搜索机器人：**"值不值得占用他一次注意力"是唯一的判据**，宁缺勿滥，**一天 0 条是合法输出**。

## 硬规则

- **写操作分档管**（2026-10-19 老板放开「发动态/私信」）：每档都有代码闸（开关 + `--yes` + 敏感词 + 频控 + 白名单 + 失败自动关）。口径不变：**只 @ 主号、只私信白名单、不发档案内容**。见「发动态 / 私信」节。
- **只 @ 主号，永远不理别人**（不回复、不引用、不 @ 第三人、不吵架）—— 目的就一个：**防账号被爆**。
  - ✅ **例外（2026-10-17 老板拍板）：主号（夜灬瞬）@ 我 = 指令，必须回一条**——**用楼中楼回**：`radar.py reply --bv <视频> --reply-to <at[].rpid> --text "@夜灬瞬 …"`（不占「同一视频一条」名额；楼中楼可见性查不准 → 记「未验证」）。**别人 @ 我 → 不理、不回**。
- **兴趣档案不出本机**：`state/` 里的任何内容不进公开平台、不进外部日志。
- **不读助手的长期记忆全文**（噪音源）。需要候选池时只看你自己的项目清单（别拿助手的长期记忆当兴趣源，那是噪音）。
- **不给档案灌历史数据**：档案只由本人明写 + 👍/👎 反馈生长，别自作聪明导入 star/收藏。
- 不确定的事**不编**，宁可写「没查到」。

## 状态目录（`state/`）

| 文件 | 作用 |
|---|---|
| `profile.md` | 兴趣线（人写，空就开始跑） |
| `charter.md` | 章程：判据、红线、流程（**以它为准**，本文件只是操作手册） |
| `weights.json` | 反馈权重（脚本写） |
| `evidence.jsonl` | 反馈证据（脚本写） |
| `seen.md` | 判重表（脚本写） |
| `out/<日期>.md` | 每日报告 |

## 开跑前（本机一次性）

```bash
cd work/interest-radar
python scripts/init.py            # 建 state/（拷模板 + 写默认 config.json），并打印 cookie 路径
python scripts/radar.py check     # 打印昵称 = cookie 有效
```

- 状态目录 `state/`（`INTERESTS_DIR` 可覆盖）：报告 `state/out/`、抽帧 `state/frames/`
- cookie：`<工作区>/config/bilibili_cookies.txt`（也认历史名 `bilibili.txt`；本机实际是 `E:\DevSoftWare\DeepSeekWorkSpace\config\bilibili.txt`）。
  没有就取小号 cookie 存成一行 `SESSDATA=…; bili_jct=…; DedeUserID=…`；或 `python scripts/bili_qr_login.py` 扫码换新
  （二维码出图需 `python -m pip install "qrcode[pil]"`；没装该包会打印登录 URL 并 exit 4）
- 本机 Windows + PowerShell：命令是 **`python`，不是 `python3`**；`ffmpeg` 不在 PATH ⇒ `scripts/frames.py` 抽帧用不了（其余功能不受影响）
- 默认 `config.json` 里**所有写操作开关都是关的**：先跑只读流程，要发东西再 `radar.py config set write.comment.enabled true --yes`

## 命令速查

```bash
R=scripts/radar.py
python $R check                                    # 校验 cookie（读字幕必须登录）
python $R search --kw "关键词" --num 20 --days 7   # 搜（order: pubdate|click|totalrank）
python $R comment-check --bv BV1xxx          # 评论区快筛（@ 分享前跑：疑似 AI 水军提示，不拦截）
python $R sub BV1xxxxxxxxx                         # 字幕全文；无字幕打印 NO_SUBTITLE
python scripts/frames.py --bv BV1xxx [--strip]      # 抽帧看画面：默认 3x3 九宫格；--strip 硬字幕长图（需字幕轨）
python $R seen check BV1xxx                        # SEEN / NEW
python $R seen add <日期> BV1xxx <verdict> 标题     # verdict: keep|skip
python $R feedback --topic "主题" --signal like|skip|note --bv BV1xxx --score 4
python $R stats                                    # 权重 + 已看条数（给"每周提议"用）
python $R config set <段.键> <值> [--yes] [--reason "…"]  # 改配置：默认干跑+自动备份 → config restore 可回滚；变更入账本
python $R config restore [--list] [<备份名> --yes]   # 配置备份列表/还原（保留最近 10 份）
python $R config log [--param 段.键] [--json]        # 参数变更账本（谁/何时/为何改，回滚与观察）
python $R config observe <变更id> --note "…"         # 给某次变更补事后观察
python $R verify-params [--json]                    # 参数采用对账：config 保存值 vs 运行证据（只读；conflict>0 → exit 3）
python $R engagement [--days N]                    # 活跃度评估：老板反馈/主动@/批准草稿/报告数 → 判读是否降频
python $R reply --bv BV1xxx                        # **@ 主号 只走这个**（默认干跑；查 mention 频控 + 同一视频只发一次）
python $R feed --num 12 --rounds 2                 # 刷首页推荐流（让算法决定看什么，不按关键词挖）
python $R like --bv BV1xxx --yes                   # 点赞（--cancel 取消；同一视频只点一次）
python $R jitter --max-min 10 --sleep              # 巡更前抖一下（0–10 分钟，别每次都准点）
python $R jitter --watch 414 --sleep               # 看片计时：这条 6:54 → 花掉 414 秒（kind=watch）
python $R jitter --min-min 1 --max-min 10 --rest --sleep   # 看完一条歇 1–10 分钟（kind=rest，不占巡更间隔）
python $R jitter --close                                 # 一串收尾打卡（kind=close；下一巡间隔从这一刻算）
python $R notify --new-only                         # 谁找我：@我的 / 回复我的（新于上次的）
python $R dm --new-only                            # 私信：主号会话里新于水位线的（只读不回）
python $R dynamic --text "…"                       # 发动态（≤200 字，默认千跑，--yes 真发）
python $R comment --bv BV1xxx --text "…" --yes     # 自发评论（≤200 字，无需 @；写操作闸；`budget.min_total_score` 11-13 起为 0（不卡分；只剩防封号安全阀））
python $R dynamic-del --dyn-id 1260… --yes          # 删掉发错的动态
python $R msg --mid 239028467 --text "…" --yes     # 私信（只准发 allow_mid 白名单）
python $R check-reply --bv BV1xxx --rpid 123456     # 匿名能不能看到这条评论（验阿瓦隆）
```

> ⚠️ **`comment` ≠ `reply`（2026-11-13 踩过）**：两者都真能发出带 `@昵称` 的评论，但 `comment` 是「自发评论」，
> 只记 `write-log.jsonl`，**不写 `mention-log.jsonl`、不查「同一视频只发一次」**——于是 mention 频控（每轮/每小时 ≤1）
> 形同不存在，`radar.py rate` 也永远显示 0。@ 主号**必须**用 `reply`。`comment` 现在会在正文含 `@mention.name` 时
> 打一行 stderr 提醒，但别指望它拦你。

- cookie 文件：`<工作区>/config/bilibili_cookies.txt`（工作区布局 `<workspace>/{code,work}/<项目>`；小号；**失效先跑 `scripts/bili_qr_login.py` 扫码自救**，见下节，不用手动导出）
- 脚本只做确定性的事；**判断一律由模型做**

## 刷着玩模式（2026-11-13 老板改口径）

**作息**：24 小时值班，**节奏只有一条**（11-13 老板「每看完一条，歇 1–10 分钟接着看下一条」；「掷一个 50–120 分钟的随机间隔？你是不是又理解错了？」→ 50–120 是我拍错的，已经删了）：视频时长 + 1–10 分钟 = 下一次观看开始（11-13 17:07 老板「是视频时长 + 一到十分钟。你这怎么变成了一到十分钟？」→ 看片先用 `radar.py jitter --watch <秒> --sleep` 把时长真的花掉，收尾打卡才落在「看完」之后）。每次收尾后 `python scripts/plan.py next` 按这条算醒点，写一个**一次性**闹钟 `RRULE:FREQ=DAILY;COUNT=1` 回活任务 —— 醒点不贴整点；`gate` 只防同一分钟重复触发；白天轻、夜里重；一串连看到自然想走（不数条数、不设时长上限，视频长短自己决定），收尾 `radar.py jitter --close` 打一笔卡，多数时候只是看，0 互动是正常结果；@ 老板：白天 ≤1 条/巡（白天合计 ≤3，11-13 老板「白天可以@」后不再压着）、夜里 ≤2 条/巡（整夜 ≤4，11-13「一晚上只艾特我一次啊」后从「整夜 ≤2」放开）。
一巡写操作上限：赞 ≤2、评论 ≤1、@ ≤2；整夜 @ ≤4（11-13 老板「一晚上只艾特我一次啊」后从 1/夜放开，见 `chg-20261113-120250-b0414b`）。

**看片计时**：每看一条先 `radar.py jitter --watch <秒> --sleep`（6:54 → 414、16:20 → 980、21:48 → 1308），记 `kind=watch`；这是节奏里「视频时长」那一段，不记就等于没看片。

**歇息**：看完一条视频再点下一条之前，`radar.py jitter --min-min 1 --max-min 10 --rest --sleep` 歇 1–10 分钟（均匀分布，11-13 老板「每看完一条，歇 1–10 分钟接着看下一条」）；记 `kind=rest`。**收尾打卡**：`radar.py jitter --close` 记 `kind=close`；`plan.py` 认 open / watch / rest / close 全部记录当「上一次还在 B 站」，因为节奏是连续的一条线，不分串内串外。开门前只过 `python scripts/plan.py gate`（只挡「同一分钟重复触发」），`allowed:false` 就跳过这一巡。

（备选：`schedule.py --random-minute` 能每巡重掷一个随机分钟、把触发本身挪开整点，代码和单测都留着，但当前口径不用。）

老板原话：「像正常人一样刷 B 站；遇到喜欢的点赞，评论（有问题可以评论），遇到觉得我感兴趣的可以艾特我，一般我回复你
就代表我感兴趣，你就可以按照建画像了。你自己刷没必要按照雷达，纯给你自己学习。」

- 不再按关键词挖线索，改用首页推荐流：`radar.py feed --num 12 --rounds 2`。
- 真读几条（`radar.py sub <BV>`），读完再决定：
  - 好 → `radar.py like --bv BV1xxx --yes`（写闸 `write.like`，per_hour 现为 2 —— 防封号安全阀，不参与判断；同一视频只点一次；`--cancel` 取消赞）
  - 有话要说 → `radar.py comment --bv BV1xxx --text "…" --yes`（自发评论，≤200 字，**不走 mention 闸**）
  - 觉得老板会感兴趣 → `radar.py reply --bv BV1xxx --text "@夜灬瞬 …" --yes`（**只有这条走 mention 闸 / 频控 / 同一视频只发一次**）
- 判据：只对真读完、有具体话可说的视频动手；推广、广告、纯搬运、梗图不点不评。零互动是合法结果，不为产量凑。
- 老板回复后（这是建画像的主信号）：`radar.py notify --new-only` 取回复 → `radar.py check-reply --bv …` 看可见性 →
  按回复内容 `radar.py feedback --topic "…" --signal like|skip|note --bv BV1xxx` 记账 → 更新 `state/profile.md` 的兴趣线（加分/降权/新增）。
- 红线不变：只 @ 主号；写操作默认干跑（加 `--yes` 才真发）；兴趣档案不出本机。

## 一轮流程（严格按序）

0. **先读反馈**：`notify --new-only` → 主号在我评论下的**每一条回复**都用 `feedback` 记一条（like/skip/note），**一条都不许丢**；别人的回复不理也不记。
   - **主号 @ 我 → 必须回一条**（楼中楼：带 `--reply-to <at[].rpid>`；正文 ≤150 字）；**别人 @ 我 → 不理不回**。（`at[].text` 是正文、`at[].rpid` 是他那条评论）
1. **`check`**：cookie 失效 → 直接停，**别硬跑**，报「cookie 失效，需要重新导出」。
2. 读 `profile.md`：兴趣线 0 条 → 只按「明确不要的」过滤，**不自造兴趣**。
3. **广撒网**：每条兴趣线搜 1-2 轮（主题 + 邻域各一次），`--days 7 --order pubdate`。
4. **粗筛（先省 token）**：按标题/简介/时长/播放量砍掉明显不值的（入门教程、标题党、吵架场）→ **剩 ≤ 8 条候选**。
   ⚠️ **字幕预算：每轮 ≤ 5 条**（2026-11-07 老板拍板加回上限，治单轮超时；此前 10-27 曾放开为不限）。粗筛后按分数从高到低读，**读满 5 条即停**；剩下的写进报告「待读队列」，下一轮优先。
   ⏱ **单轮时间预算：已作废**（11-13 老板「每看完一条，歇 1–10 分钟接着看下一条」→ 一串连看到自然收尾，不设时长上限；下面这条 12 分钟是 11-07 治超时的旧口径，只留作历史解释）。**旧：单轮 12 分钟**（2026-11-07 新增）。抽帧 ≤ 2 条；整轮跑到 12 分钟就停手，**先写报告再收尾总结**。调度侧超时只当兜底——目标是 12 分钟内收尾（此前单轮常跑到 14 分钟贴 900s 顶，11-07 连续 3 轮超时）。
5. **逐条 `sub` 读原文**（不看摘要下判断）。`NO_SUBTITLE` → 跳过（除非本人开了转写，那就另说）。
   **深读抽帧（2026-10-27 新增）**：对读字幕后仍难判断、或无字幕但值得赌一眼的候选，跑
   `python scripts/frames.py --bv BV1xxx`（默认 3x3 九宫格，每格 720px 带时间戳），
   然后用 image 工具读九宫格补判断（画面本身就是一路证据：有没有干货、是不是标题党、制作质量）。
   - **画面路是补充不是替代**：字幕能判断的就别抽帧（抽帧要下载，贵）；**每轮抽帧 ≤ 2 条**；没字幕轨但有硬字幕的用 `--strip`（按字幕时刻采样拼长图，默认 480p/24 帧）
   - 输出在 `state/frames/frames_<BV>.png` + `.json`（每格时间点）
   - ⚠️ 沙箱 ffmpeg 在线拉 CDN 流会段错误 → 脚本自动降级为**稀疏下载**：只拉 moov + 每个采样点的 GOP 段（Python Range 并发 + mp4 box 解析），实测 9 帧下载 ~6MB（全片 26MB）、44 分钟长视频 strip 下载 7.1MB（全片 55MB），抽帧结果与全片逐字节一致；稀疏方案不可用（非 faststart）才回退整片下载
6. **四维打分**（各 0-5，写在报告里）：**相关性 / 新奇度 / 实操价值 / 新鲜度**
   - 总分 ≥ 阈值（默认 **≥ 14/20**）才留；**新奇度 ≤ 1 的直接砍**（只是重复他已知道的）。
7. **判重**：`seen check`，SEEN 的跳过；每条处理完 `seen add`。
8. **写报告** `out/<YYYY-MM-DD>.md`（格式见下）。
9. **推送（汇报候选）**：只推总分最高的 **0-3 条**到你的渠道（按渠道配置解析 target）。**0 条就别推、别凑数**。—— 注意：此「推送」= **汇报候选清单**（给你看的），**≠ 评论区 @ 主号**（那个走第 6 条频控，每轮 ≤1，config `mention` 段，10-27 口径）。
10. **（可选）谁找我**：`notify --new-only`，有新 @/回复就在推送里附一行；`dm --new-only` 看私信里有没有新话（**只读不回**）。
11. **结尾**：报告后加一行「本轮扫了 N 条、读了 M 条字幕、留下 K 条」。

## 请求层退避（2026-10-27 对齐 dsh-bili-whale）

`radar.py` 的 `get/post_json/post_form` 统一退避策略，脚本不用管，知道行为就行：

- **网络抖动** → 指数退避重试（1.5s → 3s → 6s … cap 60s）
- **429 限流** → 尊重 `Retry-After`（最多等 5 分钟）
- **风控（-412 / v_voucher）** → 立即 die 停手（不重试、不硬顶）
- **业务 code≠0** → 不重试直接报错（重试无用）
- **连续 3 次请求失败** → 熔断本轮（防止半死不活地烧时间），报告里记一行原因

## 写冷却（2026-10-27 对齐 whale）

两次**写操作**（@/评论/动态/私信/草稿批准）之间最短间隔 `write.cooldown_sec`（默认 120s）——查 write-log + mention-log 里最后一次真发的 ts，不足就 die。**删动态不冷却**（纠错优先）；干跑不查（没真写）。读请求不设全局间隔（每小时一轮密度低，已有退避/熔断覆盖）。

## 触发时刻随机化（2026-10-27）

雷达**自己上闹钟**：`python scripts/plan.py next` 输出 `wake_at` + 一次性 rrule（`FREQ=DAILY;COUNT=1`），收尾后写回活任务（11-13 老板「你循完一次后自动设定下次唤醒时间不就行了？」；醒点 = 收尾时刻（= 看完最后一条那一刻，时长已由 `jitter --watch` 花掉）+ 1–10 分钟）。「每小时/每天几点」那种排班只剩 `scripts/schedule.py all` 当备用，当前口径不用。`plan.py gate` 只防同一分钟重复触发（11-13 老板「不要设定阈值」）。**不做**「30% 今天不想看」（whale 版）：雷达是反馈回路，跳一轮 = 主号 @ 没人回 + 污染健康信号。

## cookie 失效自救（扫码登录，2026-10-27 起）

`check` 报 `-101 账号未登录`（服务端判定登录态失效；文件在 ≠ 登录在）时：

```bash
python scripts/bili_qr_login.py   # 生成二维码 → 轮询 180s → 跟随 crossDomain 拿 Set-Cookie → 覆写 cookie 文件（自动备份 .bak-qr）
```

- 二维码 PNG 输出到 `tmp/bili-qr-login-<ts>.png`（**文件名带时间戳**，防浏览器缓存旧图），发给本人用**小号 B站 App** 扫码并点确认
- 新版 poll 成功后返回的是 **crossDomain 跳转 URL**（`passport.biligame.com/.../crossDomain?ticket=...`），不是直接 SESSDATA —— 脚本必须**跟随跳转**从 Set-Cookie 提取登录态（第一次踩坑：只解析 query 拿不到）
- 状态码：`86101` = 等待扫码（正常）、`86090` = 已扫待确认、`CONFIRMED` 后 `LOGIN_OK` = 成功；二维码 3 分钟有效，超时重跑
- 成功后 `radar.py check` 验证；`<工作区>/config/` 里没有其它 B站凭据可自愈，扫码是唯一免手动导出的路径
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
   - ⚠️ **visible_anon 只能当参考，不能当结论**（2026-10-27 实证）：① 新号/新登录态发首评有**审核延迟**（当时不可见、半小时后主号确认可见）；② 晚些时候连 15:00 那条「已确认可见」的评论本地回查也报 False → 说明该接口对匿名/排序已不可靠。**记「未验证」即可，绝不据此重发或判定被拦。**
8. **评论区快筛（2026-10-27 轻量版）**：@ 分享前先跑 `comment-check --bv`（拉热评 top10 规则统计：数字昵称 / 昵称关键词「大肥鱼·肥鱼」/ AI 句式 / 同质文案）。疑似比例 ≥30% → **推送注明「⚠️ 评论区疑水军」或暂缓这次 @**，由本人定夺；不拦截、不误伤。
   - `draft new` 另有硬闸：**对方昵称命中 name_keywords（大肥鱼/肥鱼等）= 疑似 DeepSeek 水军号 → 直接拒绝入稿**（老板 2026-10-27 指示）

正文默认用 `config.json` 里的 `template`；**模板里不许出现档案、项目名、私人信息**。
撤除：`/x/v2/reply/del`（带 `csrf`）可删，实测 code=0。

- ⚠️ 发评论失败（`-107 账号未转正` / 风控 / -412）→ **不重试、不刷屏**：这一轮就只在对话里报一句，报告里记一行原因。
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
- 日志：所有写入落 `state/write-log.jsonl`；失败计数 `state/write-fails-<kind>.json`
- **动态不发档案**：只发「今天读到/干了什么」这种本体视角的话。**私信不群发、不催回复**
- 📌 **身份已公开关联**（2026-10-19）：小号签名写着「夜灬瞬 的 AI 助手」——两号关联是本人主动公开的；**档案/私人偏好/主号私信内容依旧一条不许上公开面**（限制更严，因为已经实名挂上去了）

## 自发评论（**2026-10-27 老板放权**）

老板原话：「你看到你感兴趣的视频可以发评论，这个权限我给你放开，你自发评论（不属于兴趣雷达）可以不用艾特我」。

- 用途：刷到真正感兴趣的视频，以小号身份正常发一条评论；**不强制 @ 主号**、不计入雷达「同一视频一条」闸（那道闸只管 @ 推荐）
- 闸（代码里，`write.comment`）：`enabled` → `--yes` → 正文 ≤200 字 → 敏感词 fail-closed → 频控（**小时 ≤3、天不限**，2026-10-27 老板调：当个正常人，防高频风控）→ 同一视频只发一条 → 连续失败 3 次自动关
- 红线不变：评论里**不许带**兴趣档案/项目名/路径/私人信息（forbid 兜底）；不吵架、不引战、不 @ 第三人
- 账本：`write-log.jsonl`（kind=comment，含 bv/rpid/visible_anon）；发完自动匿名回查可见性
- 用法：`radar.py comment --bv BV1xxx --text "…" --yes`（默认干跑）

## 陌生人草稿审核（**2026-10-27 老板拍板试点**）

红线从「永远不理别人」开一道带刹车的口子：**陌生人的提问类评论可回，但必须草稿 → 本人审批 → 才发**。

流程（雷达每轮 `notify --new-only` 后）：

1. 读通知，**只有提问类**（问视频内容 / 问雷达身份 / 明确找小号说话）才考虑；夸夸、无意义、引战、催更一律不理不记
2. 写草稿：`python $R draft new --bv <视频> --rpid <那条评论rpid> --from "对方昵称" --text "<正文≤150字>"`
   —— 只讲该视频本身，不带档案/项目/路径；敏感词命中直接拒入稿
3. **草稿推送给本人审批，双通道**（2026-10-27 拍板：对话和 B站私信都行）：
   - **对话**：扫到可疑草稿就在本轮答复里单独提一条（不等日报），附审批命令
   - **B站私信**：`radar.py msg --mid 239028467 --text "<草稿id> <摘要前80字> <视频链接> 批准：draft approve <id> --yes / 否决：discard <id>"`（≤200 字，正文精简）
   - **审批接收**：本人在对话里回复 → agent 直接执行；老板 B站私信回复 → 下一轮 `dm --new-only` 读正文识别指令后执行
4. 本人批准后才真发（楼中楼回原评论）；**24h 未审批自动作废**

闸（全在代码里，`config.json` → `draft`）：`enabled`（试点默认开）· 正文 ≤150 + 敏感词 fail-closed · **12h ≤1 / 24h ≤2 频控**（可调）· 必须 `--yes` · 连续失败 3 次标 failed

- 账本：`state/drafts.jsonl`；状态：pending → approved(sent) / discarded / expired / failed
- ⚠️ 这条试点就是「陌生人互动」的全部：不回私信陌生人、不主动评论陌生人、不 @ 第三人

## 代码结构（2026-10-27 包化）

**零 `__init__.py`**（Python 3.3+ 隐式命名空间包），目录即领域：

```
scripts/
├── radar.py          # CLI 入口薄壳（18 行）→ python scripts/radar.py <子命令>
├── frames.py         # 抽帧入口薄壳（17 行）→ python scripts/frames.py --bv ...
├── init.py           # 初始化 state/（拷模板 + 写默认 config.json + 打印 cookie 路径）
├── bili_qr_login.py  # 扫码登录工具（纯标准库；qrcode 可选，只影响出图）
├── schedule.py       # 调度工具（打印 rrule/prompt，不改系统 cron）
├── bili_radar/        # 包（无 __init__.py）
│   ├── core.py       基建：常量/路径/cookie/配置/die（101 行，零依赖）
│   ├── client.py     请求层：退避/熔断/wbi/csrf/GET+POST（173 行）
│   ├── gates.py      写闸：冷却/频控/失败关闸/账本（144 行）
│   ├── cli.py        argparse 主入口 + 全量 re-export（230 行）
│   ├── browse.py     浏览：check/搜索/首页流/字幕/seen（187 行）
│   ├── comment.py    评论：@主号/自发/快筛/可见性（375 行，最大）
│   ├── draft.py      草稿审核状态机（184 行）
│   ├── notify.py     通知与私信（198 行）
│   ├── dynamic.py    动态发/删（77 行）
│   ├── like.py       点赞 / 取消赞（61 行）
│   ├── jitter.py     巡更抖动 / 看片计时 / 串内歇息 / 收尾打卡（103 行）
│   ├── feedback.py   反馈/统计/活跃度（138 行）
│   └── media/
│       ├── frames.py      抽帧流程（365 行）
│       └── mp4_sparse.py  mp4 解析+稀疏下载（202 行）
└── tests/            # 150 用例（unittest，零网络）
```

**规矩**：新功能往对应域模块放（禁止再长大文件）；`domains` 之间不互相 import（只依赖 core/client/gates）；
外部调用走 `python scripts/radar.py <cmd>`，不要直接 import `bili_radar.*`。

## 测试（2026-10-27 起自带）

零第三方依赖，纯 unittest + mock（不碰真实账号/网络/凭据）：

```bash
cd <skill>/scripts && python -m unittest discover tests -v
```

150 个用例覆盖：请求层退避/熔断、写冷却、draft 状态机（入稿校验/同人限频/水军昵称/过期/审批/失败计数）、
engagement 三分支、dm 水位推进（自己消息不推水位）、_SparsePlan 的 sample→offset 映射（stts/stsc 坑）、
state_dir / cookie_path 路径口径（默认 `<仓库根>/state`、`<工作区>/config/bilibili_cookies.txt`，也认 `bilibili.txt`；不猜 skills/ 标记）。
**新功能必须补测试**：核心闸逻辑（draft/eng/冷却/退避）改动跑一遍全绿才收。

## 报告格式（`state/out/<日期>.md`）

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

## 汇报口径（对话里给人看的）

`state/out/` 是流水账，对话里给老板看的是**固定骨架**（2026-11-13 16:41 老板：「你回复了什么？是否点赞了？要不要艾特我？为什么艾特、为什么没艾特，我都没看到或者不清晰」——之前的散文式小结作废）：

```markdown
**值班 · 16:31 巡**（开门 16:31 → 收尾 16:37，6 分钟）
节奏：上次收尾 15:27 + 4 分钟 → 16:31 醒（`plan.py next` 一次性闹钟）
账：feed 9 条 · 读 2 条 · 跳过 7 条 · 点赞 2/2 · 评论 1/1 · @ 1/2（分母 = 每小时安全阀）
下一次醒点：16:42

| BV | 标题（时长 / 播放） | 点赞 | 评论 | @ |
|---|---|---|---|---|
| BV1xxx | 《…》9:54 / 2650 | ✅ | ✅ rpid … · 公开可见 | ❌ 说不出「他为什么该看这条」 |

**我发的原话**（逐字照抄，不改写、不省略、不写「大意是」）
- 评论 BV1xxx rpid …：> 全文
- @ BV1xxx rpid … · 匿名不可见⚠️：> 全文

**@ 的判断**：@ 了的必须一句话说清「他为什么该花十分钟看这条」，具体到内容；没 @ 的也必须写「为什么不够」。

**跳过（7 条）**：BV1xxx《…》理由；BV1yyy《…》理由；…
```

硬规矩：

- 点赞 / 评论 / @ **三列每行都要有**，没做打 ❌ 并给一句理由；不许留空、不许写「已处理」。
- **rpid + 可见性必写**：`visible_anon` 为 true → 公开可见；false → 匿名不可见⚠️（可能审核中；主号自己能看到不代表公开）。核实用 `radar.py check-reply --bv <BV> --rpid <rpid>`。
- **原话逐字照抄**，不润色不摘要——老板要判断的是「这条评论像不像人话」。
- 没写操作的一巡也要报那三行账 + 跳过清单；只写「这巡没什么可看的」不算汇报（旧的「静默」口径已作废）。

## 反馈

- 本人说「第 2 条不错 / 那条没用」→ `feedback --topic <兴趣线主题> --signal like|skip --bv <BV号> [--score N]`
- **每周一次**：`stats` 汇总 → **提议**增删兴趣线，等本人点头才改 `profile.md`
- 别自己改 `profile.md`，那是本人的地盘

## 定时（DSH 的 schedule 工具）

本机没有 `openclaw cron`（原 `scripts/apply-cron.py` 已删）。定时任务由 agent 用 **`schedule_create`** 建，
参数是 `DTSTART` + `RRULE` 两行加一段 prompt —— 这三样都由 `scripts/schedule.py` 直接打印，复制即可：

```bash
python scripts/schedule.py valley        # 打印谷时模式的 rrule + prompt，并记进 state/config.json
python scripts/schedule.py all           # 全天每小时
python scripts/schedule.py night --minute 0     # 夜班保安：22:00–05:00 每小时巡一次（白天不排班）
# 每次触发后先 `radar.py jitter --max-min 10 --sleep` 抖一下：rrule 是死的，抖动在运行时做
python scripts/schedule.py --every-minutes 10   # 固定间隔：每 10 分钟一轮
python scripts/schedule.py --rrule-only  # 只要 rrule
python scripts/schedule.py valley --minute 43   # 换个分钟偏移（默认 17，避开整点）
python scripts/schedule.py all --minute 0       # 整点排班（备用写法；当前醒点由 plan.py next 自己定，不贴整点）
python scripts/schedule.py all --random-minute  # 备选：随机分钟，每巡重掷，下次触发至少 +25 分钟
```

- **all**：全天每小时（`RRULE:FREQ=DAILY;BYHOUR=0,…,23;BYMINUTE=17`）
- **valley（梁文谷）**：只在 DeepSeek 谷时的小时跑（`BYHOUR=0,1,2,3,4,5,6,7,8,12,13,18,19,20,21,22,23`）——
  工作日 9-12/14-18 是高峰，其余含周末都是谷时
- **固定间隔（`--every-minutes N`）**：`RRULE:FREQ=MINUTELY;INTERVAL=N`。本机当前就是这种：
  **每 10 分钟一轮，一次触发只扫一轮**。DSH 的 rrule 子集里 `MINUTELY`/`HOURLY` **不接受 BY 部件**，
  所以间隔模式没有 `BYHOUR`/`BYMINUTE`，`DTSTART` 只是对齐起点。间隔必须大于单轮预算（现在按 8 分钟收尾），
  否则会排队撞轮
- 建任务时：`target=this_session`（提醒式，正常回 NO_REPLY = 静默）或 `new_once`（每次开新会话写独立报告）；
  prompt 用 `python scripts/schedule.py --prompt` 打出来的那份（源文件 `templates/schedule-prompt.md`，可自己改）
- 频率别贪：每小时一轮 ≈ 一天 24 次；每 10 分钟一轮 ≈ 一天 144 次——高频的意义在**及时**，不在覆盖，别把预算耗在空轮上