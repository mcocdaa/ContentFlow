# ContentFlow Studio Workspace Rules (Always-On Memory & Operations Manual)

本文件为 ContentFlow 仓库的永久工作区准则与跨会话记忆锚点。每次启动新会话、执行后台定时任务或开发扩展功能时，必须严格遵守以下共性工程规范与个性创新闭环。

## 1. 共性与个性分层铁律（Commonality Automation vs. Per-Episode Innovation）

* **共性全自动化（走 `core/` 标准管线，禁止每期手写重复胶水脚本）**：
  * 市场对比与瓶颈诊断：`./.venv/bin/python cli.py benchmark --project <id> --online`
  * 多幕 1080P 60FPS 光流补帧 + 鼓点近景切镜（Beat Punch-In）+ `-14 LUFS` 装配：`./.venv/bin/python cli.py assemble-episode --spec <spec.json>`（底层调用 `core/episode_assembler.py`）
  * B 站 16:9 / 4:3 高 CTR 封面生成：`./.venv/bin/python cli.py design-cover --project <id>`（娱乐/宅舞/鬼畜分类自动启用高明度 `vivid_scene`，科技科普沿用 `tech_split`）
  * 发布前 100 分制硬门槛验收：`./.venv/bin/python cli.py quality-check --project <id> --threshold 90`
  * 合规投递与置顶评论同步：`cli.py publish` 与 `cli.py sync-pins`
* **个性每期创新（每集必须全新构思，严禁走老路）**：
  * **立项前先查流水与对标**：先检查 `/home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json` 中的播放、3 秒划走率、封标星级（`tm_stars`）与观众评论点单，再运行 `cli.py benchmark --online` 拆解 B 站实时榜单头部爆款的封面明度、景别切换频率与留存钩子。
  * **严禁连续雷同与静态站桩**：立项必须写入 `brief.json` 的 `creative_spec` 并在 `library/creative_ledger.json` 登记；`VideoQualityGate` 会自动拦截近 3 期重复题材或舞台场景。娱乐向成片严禁回退为 `studio_renderer.py` 静态立绘 PPT。
  * **突破单机位**：长于 8 秒的舞蹈/整活片段优先启用 `EpisodeAssembler` 的 `beat_punch_bpm` 鼓点切镜（全景/近景特写交替），保持每 2–3 秒一次视觉焦点变化。

## 2. 三大安全与质量红线

1. **24 GiB RAM / 8 GiB VRAM 低内存严格串行执行红线**：
   * 禁止并发运行多个 Python、`PyTorch`、`rembg`、`pyiqa`、`Kokoro-82M`、`pytest`、可灵 CLI 轮询或 `ffmpeg` 进程。
   * 启动任何渲染、门禁或测试任务前必须先运行 `free -m` 确认 `available >= 5000` MiB；本地 TTS 调用完毕后必须立即执行 `tts.close()` 释放显存与内存。
2. **隐私与社区礼仪红线**：
   * **绝对零群发 `@股东`**：简介、标签与置顶评论中严禁出现任何 `@用户名`（由 `VideoQualityGate` 自动拦截扣分）；仅当兑现某位观众的具体点单时，才允许在其原评论下礼貌单点回复一次附上新稿件 BVID。
   * **严禁泄露个人账号信息**：任何日志、遥测快照（`bilibili_latest.json` 等）、文档或对话输出中，禁止打印或提交真实 `uid`（`DedeUserID`）、`uname` 或 Cookie；遥测文件中账号字段统一脱敏为 `"<REDACTED>"`。
3. **视觉与几何比例强制抽检**：
   * 成片流参数必须严格满足 `1920x1080`、`SAR=1:1`、`DAR=16:9`、`60.00fps`、`yuv420p`、`bt709`；所有参考视频转 16:9 必须等比缩放填充（严禁横向拉伸人物）。
   * 每次生成关键帧锚点图、原始视频抽帧表、最终 `diagnostic_contact_sheet.jpg` 以及 `*_cover.jpg` 后，必须调用 `read_file` 肉眼核验无肢体畸变、无多余物件、无黑边且娱乐封面暗部占比 `< 20%`。

## 3. 外部引擎实况与开源合规

* **主力视觉生成引擎**：可灵 AI 官方 CLI（`./vendor/kling_cli/node_modules/.bin/kling`，当前 SSVIP 会员积分充足）。提示词必须严格纯视觉描写角色外观与动作，严禁写入受商业版权保护的游戏/动漫 IP 专有名词；优先使用开源或 PCL / CC 授权角色（如「DeepSeek 蓝色大肥鱼」「弱音ハク」等）。
* **已知不可用资源**：火山方舟（VolcEngine Ark）`ARK_API_KEY` 当前已过期（`InvalidSubscription`），请勿在无新订阅时强行调用 Seedream / Seedance。
* **音画版权与 AIGC 合规**：必须使用 `Noto Sans CJK SC` 开源字体，严禁未授权克隆声优原声或直用未授权商用歌曲；每期简介必须保留完整【借物表 (Credits)】及 `GB 45438-2025` AIGC 合规声明。

## 4. 持续微进化协议（Kaizen Continuous Improvement）

* 工作区长期演进任务清单维护在 `docs/EVOLUTION_BACKLOG.md`。
* 每当定时任务巡检发现排队存货充足（`>= 2` 天待发）或用户指示自主优化工作区时，主动从 `docs/EVOLUTION_BACKLOG.md` 认领 **1 个最高优先级未完成切片（Kaizen Slice）**，编写代码与单测，顺序跑通 `ruff format --check .`、`ruff check .`、`mypy core cli.py` 与 `pytest -q`，随后更新 `EVOLUTION_BACKLOG.md` 实测结果并 `git commit && git push origin main`，确保经验与工具能力永久沉淀不丢失。
