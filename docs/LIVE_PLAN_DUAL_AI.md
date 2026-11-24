# Dual/Trio-AI Interactive Livestream Runbook (`DeepSeek 蓝色大肥鱼 × Gemini娘 × 弱音ハク`)

> **三人铁三角完整 60 分钟节目单与晚间导流运营方案**：请参阅 [LIVE_PROGRAM_TRIO_SHOW.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/LIVE_PROGRAM_TRIO_SHOW.md)（「18:30 投新片 + 19:00–20:00 三人直播接力」导流闭环、四段式节目单、`扣1/扣2/扣3` 实时投票条、涨粉庆祝横幅与 `LIVE_LLM_API_KEY` 接真大模型指南）。

本手册面向 ContentFlow 工作室运营者，同时覆盖两种开播模式：
1. **OBS 浏览器源模式（K7）**：适合需要人工画面微调与 OBS 本地监视的 1080P60 互动直播。
2. **100% 无头零麦克风全自动直播模式 + Docker 沙箱（K8，推荐）**：无需桌面环境、无需 OBS、**零麦克风与声卡设备挂载**，支持 `--cast trio`（默认：大肥鱼 × 弱音ハク × Gemini娘铁三角 + 右侧实时弹幕投票条 + 金色涨粉庆祝条）与 `--cast dual`（双人经典版），由 `Pillow + NumPy` 直接渲染 `1920x1080 @ 30 FPS` 舞台画面，配合 `edge-tts` 多角色合成人声与自动避让（Ducking）Lo-Fi 背景音乐，经由双 OS 管道（`rawvideo` + `s16le 48kHz stereo`）直推单一 `ffmpeg`（优先 `h264_nvenc` CBR `4500k`，自动回退 `libx264`）并全周期自动托管 B 站开播/关播（`try...finally: stopLive`）。

---

## 1. 5 分钟 B 站实名直播间准备与分区选择

1. **实名与开播权限**：登录 B 站「直播中心」完成实名认证并开通个人直播间。
2. **推荐分区 `area_id`**：
   - `area_id=1062`（默认推荐）：科技 / AI 互动实验分区，适合双 AI 实时策划、互动整活与技术整活直播。
   - `area_id=371`：虚拟主播 → 虚拟日常分区，适合二次元角色日常吐槽、冲千粉陪伴与粉丝点单直播。
3. **推荐标题（严格不含 `@用户名` 与商业版权 IP）**：
   - `【双AI合租直播】大肥鱼×Gemini娘现场策划018期！15粉冲1000粉`
   - 直播间简介注明：`本直播间由 AI 实时驱动互动 · GB 45438-2025`。
4. **隐私与密钥零暴露红线**：
   - **K7 OBS 弹幕模式**（`scripts/launch_live_mvp.py`）采用匿名访客模式（`uid=0`）读取公开弹幕流，无需 Cookie。
   - **K8 无头全自动推流模式**（`scripts/launch_headless_live.py`）通过 `AuthVault`（`~/.contentflow/accounts/bilibili/cookies.json`，严格 `0600` 权限）调用开播/停播接口，**RTMP 推流地址/串流码、`room_id`、`uid`、`DedeUserID`、`SESSDATA`、`bili_jct` 仅驻留内存，绝不打印、不落盘、不写入 JSON/清单/stderr 日志**（统一脱敏为 `<REDACTED_RTMP_URL>` / `<REDACTED>`）。
   - 如需接入 OpenAI 兼容大语言模型提升即兴对话效果，仅通过本地环境变量设置 `LIVE_LLM_API_KEY`（及可选 `LIVE_LLM_BASE_URL` / `LIVE_LLM_MODEL`），严禁提交至 Git。

---

## 2. 100% 无头零麦克风全自动推流模式（K8）

### 2.1 架构与安全铁律

