"""Unit tests for ContentFlow core modules, CLI, and skill scripts."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import cli
from core.asset_library import AssetLibrary
from core.copywriting import CopywritingEngine
from core.figure_orchestrator import FigurePipelineMode, FigureVideoOrchestrator
from core.html_formatter import _format_inline, markdown_to_wechat_html
from core.models import FactSheet
from core.video_api_router import VideoApiRouter


def _load_script_module(name: str, rel_path: str):
    script_path = Path(__file__).resolve().parent.parent / rel_path
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_formatter_escaped_inline_and_ordered_lists() -> None:
    md = (
        "# Heading <1>\n\n"
        "Paragraph with **<bold> & text** and `x < y & z > 0`.\n\n"
        "- Bullet one\n"
        "- Bullet two\n\n"
        "1. First ordered item\n"
        "2. Second ordered item\n"
    )
    html_out = markdown_to_wechat_html(md, theme_name="tech_blue", title="Custom <Title>")
    assert "Custom &lt;Title&gt;" in html_out
    assert "Heading &lt;1&gt;" in html_out
    assert "&lt;bold&gt; &amp; text" in html_out
    assert "x &lt; y &amp; z &gt; 0" in html_out
    assert "<ul " in html_out and "</ul>" in html_out
    assert "<ol " in html_out and "</ol>" in html_out
    assert "<li " in html_out
    # Ensure inline formatter escapes raw HTML tags
    inline = _format_inline("<script>alert(1)</script> **ok**", {"primary": "#000", "code_bg": "#eee"})
    assert "<script>" not in inline
    assert "&lt;script&gt;" in inline


def test_asset_library_crud_and_master_reference(tmp_path: Path) -> None:
    lib = AssetLibrary(root_dir=tmp_path)
    src_img = tmp_path / "sample.jpg"
    Image.new("RGB", (64, 64), color=(100, 150, 200)).save(src_img)

    item = lib.register_asset(
        src_path=src_img,
        asset_id="test_char_teaching",
        asset_type="image",
        category="character",
        character_id="test_char",
        emotion="teaching",
        tags=["pointer", "16:9"],
        project_id="001_demo",
    )
    assert item.id == "test_char_teaching"
    assert "001_demo" in item.used_in_projects

    found = lib.search_assets(character_id="test_char", emotion="teaching")
    assert len(found) == 1
    assert found[0].id == "test_char_teaching"

    ref = lib.get_character_master_reference("test_char")
    assert ref is not None and ref.exists()

    master = lib.set_character_master_reference("test_char", src_img)
    assert master.exists()
    assert lib.get_character_master_reference("test_char") == master


def test_video_api_router_does_not_autoselect_stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("KLING_ACCESS_KEY", "dummy_kling_ak")
    monkeypatch.setenv("KLING_SECRET_KEY", "dummy_kling_sk")
    monkeypatch.setenv("MINIMAX_API_KEY", "dummy_minimax_key")

    router = VideoApiRouter()
    providers = router.get_available_providers()
    assert providers["volcengine_seedance"] is False
    assert providers["kling_ai"] is False
    assert providers["minimax"] is False
    assert providers["local_simulator"] is True

    img = tmp_path / "anchor.jpg"
    Image.new("RGB", (64, 64), color=(20, 40, 60)).save(img)
    out_mp4 = tmp_path / "out.mp4"

    with patch.object(router, "_dispatch_simulator", return_value=out_mp4) as mock_sim:
        res = router.generate_video_from_image(
            image_path=img,
            prompt="test dance",
            provider="auto",
            output_path=out_mp4,
        )
        assert res == out_mp4
        mock_sim.assert_called_once()


def test_figure_orchestrator_readiness_and_invalid_mode(tmp_path: Path) -> None:
    fo = FigureVideoOrchestrator()
    readiness = fo.get_pipeline_readiness()
    assert "mode_1_3d" in readiness
    assert "mode_2_keyframe" in readiness
    assert "mode_3_api" in readiness
    assert FigurePipelineMode.THREE_D.value == "3d"

    with pytest.raises(ValueError, match="Unknown pipeline mode"):
        fo.run_pipeline(mode="invalid_mode", project_dir=tmp_path)


def test_cli_init_copy_and_reuse_asset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "CONTENTFLOW_ROOT", tmp_path)
    monkeypatch.setattr(cli, "PROJECTS_DIR", projects_dir)

    # 1. init-project
    init_args = argparse.Namespace(name="TestApp", force=False)
    assert cli.cmd_init_project(init_args) == 0
    proj_dir = projects_dir / "001_testapp"
    assert (proj_dir / "brief.json").exists()

    # 2. generate-copy
    copy_args = argparse.Namespace(project="001_testapp", theme="tech_blue")
    assert cli.cmd_generate_copy(copy_args) == 0
    assert (proj_dir / "output" / "copy" / "wechat.html").exists()

    # 3. reuse-asset via AssetLibrary and CLI subparser
    lib = AssetLibrary(root_dir=tmp_path)
    src_img = tmp_path / "char.png"
    Image.new("RGBA", (32, 32), color=(255, 0, 0, 255)).save(src_img)
    lib.register_asset(
        src_path=src_img,
        asset_id="yowane_pose2_pointer",
        category="character",
        character_id="yowane_haku",
        emotion="warning",
        tags=["pointer"],
    )

    with patch("core.asset_library.AssetLibrary", return_value=lib):
        monkeypatch.setattr(
            "sys.argv",
            ["cli.py", "reuse-asset", "--project", "001_testapp", "--char-id", "yowane_haku", "--pose", "pointer"],
        )
        rc = cli.main()
        assert rc == 0
        assert (proj_dir / "assets" / "yowane_pose2_pointer.png").exists()


def test_copywriting_engine() -> None:
    facts = FactSheet.from_dict(
        {
            "project_id": "001_demo",
            "name": "DemoFlow",
            "tagline": "Fast content automation",
            "category": "AI Tools",
            "description": "End-to-end content suite",
            "pain_points": ["Slow manual editing"],
            "solutions": ["Automated rendering"],
            "key_features": [{"name": "Fast", "headline": "10x speed", "detail": "Uses native pipelines."}],
        }
    )
    engine = CopywritingEngine()
    pkg = engine.generate_all(facts)
    assert "DemoFlow" in pkg.wechat_md
    assert "<ol " in pkg.wechat_html
    assert len(pkg.scenes) == 4


def test_skill_scripts_helpers(tmp_path: Path) -> None:
    gen_pose = _load_script_module("generate_pose", ".agents/skills/figure-tutorial-video/scripts/generate_pose.py")
    assert (
        gen_pose.normalize_ark_url("https://ark.cn-beijing.volces.com/api/v3")
        == "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    )
    assert (
        gen_pose.normalize_ark_url("https://ark.cn-beijing.volces.com/api/plan/v3/")
        == "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations"
    )
    prompt = gen_pose.resolve_pose_prompt("warning_pointer")
    assert "激光教鞭" in prompt

    comp = _load_script_module("composite_scene", ".agents/skills/figure-tutorial-video/scripts/composite_scene.py")
    proj_dir = tmp_path / "proj"
    layers_dir = proj_dir / "assets" / "decomposed_layers"
    layers_dir.mkdir(parents=True)
    bg_path = layers_dir / "layer_0_z0_background.jpg"
    board_path = layers_dir / "layer_1_z1_全息大屏底板.png"
    char_path = proj_dir / "assets" / "char_transparent.png"
    Image.new("RGB", (2560, 1440), color=(20, 30, 40)).save(bg_path)
    Image.new("RGBA", (1389, 781), color=(0, 50, 80, 180)).save(board_path)
    Image.new("RGBA", (400, 900), color=(255, 200, 200, 255)).save(char_path)

    outputs = comp.batch_composite_project(proj_dir)
    assert len(outputs) == 1
    assert outputs[0].exists()


def test_canonical_http_server_and_webui(tmp_path: Path) -> None:
    import threading
    import requests
    from core.server import create_server

    # Seed a character pose asset in tmp_path library
    lib = AssetLibrary(root_dir=tmp_path)
    src_img = tmp_path / "yowane.png"
    Image.new("RGBA", (32, 32), color=(10, 20, 30, 255)).save(src_img)
    lib.register_asset(
        src_path=src_img,
        asset_id="yowane_teaching_pose",
        category="character",
        character_id="yowane_haku",
        emotion="teaching",
        tags=["teaching"],
    )

    server = create_server(host="127.0.0.1", port=0, root_dir=tmp_path)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. GET /api/v1/health
        r_health = requests.get(f"{base_url}/api/v1/health", timeout=5)
        assert r_health.status_code == 200
        assert r_health.json() == {"status": "ok", "service": "contentflow", "version": "0.1.0"}

        # 2. GET /api/v1/status
        r_status = requests.get(f"{base_url}/api/v1/status", timeout=5)
        assert r_status.status_code == 200
        status_data = r_status.json()
        assert status_data["status"] == "ok"
        assert "pipelines" in status_data
        assert "video_providers" in status_data

        # 3. POST & GET /api/v1/library/characters
        r_char_post = requests.post(
            f"{base_url}/api/v1/library/characters",
            json={
                "char_id": "noshiro",
                "name": "Noshiro",
                "master_ref": "library/characters/noshiro/master_reference.jpg",
                "description": "3D PVC figurine teacher",
            },
            timeout=5,
        )
        assert r_char_post.status_code == 201
        assert r_char_post.json()["character"]["char_id"] == "noshiro"

        r_chars = requests.get(f"{base_url}/api/v1/library/characters", timeout=5)
        assert r_chars.status_code == 200
        chars_payload = r_chars.json()
        assert "noshiro" in chars_payload["characters"]
        assert "yowane_haku" in chars_payload["characters"]

        # 4. POST & GET /api/v1/projects
        r_proj_post = requests.post(
            f"{base_url}/api/v1/projects",
            json={"project_name": "api_studio_demo", "mode": "3d"},
            timeout=5,
        )
        assert r_proj_post.status_code == 201
        created_proj = r_proj_post.json()
        assert created_proj["project_id"] == "001_api_studio_demo"
        assert created_proj["mode"] == "3d"

        r_projs = requests.get(f"{base_url}/api/v1/projects", timeout=5)
        assert r_projs.status_code == 200
        projs_list = r_projs.json()["projects"]
        assert len(projs_list) == 1
        assert projs_list[0]["project_id"] == "001_api_studio_demo"
        for count_key in ("raw_assets", "whiteboards", "backgrounds", "composited", "scripts"):
            assert count_key in projs_list[0]

        # 5. POST /api/v1/projects/{project_name}/reuse-asset
        r_reuse = requests.post(
            f"{base_url}/api/v1/projects/001_api_studio_demo/reuse-asset",
            json={"char_id": "yowane_haku", "pose": "teaching"},
            timeout=5,
        )
        assert r_reuse.status_code == 200
        assert r_reuse.json()["status"] == "ok"

        # 6. POST /api/v1/format-html
        r_fmt = requests.post(
            f"{base_url}/api/v1/format-html",
            json={"text": "# Section 1\n\n- **Point** A", "title": "Board Title"},
            timeout=5,
        )
        assert r_fmt.status_code == 200
        html_str = r_fmt.json()["html"]
        assert "Board Title" in html_str
        assert "<strong" in html_str

        # 7. GET / Studio WebUI & Bilingual (EN/ZH) I18N Dictionary
        r_ui = requests.get(f"{base_url}/", timeout=5)
        assert r_ui.status_code == 200
        assert "ContentFlow Studio" in r_ui.text
        assert "/api/v1/health" in r_ui.text
        assert "3-Layer Holographic Stage Compositing Gallery" in r_ui.text
        assert "curl -s" not in r_ui.text
        assert 'id="lang-toggle-btn"' in r_ui.text
        assert "localStorage.getItem('contentflow_lang')" in r_ui.text
        for en_phrase in (
            "3D Render + AI Interpolation",
            "2D Keyframe + Motion Synthesis",
            "Single Figurine -> Video LLM",
            "001 · Universal Dev Engine",
            "002 · Yowane Haku CI/CD",
            "Yowane Haku",
        ):
            assert en_phrase in r_ui.text
        for zh_phrase in (
            "多模态生产管线与视频引擎就绪状态",
            "项目工作区",
            "角色数字资产库与动作复用",
            "三层全息舞台解耦合成预览",
            "全渠道文案与全息白板排版引擎",
            "ContentFlow Studio — 2D/3D 手办与全息教学视频工作台",
            "点击「渲染全息排版」预览排版效果...",
            "001 · 通用开发引擎科普",
            "002 · 弱音白 CI/CD 教程",
            "复用资产失败",
            "未找到角色资产",
        ):
            assert zh_phrase in r_ui.text
        assert 'data-i18n="fmt_preview_placeholder"' in r_ui.text
        assert 'data-i18n="health_checking"' in r_ui.text
        assert 'data-i18n-alt="alt_layer_z0"' in r_ui.text
        assert "No video projects yet" in r_ui.text
        assert "暂无短视频工程" in r_ui.text
        assert "No character assets yet" in r_ui.text
        assert "暂无角色立绘资产" in r_ui.text
        assert "document.title = t('page_title')" in r_ui.text
        assert "sanitizeAsciiFilename" in r_ui.text
        assert "FMT_LINE_MAP" in r_ui.text
        assert "translateFmtFields" in r_ui.text

        # 8. GET /media/ character asset
        r_media = requests.get(
            f"{base_url}/media/library/characters/yowane_haku/teaching/yowane_teaching_pose.png",
            timeout=5,
        )
        assert r_media.status_code == 200
        assert r_media.headers["Content-Type"] == "image/png"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_resolve_project_layers_per_project(tmp_path: Path) -> None:
    from core.server import resolve_project_layers

    layers_002 = resolve_project_layers(tmp_path / "002_yowane_cicd")
    assert "002_yowane_cicd" in layers_002["z1_whiteboard"]
    assert "yowane" in layers_002["z2_cutout"]

    layers_005 = resolve_project_layers(tmp_path / "005_transformer_noshiro_tutorial")
    assert layers_005["z0_background"] != layers_002["z0_background"]
    assert layers_005["z1_whiteboard"] != layers_002["z1_whiteboard"]
    assert "noshiro" in layers_005["z2_cutout"]
    assert "005_transformer_noshiro_tutorial" in layers_005["final_composited"]

    layers_004 = resolve_project_layers(tmp_path / "004_ai_api_tutorial_2b")
    assert layers_004["z0_background"] != layers_002["z0_background"]
    assert layers_004["z1_whiteboard"] != layers_002["z1_whiteboard"]
    assert "2b" in layers_004["z2_cutout"]
    assert "004_ai_api_tutorial_2b" in layers_004["final_composited"]

    layers_006 = resolve_project_layers(tmp_path / "006_deepseek_whale_phone_number")
    assert layers_006["z1_whiteboard"] != layers_002["z1_whiteboard"]
    assert "006_deepseek_whale_phone_number" in layers_006["final_composited"]
