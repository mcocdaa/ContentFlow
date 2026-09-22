# 3D手办弱音的CI/CD避坑指南 · 项目全案归档说明

> **项目标识**：`yowane_cicd`  
> **内容定位**：二次元虚拟偶像科普 & 开发者工程避坑短剧  
> **视觉基调**：3D手办美学（Alter/Apex旗舰级做工）+ 未来全息科技教室 + 顶级ACG御姐审美  
> **核心主角**：弱音白（Yowane Haku）全身体态立绘（脚踩透明亚克力手办底座、柔顺真发质感银白长发、傲人沙漏曲线、微透肉黑丝、红底高跟鞋）  
> **制作引擎**：ContentFlow + 字节跳动火山引擎 Doubao-Seedream-5.0-Pro + MoneyPrinterTurbo (Edge-TTS)

---

## 一、 项目背景与解决的核心痛点

在传统的二次元科普短视频制作中，常常面临两大极端问题：
1. **画风生硬割裂**：左右生硬分屏，左侧动漫人物与右侧板书风格迥异，缺少空间纵深感。
2. **手办质感失真或人物缺乏吸引力**：一味强调手办导致模型生成粘土/塑料块状假发；或人物体态保守呆滞，缺乏二次元圈层的高吸引力。

本项目确立并跑通了**“单场景融合 + 全身立绘 + 真实丝滑发丝 + 图层级完全解耦复用”**的工业化管线：
- **拒绝分屏，单场景统合**：弱音老师站立于未来科技教室左侧，与右侧悬浮的全息白板同处一个 3D 景深空间。
- **全身完整入镜**：脚踩精致透明亚克力底座，地面具备物理级投射柔和阴影，保留手办微缩景观的精致感。
- **顶奢手办与真实真发丝流光**：采用 `doubao-seedream-5.0-pro` 专属提示词工程，呈现如丝绸般的瀑布银发、微醺迷人的酒红眼眸与贴身干练的知性教师装扮。
- **图层完全解耦**：教室背景、全息白板、人物立绘三层分离，沉淀为资产库，供后续 Docker、K8s 等视频 100% 零成本复用。

---

## 二、 5套分镜场景与全息板书设计

| 场景编号 | 分镜主题 | 弱音动作/神态 | 全息白板展示内容 | 对应成片资产路径 |
| :--- | :--- | :--- | :--- | :--- |
| **Scene 1** | 手动发包的痛 | 扶眼镜微叹气，神态无奈性感 | 红色警报：手动部署终端崩溃日志、单测全部暴雷、502 线上故障诊断 | `assets/yowane_v3_scene1.jpg` |
| **Scene 2** | 三大玄学坑点预警 | **手持激光教鞭**精准指向板书，严肃警告 | 橙红警示：分支冲突拆盲盒、环境玄学差异、坏代码溜进主干 | `assets/yowane_v3_scene2.jpg` |
| **Scene 3** | CI 自动化门禁 | **右手平摊优雅展示**全绿流水线，自信微笑 | 翡翠绿架构：Git Push ➔ Lint 扫描 ➔ 自动化单测 ➔ 质量门禁全绿 | `assets/yowane_v3_scene3.jpg` |
| **Scene 4** | CD 容器化交付 | **双手知性阐述手势**，重心微倾身姿婀娜 | 科技蓝拓扑：Dockerfile ➔ 不可变 OCI 镜像 ➔ 金丝雀发布 ➔ 秒级自愈 | `assets/yowane_v3_scene4.jpg` |
| **Scene 5** | 告别加班摸鱼 | **右手开朗竖大拇指点赞**，灿烂治愈微笑 | 金色圆满：100% 自动化成功、准点下班第一法则、下期实战预告 | `assets/yowane_v3_scene5.jpg` |

---

## 三、 核心沉淀资产库（`library/`）

所有基础资产已登记入 `library/registry.json`，支持跨项目通过 CLI 调取：

### 1. 场景与道具底板（100% 跨项目复用）
- **纯净全息教室背景**：`library/scenes/cyber_classroom_clean_bg.jpg` (2560x1440)
- **发光全息大屏底盘**：`library/props/holographic_whiteboard_chassis.png` (1389x781)

### 2. 弱音 5 套高精度透明人物立绘（`library/characters/yowane_haku/`）
- `troubled/yowane_alluring_pose1_troubled.png`：扶眼镜困扰微叹气
- `warning/yowane_alluring_pose2_pointer.png`：手持金色教鞭警示敲黑板
- `confident/yowane_alluring_pose3_allgreen.png`：单手优雅平摊邀请展示
- `explaining/yowane_alluring_pose4_container.png`：双手知性阐释容器架构
- `thumbs_up/yowane_alluring_pose5_thumbsup.png`：单手竖大拇指点赞庆祝

---

## 四、 交付产物清单（`delivery/`）

### 1. 视频与视听物料
- **1080P 成品短视频**：`output/yowane_cicd/video/3D手办弱音的CI_CD避坑指南_final.mp4`（时长 25.4s，比特率 ~673kbps，高保真画质）
- **视频封面图**：`delivery/3D手办弱音的CI_CD避坑指南_cover.jpg`
- **字幕文件**：`delivery/3D手办弱音的CI_CD避坑指南_subtitle.srt`
- **旁白音频**：`output/yowane_cicd/video/3D手办弱音的CI_CD避坑指南_audio.mp3`（音色：`zh-CN-XiaoxiaoNeural`）

### 2. 全渠道宣发文案
- **微信公众号长文（HTML内联排版）**：`delivery/wechat.html` / `delivery/wechat.md`
- **小红书爆款图文卡片**：`delivery/xiaohongshu.md`
- **知乎深度技术问答**：`delivery/zhihu.md`
- **V2EX 极客分享帖**：`delivery/v2ex.md`
- **产品发布简讯**：`delivery/release.md`
- **结构化分镜定义**：`delivery/storyboard.json`

---

## 五、 本地复现与流水线执行命令

```bash
# 1. 重新合成 5 套超清 2.5K 教学全景图
vendor/MoneyPrinterTurbo/.venv/bin/python projects/yowane_cicd/scripts/compose_scenes.py

# 2. 一键调用 MoneyPrinterTurbo 渲染 1080P 视频
python3 cli.py generate-video --project yowane_cicd --aspect 16:9 --voice zh-CN-XiaoxiaoNeural

# 3. 检索中央资产库中的弱音立绘
python3 cli.py list-assets --character yowane_haku
```
