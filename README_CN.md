<div align="center">

# ContentFlow

**面向 3D 手办虚拟偶像科普与全渠道图文的解耦式三层全息视频生产工作台。**

[![Family: *Flow](https://img.shields.io/badge/Family-*Flow-6366f1?style=flat-square)](https://github.com/mcocdaa/ContentFlow)
[![CI](https://img.shields.io/github/actions/workflow/status/mcocdaa/ContentFlow/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/mcocdaa/ContentFlow/actions)
[![Release](https://img.shields.io/github/v/release/mcocdaa/ContentFlow?style=flat-square)](https://github.com/mcocdaa/ContentFlow/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981?style=flat-square)](LICENSE)

[English](README.md) · [简体中文](README_CN.md)

<img src="docs/assets/demo_contentflow.gif" alt="ContentFlow Demo" width="840">

</div>

---

## ✨ 核心特性

- **三层解耦全息视觉合成（3-Layer Decoupled Visual Compositing）**：严格分离 `Z=0` 3D 演播室背景舞台、`Z=1` HTML 渲染全息白板（`1920x1080` 超清无乱码排版与图表）与 `Z=2` Rembg 透明通道手办人物抠像，彻底杜绝 AI 生图文字乱码与人物遮挡。
- **中央角色与多姿态资产库（`library/`）**：集中管理 3D 手办主参考图（Master Reference）与多情绪/动作透明抠像（`teaching`、`warning`、`proud`、`pointing`），支持跨项目一键检索与零成本复用。
- **全渠道文案矩阵与内联 CSS 排版引擎**：基于结构化 `FactSheet` 一键生成微信公众号深度长文、小红书图文、知乎回答、V2EX 帖与发布通告，内置防 XSS 转义的微信公众号与白板全内联 CSS HTML 转换器（`core/html_formatter.py`）。
- **内置 Studio WebUI 与统一 Canonical HTTP API**：遵循 *“Human via UI, AI via API, Single Canonical API”* 架构（`python3 cli.py serve`），纯 Python 标准库零外部 Web 框架依赖即可启动。
- **50x 极速 FFmpeg 预转与 MoneyPrinterTurbo 1080P 成片**：内置原生 FFmpeg 硬件级静图秒级转流加速层，结合 MoneyPrinterTurbo、Edge-TTS/Seed-TTS 自然语音与高精度字幕对齐，快速输出 1080P 成片。

---

## 🚀 快速开始

### 1. 启动 Studio WebUI 与 Canonical API 服务

```bash
git clone https://github.com/mcocdaa/ContentFlow.git
cd ContentFlow

# 启动可视化工作台与统一 HTTP JSON API 服务
python3 cli.py serve --port 8090
```

在浏览器访问 **`http://127.0.0.1:8090`** 即可查看三路管线就绪状态、浏览中央手办资产库、初始化项目工作区，并实时预览内联 CSS 白板/公众号排版。

### 2. CLI 三步极简工作流

```bash
# 第一步：初始化带 00x 序号的项目工作区（支持 hybrid / 3d / keyframe / api 模式）
python3 cli.py init my_topic --mode hybrid

# 第二步：从中央角色库复用指定手办角色的透明教学姿态资产
python3 cli.py reuse-asset --project my_topic --char yorha_2b --pose teaching

# 第三步：将脚本/Markdown 转换为可直接用于公众号或 Z=1 全息白板的内联 CSS HTML
python3 cli.py format-html --input script.txt --output board.html
```

一键执行全渠道文案生成与 1080P 配音字幕视频渲染：

```bash
python3 cli.py run-all --project my_topic --aspect 16:9 --voice zh-CN-YunxiNeural
```

---

## 🤖 AI 与 API 调用

AI 智能体与自动化脚本可直接调用与 Studio WebUI 完全同源的 `/api/v1/*` 接口：

```bash
# 1. 查询 3D / 关键帧 / 视频大模型管线就绪状态
curl -s http://127.0.0.1:8090/api/v1/status | python3 -m json.tool

# 2. 无头模式创建新项目工作区
curl -s -X POST http://127.0.0.1:8090/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name": "transformer_tutorial", "mode": "hybrid"}'

# 3. 通过 API 将 Markdown 渲染为内联 CSS HTML
curl -s -X POST http://127.0.0.1:8090/api/v1/format-html \
  -H "Content-Type: application/json" \
  -d '{"title": "Self-Attention 核心机制", "theme": "tech_blue", "text": "# 核心公式\n\n- **Query / Key / Value** 向量投影"}'
```

| 接口路径 | 方法 | 功能说明 |
| :--- | :--- | :--- |
| `/api/v1/health` | `GET` | 服务存活与版本健康检查 |
| `/api/v1/status` | `GET` | 检查 Blender 3D、ComfyUI 关键帧与 Seedance/Kling 视频 API 就绪度 |
| `/api/v1/library/characters` | `GET` / `POST` | 查询或注册可复用 3D 手办角色及多姿态资产 |
| `/api/v1/projects` | `GET` / `POST` | 列出所有项目的分层素材统计，或初始化新项目工作区 |
| `/api/v1/projects/{name}/reuse-asset` | `POST` | 将 `library/` 中的指定角色姿态导入目标项目 `assets/` |
| `/api/v1/format-html` | `POST` | 将 Markdown/文本转换为内联 CSS HTML（支持 `tech_blue` / `emerald`） |

---

## 📁 目录结构与开源协议

```text
ContentFlow/
├── cli.py                   # 统一命令行入口（init, reuse-asset, format-html, run-all, serve）
├── config/                  # 全渠道规格配置、音色预设与全局路径管理
├── core/
│   ├── server.py            # 零依赖 Canonical HTTP API 与 Studio WebUI 服务端
│   ├── asset_library.py     # 中央角色库与多姿态资产注册检索引擎
│   ├── figure_orchestrator.py # 3D Blender / 关键帧插帧 / 视频大模型管线编排器
│   ├── html_formatter.py    # 防 XSS 内联 CSS 微信公众号与 Z=1 全息白板转换器
│   ├── copywriting.py       # 全渠道图文文案生成引擎（微信/小红书/知乎/V2EX）
│   ├── asset_builder.py     # 幻灯片合成与 50x 极速 FFmpeg 静图转流引擎
│   └── video_engine.py      # 无头 MoneyPrinterTurbo 1080P 视频与字幕合成器
├── library/                 # 可复用手办主参考图、透明抠像与 PMX/VMD 动作库
├── projects/                # 按 00x_<topic> 归档的项目工作区
├── docs/assets/             # 演示 GIF 与文档媒体资源
└── tests/                   # Pytest 单元测试与 Canonical API 集成测试套件
```

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源发布。
