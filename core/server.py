"""ContentFlow Canonical HTTP JSON API Server & Studio WebUI.

Implements the 'Human via UI, AI via API, Single Canonical API' architecture using
Python's standard library (`http.server.ThreadingHTTPServer`, `json`, `urllib.parse`).
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import cli
from core.asset_library import AssetLibrary
from core.figure_orchestrator import FigureOrchestrator
from core.html_formatter import HTMLFormatter
from core.video_api_router import VideoAPIRouter

STUDIO_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ContentFlow Studio — Canonical API & WebUI</title>
  <style>
    :root {
      --bg: #0b0f19;
      --surface: #111827;
      --surface-alt: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --warn: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      line-height: 1.6;
      min-height: 100vh;
    }
    header {
      background: rgba(17, 24, 39, 0.9);
      border-bottom: 1px solid var(--border);
      padding: 16px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(8px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 9999px;
      background: var(--surface-alt);
      border: 1px solid var(--border);
    }
    .badge.ok { border-color: rgba(16,185,129,0.5); color: #34d399; background: rgba(16,185,129,0.1); }
    .badge.warn { border-color: rgba(245,158,11,0.5); color: #fbbf24; background: rgba(245,158,11,0.1); }
    main {
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px 28px;
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 24px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    .col-12 { grid-column: span 12; }
    .col-6 { grid-column: span 6; }
    @media (max-width: 1024px) { .col-6 { grid-column: span 12; } }
    h2 {
      font-size: 17px;
      font-weight: 600;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }
    .subcard {
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
    }
    .subcard h3 { font-size: 14px; margin-bottom: 6px; color: #e2e8f0; }
    .muted { color: var(--text-muted); font-size: 13px; }
    input, select, textarea {
      width: 100%;
      background: #0f172a;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px 12px;
      font-size: 14px;
      margin-bottom: 10px;
    }
    textarea { min-height: 120px; font-family: monospace; resize: vertical; }
    button {
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 9px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    button:hover { background: var(--primary-hover); }
    button.secondary { background: var(--surface-alt); border: 1px solid var(--border); }
    .row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
    .preview-box {
      background: #ffffff;
      color: #1f2937;
      border-radius: 8px;
      padding: 16px;
      max-height: 360px;
      overflow-y: auto;
      border: 1px solid var(--border);
    }
    /* AI API Docs Drawer */
    .drawer {
      position: fixed;
      top: 0;
      right: -540px;
      width: 520px;
      max-width: 92vw;
      height: 100vh;
      background: var(--surface);
      border-left: 1px solid var(--border);
      padding: 24px;
      overflow-y: auto;
      transition: right 0.25s ease;
      z-index: 50;
      box-shadow: -8px 0 30px rgba(0,0,0,0.6);
    }
    .drawer.open { right: 0; }
    pre.code {
      background: #090d16;
      color: #38bdf8;
      padding: 12px;
      border-radius: 8px;
      font-size: 12px;
      overflow-x: auto;
      border: 1px solid #1e293b;
      margin: 8px 0 16px 0;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>🎬 ContentFlow Studio</span>
      <span id="health-badge" class="badge">Checking API...</span>
    </div>
    <div>
      <button class="secondary" onclick="toggleDocs()">🤖 AI API Docs</button>
    </div>
  </header>

  <main>
    <!-- Pipeline & Provider Readiness -->
    <section class="card col-12">
      <h2>
        <span>⚡ Pipeline & Video Provider Readiness</span>
        <button class="secondary" onclick="loadStatus()">Refresh</button>
      </h2>
      <div id="status-container" class="status-grid"></div>
    </section>

    <!-- Projects List & Creator -->
    <section class="card col-6">
      <h2>📁 Projects Workspace</h2>
      <div class="row">
        <input id="new-proj-name" placeholder="New project name (e.g. cyber_tutorial)" />
        <select id="new-proj-mode" style="max-width: 160px;">
          <option value="hybrid">2D/3D Hybrid</option>
          <option value="3d">3D Blender</option>
          <option value="keyframe">Keyframe RIFE</option>
          <option value="api">Cloud Video API</option>
        </select>
        <button onclick="createProject()">+ New Project</button>
      </div>
      <div id="projects-container"></div>
    </section>

    <!-- Character Asset Library Browser & Reuse -->
    <section class="card col-6">
      <h2>🧝‍♀️ Character Asset Library & Reuse</h2>
      <div class="row">
        <input id="reuse-project" placeholder="Target Project (e.g. 002_yowane_cicd)" />
        <input id="reuse-char" placeholder="Character ID (e.g. yowane_haku)" />
        <input id="reuse-pose" placeholder="Pose (e.g. teaching)" />
        <button onclick="reuseAsset()">Reuse Asset</button>
      </div>
      <div id="reuse-msg" class="muted" style="margin-bottom:8px;"></div>
      <div id="characters-container" class="status-grid"></div>
    </section>

    <!-- Interactive Whiteboard HTML Formatter Previewer -->
    <section class="card col-12">
      <h2>📝 Interactive Whiteboard & WeChat HTML Formatter</h2>
      <div class=" status-grid">
        <div>
          <input id="fmt-title" value="CI/CD Pipeline Architecture" placeholder="Presentation Title" />
          <textarea id="fmt-text"># Pipeline Overview

1. **Deterministic Builds** with `uv` and locked dependencies.
2. **Automated Verification** across unit and integration suites.

- Zero manual glue scripts
- Full artifact traceability</textarea>
          <button onclick="formatHtml()">Render Presentation HTML</button>
        </div>
        <div>
          <div id="fmt-preview" class="preview-box">Click "Render Presentation HTML" to preview...</div>
        </div>
      </div>
    </section>
  </main>

  <!-- AI API Docs Drawer -->
  <aside id="api-drawer" class="drawer">
    <h2>
      <span>🤖 AI Canonical HTTP API (`/api/v1/*`)</span>
      <button class="secondary" onclick="toggleDocs()">Close ✕</button>
    </h2>
    <p class="muted" style="margin-bottom:14px;">
      ContentFlow strictly follows "Human via UI, AI via API, Single Canonical API".
      Both this Studio WebUI and AI agents interact with the exact same JSON endpoints:
    </p>
    <h4>1. Health & Readiness</h4>
    <pre class="code">curl -s http://127.0.0.1:8090/api/v1/health
curl -s http://127.0.0.1:8090/api/v1/status</pre>

    <h4>2. Character Asset Library</h4>
    <pre class="code">curl -s http://127.0.0.1:8090/api/v1/library/characters

curl -s -X POST http://127.0.0.1:8090/api/v1/library/characters \\
  -H "Content-Type: application/json" \\
  -d '{"char_id":"noshiro","name":"Noshiro","master_ref":"assets/noshiro.jpg","description":"3D figurine"}'</pre>

    <h4>3. Projects & Asset Reuse</h4>
    <pre class="code">curl -s http://127.0.0.1:8090/api/v1/projects

curl -s -X POST http://127.0.0.1:8090/api/v1/projects \\
  -H "Content-Type: application/json" \\
  -d '{"project_name":"demo_tutorial","mode":"hybrid"}'

curl -s -X POST http://127.0.0.1:8090/api/v1/projects/demo_tutorial/reuse-asset \\
  -H "Content-Type: application/json" \\
  -d '{"char_id":"yowane_haku","pose":"teaching"}'</pre>

    <h4>4. Presentation HTML Formatter</h4>
    <pre class="code">curl -s -X POST http://127.0.0.1:8090/api/v1/format-html \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Demo","text":"# Hello\\n\\n- **Fast** pipeline"}'</pre>
  </aside>

  <script>
    function toggleDocs() {
      document.getElementById('api-drawer').classList.toggle('open');
    }

    async function loadHealth() {
      const res = await fetch('/api/v1/health');
      const data = await res.json();
      const badge = document.getElementById('health-badge');
      badge.textContent = `${data.service} v${data.version} • ${data.status.toUpperCase()}`;
      badge.className = 'badge ok';
    }

    async function loadStatus() {
      const res = await fetch('/api/v1/status');
      const data = await res.json();
      const container = document.getElementById('status-container');
      container.innerHTML = '';
      for (const [key, info] of Object.entries(data.pipelines || {})) {
        const ready = info.status === 'ready';
        const div = document.createElement('div');
        div.className = 'subcard';
        div.innerHTML = `
          <h3>${info.name || key}</h3>
          <span class="badge ${ready ? 'ok' : 'warn'}">${info.status}</span>
        `;
        container.appendChild(div);
      }
      const provDiv = document.createElement('div');
      provDiv.className = 'subcard';
      const provBadges = Object.entries(data.video_providers || {})
        .map(([k, v]) => `<span class="badge ${v ? 'ok' : 'warn'}">${k}: ${v ? 'ON' : 'OFF'}</span>`)
        .join(' ');
      provDiv.innerHTML = `<h3>Video Providers</h3><div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">${provBadges}</div>`;
      container.appendChild(provDiv);
    }

    async function loadProjects() {
      const res = await fetch('/api/v1/projects');
      const data = await res.json();
      const container = document.getElementById('projects-container');
      const rows = (data.projects || []).map(p => `
        <tr>
          <td><strong>${p.project_id}</strong></td>
          <td>${p.raw_assets}</td>
          <td>${p.whiteboards}</td>
          <td>${p.backgrounds}</td>
          <td>${p.composited}</td>
          <td>${p.scripts}</td>
        </tr>
      `).join('');
      container.innerHTML = `
        <table>
          <thead><tr><th>Project</th><th>Raw</th><th>Boards</th><th>BGs</th><th>Comp</th><th>Scripts</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    async function createProject() {
      const project_name = document.getElementById('new-proj-name').value.trim();
      const mode = document.getElementById('new-proj-mode').value;
      if (!project_name) return;
      await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name, mode })
      });
      document.getElementById('new-proj-name').value = '';
      await loadProjects();
    }

    async function loadCharacters() {
      const res = await fetch('/api/v1/library/characters');
      const data = await res.json();
      const container = document.getElementById('characters-container');
      const chars = data.characters || {};
      container.innerHTML = Object.values(chars).map(c => {
        const poses = Object.keys(c.poses || {}).join(', ') || 'none';
        return `
          <div class="subcard">
            <h3>${c.name} <span class="muted">(${c.char_id})</span></h3>
            <div class="muted">Poses: ${poses}</div>
          </div>
        `;
      }).join('');
    }

    async function reuseAsset() {
      const project = document.getElementById('reuse-project').value.trim();
      const char_id = document.getElementById('reuse-char').value.trim();
      const pose = document.getElementById('reuse-pose').value.trim();
      if (!project) return;
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(project)}/reuse-asset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ char_id, pose })
      });
      const data = await res.json();
      document.getElementById('reuse-msg').textContent = data.status === 'ok'
        ? `✅ Reused into ${data.project}: ${data.dest_path}`
        : `❌ ${data.error || 'Failed to reuse asset'}`;
      await loadProjects();
    }

    async function formatHtml() {
      const title = document.getElementById('fmt-title').value;
      const text = document.getElementById('fmt-text').value;
      const res = await fetch('/api/v1/format-html', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, title })
      });
      const data = await res.json();
      document.getElementById('fmt-preview').innerHTML = data.html || '';
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadHealth();
      loadStatus();
      loadProjects();
      loadCharacters();
      formatHtml();
    });
  </script>
</body>
</html>
"""


