# ContentFlow Workspace Evolution Log & Kaizen Backlog

本文档是 ContentFlow 工作室的持久化经验库与渐进式升级清单，用于沉淀实测数据结论，并驱动空闲时段与定时任务下的持续微进化（每次认领 1 项，验证后提交 Git）。

---

## 一、 实测流水与爆款对比沉淀结论（Verified Empirical Insights）

1. **封面明度与死黑面积对比（决定白底信息流点击率 CTR）**
   * **全站百万爆款实测**（`rid=129` 榜首 `789万`、`rid=119` 榜首 `632万`）：封面平均明度 `172.3 ~ 195.1`，接近纯黑区域（`< 45`）占比仅 **`0.2% ~ 0.8%`**。
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

---

## 二、 已完成进化记录（Completed Slices）

* ✅ **E1 — 礼仪与比例双重护栏**：清空所有预设及线上简介中的群发 `@股东`；在 `core/quality_gate.py` 中新增 `DAR` vs 分辨率拉伸一票否决项、`@` 群发扣分校验，以及基于 `library/creative_ledger.json` 的近 3 期题材防重校验。
* ✅ **E2 — 008 热替换重制 & 010/011 新梗实景交付**：告别站桩拉伸旧版，上线 `008` 机房伪监控偷跳宅舞（`BV18AWC6YEPa`）、`010` 司凤战损吐蓝血×邦吧星奇摇（`BV121sw62EGg` 兑现「白的黑板」点单并单点礼貌回复）、`011` 社畜弱音《回答我》18:30 街头潮舞（`BV198sw6oEHN`，11/18 18:30 定时发布）。
* ✅ **E3 — 共性工程代码化**：落地 `core/competitor_benchmark.py`（`cli.py benchmark` 对标爆款客观指标）、`core/episode_assembler.py`（`cli.py assemble-episode` 统一 60FPS 光流 + `Beat Punch-In` 鼓点切镜 + `-14 LUFS`）、`core/analytics.py` 去硬编码重构，以及 `core/cover_designer.py` 的 `vivid_scene` 高明度封面引擎并完成 `008/010/011` 线上封面热更新。
* ✅ **E4 — 真实爆款伴奏引擎 (`core/bgm_hunter.py`) + O(1) 流式低内存管线 + 可灵 4.0 旗舰升级 + 全线稿件热升级 (`008/010/011/012`)**：
  * 全线热升级 `008`（真《Telepathy》原曲踩点）、`010`（986万爆款《司凤版雨爱》邦吧原声 + 138 BPM 切镜）与定时稿 `011`（真 Phonk + 街头潮舞原声，11/18 18:30）；
  * 采用旗舰 `kling-video-v4_0` + `kling-video-v3_0` + 真《大展鸿图》二创原声交付 `012_dafeiyu_dazhanhongtu_villa`（`98.0 / 100 [S / VIRAL_READY]`，封面明度 `161.89`、暗部 `7.7%`），热替换原旧白板排期 `009`（`BV1hwWC6PEYu`，已过审 `state=-40`，11/17 18:30 发布），并将 `003`（`BV18AWC6YE3M`）延后至 11/19 18:30。

---

## 三、 待推进微改进队列（Prioritized Kaizen Queue）

每次空闲唤醒或空闲收尾时，按顺序认领 **1 项**实现、验证并更新此处状态：

* ✅ **K0 — 2026-11-19 18:30 CST 前用全新 013（可灵 4.0 + 真伴奏 60FPS）热替换旧白板存货 003**
  * 已交付全新 `013_yowane_rooftop_lixicheng_march`（早八弱音晴空樱花天台×《李羲承进行曲》`BV1bsXQYAEn4` 真原声 60FPS 多景别切镜，门禁 **`94.0 / 100 [S / VIRAL_READY]`**、`0` 阻断，`vivid_scene` 封面平均明度 **`182.43`**、暗部 **`7.55%`**），热替换原 `003` 定时稿 **`BV18AWC6YE3M`**（`aid=117612847570833`，`dtime=1795084200` -> `2026-11-19 18:30 CST`，已过审 `state=-40`）；线上 11/17 (`012` `BV1hwWC6PEYu`)、11/18 (`011` `BV198sw6oEHN`)、11/19 (`013` `BV18AWC6YE3M`) 三支定时排期已 100% 清零老旧静态白板 PPT。
* ✅ **K1 — 真实爆款伴奏提取与多轨侧链闪避混音增强**
  * 已由 `core/bgm_hunter.py`（`cli.py fetch-bgm` + `concat_or_duck_segments`）及双侧链闪避/冲击低音合成落地并应用于 `008/010/011/012/013`。
* ✅ **K2 — 黄金前 2 秒综艺花字与动态贴纸开场钩子**
  * 已在 `core/episode_assembler.py` 落地 `EpisodeSpec.hook_banner_text` / `hook_banner_sec`（流式合成前单次预渲染 `< 1 MiB` `O(1)` 撞色胶囊花字 RGBA 图块 + 前 `0.18s` 弹出缓动，`t >= hook_banner_sec` 零拷贝透传），补充单测 `test_episode_assembler_hook_banner_overlay`（全仓 **`49 passed`** Pytest 100% 通过），并已在 `013` 成片前 `1.6s` 实装验证。
* `[ ] K3 — 发布后 24h/72h 流水自动归因与对比回顾脚本`
  * 目标：扩展 `cli.py benchmark`，记录不同期 `vivid_scene` 封面 vs 旧版封面的 `tm_stars`、`crash_rate_pct` 与 `full_play_ratio_pct` 真实变化并自动写入本文件经验区。
* `[ ] K4 — 外部真音乐（MiniMax Music / Suno）与情绪语音（MiniMax Speech / Fish-Audio）路由器插件位`
  * 目标：在用户补充相应 API Key 后，即插即用地替换本地平直念白与正弦波伴奏（`config/settings.py` 与 `.env.example` 已预留 `MINIMAX_API_KEY`）。
