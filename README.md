<div align="center">

# ContentFlow

**Decoupled 3-layer holographic video & multi-channel content studio for AI figurine tutorials.**

[![Family: *Flow](https://img.shields.io/badge/Family-*Flow-6366f1?style=flat-square)](https://github.com/mcocdaa/ContentFlow)
[![CI](https://img.shields.io/github/actions/workflow/status/mcocdaa/ContentFlow/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/mcocdaa/ContentFlow/actions)
[![Release](https://img.shields.io/github/v/release/mcocdaa/ContentFlow?style=flat-square)](https://github.com/mcocdaa/ContentFlow/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981?style=flat-square)](LICENSE)

[English](README.md) · [简体中文](README_CN.md)

<img src="docs/assets/demo_contentflow.gif" alt="ContentFlow Demo" width="840">

</div>

---

## ✨ Highlights

- **3-Layer Decoupled Visual Compositing**: Strictly separates `Z=0` 3D Studio Stage, `Z=1` HTML-rendered Holographic Whiteboard (`1920x1080` crisp text/charts), and `Z=2` Rembg Alpha Figurine Cutout—eliminating AI text garbling and character occlusion.
- **Central Character Asset Library (`library/`)**: Catalogs reusable 3D figurine characters, master reference sheets, and multi-emotion pose cutouts (`teaching`, `warning`, `proud`, `pointing`) across projects.
- **Multi-Channel Copywriting & Inline-CSS HTML Formatter**: Generates publication-ready copy for WeChat Official Accounts, Xiaohongshu, Zhihu, V2EX, and release notes, with an XSS-safe inline-CSS HTML formatter (`core/html_formatter.py`).
- **Built-in Studio WebUI & Canonical HTTP API**: Follows the *"Human via UI, AI via API, Single Canonical API"* architecture (`python3 cli.py serve`) powered purely by Python's standard library.
- **50x Faster FFmpeg + MoneyPrinterTurbo 1080P Rendering**: Pre-converts static scene slides into hardware-accelerated MP4 streams via FFmpeg before invoking MoneyPrinterTurbo with Edge-TTS/Seed-TTS voiceover and frame-accurate subtitles.

---

## 🚀 Quick Start

### 1. Launch Studio WebUI & Canonical API

```bash
git clone https://github.com/mcocdaa/ContentFlow.git
cd ContentFlow

# Start the Studio WebUI and Canonical HTTP JSON API server
python3 cli.py serve --port 8090
```

Open **`http://127.0.0.1:8090`** in your browser to inspect pipeline readiness, browse the character asset library, initialize projects, and preview inline-CSS HTML boards.

### 2. CLI 3-Step Workflow

```bash
# Step 1: Initialize a sequential project workspace (hybrid / 3d / keyframe / api)
python3 cli.py init my_topic --mode hybrid

# Step 2: Reuse a pre-cut figurine pose from the central character library
python3 cli.py reuse-asset --project my_topic --char yorha_2b --pose teaching

# Step 3: Format Markdown/script notes into standalone inline-CSS HTML for WeChat or Z=1 Whiteboards
python3 cli.py format-html --input script.txt --output board.html
```

To generate full multi-channel copywriting and render the 1080P MP4 video end-to-end:

```bash
python3 cli.py run-all --project my_topic --aspect 16:9 --voice zh-CN-YunxiNeural
```

---

## 🤖 AI & Headless API

AI agents and automation pipelines interact with the exact same `/api/v1/*` backend used by the Studio WebUI:

```bash
# 1. Inspect 3D / Keyframe / API pipeline readiness & video providers
curl -s http://127.0.0.1:8090/api/v1/status | python3 -m json.tool

# 2. Create a new project workspace headlessly
curl -s -X POST http://127.0.0.1:8090/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name": "transformer_tutorial", "mode": "hybrid"}'

# 3. Render Markdown into inline-CSS HTML via API
curl -s -X POST http://127.0.0.1:8090/api/v1/format-html \
  -H "Content-Type: application/json" \
  -d '{"title": "Self-Attention Mechanics", "theme": "tech_blue", "text": "# Core Formula\n\n- **Query / Key / Value** projection"}'
```

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/v1/health` | `GET` | Service liveness & version check |
| `/api/v1/status` | `GET` | Readiness of 3D Blender, ComfyUI Keyframe, and Seedance/Kling APIs |
| `/api/v1/library/characters` | `GET` / `POST` | List or register reusable figurine characters & poses |
| `/api/v1/projects` | `GET` / `POST` | List project asset counts or initialize a new project workspace |
| `/api/v1/projects/{name}/reuse-asset` | `POST` | Import a character pose from `library/` into a project |
| `/api/v1/format-html` | `POST` | Convert Markdown/text into inline-CSS HTML (`tech_blue` / `emerald`) |

---

## 📁 Project Structure

```text
ContentFlow/
├── cli.py                   # Unified CLI entry point (init, reuse-asset, format-html, run-all, serve)
├── config/                  # Channel specs, voice presets, and global paths
├── core/
│   ├── server.py            # Zero-dependency Canonical HTTP API & Studio WebUI
│   ├── asset_library.py     # Central character & multi-pose asset registry
│   ├── figure_orchestrator.py # 3D Blender / Keyframe / Seedance API pipeline router
│   ├── html_formatter.py    # XSS-safe inline-CSS WeChat & Z=1 Whiteboard formatter
│   ├── copywriting.py       # Multi-channel copy generator (WeChat, XHS, Zhihu, V2EX)
│   ├── asset_builder.py     # Slide synthesizer & 50x faster FFmpeg image-to-MP4 converter
│   └── video_engine.py      # Headless MoneyPrinterTurbo 1080P video & subtitle compositor
├── library/                 # Reusable figurine master references, cutouts, and PMX/VMD assets
├── projects/                # Sequential 00x_<topic> project workspaces
├── docs/assets/             # Showcase GIFs and documentation media
└── tests/                   # Pytest unit & canonical API integration test suite
```

## 📄 License

Released under the [MIT License](LICENSE).