def _count_files(directory: Path) -> int:
    if not directory.exists() or not directory.is_dir():
        return 0
    return sum(1 for p in directory.iterdir() if p.is_file())


def inspect_project_counts(proj_dir: Path) -> Dict[str, int]:
    """Computes scene and asset counts for a project directory."""
    assets_dir = proj_dir / "assets"
    raw_assets = _count_files(proj_dir / "raw_assets") + _count_files(assets_dir)
    whiteboards = _count_files(proj_dir / "whiteboards")
    backgrounds = _count_files(proj_dir / "backgrounds")
    composited = _count_files(proj_dir / "composited") + _count_files(proj_dir / "images")
    scripts = _count_files(proj_dir / "scripts")

    if (proj_dir / "script.txt").is_file():
        scripts += 1
    if (proj_dir / "brief.json").is_file():
        scripts += 1
    if (proj_dir / "output" / "copy").is_dir():
        scripts += _count_files(proj_dir / "output" / "copy")

    if assets_dir.is_dir():
        layers_dir = assets_dir / "decomposed_layers"
        if layers_dir.is_dir():
            for f in layers_dir.iterdir():
                if f.is_file():
                    if "board" in f.name.lower() or "layer_1" in f.name.lower():
                        whiteboards += 1
                    elif "bg" in f.name.lower() or "background" in f.name.lower():
                        backgrounds += 1
        for f in assets_dir.iterdir():
            if f.is_file() and ("composited" in f.name.lower() or "scene" in f.name.lower()):
                composited += 1

    return {
        "raw_assets": raw_assets,
        "whiteboards": whiteboards,
        "backgrounds": backgrounds,
        "composited": composited,
        "scripts": scripts,
    }


