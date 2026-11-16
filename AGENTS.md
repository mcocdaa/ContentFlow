# ContentFlow Studio Workspace Rules (Always-On Memory & Operations Manual)

本文件为 ContentFlow 仓库的永久工作区准则与跨会话记忆锚点。每次启动新会话、执行后台定时任务或开发扩展功能时，必须严格遵守以下共性工程规范与个性创新闭环。

## 1. 共性与个性分层铁律（Commonality Automation vs. Per-Episode Innovation）

* **共性全自动化（走 `core/` 标准管线，禁止每期手写重复胶水脚本）**：
  * 真实爆款伴奏检索与 `48kHz` 立体声切片：`./.venv/bin/python cli.py fetch-bgm --query <关键词> / --bvid <BV号>`（底层调用 `core/bgm_hunter.py`，自动提取音轨并生成借物表致谢行，告别单薄正弦波蜂鸣器）
  * 市场对比与瓶颈诊断：`./.venv/bin/python cli.py benchmark --project <id> --online`
  * 多幕 1080P 60FPS 光流补帧 + 鼓点近景切镜（Beat Punch-In）+ `-14 LUFS` 装配：`./.venv/bin/python cli.py assemble-episode --spec <spec.json>`（底层调用 `core/episode_assembler.py` 的 `O(1)` 两帧滑窗流式管线）
  * B 站 16:9 / 4:3 高 CTR 封面生成：`./.venv/bin/python cli.py design-cover --project <id>`（娱乐/宅舞/鬼畜分类自动启用高明度 `vivid_scene`，科技科普沿用 `tech_split`）
  * 发布前 100 分制硬门槛验收：`./.venv/bin/python cli.py quality-check --project <id> --threshold 90`
  * 合规投递与置顶评论同步：`cli.py publish` 与 `cli.py sync-pins`
* **个性每期创新（每集必须全新构思，严禁走老路）**：
  * **立项前先查流水与对标**：先检查 `/home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json` 中的播放、3 秒划走率、封标星级（`tm_stars`）与观众评论点单，再运行 `cli.py benchmark --online` 拆解 B 站实时榜单头部爆款的封面明度、景别切换频率与留存钩子。
  * **严禁连续雷同与静态站桩**：立项必须写入 `brief.json` 的 `creative_spec` 并在 `library/creative_ledger.json` 登记；`VideoQualityGate` 会自动拦截近 3 期重复题材或舞台场景。娱乐向成片严禁回退为 `studio_renderer.py` 静态立绘 PPT。
  * **突破单机位**：长于 8 秒的舞蹈/整活片段优先启用 `EpisodeAssembler` 的 `beat_punch_bpm` 鼓点切镜（全景/近景特写交替），保持每 2–3 秒一次视觉焦点变化。

## 2. 三大安全与质量红线

1. **24 GiB RAM / 8 GiB VRAM 低内存严格串行与 `O(1)` 内存安全红线**：
   * 禁止并发运行多个 Python、`PyTorch`、`rembg`、`pyiqa`、`Kokoro-82M`、`pytest`、可灵 CLI 轮询或 `ffmpeg` 进程。
   * 视频补帧必须走 `EpisodeAssembler` 的 `O(1)` 两帧滑窗流式管线（`stream_interpolated_60fps`，峰值帧缓存 `< 45 MiB`，严禁整段原帧全量驻留内存）；`VideoQualityGate` 必须在 `finally:` 中释放 `release_pyiqa_models()` 并触发 `gc.collect()`。
   * 启动任何渲染、门禁或测试任务前必须先运行 `free -m` 确认 `available >= 5000` MiB；本地 TTS 调用完毕后必须立即执行 `tts.close()`；优先直接执行单代理闭环，已完成子代理必须立即清理（`manage_subagents kill_all`）。
2. **隐私与社区礼仪红线**：
   * **绝对零群发 `@股东`**：简介、标签与置顶评论中严禁出现任何 `@用户名`（由 `VideoQualityGate` 自动拦截扣分）；仅当兑现某位观众的具体点单时，才允许在其原评论下礼貌单点回复一次附上新稿件 BVID。
   * **严禁泄露个人账号信息**：任何日志、遥测快照（`bilibili_latest.json` 等）、文档或对话输出中，禁止打印或提交真实 `uid`（`DedeUserID`）、`uname` 或 Cookie；遥测文件中账号字段统一脱敏为 `"<REDACTED>"`。