| 模块 | 职责与硬约束 |
| --- | --- |
| `core/live_studio/bilibili_live_api.py` | 封装 `GetInfo` / `Room/update` / 可选非致命封面上传 / `startLive` / 幂等 `stopLive`；遇到 `code=60024` 时自动生成官方人脸认证二维码 `output/live_face_auth_qr.png` 并干净退出（**严禁绕过人脸验证**）；内置 `scrub_rtmp_secrets()` 全链路脱敏。 |
| `core/live_studio/headless_streamer.py` | `HeadlessStageRenderer`（1920x1080 30FPS，支持 `--cast trio` 三人舞台与 `--cast dual` 双人舞台，优先透明抠图、优雅回退定型立绘，内置活跃发言光环、律动、音频波形、15/1,000 粉进度条、金色涨粉庆祝条、右上角永久 `GB 45438-2025` 标识、右侧实时弹幕投票条 + 脱敏弹幕墙与底部高对比字幕）+ `SyntheticAudioMixer`（`zh-CN-XiaoxiaoNeural` 大肥鱼 / `zh-CN-XiaoyiNeural` Gemini娘 / `zh-TW-HsiaoYuNeural` 弱音ハク + 离线纯 NumPy 三声部旋律回退 + Lo-Fi 自动避让 BGM，每视频帧精确对齐 `1600` 立体声样本 = `6400` 字节，零音画漂移、**绝对零麦克风**）+ `HeadlessLiveStreamer`（单 `ffmpeg` 双 OS 管道直推 + `finally: stop_live` 兜底关播）。 |
| `scripts/launch_headless_live.py` | 统一 CLI 入口（支持 `--cast trio/dual`、`--poll-topic`、`--poll-options`），向 stdout 输出无隐私、可 `grep` 的单行 JSON 状态标签：`FACE_AUTH_REQUIRED`、`LIVE_STARTED`、`DRY_STREAM_DONE`、`LIVE_STOPPED`。 |

### 2.2 15–20 秒本地零麦克风 Dry-Stream 验片（支持 `--cast trio` / `--cast dual`）

```bash
# 1) 检查可用内存（必须 >= 5000 MiB）
free -m

# 2) 运行 15 秒铁三角无头干跑测试（输出本地 MP4 + 抽帧视觉核验 PNG）
./.venv/bin/python scripts/launch_headless_live.py \
  --mode dry-stream \
  --cast trio \
  --duration-sec 15 \
  --poll-topic "下期主控弹幕公投" \
  --poll-options "大肥鱼,Gemini娘,弱音大姐头" \
  --output-mp4 /tmp/trio_live_preview.mp4 \
  --frame-dump-path /tmp/trio_live_stage_preview.png \
  --follower-count 15 \
  --follower-goal 1000
```

### 2.3 一键全自动 B 站开播（含 `finally:` 自动停播与高光切片清单）

```bash
./.venv/bin/python scripts/launch_headless_live.py \
  --mode go-live \
  --cast trio \
  --duration-sec 3600 \
  --area-id 1062 \
  --title "【铁三角AI合租直播】大肥鱼×Gemini娘×弱音现场弹幕公投！15粉冲1000粉" \
  --poll-topic "下期主控弹幕公投" \
  --poll-options "大肥鱼,Gemini娘,弱音大姐头" \
  --record-dir output/live_sessions/session_001 \
  --follower-count 15 \
  --follower-goal 1000
```

- **阵容与投票配置**：默认 `--cast trio` 启用三人铁三角舞台；如需切换经典双人布局，传入 `--cast dual`。通过 `--poll-topic` 与 `--poll-options` 可自定义右侧 `扣1/扣2/扣3` 实时弹幕投票议题与 2–3 个选项（详细 60 分钟节目单见 [LIVE_PROGRAM_TRIO_SHOW.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/LIVE_PROGRAM_TRIO_SHOW.md)）。

- **若首次开播触发 `code=60024`（人脸验证）**：终端输出 `FACE_AUTH_REQUIRED` 并将二维码保存至 `output/live_face_auth_qr.png`。请使用 B 站手机客户端扫码完成官方人脸认证后，重新执行上述命令即可自动进入 `LIVE_STARTED` 推流状态。
- **分区切换**：如需在「虚拟主播 → 虚拟日常」分区开播，将 `--area-id 1062` 改为 `--area-id 371`。
- **异常/Ctrl+C 安全关播**：`SIGINT`/`SIGTERM` 或推流中途发生网络异常时，`HeadlessLiveStreamer` 始终在 `finally:` 中自动调用 `stopLive` 关播并导出 `live_highlights_ffmpeg_clip_plan.json`。