def list_projects_summary(projects_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lists all projects in projects/ with their scene/asset counts."""
    target_projects_dir = projects_dir or cli.PROJECTS_DIR
    if not target_projects_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for proj in sorted(target_projects_dir.iterdir()):
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        brief_file = proj / "brief.json"
        brief_data: Dict[str, Any] = {}
        if brief_file.exists():
            try:
                brief_data = json.loads(brief_file.read_text(encoding="utf-8"))
            except Exception:
                brief_data = {}

        counts = inspect_project_counts(proj)
        items.append(
            {
                "project_id": proj.name,
                "project_name": brief_data.get("name", proj.name),
                "name": proj.name,
                "mode": brief_data.get("mode", "hybrid"),
                "path": str(proj),
                "counts": counts,
                **counts,
            }
        )
    return items


class ContentFlowHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer holding an optional workspace root override."""

    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: Any, root_dir: Optional[Path] = None):
        super().__init__(server_address, RequestHandlerClass)
        self.root_dir = root_dir


class ContentFlowRequestHandler(BaseHTTPRequestHandler):
    """Canonical HTTP request handler for ContentFlow API and Studio WebUI."""

    server: ContentFlowHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        """Silence noisy access logs during CLI/test operation."""
        return

    def _get_root_dir(self) -> Path:
        return getattr(self.server, "root_dir", None) or cli.CONTENTFLOW_ROOT

    def _get_projects_dir(self) -> Path:
        root_override = getattr(self.server, "root_dir", None)
        if root_override is not None:
            return root_override / "projects"
        return cli.PROJECTS_DIR

    def _send_json(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str, status_code: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_html(STUDIO_HTML)
            return

        if path == "/api/v1/health":
            self._send_json({"status": "ok", "service": "contentflow", "version": "0.1.0"})
            return

        if path == "/api/v1/status":
            orchestrator = FigureOrchestrator()
            router = VideoAPIRouter()
            pipelines = orchestrator.verify_pipeline_readiness()
            providers = router.get_available_providers()
            self._send_json(
                {
                    "status": "ok",
                    "pipelines": pipelines,
                    "video_providers": providers,
                    "providers": providers,
                }
            )
            return

        if path == "/api/v1/library/characters":
            lib = AssetLibrary(root_dir=self._get_root_dir())
            characters = lib.list_characters()
            self._send_json(
                {
                    "status": "ok",
                    "characters": characters,
                    "total": len(characters),
                }
            )
            return

        if path == "/api/v1/projects":
            projects = list_projects_summary(self._get_projects_dir())
            self._send_json(
                {
                    "status": "ok",
                    "projects": projects,
                    "total": len(projects),
                }
            )
            return

        self._send_json({"status": "error", "error": f"Not found: {path}"}, status_code=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json({"status": "error", "error": f"Invalid JSON body: {exc}"}, status_code=400)
            return

        if path == "/api/v1/library/characters":
            char_id = str(body.get("char_id", "")).strip()
            name = str(body.get("name", char_id)).strip()
            master_ref = str(body.get("master_ref", "")).strip()
            description = str(body.get("description", "")).strip()
            poses = body.get("poses") if isinstance(body.get("poses"), dict) else None
            if not char_id:
                self._send_json({"status": "error", "error": "char_id is required"}, status_code=400)
                return

            lib = AssetLibrary(root_dir=self._get_root_dir())
            entry = lib.register_character(
                char_id=char_id,
                name=name,
                master_ref=master_ref,
                description=description,
                poses=poses,
            )
            self._send_json({"status": "ok", "character": entry}, status_code=201)
            return

        if path == "/api/v1/projects":
            project_name = str(body.get("project_name") or body.get("name") or "").strip()
            mode = str(body.get("mode", "hybrid")).strip()
            force = bool(body.get("force", False))
            if not project_name:
                self._send_json({"status": "error", "error": "project_name is required"}, status_code=400)
                return

            projects_dir = self._get_projects_dir()
            projects_dir.mkdir(parents=True, exist_ok=True)
            prev_projects_dir = cli.PROJECTS_DIR
            try:
                cli.PROJECTS_DIR = projects_dir
                init_args = argparse.Namespace(name=project_name, force=force, mode=mode)
                cli.cmd_init_project(init_args)
                proj_dir = cli.resolve_project_dir(project_name)
            finally:
                cli.PROJECTS_DIR = prev_projects_dir

            # Ensure canonical subdirectories and persist mode in brief.json
            for sub in ("raw_assets", "whiteboards", "backgrounds", "composited", "scripts", "assets"):
                (proj_dir / sub).mkdir(parents=True, exist_ok=True)
            brief_file = proj_dir / "brief.json"
            if brief_file.exists():
                try:
                    brief_data = json.loads(brief_file.read_text(encoding="utf-8"))
                    brief_data["mode"] = mode
                    brief_file.write_text(json.dumps(brief_data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

            counts = inspect_project_counts(proj_dir)
            self._send_json(
                {
                    "status": "ok",
                    "project_id": proj_dir.name,
                    "project_name": project_name,
                    "mode": mode,
                    "path": str(proj_dir),
                    "counts": counts,
                    **counts,
                },
                status_code=201,
            )
            return

        reuse_match = re.match(r"^/api/v1/projects/([^/]+)/reuse-asset$", path)
        if reuse_match:
            project_name = unquote(reuse_match.group(1))
            req_char_id = str(body["char_id"]) if body.get("char_id") is not None else None
            req_pose = str(body["pose"]) if body.get("pose") is not None else None
            raw_asset_id = body.get("asset_id") or body.get("asset")
            asset_id = str(raw_asset_id) if raw_asset_id is not None else None

            root_dir = self._get_root_dir()
            projects_dir = self._get_projects_dir()
            prev_root = cli.CONTENTFLOW_ROOT
            prev_projects = cli.PROJECTS_DIR
            try:
                cli.CONTENTFLOW_ROOT = root_dir
                cli.PROJECTS_DIR = projects_dir
                proj_dir = cli.resolve_project_dir(project_name)
                reuse_args = argparse.Namespace(
                    project=project_name,
                    asset=asset_id,
                    char_id=req_char_id,
                    pose=req_pose,
                )
                rc = cli.cmd_reuse_asset(reuse_args)
                if rc == 0:
                    assets_dir = proj_dir / "assets"
                    files = sorted(assets_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    dest_path = str(files[0]) if files else str(assets_dir)
                    self._send_json(
                        {
                            "status": "ok",
                            "project": proj_dir.name,
                            "char_id": req_char_id,
                            "pose": req_pose,
                            "dest_path": dest_path,
                        }
                    )
                    return

                # Fallback: check library/characters/index.json poses or master_ref
                lib = AssetLibrary(root_dir=root_dir)
                chars = lib.list_characters()
                if req_char_id and req_char_id in chars:
                    cinfo = chars[req_char_id]
                    rel_target = (cinfo.get("poses") or {}).get(req_pose or "") or cinfo.get("master_ref")
                    if rel_target:
                        src_file = root_dir / rel_target
                        if src_file.exists():
                            dest_dir = proj_dir / "assets"
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest_file = dest_dir / src_file.name
                            shutil.copy2(src_file, dest_file)
                            self._send_json(
                                {
                                    "status": "ok",
                                    "project": proj_dir.name,
                                    "char_id": req_char_id,
                                    "pose": req_pose,
                                    "dest_path": str(dest_file),
                                }
                            )
                            return
            finally:
                cli.CONTENTFLOW_ROOT = prev_root
                cli.PROJECTS_DIR = prev_projects

            self._send_json(
                {"status": "error", "error": f"Asset not found for char_id={req_char_id}, pose={req_pose}"},
                status_code=404,
            )
            return

        if path == "/api/v1/format-html":
            text = str(body.get("text", ""))
            title = body.get("title")
            theme = str(body.get("theme", "tech_blue"))
            formatted = HTMLFormatter.format_text_to_html(
                text=text,
                title=str(title) if title is not None else None,
                theme_name=theme,
            )
            self._send_json(
                {
                    "status": "ok",
                    "html": formatted,
                    "title": title,
                    "theme": theme,
                }
            )
            return

        self._send_json({"status": "error", "error": f"Not found: {path}"}, status_code=404)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8090,
    root_dir: Optional[Path] = None,
) -> ContentFlowHTTPServer:
    """Creates a ThreadingHTTPServer bound to (host, port) without starting the loop."""
    return ContentFlowHTTPServer((host, port), ContentFlowRequestHandler, root_dir=root_dir)


def run_server(host: str = "127.0.0.1", port: int = 8090, root_dir: Optional[Path] = None) -> int:
    """Starts the ContentFlow Canonical HTTP API & Studio WebUI server."""
    server = create_server(host=host, port=port, root_dir=root_dir)
    raw_host, actual_port = server.server_address[:2]
    actual_host = raw_host.decode("utf-8") if isinstance(raw_host, bytes) else str(raw_host)
    print(f"[+] ContentFlow Studio WebUI & Canonical API running at http://{actual_host}:{actual_port}")
    print(f"    - Studio WebUI: http://{actual_host}:{actual_port}/")
    print(f"    - Health API:   http://{actual_host}:{actual_port}/api/v1/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down ContentFlow server...")
    finally:
        server.server_close()
    return 0

