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

---

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
* ⏳ **K6 — 多角色高表现力情感配音接入（通过 `core/audio_router.py` 激活 MiniMax Speech / Fish-Audio，打造大肥鱼/Gemini娘/弱音专属声线）**
  * 目标：基于已落地的 `K4` 路由器，接入 MiniMax Speech / Fish-Audio 情感配音与角色声线配置档（voice profile），让大肥鱼、Gemini娘、弱音ハク在多角色群像短剧与互动中具备高辨识度语气与情绪起伏，同时保留无 Key 时平滑回退本地 TTS。
* ✅ **K7 — 双 AI 实时互动直播间 MVP（`core/live_studio/` 弹幕监听 + 双重合规风控 + OBS 透明舞台 + 高光自动打点切片）**
  * 已落地纯轻量异步包 `core/live_studio/`（仅依赖标准库 + `aiohttp` + `httpx` + `pydantic`，零 PyTorch / GPU 占用）：`safety.py`（`LiveComplianceGuard` 双向输入/输出风控，拦截 PII/Cookie/UID/手机号/邮箱/开盒、中英 Prompt Injection、NSFW/政治/网暴与 `@` 提及，内置强制 `GB 45438-2025` 标识与角色内兜底台词）、`danmaku.py`（16 字节大端 B 站直播二进制帧编解码与受限 `proto_ver=2` zlib 解压、无 UID `DANMU_MSG`/`SEND_GIFT`/`INTERACT_WORD` 解析、匿名访客 `BilibiliDanmakuClient` 与离线 `MockDanmakuSource`）、`director.py`（`DualAILiveDirector` `gift > danmaku > enter > idle` 优先级抢占、可插拔 `OpenAICompatibleResponder` + 零 Key 喜剧对话库兜底、`HighlightTracker` 脱敏 JSONL 与 60–90 秒 `ffmpeg` 切片清单生成）及 `stage_server.py` + `stage.html`（`1920x1080` 高明度 OBS Browser Source 透明舞台、白名单立绘路由防穿越、纯 `textContent` 防 XSS）；
  * 已配套 `scripts/launch_live_mvp.py`（支持 `--mode mock|live`、`--record-highlights`、`--duration-sec` 与低内存巡检）、`docs/LIVE_PLAN_DUAL_AI.md` 运营手册及 `tests/test_live_studio.py`（`12 passed` 离线+WebSocket 单测）；全仓串行门禁通过（`ruff format --check .` `70 files` / `ruff check .` / `mypy core cli.py scripts/launch_live_mvp.py` `35 source files` / `pytest -q` **`77 passed`**）。
* ✅ **K8 — 100% 无头零麦克风全自动 B 站直播引擎 + 非特权 Docker 沙箱（`core/live_studio/bilibili_live_api.py` + `headless_streamer.py` + `Dockerfile.live`）**
  * 已落地全自动无头直播链路：`core/live_studio/bilibili_live_api.py`（`BilibiliLiveController` 封装 `GetInfo` / `Room/update` / 非致命封面上传 / `startLive` / 幂等 `stopLive`，遇到 `code=60024` 自动生成官方人脸认证二维码 `output/live_face_auth_qr.png` 绝不绕过；`RoomStatus`/`StartLiveResult`/`scrub_rtmp_secrets()` 全链路将 RTMP 推流地址、串流码、`room_id`、`uid` 与 Cookie 脱敏为 `<REDACTED_RTMP_URL>` / `<REDACTED>`）、`core/live_studio/headless_streamer.py`（`HeadlessStageRenderer` 1920x1080@30FPS 定型大肥鱼×Gemini娘透明抠图舞台 + 活跃发言光环 + 音频波形 + `15 / 1,000 粉` 进度条 + 右上角永久 `本直播间由 AI 实时驱动互动 · GB 45438-2025` + 脱敏弹幕墙与高对比字幕；`SyntheticAudioMixer` 100% 合成 `s16le` 48kHz 立体声双角色 `edge-tts` + 离线纯 NumPy 旋律回退 + Lo-Fi 自动闪避 BGM，每视频帧精确对齐 `1600` 样本 = `6400` 字节；`HeadlessLiveStreamer` 单 `ffmpeg` 双 OS 管道直推、自动检测 `h264_nvenc` CBR `4500k` 并回退 `libx264`，全程 `try...finally: stop_live` 与高光切片清单导出）、`scripts/launch_headless_live.py`、`Dockerfile.live`（`python:3.12-slim` + `ffmpeg` + `fonts-noto-cjk` 非 root `UID 10001` 零音频设备镜像）及 `docs/LIVE_PLAN_DUAL_AI.md` 升级；
  * **安全与实测验收**：强制零麦克风审计（`grep -rnE "/dev/snd|alsa|pulse|pyaudio|sounddevice" core/live_studio/ scripts/launch_headless_live.py Dockerfile.live` -> **`0` 命中**）；20 秒无头干跑实测达标（`h264_nvenc` `1920x1080` `30/1fps` `yuv420p` `4594 kbps`，`aac` `48000Hz` 立体声，精确 `20.000s`，`mean_volume=-19.5 dB` / `max_volume=-3.1 dB`，抽帧视觉与高光切片清单均人工核验通过）；补全 `tests/test_headless_live.py`（`11 passed`，含 `K7+K8` 共 `23 passed`），全仓串行门禁通过（`ruff format --check .` `74 files` / `ruff check .` / `mypy core cli.py scripts/launch_live_mvp.py scripts/launch_headless_live.py` `38 source files` / `pytest -q` **`88 passed`**）。
