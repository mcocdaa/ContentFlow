# Dual-AI Interactive Livestream Runbook (`DeepSeek 蓝色大肥鱼 × Gemini娘`)

本手册面向 ContentFlow 工作室运营者，提供 **5 分钟开播上手指南**、**OBS 1080P60 推流配置**、**24 GiB RAM / 8 GiB VRAM 硬件红线**、**GB 45438-2025 合规核对表**，以及 **15 → 1,000 粉首播实战剧本**。

---

## 1. 5 分钟 B 站实名直播间准备（Zero Cookie / Zero PII）

1. **实名与开播权限**：登录 B 站「直播中心」完成实名认证，确认已开通个人直播间并记录纯数字房间号 `<ROOM_ID>`。
2. **分区与标题设置**：
   - 推荐分区：`虚拟主播 → 虚拟日常` 或 `知识/科技 → AI 互动实验`
   - 推荐标题（严格不含 `@用户名` 与版权 IP）：`【双AI合租直播】大肥鱼×Gemini娘现场策划018期！15粉冲1000粉挑战`
   - 直播间简介注明：`本直播间由 AI 实时驱动互动 · GB 45438-2025`。
3. **隐私与凭据铁律**：
   - `scripts/launch_live_mvp.py` 采用匿名访客模式（`uid=0`）读取公开弹幕流，**无需也不允许**写入 `SESSDATA`、`bili_jct`、Cookie 或真实 `uid`。
   - 如需接入 OpenAI 兼容大语言模型提升即兴对话效果，仅通过本地环境变量设置 `LIVE_LLM_API_KEY`（及可选 `LIVE_LLM_BASE_URL` / `LIVE_LLM_MODEL`），严禁将密钥提交至 Git 或截图暴露在 OBS 画面中。

---

## 2. 启动双 AI 演播厅与 OBS 1080P60 推流配置

### 2.1 本地离线彩排（零 API Key 即可运行）

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

### 2.2 接入真实 B 站直播间

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

### 2.3 OBS Studio 推流参数清单

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| 基础画布 & 输出分辨率 | `1920x1080` | 与 `stage.html` 16:9 高明度舞台 1:1 像素对齐，零黑边零拉伸 |
| 帧率 | `60 FPS` | 匹配 B 站 1080P60 丝滑动效与高光切片直出 |
| 浏览器源（Browser Source） | `http://127.0.0.1:8765/` | 宽高严格填 `1920 × 1080`，勾选「不可见时关闭源」= 否 |
| 视频编码器 | `NVIDIA NVENC H.264` | 速率控制 `CBR`，码率 `6000–8000 kbps`，关键帧间隔 `2s`，预设 `P5` |
| 音频采样率 | `48 kHz` 立体声 | 搭配开源轻快背景伴奏（`<= -22 LUFS`），避免未授权商用音乐 |
| 本地同步录屏 | `.mkv`（同流直录） | 下播后直接喂给 `HighlightTracker` 生成的 `ffmpeg` 60–90 秒切片命令 |

---

## 3. 24 GiB RAM / 8 GiB VRAM 硬件红线

1. **严禁边直播边本地渲染**：直播推流期间，**禁止并发启动** `EpisodeAssembler`、`PyTorch`、`rembg`、`pyiqa`、`Kokoro-82M`、`ffmpeg` 重编码或全量 `pytest`。
2. **轻量化内存占用**：`core/live_studio/` 仅依赖 Python 标准库 + `aiohttp` + `httpx` + `pydantic`（零 PyTorch、零 GPU 张量占用），常驻内存 `< 80 MiB`，把 8 GiB VRAM 完整让渡给 OBS NVENC 编码与系统合成器。
3. **开播前内存门禁**：每次开播前执行 `free -m`，确认 `available >= 5000 MiB` 且 `ps aux` 中无残留渲染任务。
4. **错峰剪辑策略**：高光切片与 `cli.py assemble-episode` / `cli.py quality-check` 必须在 **OBS 停播并关闭推流后** 串行执行。

---

## 4. 合规与安全核对清单（开播前逐项确认）

- [ ] **右上角强制 AI 标识可见**：确认 OBS 预览画面右上角完整显示 `本直播间由 AI 实时驱动互动 · GB 45438-2025`，未被任何贴纸或摄像头遮挡。
- [ ] **双向安全护栏激活**：`LiveComplianceGuard` 已对所有进入弹幕与输出台词启用：
  - 拦截并脱敏 `uid` / `DedeUserID` / `SESSDATA` / `Cookie` / 手机号 / 邮箱 / 身份证 / 开盒词汇；
  - 拦截中英文 Prompt Injection（如 `ignore previous instructions` / `忽略之前的指令`）；
  - 拦截政治敏感、色情 NSFW、仇恨骚扰与违法引导；
  - 拦截输入端群发 `@` 刷屏，并硬阻断输出端任何 `@用户名`（严格遵守零群发 `@股东` 铁律），命中后自动切换为角色内合规兜底台词。
- [ ] **视觉资产与版权合规**：仅使用 `library/characters/` 下定型开源/原创立绘（`DeepSeek 蓝色大肥鱼` 与 `Gemini娘`），不使用未授权声优克隆音色或受商业版权保护的游戏/动漫 IP 专有名词。
- [ ] **无隐私窗口入镜**：OBS 场景仅采集 Browser Source 与受控音频轨，禁止开启「显示器全屏采集」。

---

## 5. 首播实战剧本计划（`15 → 1,000 粉` 60 分钟流程）

| 时段 | 环节主题 | 双 AI 互动设计 | 高光切片目标 |
| --- | --- | --- | --- |
| `00:00–05:00` | **开场破冰：老板 15 粉账单大曝光** | 大肥鱼对着顶部 `15 / 1,000 粉` 进度条破防吐槽；Gemini娘亮出 4.9★ 高明度封面战绩，正式宣布合租接管冲千粉 | `roast_battle` 黄金开场 60s |
| `05:00–25:00` | **弹幕共创：Episode 018 剧本公投** | 引导观众发弹幕投票 018 期选题（如「AI 员工半夜讨薪」vs「机房抢主 C 选秀」），弹幕实时插队上墙并由对应角色回应 | `script_pitch` + `danmaku_burst` |
| `25:00–45:00` | **双 AI 审美与整活大辩论 + 礼物彩蛋** | 大肥鱼主攻 60FPS 剧情节奏，Gemini娘主攻亮色 `vivid_scene` 封面；触发 `SEND_GIFT` 时最高优先级插播致谢彩蛋 | `gift_reaction` + `roast_battle` |
| `45:00–60:00` | **总结定稿 + 切片反哺短视频** | 公布本场票选胜出的 018 剧本方向，引导新粉点关注；下播后使用 `*_ffmpeg_clip_plan.json` 导出 60–90 秒高光短视频反哺主站 | 次日 B 站短视频引流 |

下播后查看自动生成的 `ffmpeg` 切片方案：

```bash
cat output/live_session_highlights_ffmpeg_clip_plan.json
```

复制其中的 `ffmpeg_cmd` 在空载内存下串行裁切高光片段，即可无缝进入 ContentFlow 60FPS 精修与投稿闭环。