3. **视觉与几何比例强制抽检**：
   * 成片流参数必须严格满足 `1920x1080`、`SAR=1:1`、`DAR=16:9`、`60.00fps`、`yuv420p`、`bt709`；所有参考视频转 16:9 必须等比缩放填充（严禁横向拉伸人物）。
   * 每次生成关键帧锚点图、原始视频抽帧表、最终 `diagnostic_contact_sheet.jpg` 以及 `*_cover.jpg` 后，必须调用 `read_file` 肉眼核验无肢体畸变、无多余物件、无黑边且娱乐封面暗部占比 `< 20%`。

## 3. 外部引擎旗舰模型铁律与开源合规

* **可灵旗舰模型铁律（Flagship Models Only，严禁降级凑合）**：
  * 主力视觉生成引擎为可灵 AI 官方 CLI（`./vendor/kling_cli/node_modules/.bin/kling`，SSVIP 会员积分充足）：
    * 文生图 / 图生图关键帧锚点：一律使用 **`kling-image-v3_0_omni`**（`2k`/`4k`）；
    * 图生视频 / 文生视频 / 多参考视频：一律使用旗舰 **`kling-video-v4_0`**（`1080p` Pro）或 **`kling-video-v3_0_omni`**（`1080p`/`4k`）；
    * 动作控制（`motion_control`）：一律使用 **`kling-video-v3_0`**（`1080p` Pro）。
  * **严禁降级使用旧代或阉割快模**：禁止调用 `v2_5`、`v2_6`、`v2_1`、`v3_0_turbo`、`v4_0_flash`、`720p` 低清档，以及 `flash`/`flash_lite` 轻量推理模型；所有提示词必须纯视觉描写外观与动作，严禁写入受商业版权保护的游戏/动漫 IP 专有名词，优先使用开源或 PCL / CC 授权角色（如「DeepSeek 蓝色大肥鱼」「弱音ハク」等）。
  * **异步离线提交与回收规范（严禁 `--poll` 阻塞驻留）**：所有可灵 CLI 生图/生视频调用一律去掉 `--poll` 参数，采用 `KLING_NONINTERACTIVE=1 ./vendor/kling_cli/node_modules/.bin/kling ... -q` 秒级提交拿到 `generationId` 后立即退出进程释放本地内存（交由云端离线渲染）；等待期间使用 `schedule` 单次定时器零消耗休眠（严禁跑 shell `sleep` 或长时 `--poll`），唤醒后通过 `KLING_NONINTERACTIVE=1 ./vendor/kling_cli/node_modules/.bin/kling query_tasks <generationId> -q` 秒拉结果。
* **已知不可用资源**：火山方舟（VolcEngine Ark）`ARK_API_KEY` 当前已过期（`InvalidSubscription`），请勿在无新订阅时强行调用 Seedream / Seedance。
* **音画版权与 AIGC 合规**：必须使用 `Noto Sans CJK SC` 开源字体，严禁未授权克隆声优原声；优先通过 `core/bgm_hunter.py`（`cli.py fetch-bgm`）提取 B 站热梗伴奏/二创混音片段并在【借物表 (Credits)】中完整注明原曲、二创 UP 主及 BVID 与 `GB 45438-2025` AIGC 合规声明，禁止用单薄纯正弦波电子蜂鸣充当娱乐热舞 BGM。

## 4. 持续微进化协议（Kaizen Continuous Improvement）

* 工作区长期演进任务清单维护在 `docs/EVOLUTION_BACKLOG.md`。
* 每当定时任务巡检发现排队存货充足（`>= 2` 天待发）或用户指示自主优化工作区时，主动从 `docs/EVOLUTION_BACKLOG.md` 认领 **1 个最高优先级未完成切片（Kaizen Slice）**，编写代码与单测，顺序跑通 `ruff format --check .`、`ruff check .`、`mypy core cli.py` 与 `pytest -q`，随后更新 `EVOLUTION_BACKLOG.md` 实测结果并 `git commit && git push origin main`，确保经验与工具能力永久沉淀不丢失。
