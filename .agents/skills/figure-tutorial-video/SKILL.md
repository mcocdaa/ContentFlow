---
name: figure-tutorial-video
description: >-
  端到端 3D 手办虚拟偶像技术科普与教学短视频生产管线。
  支持通过 Doubao-Seedream-5.0-Pro 保持高吸引力二次元手办角色特征（全身立绘、真实发丝光泽、性感沙漏曲线、亚克力底座）、
  自动化发丝级 rembg 抠图、纯净科技教室背景与发光全息白板图层解耦合成、中央数字资产库（library/）沉淀复用、
  以及基于 MoneyPrinterTurbo 的自动音画卡点、字幕描边与 1080P 成片渲染。
---

# 3D手办虚拟偶像教学视频生产管线 (Figure Tutorial Video Skill)

本技能提供从虚拟偶像立绘设计、多动作一致性生成、透明图层解耦、全息白板图表动态排版、中央资产库沉淀到最终 1080P 视频装配的完整工业化生产流程。

---

## 核心设计哲学与解决的行业痛点

1. **拒绝生硬分屏，单场景统合**：
   - 彻底废弃左右生硬割裂的双拼图，采用统一的 3D 未来科技教室大场景。
   - 人物立于画面左侧，右侧悬浮青蓝发光全息大屏，处于同一光影和景深体系内。
2. **顶奢二次元手办美学与真人发丝流光**：
   - 解决 AI 常见的“塑料泥塑假发”问题：使用专用发丝流光提示词（`瀑布般丝滑银白长发，顶级真发丝渲染，发丝根根分明细如蚕丝`）。
   - 解决“身形保守直筒”问题：参考 Pixiv 日榜与 Alter/Apex 顶奢手办做工，呈现凹凸有致沙漏身材、贴身白丝绸衬衫、微透肉黑色高光丝袜（sheer black pantyhose）与红底漆皮高跟鞋。
3. **全身手办立姿与物理级底座投影**：
   - 人物从头到脚完整入镜，脚踩精致透明亚克力手办底座，并在地面生成柔和漫反射接触阴影。
4. **图层级完全解耦与资产复用（`library/`）**：
   - 教室底图、全息白板底座、人物立绘三层彻底解耦。后续出 Docker、K8s、Git 等任何新视频，底图与底座零成本复用，只需生成专属板书与调用人物动作！

---

## 生产流水线标准作业流程 (SOP)

### 阶段 1：角色视觉规范确立与基准立绘生成 (Anchor Generation)

使用 `doubao-seedream-5.0-pro`（分辨率 `2560x1440`）生成第一张角色基准全身立绘。
- **提示词规范**：参考 [PROMPT_GUIDE.md](./references/PROMPT_GUIDE.md) 与 [prompt_presets.json](./resources/prompt_presets.json)。
- **核心要素**：全身立绘、纯净浅灰摄影棚背景、透明亚克力手办底座、真发发丝流光、极致沙漏身材、知性开襟西装与透肉黑丝。
- **产物**：`assets/character_anchor.jpg`。

### 阶段 2：基于图生图特征锚定的连贯动作生成 (Action Poses)

通过将第一张立绘进行 Base64 编码作为参考图（`image: data:image/jpeg;base64,...`），调用 `doubao-seedream-5.0-pro` 生成多套教学专属动作，确保脸型、发色、身材、服装百分之百一致：
- **动作 1（叹气困扰）**：轻扶眼镜，神态性感无奈微蹙，对应痛点暴雷。
- **动作 2（激光教鞭）**：右手持金色细长教鞭敲指板书，严肃警告，对应坑点预警。
- **动作 3（单手邀请）**：身体微侧，右手优雅平摊指向展示区，自信微笑，对应全绿流水线。
- **动作 4（双手阐述）**：双手在胸前知性比划阐述，重心微倾，对应架构与拓扑讲解。
- **动作 5（竖大拇指）**：右手竖大拇指点赞，元气治愈灿烂微笑，对应准点下班与号召关注。

使用脚本自动化运行：
```bash
python3 .agents/skills/figure-tutorial-video/scripts/generate_pose.py \
  --ref-image "projects/{project_id}/assets/character_anchor.jpg" \
  --pose "warning_pointer" \
  --output "projects/{project_id}/assets/pose2_pointer.jpg"
```

### 阶段 3：发丝级透明立绘提取 (rembg Cutout)

利用 ONNXRuntime 加速的 `rembg` 工具，对每张立绘扣除背景，保留完整的亚克力透明底座与丝滑发丝高光：
```python
from rembg import remove
from PIL import Image

inp = Image.open("pose.jpg")
out = remove(inp)
out.save("pose_transparent.png")
```

### 阶段 4：全息白板图表设计与图层合成 (Scene Compositing)

使用内置合成器 [composite_scene.py](./scripts/composite_scene.py)：
1. 载入 2560x1440 纯净教室底图：`library/scenes/cyber_classroom_clean_bg.jpg`。
2. 载入全息白板底座并放置在 `(585, 78)`：`library/props/holographic_whiteboard_chassis.png`。
3. 动态绘制高对比度全息 HUD 内容（终端报错日志、流水线流程节点、架构图、绿色通行胶囊标签），**内容起始坐标严格设置为 x=340**，避开左侧人物站姿区域。
4. 缩放人物立绘至高度 1180px，置于左侧 `(180, 200)`，在地面 `(cx, cy)` 绘制柔和椭圆漫反射高斯模糊投影（接触阴影）。
5. 导出超清 2560x1440 最终分镜场景图。

