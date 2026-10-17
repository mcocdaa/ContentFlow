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
  <title>ContentFlow Studio — 2D/3D Figurine & Holographic Video Workspace</title>
  <style>
    :root {
      --bg: #070b14;
      --surface: #111827;
      --surface-alt: #1a2436;
      --surface-elevated: #0f172a;
      --border: #2a3a52;
      --border-highlight: #38bdf8;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --cyan: #06b6d4;
      --warn: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 15% 0%, #111c35 0%, var(--bg) 55%);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      line-height: 1.45;
      min-height: 100vh;
    }
    header {
      background: rgba(15, 23, 42, 0.92);
      border-bottom: 1px solid var(--border);
      padding: 12px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(10px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
      white-space: nowrap;
    }
    .brand-sub {
      font-size: 12px;
      font-weight: 500;
      color: #7dd3fc;
      background: rgba(14, 165, 233, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 3px 9px;
      border-radius: 9999px;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 9px;
      border-radius: 9999px;
      background: var(--surface-alt);
      border: 1px solid var(--border);
      white-space: nowrap;
    }
    .badge.ok { border-color: rgba(16,185,129,0.5); color: #34d399; background: rgba(16,185,129,0.12); }
    .badge.warn { border-color: rgba(245,158,11,0.5); color: #fbbf24; background: rgba(245,158,11,0.12); }
    .badge.cyan { border-color: rgba(56,189,248,0.5); color: #38bdf8; background: rgba(56,189,248,0.12); }
    main {
      max-width: 1360px;
      margin: 0 auto;
      padding: 16px 20px 28px 20px;
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }
    .card {
      min-width: 0;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 6px 24px rgba(0,0,0,0.3);
    }
    .col-12 { grid-column: span 12; }
    .col-6 { grid-column: span 6; }
    @media (max-width: 820px) { .col-6 { grid-column: span 12; } }
    h2 {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }
    .subcard {
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
    }
    .subcard h3 {
      font-size: 13px;
      margin-bottom: 5px;
      color: #f1f5f9;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }
    .muted { color: var(--text-muted); font-size: 12px; }
    input, select, textarea {
      width: 100%;
      background: var(--surface-elevated);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 7px 10px;
      font-size: 13px;
      outline: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--border-highlight);
    }
    textarea { min-height: 112px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; resize: vertical; }
    button {
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 7px;
      padding: 7px 13px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      flex-shrink: 0;
      transition: all 0.15s ease;
    }
    button:hover { background: var(--primary-hover); }
    button.secondary {
      background: var(--surface-alt);
      border: 1px solid var(--border);
      color: #e2e8f0;
    }
    button.secondary:hover {
      border-color: var(--border-highlight);
      color: #fff;
    }
    button.secondary.active {
      background: rgba(14, 165, 233, 0.18);
      border-color: #38bdf8;
      color: #38bdf8;
    }
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }
    .form-grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }
    .field-label {
      display: block;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid rgba(51,65,85,0.65); }
    th { color: var(--text-muted); font-weight: 600; font-size: 11.5px; white-space: nowrap; }
    tr.proj-row { cursor: pointer; transition: background 0.12s; }
    tr.proj-row:hover { background: rgba(56, 189, 248, 0.08); }
    tr.proj-row.selected { background: rgba(56, 189, 248, 0.14); }
    .char-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      max-height: 175px;
      overflow-y: auto;
    }
    .pose-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-top: 6px;
    }
    .pose-pill {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(59, 130, 246, 0.14);
      border: 1px solid rgba(59, 130, 246, 0.4);
      color: #93c5fd;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.12s;
    }
    .pose-pill:hover, .pose-pill.active {
      background: var(--primary);
      border-color: var(--primary);
      color: #ffffff;
    }
    .status-toast {
      font-size: 12px;
      padding: 6px 10px;
      border-radius: 6px;
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid var(--border);
      color: var(--text-muted);
      margin-bottom: 8px;
      min-height: 31px;
      display: flex;
      align-items: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .status-toast.visible {
      background: rgba(16, 185, 129, 0.12);
      border-color: rgba(16, 185, 129, 0.4);
      color: #6ee7b7;
    }
    /* 3-Layer Holographic Compositing Gallery */
    .compositor-layout {
      display: grid;
      grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
      gap: 14px;
      align-items: stretch;
    }
    .compositor-layout > * { min-width: 0; }
    .layer-cards-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .layer-card {
      min-width: 0;
      background: var(--surface-elevated);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 8px;
      cursor: pointer;
      transition: all 0.18s ease;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .layer-card:hover {
      border-color: rgba(56, 189, 248, 0.6);
      transform: translateY(-1px);
    }
    .layer-card.active {
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.28), 0 8px 20px rgba(6, 182, 212, 0.18);
      background: rgba(14, 165, 233, 0.1);
    }
    .layer-thumb-wrap {
      width: 100%;
      aspect-ratio: 16 / 9;
      border-radius: 6px;
      overflow: hidden;
      background: repeating-conic-gradient(#162032 0% 25%, #0d1524 0% 50%) 50% / 14px 14px;
      border: 1px solid rgba(255,255,255,0.08);
      margin-bottom: 7px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .layer-thumb-wrap img {
      width: 100%;
      height: 100%;
      max-width: 100%;
      object-fit: contain;
      display: block;
    }
    .layer-title {
      font-size: 11.5px;
      font-weight: 600;
      color: #f1f5f9;
      margin-bottom: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .layer-meta {
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .spotlight-box {
      min-width: 0;
      background: var(--surface-elevated);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .spotlight-stage {
      width: 100%;
      aspect-ratio: 16 / 9;
      border-radius: 7px;
      overflow: hidden;
      background: repeating-conic-gradient(#162032 0% 25%, #0d1524 0% 50%) 50% / 16px 16px;
      border: 1px solid rgba(56, 189, 248, 0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 8px;
    }
    .spotlight-stage img {
      width: 100%;
      height: 100%;
      max-width: 100%;
      object-fit: contain;
      display: block;
    }
    .formatter-grid {
      display: grid;
      grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
      gap: 14px;
      align-items: stretch;
    }
    .formatter-grid > * { min-width: 0; }
    .preview-box {
      background: #ffffff;
      color: #1f2937;
      border-radius: 8px;
      padding: 12px;
      height: 215px;
      overflow-y: auto;
      border: 1px solid var(--border);
      zoom: 0.78;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>🎬 ContentFlow Studio</span>
      <span class="brand-sub">2D/3D Figurine & Holographic Video Engine</span>
    </div>
    <div class="header-actions">
      <span id="health-badge" class="badge ok">Checking Studio Engine...</span>
      <button class="secondary" onclick="loadStatus()">↻ Refresh</button>
    </div>
  </header>

  <main>
    <!-- Pipeline & Video Provider Readiness -->
    <section class="card col-12" style="padding: 12px 16px;">
      <h2 style="margin-bottom: 8px;">
        <span>⚡ Multi-Modal Pipeline & Video Provider Readiness</span>
        <span class="badge cyan">3 Production Modes Ready</span>
      </h2>
      <div id="status-container" class="status-grid"></div>
    </section>

    <!-- Projects Workspace -->
    <section class="card col-6">
      <h2>
        <span>📁 Projects Workspace</span>
        <span id="projects-count-badge" class="badge">7 Projects</span>
      </h2>
      <div class="row">
        <input id="new-proj-name" placeholder="New project (e.g. rag_demo)" style="flex: 1; min-width: 120px;" />
        <select id="new-proj-mode" style="width: 132px; flex-shrink: 0;">
          <option value="hybrid">Hybrid 2D/3D</option>
          <option value="3d">3D Blender</option>
          <option value="keyframe">Keyframe RIFE</option>
          <option value="api">Cloud Video API</option>
        </select>
        <button id="btn-create-project" onclick="createProject()">+ Create</button>
      </div>
      <div id="projects-container" style="max-height: 215px; overflow-y: auto;"></div>
    </section>

    <!-- Character Asset Library Browser & Reuse -->
    <section class="card col-6">
      <h2>
        <span>🧝‍♀️ Character Asset Library & Reuse</span>
        <span class="badge cyan">Click Pose Pill or Reuse</span>
      </h2>
      <div class="form-grid-2">
        <div>
          <label class="field-label" for="reuse-project">Target Project</label>
          <select id="reuse-project"></select>
        </div>
        <div>
          <label class="field-label" for="reuse-char">Character Anchor</label>
          <select id="reuse-char" onchange="syncCharacterPoseOptions()"></select>
        </div>
      </div>
      <div class="row">
        <select id="reuse-pose" style="flex: 1;"></select>
        <button id="btn-reuse-asset" onclick="reuseAsset()">Reuse Pose Into Project</button>
      </div>
      <div id="reuse-msg" class="status-toast">Select any character pose pill below to copy into Target Project</div>
      <div id="characters-container" class="char-grid"></div>
    </section>

    <!-- Visual 3-Layer Holographic Compositing Gallery -->
    <section id="compositor-section" class="card col-12">
      <h2>
        <span style="white-space: nowrap;">🖼️ 3-Layer Holographic Stage Compositing Gallery</span>
        <div style="display: flex; align-items: center; gap: 6px;">
          <select id="compositor-project" onchange="selectCompositorProject(this.value)" style="width: 175px; padding: 5px 8px; font-size: 12px;"></select>
          <button id="step-btn-z0" class="secondary" style="padding: 5px 9px; font-size: 12px;" onclick="activateLayerStep('z0')">Z=0 Stage</button>
          <button id="step-btn-z1" class="secondary" style="padding: 5px 9px; font-size: 12px;" onclick="activateLayerStep('z1')">Z=1 Board</button>
          <button id="step-btn-z2" class="secondary" style="padding: 5px 9px; font-size: 12px;" onclick="activateLayerStep('z2')">Z=2 Cutout</button>
          <button id="step-btn-final" class="secondary active" style="padding: 5px 9px; font-size: 12px;" onclick="activateLayerStep('final')">Final 1080P</button>
        </div>
      </h2>
      <div class="compositor-layout">
        <div style="display: flex; flex-direction: column; justify-content: space-between;">
          <div class="layer-cards-grid">
            <div id="layer-card-z0" class="layer-card" onclick="activateLayerStep('z0')">
              <div class="layer-thumb-wrap">
                <img id="layer-img-z0" src="/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_0_z0_background.jpg" alt="Z=0 Stage Background" />
              </div>
              <div>
                <div class="layer-title">Z=0 Stage BG</div>
                <div class="layer-meta"><span class="badge">2560×1440</span></div>
              </div>
            </div>

            <div id="layer-card-z1" class="layer-card" onclick="activateLayerStep('z1')">
              <div class="layer-thumb-wrap">
                <img id="layer-img-z1" src="/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_1_z1_全息大屏底板.png" alt="Z=1 Glowing Holographic Whiteboard" />
              </div>
              <div>
                <div class="layer-title">Z=1 Holo Board</div>
                <div class="layer-meta"><span class="badge cyan">RGBA Glass</span></div>
              </div>
            </div>

            <div id="layer-card-z2" class="layer-card" onclick="activateLayerStep('z2')">
              <div class="layer-thumb-wrap">
                <img id="layer-img-z2" src="/media/projects/002_yowane_cicd/assets/yowane_pose2_transparent.png" alt="Z=2 Rembg Figurine Cutout" />
              </div>
              <div>
                <div class="layer-title">Z=2 Cutout</div>
                <div class="layer-meta"><span class="badge ok">Alpha PNG</span></div>
              </div>
            </div>

            <div id="layer-card-final" class="layer-card active" onclick="activateLayerStep('final')">
              <div class="layer-thumb-wrap">
                <img id="layer-img-final" src="/media/projects/002_yowane_cicd/assets/yowane_v3_scene2.jpg" alt="Final 1080P Composited Frame" />
              </div>
              <div>
                <div class="layer-title">Final Composite</div>
                <div class="layer-meta"><span class="badge ok">1080P Master</span></div>
              </div>
            </div>
          </div>
          <div class="subcard" style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center; padding: 8px 12px;">
            <span class="muted">Z-Order: <strong>Z=0 Stage</strong> → <strong>Z=1 Holographic Board</strong> → <strong>Z=2 Figurine Cutout</strong></span>
            <span id="compositor-layer-tag" class="badge ok">Active: Final 1080P Composite</span>
          </div>
        </div>

        <div class="spotlight-box">
          <div class="spotlight-stage">
            <img id="compositor-spotlight-img" src="/media/projects/002_yowane_cicd/assets/yowane_v3_scene2.jpg" alt="Active Layer Preview" />
          </div>
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <div style="min-width: 0;">
              <div id="compositor-spotlight-title" style="font-size: 13px; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Final 1080P Composite • 002_yowane_cicd</div>
              <div id="compositor-spotlight-desc" class="muted" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Merged Z=0 stage + Z=1 glass board + Z=2 figurine cutout</div>
            </div>
            <span class="badge cyan">Zero Occlusion</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Interactive Whiteboard & WeChat HTML Formatter Previewer -->
    <section id="formatter-section" class="card col-12">
      <h2>
        <span>📝 Interactive Holographic Whiteboard & WeChat HTML Formatter</span>
        <span class="badge">Inline CSS • Zero External Stylesheets</span>
      </h2>
      <div class="formatter-grid">
        <div>
          <div class="row">
            <input id="fmt-title" value="3-Layer Holographic Video Pipeline" placeholder="Presentation Title" style="flex: 1;" />
            <button id="btn-render-html" onclick="formatHtml()">Render HTML</button>
          </div>
          <textarea id="fmt-text">1. **Deterministic Z-Order Stage** separating `Z=0` background, `Z=1` glass board, and `Z=2` figurine cutout.
2. **Automated Quality Gates** across unit, API, and visual regression suites.

- Zero manual glue scripts on production servers
- Full artifact traceability from script to 1080P MP4</textarea>
        </div>
        <div>
          <div id="fmt-preview" class="preview-box">Click "Render HTML" to preview...</div>
        </div>
      </div>
    </section>
  </main>

  <script>
    let STUDIO_PROJECTS = [];
    let STUDIO_CHARACTERS = {};
    let ACTIVE_PROJECT_ID = '002_yowane_cicd';
    let ACTIVE_LAYER_STEP = 'final';

    const LAYER_STEP_META = {
      z0: {
        short: 'Z=0 Stage Background',
        desc: '16:9 2560×1440 background stage decomposed without foreground clutter'
      },
      z1: {
        short: 'Z=1 Holographic Board',
        desc: 'Translucent cyan glass projection board rendered with typography cards'
      },
      z2: {
        short: 'Z=2 Figurine Cutout',
        desc: 'High-precision alpha-channel 3D figurine cutout positioned at x=2%..34%'
      },
      final: {
        short: 'Final 1080P Composite',
        desc: 'Merged Z=0 stage + Z=1 holographic whiteboard + Z=2 figurine cutout'
      }
    };

    async function loadHealth() {
      const res = await fetch('/api/v1/health');
      const data = await res.json();
      const badge = document.getElementById('health-badge');
      badge.textContent = `Studio Ready • v${data.version}`;
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
          <h3>
            <span>${info.name || key}</span>
            <span class="badge ${ready ? 'ok' : 'warn'}">${info.status.toUpperCase()}</span>
          </h3>
          <div class="muted">Deterministic stage & audio sync</div>
        `;
        container.appendChild(div);
      }
      const provDiv = document.createElement('div');
      provDiv.className = 'subcard';
      const provBadges = Object.entries(data.video_providers || {})
        .map(([k, v]) => `<span class="badge ${v ? 'ok' : 'warn'}">${k.replace('volcengine_', '')}: ${v ? 'ON' : 'SIM'}</span>`)
        .join(' ');
      provDiv.innerHTML = `<h3><span>Video Engines</span></h3><div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">${provBadges}</div>`;
      container.appendChild(provDiv);
    }

    async function loadProjects() {
      const res = await fetch('/api/v1/projects');
      const data = await res.json();
      STUDIO_PROJECTS = data.projects || [];
      const countBadge = document.getElementById('projects-count-badge');
      if (countBadge) countBadge.textContent = `${STUDIO_PROJECTS.length} Projects`;

      const container = document.getElementById('projects-container');
      const rows = STUDIO_PROJECTS.map(p => `
        <tr class="proj-row ${p.project_id === ACTIVE_PROJECT_ID ? 'selected' : ''}" onclick="selectCompositorProject('${p.project_id}')">
          <td><strong>${p.project_id}</strong></td>
          <td><span class="badge">${p.mode || 'hybrid'}</span></td>
          <td>${p.raw_assets}</td>
          <td>${p.composited}</td>
          <td>${p.scripts}</td>
        </tr>
      `).join('');
      container.innerHTML = `
        <table>
          <thead><tr><th>Project ID</th><th>Mode</th><th>Assets</th><th>Comp</th><th>Scripts</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      const reuseProjSelect = document.getElementById('reuse-project');
      const compProjSelect = document.getElementById('compositor-project');
      const prevReuse = reuseProjSelect.value || ACTIVE_PROJECT_ID;
      const optionsHtml = STUDIO_PROJECTS.map(p =>
        `<option value="${p.project_id}">${p.project_id}</option>`
      ).join('');
      reuseProjSelect.innerHTML = optionsHtml;
      compProjSelect.innerHTML = optionsHtml;

      if (STUDIO_PROJECTS.some(p => p.project_id === prevReuse)) {
        reuseProjSelect.value = prevReuse;
      }
      if (STUDIO_PROJECTS.some(p => p.project_id === ACTIVE_PROJECT_ID)) {
        compProjSelect.value = ACTIVE_PROJECT_ID;
      } else if (STUDIO_PROJECTS.length > 0) {
        ACTIVE_PROJECT_ID = STUDIO_PROJECTS[0].project_id;
        compProjSelect.value = ACTIVE_PROJECT_ID;
      }
      updateCompositorGallery();
    }

    async function createProject() {
      const project_name = document.getElementById('new-proj-name').value.trim();
      const mode = document.getElementById('new-proj-mode').value;
      if (!project_name) return;
      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name, mode })
      });
      const created = await res.json();
      document.getElementById('new-proj-name').value = '';
      if (created && created.project_id) {
        ACTIVE_PROJECT_ID = created.project_id;
      }
      await loadProjects();
      if (created && created.project_id) {
        document.getElementById('reuse-project').value = created.project_id;
      }
    }

    async function loadCharacters() {
      const res = await fetch('/api/v1/library/characters');
      const data = await res.json();
      STUDIO_CHARACTERS = data.characters || {};

      const charSelect = document.getElementById('reuse-char');
      const charList = Object.values(STUDIO_CHARACTERS);
      charSelect.innerHTML = charList.map(c =>
        `<option value="${c.char_id}">${c.name}</option>`
      ).join('');

      if (STUDIO_CHARACTERS['yowane_haku']) {
        charSelect.value = 'yowane_haku';
      }
      syncCharacterPoseOptions();
      renderCharacterCards();
    }

    function syncCharacterPoseOptions(preferredPose) {
      const charId = document.getElementById('reuse-char').value;
      const poseSelect = document.getElementById('reuse-pose');
      const charInfo = STUDIO_CHARACTERS[charId] || {};
      const poses = Object.keys(charInfo.poses || {});
      const poseList = poses.length > 0 ? poses : ['teaching', 'explaining', 'warning', 'thumbs_up'];
      poseSelect.innerHTML = poseList.map(pose =>
        `<option value="${pose}">Pose: ${pose}</option>`
      ).join('');
      if (preferredPose && poseList.includes(preferredPose)) {
        poseSelect.value = preferredPose;
      }
      renderCharacterCards();
    }

    function renderCharacterCards() {
      const container = document.getElementById('characters-container');
      const activeChar = document.getElementById('reuse-char').value;
      const activePose = document.getElementById('reuse-pose').value;

      container.innerHTML = Object.values(STUDIO_CHARACTERS).map(c => {
        const poseKeys = Object.keys(c.poses || {});
        const pills = poseKeys.length > 0
          ? poseKeys.map(p => {
              const isSelected = (c.char_id === activeChar && p === activePose);
              return `<span class="pose-pill ${isSelected ? 'active' : ''}" onclick="quickReusePose('${c.char_id}', '${p}')">${p}</span>`;
            }).join('')
          : '<span class="muted">master anchor</span>';
        return `
          <div class="subcard" style="${c.char_id === activeChar ? 'border-color: rgba(56,189,248,0.6);' : ''}">
            <h3>
              <span>${c.name}</span>
              <span class="badge">${poseKeys.length} poses</span>
            </h3>
            <div class="pose-pills">${pills}</div>
          </div>
        `;
      }).join('');
    }

    async function quickReusePose(char_id, pose) {
      document.getElementById('reuse-char').value = char_id;
      syncCharacterPoseOptions(pose);
      await reuseAsset();
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
      const msgEl = document.getElementById('reuse-msg');
      msgEl.className = 'status-toast visible';
      if (data.status === 'ok') {
        const shortFile = (data.dest_path || '').split('/').slice(-2).join('/');
        msgEl.textContent = `✅ Reused ${char_id} (${pose}) into ${data.project} → ${shortFile}`;
        ACTIVE_PROJECT_ID = data.project;
      } else {
        msgEl.textContent = `❌ ${data.error || 'Failed to reuse asset'}`;
      }
      renderCharacterCards();
      await loadProjects();
    }

    function selectCompositorProject(projectId) {
      if (!projectId) return;
      ACTIVE_PROJECT_ID = projectId;
      const compSelect = document.getElementById('compositor-project');
      if (compSelect && compSelect.value !== projectId) {
        compSelect.value = projectId;
      }
      const reuseSelect = document.getElementById('reuse-project');
      if (reuseSelect && reuseSelect.value !== projectId) {
        reuseSelect.value = projectId;
      }
      document.querySelectorAll('tr.proj-row').forEach(tr => {
        tr.classList.toggle('selected', tr.textContent.includes(projectId));
      });
      updateCompositorGallery();
    }

    function updateCompositorGallery() {
      const proj = STUDIO_PROJECTS.find(p => p.project_id === ACTIVE_PROJECT_ID) || STUDIO_PROJECTS[0];
      const layers = (proj && proj.layers) || {
        z0_background: '/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_0_z0_background.jpg',
        z1_whiteboard: '/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_1_z1_全息大屏底板.png',
        z2_cutout: '/media/projects/002_yowane_cicd/assets/yowane_pose2_transparent.png',
        final_composited: '/media/projects/002_yowane_cicd/assets/yowane_v3_scene2.jpg'
      };
      document.getElementById('layer-img-z0').src = layers.z0_background;
      document.getElementById('layer-img-z1').src = layers.z1_whiteboard;
      document.getElementById('layer-img-z2').src = layers.z2_cutout;
      document.getElementById('layer-img-final').src = layers.final_composited;
      activateLayerStep(ACTIVE_LAYER_STEP);
    }

    function activateLayerStep(step) {
      ACTIVE_LAYER_STEP = step;
      const stepMap = {
        z0: document.getElementById('layer-img-z0').src,
        z1: document.getElementById('layer-img-z1').src,
        z2: document.getElementById('layer-img-z2').src,
        final: document.getElementById('layer-img-final').src
      };
      ['z0', 'z1', 'z2', 'final'].forEach(k => {
        const card = document.getElementById(`layer-card-${k}`);
        const btn = document.getElementById(`step-btn-${k}`);
        if (card) card.classList.toggle('active', k === step);
        if (btn) btn.classList.toggle('active', k === step);
      });
      const meta = LAYER_STEP_META[step] || LAYER_STEP_META.final;
      document.getElementById('compositor-spotlight-img').src = stepMap[step] || stepMap.final;
      document.getElementById('compositor-spotlight-title').textContent = `${meta.short} • ${ACTIVE_PROJECT_ID}`;
      document.getElementById('compositor-spotlight-desc').textContent = meta.desc;
      document.getElementById('compositor-layer-tag').textContent = `Active: ${meta.short}`;
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


def resolve_project_layers(proj_dir: Path) -> Dict[str, str]:
    """Resolves 3-layer holographic compositing preview URLs for a project."""
    z0_bg = "/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_0_z0_background.jpg"
    z1_board = "/media/projects/002_yowane_cicd/assets/decomposed_layers/layer_1_z1_全息大屏底板.png"
    z2_cutout = "/media/projects/002_yowane_cicd/assets/yowane_pose2_transparent.png"
    final_comp = "/media/projects/002_yowane_cicd/assets/yowane_v3_scene2.jpg"

    pname = proj_dir.name.lower()
    if "005" in pname or "noshiro" in pname:
        z2_cutout = "/media/projects/005_transformer_noshiro_tutorial/assets/noshiro_transparent.png"
        final_comp = "/media/projects/005_transformer_noshiro_tutorial/images/scene_2.jpg"
    elif "004" in pname or "2b" in pname:
        z2_cutout = "/media/library/characters/yorha_2b/teaching/2b_teaching_base_url.jpg"
        final_comp = "/media/projects/004_ai_api_tutorial_2b/assets/scene2_base_url.jpg"
    else:
        assets_dir = proj_dir / "assets"
        if assets_dir.is_dir():
            for f in sorted(assets_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    fname = f.name.lower()
                    if "2b" in fname:
                        z2_cutout = "/media/library/characters/yorha_2b/teaching/2b_teaching_base_url.jpg"
                        final_comp = "/media/projects/004_ai_api_tutorial_2b/assets/scene2_base_url.jpg"
                        break
                    if "noshiro" in fname:
                        z2_cutout = "/media/projects/005_transformer_noshiro_tutorial/assets/noshiro_transparent.png"
                        final_comp = "/media/projects/005_transformer_noshiro_tutorial/images/scene_2.jpg"
                        break

    return {
        "z0_background": z0_bg,
        "z1_whiteboard": z1_board,
        "z2_cutout": z2_cutout,
        "final_composited": final_comp,
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
        layers = resolve_project_layers(proj)
        items.append(
            {
                "project_id": proj.name,
                "project_name": brief_data.get("name", proj.name),
                "name": proj.name,
                "mode": brief_data.get("mode", "hybrid"),
                "path": str(proj),
                "counts": counts,
                "layers": layers,
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

    def _send_media_file(self, rel_media_path: str) -> None:
        clean_rel = unquote(rel_media_path).lstrip("/")
        for candidate_root in (self._get_root_dir(), cli.CONTENTFLOW_ROOT):
            base_resolved = candidate_root.resolve()
            target = (base_resolved / clean_rel).resolve()
            if not str(target).startswith(str(base_resolved)):
                continue
            if target.is_file() and target.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
                ext = target.suffix.lower()
                mime_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".svg": "image/svg+xml",
                }
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime_map.get(ext, "application/octet-stream"))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                self.wfile.write(data)
                return
        self._send_json({"status": "error", "error": f"Media not found: {clean_rel}"}, status_code=404)

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

        if path.startswith("/media/"):
            self._send_media_file(path[len("/media/") :])
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

