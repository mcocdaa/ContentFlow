# ContentFlow Workspace Evolution Log & Kaizen Backlog

本文档是 ContentFlow 工作室的持久化经验库与渐进式升级清单，用于沉淀实测数据结论，并驱动空闲时段与定时任务下的持续微进化（每次认领 1 项，验证后提交 Git）。

---

## 一、 实测流水与爆款对比沉淀结论（Verified Empirical Insights）

1. **历史分区榜样本的封面明度与暗部面积**
   * 当时采样的 `rid=129` 榜首（789 万播放）与 `rid=119` 榜首（632 万播放），封面平均明度为 172.3–195.1，近黑区域（RGB 最大值小于 45）占 0.2%–0.8%。不同梗的样本范围见下方按日期记录的实测。
   * **我方旧版黑底网格封面**（`010/011` 修复前）：平均明度仅 `74.1 ~ 81.6`，死黑暗部占比高达 **`44.3% ~ 57.7%`**，在 B 站亮色双列信息流中呈现明显“课件黑屏感”。
   * **升级实测结果**：切换 `CoverDesigner` 全新 `vivid_scene` 高明度模式后，`008/010/011/012/013` 封面平均明度跃升至 **`155.7 ~ 182.43`**，暗部占比降至 **`7.1% ~ 9.4%`**，客观门禁 `Cover` 维度维持 **`20.0 / 20`** 满分（待下一周期跟踪 `tm_stars` 与点击率变化）。
2. **冷启动赛道与完播留存差异（基于 `bilibili_latest.json` 线上统计）**
   * `007`（纯娱乐宅舞 `BV1Uy4j6hE1T`）：`98` 播放、`13` 点赞（**`13.3%` 点赞率**、`2` 收藏、`5.0` 满星封面）。
   * `002` / `004`（静态白板硬核科普）：3 秒划走率分别达 **`72.22%`** 与 **`63.63%`**，官方封标仅 `2.0 ~ 3.3` 星。
   * **结论**：冷启动期必须以「强情绪反差 + 流行热梗 + 真动态热舞/剧情」为主攻赛道；技术科普须配合真实工具演示或剧情包装，避免纯站桩 PPT。
3. **当前核心外部听感、内存与生成底座演进实况**
   * **真实爆款伴奏体系已打通**：新增 `core/bgm_hunter.py`（`cli.py fetch-bgm`），通过 B 站 WBI 搜索与 DASH 高码率音频抽取生成 `48kHz` 立体声伴奏切片及侧链闪避混音，完整附带 UP 主/BVID【借物表】致谢，彻底告别单薄正弦波蜂鸣器。
   * **镜头节奏与 `O(1)` 内存流式引擎**：`EpisodeAssembler` 已从整段帧数组预加载重构为两帧滑窗流式管道（`probe_video_frame_info` + `stream_interpolated_60fps`），峰值帧缓存 `< 45 MiB` 零 Swap 暴涨；`VideoQualityGate` 将 `release_pyiqa_models(); gc.collect()` 纳入外层 `try...finally` 防泄漏。
   * **旗舰模型标准**：可灵 CLI SSVIP 积分充足，文生图/图生图锚点一律用 `kling-image-v3_0_omni`（2K+），I2V/T2V 一律用旗舰 `kling-video-v4_0`（1080p）或 `kling-video-v3_0_omni`，`motion_control` 用 `kling-video-v3_0`（1080p）；火山方舟 `ARK_API_KEY` 当前已过期（`InvalidSubscription`）。

<a id="trend-case"></a>

### 2026-11-20 ·《非凡之爱》同梗对照与双角色短片

B 站稿件详情的播放快照取于北京时间 2026-11-20 16:48。第一条把梗用于 AI 角色，第二条采用“都是正常人”的改编角度。公开播放流取 480p，按约 4 fps 采样。表中“变化”包含硬切和显著推近或构图变化。

