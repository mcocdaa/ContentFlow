# 2B 小姐姐教你大模型 API 核心三要素（Base URL / API Key / Model Name）

> **所属模块**：`ContentFlow/projects/ai_api_tutorial_2b`  
> **内容形式**：3D 二次元手办科普短视频 + 全渠道多模态图文教程  
> **特邀主讲**：**2B (YoRHa No.2 Type B / 寄叶二号B型)**  
> **视觉标准**：顶奢 3D 手办级美学，凹凸有致沙漏身材、真发丝光泽、微透肉高光黑丝、全息科技教室单场景统合  

---

## 📽️ 视频分镜图文总览（6 幕超清实景）

本教程共包含 6 幕由 2B 亲自授课的 16:9 超清未来科技教室全景图，各幕板书与教学动线如下：

| 分镜序号 | 教学主题 | 2B 动作与神态 | 全息白板核心板书与图表 | 对应视觉产物 |
| :---: | :---: | :---: | :---: | :---: |
| **Scene 1** | **痛点引出** | 2B 坐在科技课桌前，轻托下巴困扰微叹气，神态性感无奈 | 红橙警告 HUD：`API CONNECTION ERROR`、`HTTP 401 UNAUTHORIZED`、`404 MODEL NOT FOUND` | `assets/scene1_intro_troubled.jpg` |
| **Scene 2** | **第一把钥匙：Base URL** | 2B 优雅站立，手持蓝色激光教鞭精准指向网络路由图 | 科技蓝 HUD：`KEY 1: BASE URL (API ENDPOINT)`、`https://api.deepseek.com/v1`、`http://localhost:11434/v1`（Ollama）网络路由链路 | `assets/scene2_base_url.jpg` |
| **Scene 3** | **第二把钥匙：API Key** | 2B 单手微抬轻抚胸前，做出严肃认真的安全警示手势 | 金紫防护 HUD：`KEY 2: API KEY (AUTHENTICATION & SECURITY)`、`Authorization: Bearer sk-...`、金色安全锁与 `.env` 防盗刷警告 | `assets/scene3_api_key.jpg` |
| **Scene 4** | **第三把钥匙：Model Name** | 2B 双手优雅平摊平举，知性微笑展示浮动模型代号卡片 | 翡翠青 HUD：`KEY 3: MODEL NAME (EXACT IDENTIFIER)`、`deepseek-reasoner`、`gpt-4o`、`claude-3-7-sonnet` 等精确模型卡片 | `assets/scene4_model_name.jpg` |
| **Scene 5** | **常见报错速查急诊室** | 2B 单手手持透明玻璃诊断平板，自信知性地看向镜头讲解 | 分级诊断 HUD：`ERROR CODE TRIAGE`：`401 (Key/余额)`、`404 (URL/模型名)`、`429 (频率限流)` 红黄蓝三级警报标签 | `assets/scene5_error_triage.jpg` |
| **Scene 6** | **全通验证与点赞下班** | 2B 露出灿烂甜美的治愈微笑，右手开朗竖起大拇指点赞 | 胜利绿 HUD：`API CALL SUCCESS: 200 OK`、`LATENCY: 48ms`、`STATUS: CONNECTED` 绿灯全亮与系统全通 | `assets/scene6_success_thumbsup.jpg` |

---

## 💡 核心科普知识点系统精讲

### 1. 钥匙一：Base URL（通信基地址）
- **是什么**：决定了客户端的 HTTP 请求发送到哪台服务器网关。
- **典型场景**：
  - 公有云官方接口：`https://api.deepseek.com/v1`
  - 聚合中转中介：`https://api.openai-proxy.com/v1`
  - 本地私有化模型（Ollama / vLLM / LM Studio）：`http://localhost:11434/v1` 或 `http://127.0.0.1:8000/v1`
- **避坑黄金法则**：90% 的兼容客户端（如 Cherry Studio, NextChat, Dify）均要求 Base URL 末尾必须携带 `/v1` 路由。漏写 `/v1` 会直接导致 404 Not Found。

### 2. 钥匙二：API Key（身份凭证与安全防线）
- **是什么**：模型服务商分配给你的鉴权密码，通常形如 `sk-xxxxxxxxxxxxxxxxxxxxxxxx`。
- **底层原理**：作为 HTTP Header 发送：
  ```http
  Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxx
  ```
- **避坑黄金法则**：
  - 严禁写死在前端 Vue/React 代码中；
  - 严禁将含有真实 Key 的 `.env` 提交到 GitHub 等公开代码仓库；
  - 本地开发统一使用 `os.environ.get("OPENAI_API_KEY")` 读取。