```bash
python3 .agents/skills/figure-tutorial-video/scripts/composite_scene.py \
  --project-dir "projects/{project_id}"
```

### 阶段 5：入库中央数字资产库 (Asset Library)

将生成的高价值资产登记入 `library/registry.json`，方便未来项目复用：
- 场景背景：`library/scenes/`
- 道具底座：`library/props/`
- 人物动作立绘：`library/characters/{character_id}/{emotion}/`

```bash
python3 cli.py reuse-asset --project my_new_project --asset yorha_2b_warning_api_key
```

### 阶段 6：高保真语音合成与声学调优 (Doubao Seed-TTS 2.0)

针对二次元与人造人/智能体角色（如 2B、弱音），接入字节跳动火山引擎 **Seed-TTS 2.0 (OpenSpeech V3)**：

1. **接口规范与网关避坑**：
   - **Base URL**：`https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional`
   - **⚠️ 成本红线**：严禁调用 `https://ark.cn-beijing.volces.com/api/v3`，会产生额外网关转发费。
   - **Resource-Id**：`seed-tts-2.0`
   - **鉴权 Header**：`X-Api-Key: <token>`, `X-Api-Resource-Id: seed-tts-2.0`
2. **V3 流式响应状态码防踩坑**：
   - `code == 0`：中间音频分片（Base64 解码并追加至文件）；
   - `code == 20000000, message == "OK"`：服务端正常完成传输标志，**必须视为成功结束，切勿判定为错误异常**。
3. **⚠️ 情感控制致命避坑：严禁在文本中注入方括号标签**：
   - 模型会把 `[冷静地]`、`[严肃地]`、`[微笑着]` 原样逐字朗读发声！
   - **正确做法**：口播文本保持 100% 纯净自然对白，通过自然标点符号（`！`、`？`）引导自回归模型推断情绪；
   - **声学物理参数调优**：
     - `speed_ratio: 0.95`（语速微降 5%，营造冷静沉着执行官质感）
     - `pitch_ratio: 0.92`（音高微降 8%，下沉基频，消除轻佻尖锐音）
4. **官方精选发音人**：
   - `zh_female_xiaohe_uranus_bigtts`（小何 2.0：知性清冷，最契合 2B 机械姬质感）
   - `zh_female_vv_uranus_bigtts`（Vivi 2.0：活力灵动二次元少女）
5. **跨语种零样本声音复刻 (ICL)**：
   - 当开通 `seed-icl-2.0` 权限后，传入 5 秒纯净原版声优原声（如石川由依 2B 日语原声切片），即可实现原汁原味的声优跨语种讲流利中文。

### 阶段 7：1:1 绝对卡点装配与 Ken Burns 运镜流水线 (Deterministic Video Assembly)

彻底规避第三方工具图库随机轮播导致的“声东击西”致命画面错位，采用严格确定性装配管线：

1. **分幕独立音频合成与毫秒级测长**：
   对 6 幕台词逐幕独立调用 Seed-TTS 2.0 生成 `scene_i.mp3`，并用 `ffprobe` 测定精确时长 $D_i$，并在幕末追加 0.25 秒自然呼吸空隙。
2. **分幕素材严格绑定与 Ken Burns 缓慢推进运镜**：
   对每张 1080P 纯净原始底图，利用 FFmpeg `zoompan` 滤镜添加 $1.00\times \to 1.04\times$ 的超平滑慢速推进运镜，赋予手办发丝与全息科技大屏呼吸感与立体纵深：
   ```bash
   zoompan=z='min(zoom+0.0003,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30
   ```
3. **精准生成 SRT 字幕与防眩光描边矢量烧录**：
   根据各幕起止毫秒时间戳自动生成精准 SRT，并通过 FFmpeg `subtitles` 滤镜使用文泉驿正黑体（WenQuanYi Zen Hei，白字 + 2.5px 纯黑立体描边）烧录于底部安全区，杜绝错字与旧文案残留。
4. **执行成片构建**：
   ```bash
   python3 projects/{project_id}/rebuild_aligned_video.py
   ```

---

## 常用脚本与工具链接

- [generate_pose.py](./scripts/generate_pose.py)：角色动作一致性生成与自动透明抠图工具。
- [composite_scene.py](./scripts/composite_scene.py)：全息科技教室与白板图层合成引擎。
- [rebuild_aligned_video.py](./scripts/rebuild_aligned_video.py)：1:1 绝对卡点音画与 Ken Burns 运镜压制引擎。
- [seed_tts.py](../../core/seed_tts.py)：火山引擎 OpenSpeech V3 Seed-TTS 2.0 工业级客户端。
- [prompt_presets.json](./resources/prompt_presets.json)：高吸引力手办二次元提示词预设库。
- [storyboard_template.json](./resources/storyboard_template.json)：五幕式技术避坑科普分镜模板。
- [PROMPT_GUIDE.md](./references/PROMPT_GUIDE.md)：手办提示词工程与发丝流光避坑指南。