| 样本 | 投稿时间（北京） | 快照播放量 | 实测时长 | 前约 18 秒变化/10 秒 | 全片变化/10 秒 | 封面平均明度 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [大肥鱼 × Claude 版](https://www.bilibili.com/video/BV1JrWJ6JERj/) | 11-08 19:42 | 1,062,523 | 63.48 秒 | 6.61 | 6.30 | 157.57 |
| [都是正常人版](https://www.bilibili.com/video/BV1wLs465EWe/) | 11-19 12:40 | 2,080,028 | 76.10 秒 | 3.87 | 4.60 | 158.42 |
| 本次双角色短片（交付母版） | — | — | 18.00 秒 | 6.11 | 6.11 | 180.44 |

两条样本在相隔 11 天的投稿里用了同一梗，支持尝试双人剧情。母版的节奏落在两条样本等长开头之间。样本经过热门筛选，本片的点击和留存仍需在公开后用账号数据验证。

母版实际采用三个 `kling-video-v4_0` 1080p 档图生视频镜头。下载的三段源片均为 1916×1080、24 fps，经 DIS 光流装配成 1920×1080、60 fps。全片 1080 帧，相邻显示时间戳间隔 16.666–16.667 毫秒。`freezedetect`（−50 dB、0.30 秒）检出 0 段近静止。最终音频为 −14.01 LUFS、−1.67 dBTP，质量门禁为 100/100。人工复看时曾发现台词指向的食物部位在画里看不清，重做末镜并同步调整配音与字幕后，才对这版母版复测。

### 2026-11-21 · 线上遥测与分群归因复盘（冷启动破圈策略转向）

* **账号与库存快照（`2026-11-21 09:15 CST`，零 PII 脱敏）**：粉丝 **`15`**、累计播放 **`558`**、点赞 **`31`**、收藏 **`3`**、评论 **`18`**；已公开 **`10`** 篇（含新完成置顶同步的 `014` `BV117sM6FEVL`）、定时过审待发 **`3`** 篇（`015` `BV12Fs36uECr` 11/21、`016` `BV1AWsh6sEQF` 11/22、`BV1PyyWzqE38` 11/23，均 `state=-40`，`0` 退回）。
* **分群归因实测（`cli.py benchmark --attribution`）**：新娱乐高明度热舞/整活赛道（`n=7`）vs 旧静态白板硬核科普赛道（`n=3`）— 平均播放 **`64.29` vs `36.00`**（**`1.79x`** / `+28.29`）、点赞率 **`6.67%` vs `0.93%`**（`+5.74%`）、平均封标星级 **`3.46★` vs `2.43★`**（`+1.03★`）、平均 3 秒划走率 **`29.91%` vs `51.51%`**（`-21.60%`）、平均完播率 **`41.40%` vs `47.17%`**；头部标杆 `011`（`BV198sw6oEHN`，`129` 播放 / `4.6★`）与 `010`（`BV121sw62EGg`，`129` 播放 / `3.7★`）。
* **冷启动瓶颈观察**：`013`（`BV18AWC6YE3M`）封标达 **`4.9★`**（`tm_pass_rate_pct=97.72%`）但初始推荐曝光极低（`10` 播放 / `2` 点赞 / 完播 `35.71%`）；`014`（`BV117sM6FEVL`）刚转公开处于冷启动初期（`1` 播放 / `1` 点赞，当前诊断 `2.0★`）。单纯 15–20 秒单人短舞缺乏角色羁绊与弹幕讨论议题，难以在 15 粉基数下突破次级推荐池与转粉瓶颈（同类转粉率中位数 `0.09%`）。
* **下阶段策略转向**：切向 **40–60 秒多 AI 角色群像喜剧短剧**（首推 `017` 大肥鱼 × Gemini娘合租运营系列，强化角色反差、剧情反转与弹幕/评论区投票互动），并同步推进 **双 AI 实时互动直播间（`K7`）** 作为实时留存与切片反哺短视频的引流漏斗。

### 2026-11-23 · 根除「小黄人变调/碎切镜」隐患、抢救 017 排期与交付 019 超 1 分钟赛博法庭长片

* **根因诊断与永久工程修复**：
  * **零小黄人保音高保护 (`core/bgm_hunter.py`)**：彻底移除 `concat_or_duck_segments` 中直接以 `np.interp` 线性抽样压扁超时配音导致音高飙升的逻辑；新增 `_time_stretch_preserve_pitch`（FFmpeg WSOLA `atempo` 保音高微调），并对超过 `max_tempo_ratio=1.18` 的台词抛出 `ValueError` 硬拦（已补 `test_concat_or_duck_segments_preserves_pitch_no_chipmunk` 校验 440Hz FFT 音高偏移 `<= ±20Hz`）。
  * **`>= 60.0s` 时长硬门槛与舒展切镜预警 (`core/quality_gate.py`)**：对第 `018+` 期及 `target_duration_sec >= 60` 企划实施 `duration_too_short` 阻断红线，严禁再生产超短视频；在 `_eval_visual_dynamics` 增加 `median_cut_gap_sec < 1.8s` 密切换告警（同步固化至 `AGENTS.md`）。
* **巡检恢复与 017 抢救实况**：
  * 恢复因重启中断的日巡：`cli.py sync-pins` 同步置顶 `015`（`BV12Fs36uECr`）与 `016`（`BV1AWsh6sEQF`），为 `015`/`014` 补齐 B 站原生 `neutral_mark` AI 声明（`ai_declaration_verified=True`），重新挂载每日 `17:00 / 19:00 CST` 常驻定时巡检。
  * **发布前热抢救 `017`（`BV1VaytzcEp9`，原定 `11/24 18:30 CST`）**：下调 `017` 全部 `beat_punch_bpm=None`、调整自然语速至 `1.06/1.08` 并精简 10 句对白使其自然落窗（经 `/tmp/ep017_rescued_sample.wav` 人工听审无变调），重跑门禁 **`100.0 / 100 [S / VIRAL_READY]`** 并完成 `edit_archive` 视频热替换与 `verify_archive_submission` 回读确认。
* **019 旗舰剧场版 2D 交付（`019_cyber_variety_court_server_busy_trial`，`BV1hsyHzrEzW`）**：
  * **全片 `70.12s`（严格 `>= 60s`） · 舒展中位切镜 `4.00s` · `-14.0 LUFS`**：复用云端 3 主角 Element 与可灵 4.0 原生中文演戏配音（7 幕 WAV + 7 张抽帧联系表全人工核听核看零瑕疵）、`O(1)` OpenCV DIS 60FPS 装配与 `vivid_scene` 高明度封面（`dark<45=12.50%`），通过 `cli.py quality-check --threshold 90`（**`94.0 / 100 [S / VIRAL_READY]`**、`0` 阻断）并成功排期 **`2026-11-26 18:30:00 CST`**（`ai_declaration_verified=True`）。

### 2026-11-23 17:00 CST · 发布前巡检与 Kaizen 切片 K6（多角色情感声线路由器）交付

* **17:00 CST 日巡核验（零 PII）**：
  * **库存与合规回读**：账号粉丝 `15`、累计播放 `695`、点赞 `35`、收藏 `3`、评论 `21`；已公开 `12` 篇置顶全部同步（`already_pinned`），未来 4 天定时排期（`11/23 BV1PyyWzqE38`、`11/24 BV1VaytzcEp9`、`11/25 BV1CqyhzWEhR`、`11/26 BV1hsyHzrEzW`）**`4/4` 均已过审 (`state=-40`) 且原生 AI 声明回读 Verified (`creation_statement_id=101`)**、`0` 退回；评论区无新增高危反馈。
  * **分群归因（`cli.py benchmark --attribution`）**：新娱乐高明度赛道（`n=9`）平均播放 `65.11` vs 旧静态白板（`n=3`）`36.33`（**`1.79x` / `+28.78`**），点赞率 `5.80% vs 0.92%`（`+4.88%`），封标星级 `3.43★ vs 2.43★`（`+1.00★`）。
* **Kaizen 切片 K6 完工**：由于排期存货充足（`4 >= 2` 天），认领并完成 `K6` 多角色情感配音配置档与批量对话合成引擎（详见下方 `K6` 记录）。

### 2026-11-23 19:00 CST · 发布后巡检（BV1PyyWzqE38 公开置顶与流水归因）与 Kaizen 切片 K9 交付

* **19:00 CST 日巡核验（零 PII）**：
  * **库存、置顶与合规回读**：账号粉丝 `15`、累计播放 `695`、点赞 `35`、收藏 `3`、评论 `22`；已公开 `13` 篇（原有 `12` 篇置顶全部 `already_pinned`，今晚 `18:30 CST` 新公开 `BV1PyyWzqE38` 已补发并置顶零 `@` 互动评论 `rpid=321095682417`，原生 AI 声明回读 `Verified` `creation_statement_id=101`）；未来 3 天定时排期（`11/24 017 BV1VaytzcEp9`、`11/25 018 BV1CqyhzWEhR`、`11/26 019 BV1hsyHzrEzW`）**`3/3` 过审 (`state=-40`) 且 AI 声明全部回读 `Verified`**、`0` 退回，无新增紧急观众反馈。
  * **分群归因（`cli.py benchmark --attribution`）**：新娱乐高明度赛道（`n=10`，含刚转公开的 `BV1PyyWzqE38`）均播 `58.60` vs 旧白板（`n=3`）`36.33`（**`1.61x` / `+22.27`**），点赞率 `5.80% vs 0.92%`（`+4.88%`），封标星级 `3.09★ vs 2.43★`（`+0.66★`），头部标杆 `BV198sw6oEHN`（`131` 播放 / `4.5★`）。
* **Kaizen 切片 K9 完工**：排期存货充足（`3 >= 2` 天），完成免费声线纠错（弱音 Edge-TTS 合法化与音调参数透传）及 B 站回读抗限流重试机制（详见下方 `K9` 记录）。

### 2026-11-24 · Swarm 双轨并行：020 打歌棚长片排期交付 + K10 三人铁三角主题直播企划与舞台升级

* **第 020 期旗舰交付（`020_trio_ai_karaoke_cat_fish_battle_mv`，`BV196yRzzELs`）**：
  * **全片 `70.12s`（严格 `>= 60s`） · 60FPS · `-14 LUFS`**：7 幕可灵 4.0 原生中文配音与说唱＋动态闪避 CC0/Free BGM（`BV1254y1V7cJ` / `BV1o4KwzPERi`），亮色 `vivid_scene` 双比例封面（`V_mean=178.04`、`dark<45=11.84%`），门禁 **`91.0 / 100 [S / VIRAL_READY]`**（`0` 阻断，Technical `20/20`、Audio `20/20`、Compliance `20/20`）；已成功定时 **`2026-11-27 18:30:00 CST`**（`aid=117669185526485`、`ai_declaration_verified=True`、`creation_statement_id=101`、`credits_present=True`、`aigc_present=True`），并登记至 `library/creative_ledger.json`；可灵账户剩余 `908` 积分（钻石会员）。至此未来定时排期已延展至 **`11/24–11/27` 共 4 天**（`017`–`020`）。
* **直播企划与舞台升级（K10）**：完成 `docs/LIVE_PROGRAM_TRIO_SHOW.md` 三人 60 分钟主题节目单与 `core/live_studio/` 三主角同台、实时弹幕公投进度条与涨粉庆祝横幅升级（详见下方 `K10` 记录），全仓串行门禁 **`105 passed in 188.71s`**，并已恢复每日 `17:00 / 19:00 CST` 常驻日巡任务。

### 2026-11-24 · Swarm 三方向并行破圈实验交付（021 AI博弈 / 022 科幻微电影 / 023 AI开源监工工具）与原创借物表门禁加固

* **历史审计结论与破圈策略**：对比过去 13 条投稿流水与 B 站实时破圈标杆（如 `BV1Poyaz8Ep4`、`BV1k9ut6GESG`、`BV1fJ3M6DELF`）后，确认旧系列 `015–020` 过度复用自嗨内梗、固定三人角色与同类双胶囊三行封面。经 Swarm 三工兵协同并严格通过 `LOCAL-HEAVY-LOCK` 串行重资源后，一次性交付并排期 3 条零旧梗差异化赛道试水稿件（排期已覆盖至 `2026-11-30`，可灵账号余额 `150` 积分，零 PII）：
  * **方向一 · Ep `021`（`021_ai_game_theory_betrayal_experiment`，`BV1nuyZztEfY`）**：5 个独立隔离 AI 零剧本争夺 1000 万真实博弈实验纪录片（终局鸽鹰双向发毒誓后双双按下 `STEAL` 清零）；`175.33s` 1080P 60FPS，`98.5 / 100 [S / VIRAL_READY]`，`tid=231`（计算机技术），定时 `2026-11-28 18:30:00 CST`（`state=-40`，`ai_declaration_verified=True`）。
  * **方向二 · Ep `022`（`022_ai_auto_reply_day7_scifi_film`，`BV1JGyZzxE2F`）**：100% 原创科幻悬疑微电影《假如你的AI学会替你回微信：7天后竟没人发现你失踪了》（可灵 4.0 电影感长镜头 + 60FPS 深夜手机交互UI + 极简电影海报封面，无竞赛后缀）；`89.000s` 1080P 60FPS，`90.5 / 100 [S / VIRAL_READY]`，`tid=47`（短片·手书），定时 `2026-11-29 18:30:00 CST`（`state=-1` 复核中，`ai_declaration_verified=True`）。
  * **方向三 · Ep `023`（`023_cyber_focus_warden_tool`，`BV1zVyZzREEC`）**：可真实本地运行的纯 Python 标准库 MIT 开源小工具《赛博防摸鱼毒舌监工》（`projects/023_cyber_focus_warden_tool/app/`，支持切屏 3 秒三级警报与罪证小票，端到端冒烟实测通过）；`121.70s` 1080P 60FPS 产品实测片，`95.5 / 100 [S / VIRAL_READY]`，`tid=230`（软件应用），定时 `2026-11-30 18:30:00 CST`（`state=-40`，`ai_declaration_verified=True`）。
* **门禁共性升级（`K11`）**：完善 `core/quality_gate.py` 原创作品借物表署名识别规则并补齐回归单测（详见下方 `K11` 记录）。

### 2026-11-25 17:00 CST · 发布前巡检、直播冷启动分区对标与 K13 零中断热切换交付

* **17:00 CST 日巡核验（零 PII）**：
  * 账号粉丝 `15`、累计播放 `896`、点赞 `37`、收藏 `3`、评论 `24`；已公开 `14` 篇（匹配项目 `13` 篇置顶全部 `already_pinned`），未来 6 天定时排期（`11/25 018 BV1CqyhzWEhR`、`11/26 019 BV1hsyHzrEzW`、`11/27 020 BV196yRzzELs`、`11/28 021 BV1nuyZztEfY`、`11/29 022 BV1JGyZzxE2F`、`11/30 023 BV1zVyZzREEC`）**全部 `state=-40` 过审且连同 `017` `7/7` 回读 `ai_declaration_verified=True`（`creation_statement_id=101`）**、`0` 退回。
  * **分群归因（`cli.py benchmark --attribution`）**：新娱乐高明度赛道（`n=11`）均播 `71.55` vs 旧白板（`n=3`）`36.33`（**`1.97x` / `+35.22`**），点赞率 `4.57% vs 0.92%`（`+3.65%`），封标星级 `3.34★ vs 2.43★`（`+0.91★`），头部单篇 `BV1VaytzcEp9`（`133` 播放 / `3.8★`）。
* **直播冷启动分区对标与晚间档期衔接（`output/live_world_03` → `live_world_04`）**：
  * 下午 `90` 分钟 2D 工坊实播（`430` 句播报、`0` Paid DeepSeek API 调用）结合实时榜单验证：`371` 分区在播房间超 `700` 间、冷启动极易沉底；`1062`（`AI应用·机器人`）当前全区仅 `36` 间在播（`top10_online_floor=626`、首页直达全部房间）且同赛道「大肥鱼」题材活跃。已预上传全新 `1062` 专属 `4:3` 亮色封面 `output/live_world_04/live_cover_1062_v3_4x3.jpg`（`800×600`、`mean_luma=192.9`、`dark<45=8.08%`），与今晚 `18:30 CST` `018` 期发布精准错峰 `2` 分钟（`18:28 CST`）开播承接视频头像在播导流。

---

### 2026-11-26 · 025–027 的真实操作演示、等比输出与投稿回执

| 项目 | 本次已有证据 | 可复用做法 |
| --- | --- | --- |
| 025 透明 PNG 动画课 | 180 秒，10800 帧。更换封面并更新借物表后，本地质量门禁 92.5/100，零阻断。旧方形图标相对 368 × 420 原画纵向多拉长 42.2%。 | 课程与独立实验室共用像素取样和脚底支点。两版封面改用[原画封面生成器](../projects/025_whale_png_motion_lab/design/cover_base.py)，以双眼中心距除以双眼中点到嘴的距离，原画为 2.171，新本地及线上双封面约 2.173。 |
| 026 双比例封面裁切 | 80 秒，4800 帧，本地质量门禁 96/100，零阻断。2720 × 1536 原画上下各裁 3 像素，以 12/17 的统一倍率生成母图。 | 从同一母图裁出 4:3。用方图、竖图、超宽图等测试开发页和独立 HTML 的两种 PNG 导出，测量同一圆的水平、垂直直径。 |
| 027 鲸鱼专注钟 | 原画头像版成片 600 秒、36000 帧、−14.10 LUFS，本地质量门禁 90/100，零阻断。离线单文件可启动、暂停、继续、重置并保存本地速记。 | 按真实时间完成十分钟跟练。四个阶段分成 20 个 30 秒片段，以全片帧号计算秒数。检查首帧 10:00、倒数第二帧 00:01、最后一帧 00:00。 |

三稿创作中心回读如下，时间均为北京时间。各稿标题、标签、简介、两版线上封面和原生「含AI生成内容」声明（本次 ID 为 1）均已核对。充电关闭，允许转载。

| 期号 / BVID | 平台分区 | 平台保存的档期 | 11 月 26 日回读状态 |
| --- | --- | --- | --- |
| 025 / `BV11NyUzuEAj` | 知识（1010） | 12 月 1 日 18:30 | 17:44:56，通过审核，等待发布（−40）。封面及借物表在原稿号下更新。 |
| 026 / `BV1Pc1EzsEUj` | 科技数码（1012） | 12 月 2 日 18:30 | 17:50:08，通过审核，等待发布（−40）。 |
| 027 / `BV1Cw1EzXEF7` | 科技数码（1012） | 12 月 3 日 18:30 | 18:05:15，通过审核，等待发布（−40）。 |

025 首次接口提交返回 `-412`，026 首次接口提交返回通用参数错误 `21001`。分别查清队列后，通过官方编辑器提交并按新 BVID 回读。系统测试 157 项通过，Ruff 格式、静态检查及 mypy（52 个文件）通过。网页演示和查稿入口见[演示库](../library/motion_cards/README.md)及[定时投稿与回读](../.agents/skills/bilibili-viral-studio/references/scheduled-release.md)。

## 二、 已完成进化记录（Completed Slices）

* ✅ **E1 — 礼仪与比例双重护栏**：清空所有预设及线上简介中的群发 `@股东`；在 `core/quality_gate.py` 中新增 `DAR` vs 分辨率拉伸一票否决项、`@` 群发扣分校验，以及基于 `library/creative_ledger.json` 的近 3 期题材防重校验。
* ✅ **E2 — 008 热替换重制 & 010/011 新梗实景交付**：告别站桩拉伸旧版，上线 `008` 机房伪监控偷跳宅舞（`BV18AWC6YEPa`）、`010` 司凤战损吐蓝血×邦吧星奇摇（`BV121sw62EGg` 兑现「白的黑板」点单并单点礼貌回复）、`011` 社畜弱音《回答我》18:30 街头潮舞（`BV198sw6oEHN`，11/18 18:30 定时发布）。
* ✅ **E3 — 共性工程代码化**：落地 `core/competitor_benchmark.py`（`cli.py benchmark` 对标爆款客观指标）、`core/episode_assembler.py`（`cli.py assemble-episode` 统一 60FPS 光流 + `Beat Punch-In` 鼓点切镜 + `-14 LUFS`）、`core/analytics.py` 去硬编码重构，以及 `core/cover_designer.py` 的 `vivid_scene` 高明度封面引擎并完成 `008/010/011` 线上封面热更新。
* ✅ **E4 — 真实爆款伴奏引擎 (`core/bgm_hunter.py`) + O(1) 流式低内存管线 + 可灵 4.0 旗舰升级 + 全线稿件热升级 (`008/010/011/012`)**：
  * 全线热升级 `008`（真《Telepathy》原曲踩点）、`010`（986万爆款《司凤版雨爱》邦吧原声 + 138 BPM 切镜）与定时稿 `011`（真 Phonk + 街头潮舞原声，11/18 18:30）；
  * 采用旗舰 `kling-video-v4_0` + `kling-video-v3_0` + 真《大展鸿图》二创原声交付 `012_dafeiyu_dazhanhongtu_villa`（`98.0 / 100 [S / VIRAL_READY]`，封面明度 `161.89`、暗部 `7.7%`），热替换原旧白板排期 `009`（`BV1hwWC6PEYu`，已过审 `state=-40`，11/17 18:30 发布），并将 `003`（`BV18AWC6YE3M`）延后至 11/19 18:30。
* ✅ **E5 — `014/015` 排期交付、定型角色参考锁、`CoverDesigner` 满画幅 Rim 辉光修复与遥测自动脱敏**：
  * **定型角色参考锁**：沉淀官方定型立绘至 `library/characters/gemini_neko/`（`fisharchive.cc` NO.004 Gemini娘），确立主力角色一律通过 `kling image_to_image`（`kling-image-v3_0_omni`）锁定锚点并清理旧版抠图缓存的硬规范。
  * **`CoverDesigner` 满画幅辉光修复**：修复 `core/cover_designer.py` 中 `rim_alpha` 局部裁剪模糊边缘问题，升级为满画幅 `rim_alpha` 模糊 + `hero_top_ratio=0.97` 构图，消除高明度实景封面描边切边瑕疵。
  * **遥测 PII 自动脱敏加固**：在 `core/analytics.py`（`BilibiliAnalytics.generate_report`）中先使用原始账号名运行 `build_optimization_directives` 过滤自评论，再将 `account.uid` / `account.uname` / `account.mid` 及评论区 UP 主本人 `uname` 统一脱敏为 `"<REDACTED>"` 后写入 `bilibili_latest.json` 与 `bilibili_growth_report.md`（已补全 `tests/test_publisher.py` 单测并完成线上实测验证）。
  * **排期交付与线上热替换**：
    * `014`（`BV117sM6FEVL`，排期 `2026-11-20 18:30 CST`，线上状态 `[通过审核，等待发布]`）；
    * `015`（`015_gemini_neko_cyber_worker_vlog`，`BV12Fs36uECr`，排期 `2026-11-21 18:30 CST`，线上热替换重制版已过审 `[通过审核，等待发布]`；质检 **`100.0 / 100 [S / VIRAL_READY]`**，封面平均明度 **`160.05`**、暗部 `<45` **`8.0%`**、切镜节奏 **`5.48 cuts/10s`**）。

---

## 三、 待推进微改进队列（Prioritized Kaizen Queue）

每次空闲唤醒或空闲收尾时，按顺序认领 **1 项**实现、验证并更新此处状态：

* ✅ **K0 — 2026-11-19 18:30 CST 前用全新 013（可灵 4.0 + 真伴奏 60FPS）热替换旧白板存货 003**
  * 已交付全新 `013_yowane_rooftop_lixicheng_march`（早八弱音晴空樱花天台×《李羲承进行曲》`BV1bsXQYAEn4` 真原声 60FPS 多景别切镜，门禁 **`94.0 / 100 [S / VIRAL_READY]`**、`0` 阻断，`vivid_scene` 封面平均明度 **`182.43`**、暗部 **`7.55%`**），热替换原 `003` 定时稿 **`BV18AWC6YE3M`**（`aid=117612847570833`，`dtime=1795084200` -> `2026-11-19 18:30 CST`，已过审 `state=-40`）；线上 11/17 (`012` `BV1hwWC6PEYu`)、11/18 (`011` `BV198sw6oEHN`)、11/19 (`013` `BV18AWC6YE3M`) 三支定时排期已 100% 清零老旧静态白板 PPT。
* ✅ **K1 — 真实爆款伴奏提取与多轨侧链闪避混音增强**
  * 已由 `core/bgm_hunter.py`（`cli.py fetch-bgm` + `concat_or_duck_segments`）及双侧链闪避/冲击低音合成落地并应用于 `008/010/011/012/013`。
* ✅ **K2 — 黄金前 2 秒综艺花字与动态贴纸开场钩子**
  * 已在 `core/episode_assembler.py` 落地 `EpisodeSpec.hook_banner_text` / `hook_banner_sec`（流式合成前单次预渲染 `< 1 MiB` `O(1)` 撞色胶囊花字 RGBA 图块 + 前 `0.18s` 弹出缓动，`t >= hook_banner_sec` 零拷贝透传），补充单测 `test_episode_assembler_hook_banner_overlay`（全仓 **`49 passed`** Pytest 100% 通过），并已在 `013` 成片前 `1.6s` 实装验证。
* ✅ **K3 — 发布后 24h/72h 流水自动归因与对比回顾脚本**
  * 已落地 `cli.py benchmark --attribution`（commit `24d41e6`），自动读取脱敏遥测快照统计不同分群的播放量、点赞率、`tm_stars`、`crash_rate_pct` 与 `full_play_ratio_pct`。
  * **线上实测归因结果（`2026-11-19 18:50 CST` 快照，已发布 `9` 篇 + 定时待发 `2` 篇，零 PII）**：
    * **新娱乐高明度热舞/整活赛道（`n=6`）** vs **旧静态白板硬核科普赛道（`n=3`）**：平均播放 **`71.33` vs `35.00`**（**`+36.33` / `2.04x`**）、点赞率 **`6.31%` vs `0.95%`**（**`+5.36%`**）、平均封标星级 **`2.87★` vs `2.43★`**（**`+0.44★`**）、平均 3 秒划走率 **`34.49%` vs `51.51%`**（**`-17.02%`**）、平均完播率 **`51.89%` vs `47.17%`**（**`+4.72%`**；其中已沉淀数据的 `010/011/012` 完播率达 **`82.87% ~ 88.33%`**）。
    * **头部标杆**：`BV121sw62EGg`（`010`，`128` 播放 / `4.69%` 点赞率 / `3.7★` / `82.87%` 完播）与 `BV198sw6oEHN`（`011`，`120` 播放 / `5.00%` 点赞率 / `4.5★` / `87.50%` 完播）。
* ✅ **K4 — 外部真音乐（MiniMax Music / Suno）与情绪语音（MiniMax Speech / Fish-Audio）路由器插件位**
  * 已落地 `core/audio_router.py`（`AudioGenerationRouter`、`SpeechRequest`/`SpeechResult`、`MusicRequest`/`MusicResult`、`ProviderStatus`），支持语音路由优先级 `minimax_speech -> fish_audio -> local_kokoro`（惰性加载 `LocalNeuralTTS` 且 `finally` 必调 `tts.close()`）与音乐路由优先级 `minimax_music -> suno -> bilibili_bgm_hunter`（惰性加载 `BilibiliBgmHunter`），零 Key 或上游 HTTP 异常时自动平滑降级，`get_status()` 与错误日志严格脱敏零密钥泄露；
  * 已同步更新 `config/settings.py`、`.env.example`、`cli.py audio-router-status [--json]` 与 `tests/test_audio_router.py`（9 项全 Mock 离线单测，零 PyTorch/网络依赖）；全仓串行门禁通过（`ruff format --check .` / `ruff check .` / `mypy core cli.py` / `pytest -q` **`60 passed`**）。
* ✅ **K5 — B 站原生 AIGC 声明（`neutral_mark`）投稿/回读校验（`verify_archive_submission`）与投稿回执 PII 自动脱敏（`--dry-run` 安全加固）**
  * 已落地 `core/publisher.py`（`BILIBILI_AI_NEUTRAL_MARK = "作者声明：该视频使用人工智能合成技术"`、`BilibiliUploader.submit_archive` / `upload_to_bilibili_api` / `edit_archive` 的向后兼容 `ai_declaration` 与 `neutral_mark` 透传及两阶段 `21001` 降级、`verify_archive_submission(aid)` 14 项零 PII 只读回验、`redact_auth_status` 统一将 `publish_manifest.json` 与 `advisor_receipt.md` 中的 `mid`/`uid`/`uname`/`dede_userid` 脱敏为 `<REDACTED>`）与 `cli.py publish`（`--ai-declaration`/`--no-ai-declaration`、`--neutral-mark`，且 `--dry-run` 强制锁定 `execute_upload=False` 与 `remote_schedule=False` 杜绝误传）；
  * 已补全 `tests/test_publisher.py`（`20 passed` 覆盖原生声明、回验、PII 脱敏与 `--dry-run --remote-schedule` 零上传安全）；全仓串行门禁通过（`ruff format --check .` `62 files` / `ruff check .` / `mypy core cli.py` `29 source files` / `pytest -q` **`65 passed`**）。
* ✅ **K6 — 多角色高表现力情感配音接入（通过 `core/audio_router.py` 激活 MiniMax Speech / Fish-Audio，打造大肥鱼/Gemini娘/弱音专属声线）**
  * 已落地 `CharacterVoiceProfile`（`dafeiyu` / `gemini_neko` / `yowane_haku` 三角色完整配置档与中英别名解析 `resolve_character_profile`）、`EmotionSpec` + `resolve_emotion_spec`（覆盖 `hype`/`deadpan`/`破防`/`吐槽` 等中英直播情绪映射至 MiniMax 合法标签与 Fish-Audio 表现力标签，并强制自然语速包络 `[0.80, 1.18]` 绝无“小黄人”变调）、`DialogueLine`/`DialogueResult` 串行多角色批量合成及零密钥/零 Fish Reference ID 泄露的 `dialogue_manifest.json` 导出；
  * 已同步扩展 `config/settings.py`（`AUDIO_ROUTER_ENV_VARS` 环境变量映射）、`.env.example`、`cli.py synthesize-speech` 子命令、`cli.py audio-router-status`（展示角色声线表且严格脱敏）及 `tests/test_audio_router.py`（新增 5 项全 Mock 离线单测）；全仓串行门禁通过（`ruff format --check .` `76 files` / `ruff check .` / `mypy` `38 source files` / `pytest -q` **`96 passed in 265.72s`**）。
* ✅ **K7 — 双 AI 实时互动直播间 MVP（`core/live_studio/` 弹幕监听 + 双重合规风控 + OBS 透明舞台 + 高光自动打点切片）**
  * 已落地纯轻量异步包 `core/live_studio/`（仅依赖标准库 + `aiohttp` + `httpx` + `pydantic`，零 PyTorch / GPU 占用）：`safety.py`（`LiveComplianceGuard` 双向输入/输出风控，拦截 PII/Cookie/UID/手机号/邮箱/开盒、中英 Prompt Injection、NSFW/政治/网暴与 `@` 提及，内置强制 `GB 45438-2025` 标识与角色内兜底台词）、`danmaku.py`（16 字节大端 B 站直播二进制帧编解码与受限 `proto_ver=2` zlib 解压、无 UID `DANMU_MSG`/`SEND_GIFT`/`INTERACT_WORD` 解析、匿名访客 `BilibiliDanmakuClient` 与离线 `MockDanmakuSource`）、`director.py`（`DualAILiveDirector` `gift > danmaku > enter > idle` 优先级抢占、可插拔 `OpenAICompatibleResponder` + 零 Key 喜剧对话库兜底、`HighlightTracker` 脱敏 JSONL 与 60–90 秒 `ffmpeg` 切片清单生成）及 `stage_server.py` + `stage.html`（`1920x1080` 高明度 OBS Browser Source 透明舞台、白名单立绘路由防穿越、纯 `textContent` 防 XSS）；
  * 已配套 `scripts/launch_live_mvp.py`（支持 `--mode mock|live`、`--record-highlights`、`--duration-sec` 与低内存巡检）、`docs/LIVE_PLAN_DUAL_AI.md` 运营手册及 `tests/test_live_studio.py`（`12 passed` 离线+WebSocket 单测）；全仓串行门禁通过（`ruff format --check .` `70 files` / `ruff check .` / `mypy core cli.py scripts/launch_live_mvp.py` `35 source files` / `pytest -q` **`77 passed`**）。
* ✅ **K8 — 100% 无头零麦克风全自动 B 站直播引擎 + 非特权 Docker 沙箱（`core/live_studio/bilibili_live_api.py` + `headless_streamer.py` + `Dockerfile.live`）**
  * 已落地全自动无头直播链路：`core/live_studio/bilibili_live_api.py`（`BilibiliLiveController` 封装 `GetInfo` / `Room/update` / 非致命封面上传 / `startLive` / 幂等 `stopLive`，遇到 `code=60024` 自动生成官方人脸认证二维码 `output/live_face_auth_qr.png` 绝不绕过；`RoomStatus`/`StartLiveResult`/`scrub_rtmp_secrets()` 全链路将 RTMP 推流地址、串流码、`room_id`、`uid` 与 Cookie 脱敏为 `<REDACTED_RTMP_URL>` / `<REDACTED>`）、`core/live_studio/headless_streamer.py`（`HeadlessStageRenderer` 1920x1080@30FPS 定型大肥鱼×Gemini娘透明抠图舞台 + 活跃发言光环 + 音频波形 + `15 / 1,000 粉` 进度条 + 右上角永久 `本直播间由 AI 实时驱动互动 · GB 45438-2025` + 脱敏弹幕墙与高对比字幕；`SyntheticAudioMixer` 100% 合成 `s16le` 48kHz 立体声双角色 `edge-tts` + 离线纯 NumPy 旋律回退 + Lo-Fi 自动闪避 BGM，每视频帧精确对齐 `1600` 样本 = `6400` 字节；`HeadlessLiveStreamer` 单 `ffmpeg` 双 OS 管道直推、自动检测 `h264_nvenc` CBR `4500k` 并回退 `libx264`，全程 `try...finally: stop_live` 与高光切片清单导出）、`scripts/launch_headless_live.py`、`Dockerfile.live`（`python:3.12-slim` + `ffmpeg` + `fonts-noto-cjk` 非 root `UID 10001` 零音频设备镜像）及 `docs/LIVE_PLAN_DUAL_AI.md` 升级；
  * **安全与实测验收**：强制零麦克风审计（`grep -rnE "/dev/snd|alsa|pulse|pyaudio|sounddevice" core/live_studio/ scripts/launch_headless_live.py Dockerfile.live` -> **`0` 命中**）；20 秒无头干跑实测达标（`h264_nvenc` `1920x1080` `30/1fps` `yuv420p` `4594 kbps`，`aac` `48000Hz` 立体声，精确 `20.000s`，`mean_volume=-19.5 dB` / `max_volume=-3.1 dB`，抽帧视觉与高光切片清单均人工核验通过）；补全 `tests/test_headless_live.py`（`11 passed`，含 `K7+K8` 共 `23 passed`），全仓串行门禁通过（`ruff format --check .` `74 files` / `ruff check .` / `mypy core cli.py scripts/launch_live_mvp.py scripts/launch_headless_live.py` `38 source files` / `pytest -q` **`88 passed`**）。
* ✅ **K9 — 免费声线纠错（弱音 Edge-TTS 合法化与音调参数透传）与 B 站回读抗限流重试机制**
  * 已在 `core/audio_router.py` 新增 `VERIFIED_FREE_EDGE_TTS_VOICES` 实测免费声线集合与 `CharacterVoiceProfile.edge_tts_pitch`，将 `yowane_haku` 的无效 Azure 专属声线 `"zh-CN-XiaohanNeural"` 修正为已验证免费 `"zh-TW-HsiaoYuNeural"`（`-4Hz`），并为 `dafeiyu`（`-2Hz`）与 `gemini_neko`（`+4Hz`）配置独立音高区分；在 `core/local_tts.py`（`_synth_edge_tts`、`synthesize_text`、`_synthesize_scenes_inprocess`、`synthesize_scenes`、`_cli_main`）与 `cli.py audio-router-status` 全链路向后兼容透传 `edge_pitch`（保留 `inspect.signature` 检测兼容旧版 3/4 参测试替身）；
  * 已在 `core/publisher.py` 为 `BilibiliUploader.verify_archive_submission` 增加瞬时限流/空响应（`-509`/`JSONDecodeError`/`ConnectionError`）指数退避重试，并新增 `verify_archives_batch` 串行批量节奏控制与脱敏兜底返回；
  * 已在 `tests/test_audio_router.py` 与 `tests/test_publisher.py` 补齐离线全 Mock 单测；全仓串行门禁通过（`ruff format --check .` `76 files` / `ruff check .` / `mypy core cli.py scripts/launch_live_mvp.py scripts/launch_headless_live.py` `38 source files` / `pytest -q` **`98 passed in 189.48s`**）。
* ✅ **K10 — 三人铁三角全自动直播企划与舞台/实时投票/涨粉庆祝升级（`docs/LIVE_PROGRAM_TRIO_SHOW.md` + `core/live_studio/` + `scripts/launch_headless_live.py`）**
  * **节目企划文档**：新增 [LIVE_PROGRAM_TRIO_SHOW.md](LIVE_PROGRAM_TRIO_SHOW.md) 并在 [LIVE_PLAN_DUAL_AI.md](LIVE_PLAN_DUAL_AI.md) 建立交叉引用，明确「18:30 投新片 + 19:00–20:00 铁三角直播接力 + 下播高光切片反哺」60 分钟四段式节目单、可选大模型 API 接入指南与 24 GiB 内存错峰规约；
  * **三人舞台与互动引擎**：在 `director.py`、`safety.py`、`headless_streamer.py`、`stage_server.py`、`__init__.py` 与 `scripts/launch_headless_live.py` 落地第三位主角 `yowane`（弱音ハク，`zh-TW-HsiaoYuNeural -4Hz` + 专属中低音离线声部）、`LivePollState` 实时弹幕公投进度条（按昵称去重改投 + 飙升标星）、`notify_follower_count` 涨粉金色横幅与优先台词、默认 `--cast trio` 与自定义 `--poll-topic` / `--poll-options`；
  * **严格门禁与预览验收**：零麦克风词法审计 `0` 命中；15 秒 `--cast trio` 本地无头预览（`h264_nvenc` `1920x1080 @ 30fps` + `48kHz` 立体声）及抽帧视觉均人工核验通过；补齐 `tests/test_live_studio.py` 与 `tests/test_headless_live.py` 单测后全仓串行门禁 **`ruff format/check`（`77 files`）+ `mypy`（`38 files`）+ `pytest -q`（`105 passed in 188.71s`）** 100% 通过。
* ✅ **K11 — 原创非二创作品借物表署名门禁兼容（`core/quality_gate.py`）与三方向并行 A/B/C 破圈实验闭环**
  * 扩展 `VideoQualityGate._eval_compliance` 中 `has_author_attr` 关键词识别集合（新增 `"原创"`、`"CC0"`、`"MIT"`、`"Noto Sans"`、`"Free BGM"`、`"无版权BGM"`），使 100% 原创短片与 MIT 开源工具实测视频在不强制出现同人「作者 / 模型提供」措辞时也能正确取得借物表满分 `6/6`，并在 `tests/test_quality_and_cover.py` 新增 `test_quality_gate_original_work_credits_full_score` 回归单测。
  * Swarm 三工兵完成 `021`（`BV1nuyZztEfY`，`98.5/100`）/ `022`（`BV1JGyZzxE2F`，`90.5/100`）/ `023`（`BV1zVyZzREEC`，`95.5/100`）全部 1080P 60FPS 交付与定时排期登记至 `library/creative_ledger.json`；后续由每日日巡追踪 48h 播放/3s划走/点赞评论流水进行三方向归因决策。
* ✅ **K12 — `4:3` 直播封面自动裁剪修复 + 实时流量/StopLiveData 观测 + 2D 活世界弹幕共建工坊与零 Key Agent 控制桥（`core/live_studio/world_engine.py` + `scripts/live_agent_ctl.py`）**
  * **同业直播对标与冷启动实测结论**：`2026-11-25 09:55 CST` 抓取 B 站 `AI应用·机器人` 分区头部在播样本后确认，小体量冷启动破圈房间（`52` 粉→`449` 在线、`1116` 粉→`2435` 在线、`742` 粉→`2442` 在线）共性在于「持续运转的 2D 活世界 + 巨型倒计时/生存数值锚点 + 3 秒弹幕即时反馈 + Agent 实时工作台明示不是录像 + 观众记忆归属感」。
  * **工程升级**：`BilibiliLiveController.upload_live_cover` 自动将任意比例封面裁剪编码为 B 站合规 `4:3 (800×600)` JPEG 并通过 `platform=web` 提交（实测 `code=0 / cover_updated=True`，彻底消除 `42603`）；`start_live` 安全捕获 `live_key`，新增 `get_live_telemetry` 与 `get_stop_live_data`（以及 `danmaku.parse_room_stats_command` 处理 `WATCHED_CHANGE`/`ONLINE_RANK_COUNT`）；新增 `ViewerMemoryStore`（零 UID 持久化熟人体系）、`LiveAgentWorld` + `WorldStageRenderer`（1080P 30FPS 稳态 `< 33ms/帧`）、`Director.enqueue_agent_speech`、`HeadlessLiveStreamer` `--stage-mode world` 控制桥（`danmaku_inbox.jsonl` / `agent_commands.jsonl` / `world_state.json` / `live_session_report.json`）与 `scripts/live_agent_ctl.py`（无需外部大模型 API Key 即可由 AI Coding Agent 亲手接管操作）；全仓串行门禁通过（`ruff` + `mypy` `40 files` + `pytest -q` `111 passed`）。
* ✅ **K13 — 2D 活世界留存/寻路优化（`b94a9c2`）+ 直播间不断流热更新与分区榜单零 PII 遥测（`core/live_studio/bilibili_live_api.py` + `scripts/live_agent_ctl.py`）**
  * **世界留存与视觉秩序加固（`b94a9c2`）**：落地危机冷却 `CRISIS_COOLDOWN_SEC=300s`、水平主走廊 `CORRIDOR_Y=278` 绕障寻路、2 名明示 AI 标识的工坊助手（`AmbientBotActor` 不虚增真实观众数）、`1`/`打卡` 零门槛入列、真实进房 `45` 秒冷却大肥鱼女声破冰欢迎、`ENTRY_EFFECT` 解析及无上限 `DualAILiveDirector.total_turns_emitted`。
  * **不断流热更新与分区榜单遥测（本次提交）**：新增 `BilibiliLiveController.update_room_info`（同一接口不断流热更新 `title` 与 `area_id`，兼容重构 `update_room_title` 5 键返回）与 `get_partition_room_list`（零 `roomid`/`uid`/`uname` PII 抓取 `room/v3/area/getRoomList` 实时在播总数、`top10_online_floor` 与 `my_rank`）；`core/live_studio/__init__.py` 导出 `BILIBILI_LIVE_AREA_ROOM_LIST_URL`；`scripts/live_agent_ctl.py` 新增 `update-room`（支持 `--notify-stage`）与 `partition-rank` 子命令；在 `tests/test_live_world.py` 补全离线单测并经线上只读冒烟确认 `partition-rank --area-id 1062` 零 PII 泄露（`total_rooms=36`）；全仓串行门禁通过（`ruff format/check` `80 files`、`mypy` `40 source files`、`pytest -q` **`117 passed in 271.33s`**）。
* ✅ **K14 — 直播弹幕防断线升级（`INTERACT_WORD_V2` / WS 重连 / 180s 危机自愈）+ v3「AI 现场制片厂」（4 栋制片建筑 / LIVE 制片大屏 / A·B·C 共创投票 / DeepSeek 幕后解说）& `Ep024` 实况前端制片交付**
  * **v2.1 稳定性与赛博演播台加固**：在 `core/live_studio/danmaku.py` 新增 `INTERACT_WORD_V2` 解析、`reconnect=True` 指数退避自动重连与 `_disconnect_ws(reset_auth=False)` 状态保留；在 `core/live_studio/headless_streamer.py` 开启 `reconnect=True` 并为 `>30s` 场次补充 `t=5s` 首帧自动抽图（`live_frame_check.png`）；在 `core/live_studio/world_engine.py` 上线暗黑玻璃态赛博演播间、`LIVE CAM · 铁三角演播席` 独立肖像区、Lv.2+ 全息鲸鱼夜景底图与 `180s` 危机自愈（`AI巡检小鱼`）根治每 10 秒闹钟刷屏。
  * **v3「AI 现场制片厂」上线**：在 `world_engine.py`（左半区 `互联网热点海 / 角色抓捕屋 / 可灵炼丹房 / 剪辑放映厅` 零碰撞建筑走位 + 右半区 `518×446` LIVE 制片大屏支持 `poll` 投票态与 `preview` 4.5s 等比轮播/闪烁 CLI 终端态，20 帧均值 **`19.03ms/帧`**）、`director.py`（`idle_call_interval_sec=75s` 节流与 `stage_change_seq` 切阶段秒打破冷却解说）、`scripts/launch_headless_live.py` 与 `scripts/live_agent_ctl.py`（`studio-stage` 指令，支持 `A/B/C` 改票去重重算与真实制片进度实时同步）；在 `tests/test_live_world.py` 补齐 4 组单测，全仓串行门禁通过（`ruff format/check` `80 files`、`mypy` `39 source files`、`pytest -q` **`122 passed in 206.64s`**）。
  * **实播复盘与下一步（K15 优先级 P0）**：`live_world_06`（`2680s`）与 `live_world_07`（`1144s`）先后实测观测到 B 站 RTMP 断流后 `ffmpeg tee [f=flv:onfail=ignore]` 仅记 `Slave muxer #0 failed: Broken pipe` 并继续写入本地 `.mkv` 导致房态归零后进程仍在后台空转（`edge-tts` 超时触发 `Thread message queue blocking` 亦放大管道阻塞风险），由下方 `K15` 正式根治；同期完成 `Ep018 (BV1CqyhzWEhR)` 409 播零 `@` 单点技术回复 4 条，与 `Ep024 (024_ai_reverse_interview_human_boss)` 70s 分镜、3 张 `2720×1536` `kling-image-v3_0_omni` 关键帧（`V=191–199`）及无水印高明度 16:9/4:3 封面（`V=203.9 / 212.4`），待可灵视频积分补充后即可补拍 7 幕正文。
* ✅ **K15 — 直播推流断线熔断、有限次自动重连与 Edge-TTS 非阻塞熔断器（`core/live_studio/headless_streamer.py` + `scripts/launch_headless_live.py`）**
  * **FFmpeg `tee` 与队列加固**：将双管道 `-thread_queue_size` 从 `512` 提升至 `2048`，并将 `go-live` 的 `tee` 容错从 `[f=flv:onfail=ignore]...|...` 反转修正为 `[f=flv]{rtmp_url}|[f={fmt}:onfail=ignore]{record_path}`，确保 RTMP 推流断线立刻触发失败而非无限空转写本地 `.mkv`，同时局部落盘故障不影响推流主链路。
  * **双重断流看门狗与有限次自愈重连**：新增 `RtmpStreamDisconnectedError`（已由 `core/live_studio/__init__.py` 导出并全程通过 `scrub_rtmp_secrets()` 脱敏）；在 `_spawn_stderr_reader` 捕获 `Broken pipe` / `Slave muxer #0 failed` 等致命推流错误，同时在 `_world_control_and_telemetry_loop` 接入 `45s` 宽限期后的 `live_status != 1` 连续 `2` 次离线心跳熔断；`run_go_live` 支持有上限的 `max_rtmp_reconnects=2` 指数退避重启（分段轮转 `live_recording_part{N}.mkv`、遇到 `code=60024` 绝不绕过、`finally` 必调 `ctrl.stop_live`），并在 CLI 暴露 `--max-rtmp-reconnects`。
  * **TTS 超时隔离与熔断器**：为 `SyntheticAudioMixer` 接入 `edge_tts_timeout_sec=5.0`、连续 `2` 次失败打开 `60s` 冷却熔断开关（记录 `tts_stats["edge_skipped_cooldown"]`）及 `_prepare_next_turn` / `_produce_one_audio_frame` `12.0s` `wait_for` 离线兜底，防止上游 TTS 超时阻塞 FFmpeg 音视频管道；在 `tests/test_headless_live.py` 补全断流、心跳离线、重连与熔断器全套离线单测并通过零麦克风词法审计（`0` 命中）。
* ✅ **K16 — 仓库 18 GiB 瘦身清理、过时 Skill/文档裁剪与 CI 现代化（`skills-lock.json` + `.gitignore` + `.github/workflows/{ci,release}.yml`）**
  * **安全瘦身实测**：清理废弃 `vendor/{ComfyUI,blender,ebsynth}`、`vendor/MoneyPrinterTurbo/{.venv,storage}` 及历次直播测试 `.mkv` 录像（保留全部分析 JSON、高光清单、抽帧表、封面与 `vendor/kling_cli`、`vendor/bin`），`vendor/` 由 `14G` 降至 `1.8G`、`output/` 由 `6.1G` 降至 `21M`，根分区实测释放 **`18 GiB`**（`262G -> 244G`）。
  * **技能与工作流减负**：移除过期火山方舟 `byted-ark-seedance-skill` / `byted-ark-seedream-skill` 与废弃静态白板 `figure-tutorial-video` 技能目录及 `docs/{FIGURE_VIDEO_ROADMAP,FUTURE_VIDEO_SLATE_018_020,product_research_and_plan}.md`，重置 `skills-lock.json`，补充 `.gitignore` 屏蔽 `projects/*/assets/` 与 `bilibili_verify_receipt.json` 噪音，统一将 `bilibili-viral-studio` / `viral-meme-innovation` 更新至 `>= 60.0s` 与 `>= 2.5s` 叙事节奏基线，并同步精简 `.github/workflows/{ci,release}.yml`、`Makefile`、`pyproject.toml` 与关联单测（移除已删除的 Node 技能检查并重新挂载 `17:00 / 19:00 CST` 常驻巡检）。
* ✅ **K17 — B 站小号黑马选题雷达（`core/breakout_radar.py` + `cli.py breakout-radar` + `.agents/skills/bilibili-breakout-radar/`）**
  * **核心能力（严格零 PII）**：新增 `BreakoutRadarEngine`（WBI 搜索 + `/x/web-interface/view` + 按 `vmid` 去重查询 `/x/relation/stat` 粉丝数）、`analyze_title_structure`（剖析移动端前 20 字钩子 `first_20_chars`、对话引号/数字反差/悬念词及公式化前后缀）、`score_breakout_candidate`（按 `views_per_follower` 倍率与投币/收藏/分享/弹幕强意愿权重评分）与 `evaluate_channel_horse_race`（对照 `trio_sitcom / ai_experiment / scifi_microfilm / oss_tool_demo` 四赛道与 `12/01` 收口门禁），全程匿名化为粉丝量级分档并写入 `library/benchmarks/breakout_radar_latest.{json,md}`。
  * **首轮线上实测雷达（`2026-11-26`，`followers <= 80000`, `views >= 20000`, `duration >= 45s`）**：扫描 `40` 条 BVID 零失败零 PII 命中 **`12`** 条黑马——头部桶 `ai_tool_demo` 占 `7/12`（如 `BV1p3raB8EMh` `3,119` 粉→`203,723` 播/`65.3x`/`10.25%` 收藏率，`BV1ZZAFzWEPJ` `16.5k` 粉→`280,690` 播/`1.11%` 分享率），强反差模型整活 `BV1nJHK6gEtd`（`28.7k` 粉→`3,643,198` 播/`126.8x`）；全部黑马中仅 `8.3%` 带赛事后缀、`33.3%` 带【前缀】标签。同步完成 `tests/test_breakout_radar.py` 离线单测。