### 2.4 Docker 非特权零设备隔离沙箱（`Dockerfile.live`）

构建纯 CPU/可选 GPU 的非 root 隔离镜像（不挂载宿主机任何音频硬件，进程以 `UID 10001` 非特权用户运行）：

```bash
# 构建镜像
docker build -f Dockerfile.live -t contentflow-live:latest .

# 1) 沙箱内 20 秒 dry-stream 离线验证（只读根文件系统 + 零音频设备）
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=512m \
  -v /tmp/live_out:/out:rw \
  contentflow-live:latest \
  --mode dry-stream \
  --duration-sec 20 \
  --output-mp4 /out/sandbox_dry_stream.mp4 \
  --frame-dump-path /out/sandbox_frame.png

# 2) 沙箱内正式开播（仅只读挂载 B 站凭证目录，可选追加 --gpus all 启用 NVENC）
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=512m \
  -v "$HOME/.contentflow/accounts/bilibili:/home/liveuser/.contentflow/accounts/bilibili:ro" \
  -v "$PWD/output:/app/output:rw" \
  -e LIVE_LLM_API_KEY \
  contentflow-live:latest \
  --mode go-live \
  --duration-sec 600 \
  --area-id 1062 \
  --record-dir /app/output/live_sessions/docker_run
```

---

## 3. 启动双 AI 演播厅与 OBS 1080P60 推流配置（K7 浏览器源模式）

### 3.1 本地离线彩排（零 API Key 即可运行）

```bash
# 先检查可用内存（必须 >= 5000 MiB）
free -m

# 启动离线彩排模式 + 高光记录器
./.venv/bin/python scripts/launch_live_mvp.py \
  --mode mock \
  --host 127.0.0.1 \
  --port 8765 \
  --record-highlights output/rehearsal_highlights.jsonl
```

验证服务状态（确认返回 `status: "running"` 且不含任何 PII）：

```bash
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool
```

### 3.2 接入真实 B 站直播间

```bash
./.venv/bin/python scripts/launch_live_mvp.py \
  --mode live \
  --room-id <ROOM_ID> \
  --host 127.0.0.1 \
  --port 8765 \
  --follower-count 15 \
  --follower-goal 1000 \
  --record-highlights output/live_session_highlights.jsonl
```

### 3.3 OBS Studio 推流参数清单

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| 基础画布 & 输出分辨率 | `1920x1080` | 与 `stage.html` 16:9 高明度舞台 1:1 像素对齐，零黑边零拉伸 |
| 帧率 | `60 FPS` | 匹配 B 站 1080P60 丝滑动效与高光切片直出 |
| 浏览器源（Browser Source） | `http://127.0.0.1:8765/` | 宽高严格填 `1920 × 1080`，勾选「不可见时关闭源」= 否 |
| 视频编码器 | `NVIDIA NVENC H.264` | 速率控制 `CBR`，码率 `6000–8000 kbps`，关键帧间隔 `2s`，预设 `P5` |
| 音频采样率 | `48 kHz` 立体声 | 搭配开源轻快背景伴奏（`<= -22 LUFS`），避免未授权商用音乐 |
| 本地同步录屏 | `.mkv`（同流直录） | 下播后直接喂给 `HighlightTracker` 生成的 `ffmpeg` 60–90 秒切片命令 |

---

## 4. 24 GiB RAM / 8 GiB VRAM 硬件红线

1. **严禁边直播边本地渲染**：直播推流期间，**禁止并发启动** `EpisodeAssembler`、`PyTorch`、`rembg`、`pyiqa`、`Kokoro-82M`、额外 `ffmpeg` 重编码或全量 `pytest`。
2. **轻量化内存占用**：`core/live_studio/` 零 PyTorch、零 GPU 张量常驻；无头双管道模式仅维护有界 4 帧滑窗队列（`< 30 MiB` 帧缓存）+ 单 `ffmpeg` 编码进程，安全控制在 24 GiB RAM / 8 GiB VRAM 红线内。
3. **开播前内存门禁**：每次开播前执行 `free -m`，确认 `available >= 5000 MiB` 且 `ps aux` 中无残留渲染任务。
4. **错峰剪辑策略**：高光切片与 `cli.py assemble-episode` / `cli.py quality-check` 必须在 **停播并关闭推流后** 串行执行。