### 3. 钥匙三：Model Name（模型唯一定位符）
- **是什么**：告诉服务商你要唤醒哪一个具体的神经网络模型。
- **代表性代号表**：
  - DeepSeek 系列：`deepseek-chat`（通用V3）、`deepseek-reasoner`（R1 满血推理）
  - OpenAI 系列：`gpt-4o`、`o1`、`o3-mini`
  - Anthropic 系列：`claude-3-7-sonnet-20250219`
- **避坑黄金法则**：模型名称区分大小写，横杠与下划线不可混用。必须严格复制官方文档中的精确 ID。

### 4. 常见报错速查口诀
- **401 Unauthorized**：Key 输错、Key 已被吊销、或者绑定的支付账户余额欠费。
- **404 Not Found**：Base URL 的路由写错（常见漏写 `/v1`），或者该服务商根本没有你填写的 Model Name。
- **429 Too Many Requests**：发包频率超过了你的 Tier 等级并发限制（RPM/TPM），或者服务商被挤爆。
- **500 / 502 / 504**：服务商上游服务崩溃或网关超时，与本地配置无关，静候恢复即可。

---

## 📦 中央数字资产库沉淀（`library/characters/yorha_2b/`）

按照 ContentFlow 资产管理架构，所有 2B 教学资产已入库并登记至 [`library/registry.json`](file:///home/mcocdaa/AI_CODE/ContentFlow/library/registry.json)：

```text
library/characters/yorha_2b/
├── master_reference.jpg                 # 2B 基准角色立绘
├── troubled/
│   └── 2b_troubled_pose1.jpg           # 困惑微叹姿态（用于痛点、故障、反思场景）
├── teaching/
│   └── 2b_teaching_base_url.jpg        # 手持激光教鞭姿态（用于寻址、规范、理论讲解）
├── warning/
│   └── 2b_warning_api_key.jpg          # 手势警戒姿态（用于安全、密钥防护、避坑警告）
├── explaining/
│   └── 2b_explaining_model_name.jpg    # 知性平摊展示（用于架构对比、选型推荐）
├── triage/
│   └── 2b_error_triage.jpg             # 诊断平板排查（用于排错指引、日志分析）
└── thumbs_up/
    └── 2b_thumbs_up_success.jpg        # 自信竖大拇指点赞（用于成功验收、收尾呼吁）
```

后续制作任何新视频（如 Prompt 工程、MCP 协议、本地部署等），可通过 CLI 一键复用：
```bash
python3 cli.py reuse-asset --project my_new_project --asset yorha_2b_warning_api_key
```

---

## 🚀 视频渲染与本地流水线执行

基于已生成的 `storyboard.json`，随时可使用内置引擎合成 1080P 成片：

```bash
# 1. 运行文案生成引擎同步更新各平台物料
python3 cli.py generate-copy --project ai_api_tutorial_2b

# 2. 一键调用 MoneyPrinterTurbo 渲染 1080P 高清成片（默认配音：zh-CN-XiaoxiaoNeural）
python3 cli.py generate-video --project ai_api_tutorial_2b --aspect 16:9 --voice zh-CN-XiaoxiaoNeural

# 3. 检索中央资产库中已注册的 2B 动作
python3 cli.py list-assets --character yorha_2b
```

---

## 🎙️ 豆包语音合成 2.0 (Doubao Seed-TTS 2.0) 2B 专属配音方案

针对 2B（石川由依声线）清冷、理智、内敛的战斗人形（Android）特质，项目提供了专属配音合成器：

### 1. 快速试跑（Dry-Run 模式预览分镜台词与情感 Tag）
```bash
python3 projects/ai_api_tutorial_2b/synthesize_doubao_2b.py --dry-run
```

### 2. 导出 API Key 并一键合成 & 自动重混流 MP4
```bash
export DOUBAO_TTS_API_KEY="your-volcengine-api-key"

# 合成 2B 专属高冷知性音（默认使用 zh_female_lengku_moon_bigtts，语速 0.95，音高 0.92）
python3 projects/ai_api_tutorial_2b/synthesize_doubao_2b.py
```
执行后将自动生成：
- `output/ai_api_tutorial_2b/video/2B小姐姐教你大模型API核心三要素_doubao_2b.mp3`
- `output/ai_api_tutorial_2b/video/2B小姐姐教你大模型API核心三要素_doubao_final.mp4`（无损替换视频音轨）

### 3. 自定义参数
```bash
python3 projects/ai_api_tutorial_2b/synthesize_doubao_2b.py \
  --voice zh_female_zhixing_moon_bigtts \
  --speed 0.92 \
  --pitch 0.90
```