---

## 5. 合规与安全核对清单（开播前逐项确认）

- [ ] **右上角强制 AI 标识可见**：确认画面右上角完整显示 `本直播间由 AI 实时驱动互动 · GB 45438-2025`，未被任何贴纸或元素遮挡。
- [ ] **绝对零麦克风确认**：无头模式仅通过合成 `s16le` 48kHz 立体声 PCM 管道输出音频，绝不采集宿主机环境声音。
- [ ] **双向安全护栏激活**：`LiveComplianceGuard` 已对所有进入弹幕与输出台词启用：
  - 拦截并脱敏 `uid` / `DedeUserID` / `SESSDATA` / `Cookie` / 手机号 / 邮箱 / 身份证 / 开盒词汇；
  - 拦截中英文 Prompt Injection（如 `ignore previous instructions` / `忽略之前的指令`）；
  - 拦截政治敏感、色情 NSFW、仇恨骚扰与违法引导；
  - 拦截输入端群发 `@` 刷屏，并硬阻断输出端任何 `@用户名`（严格遵守零群发 `@股东` 铁律），命中后自动切换为角色内合规兜底台词。
- [ ] **视觉资产与版权合规**：仅使用 `library/characters/` 与工作室已审核抠图资产（`DeepSeek 蓝色大肥鱼` 与 `Gemini娘`），不使用未授权声优克隆音色或受商业版权保护的游戏/动漫 IP 专有名词。
- [ ] **零隐私与零密钥泄露**：所有终端日志、状态 JSON、FFmpeg stderr 均已脱敏（`<REDACTED_RTMP_URL>` / `<REDACTED>`）。

---

## 6. 实战节目单计划（`15 → 1,000 粉` 60 分钟流程）

> 完整版三人铁三角「18:30 投新片 + 19:00–20:00 直播接力」四段式节目单与高光闭环，请直接查阅 [LIVE_PROGRAM_TRIO_SHOW.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/LIVE_PROGRAM_TRIO_SHOW.md)。下表保留双人轻量版对照参考：

| 时段 | 环节主题 | 双 AI 互动设计 | 高光切片目标 |
| --- | --- | --- | --- |
| `00:00–05:00` | **开场破冰：老板 15 粉账单大曝光** | 大肥鱼对着顶部 `15 / 1,000 粉` 进度条破防吐槽；Gemini娘亮出 4.9★ 高明度封面战绩，正式宣布合租接管冲千粉 | `roast_battle` 黄金开场 60s |
| `05:00–25:00` | **弹幕共创：Episode 018 剧本公投** | 引导观众发弹幕投票 018 期选题（如「AI 员工半夜讨薪」vs「机房抢主 C 选秀」），弹幕实时插队上墙并由对应角色回应 | `script_pitch` + `danmaku_burst` |
| `25:00–45:00` | **双 AI 审美与整活大辩论 + 礼物彩蛋** | 大肥鱼主攻 60FPS 剧情节奏，Gemini娘主攻亮色 `vivid_scene` 封面；触发 `SEND_GIFT` 时最高优先级插播致谢彩蛋 | `gift_reaction` + `roast_battle` |
| `45:00–60:00` | **总结定稿 + 切片反哺短视频** | 公布本场票选胜出的 018 剧本方向，引导新粉点关注；下播后使用 `*_ffmpeg_clip_plan.json` 导出 60–90 秒高光短视频反哺主站 | 次日 B 站短视频引流 |

下播后查看自动生成的 `ffmpeg` 切片方案：

```bash
cat output/live_sessions/session_001/live_highlights_ffmpeg_clip_plan.json
```

复制其中的 `ffmpeg_cmd` 在空载内存下串行裁切高光片段，即可无缝进入 ContentFlow 60FPS 精修与投稿闭环。
