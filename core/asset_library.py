"""Digital Asset Management & Centralized Reuse Library for ContentFlow.
Enables cross-project asset accumulation, semantic tagging, and smart reuse
for characters, scenes, props, and video clips.
"""

from __future__ import annotations
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AssetItem:
    id: str
    type: str  # "image", "video", "audio"
    category: str  # "character", "prop", "scene", "bgm", "sfx"
    tags: List[str] = field(default_factory=list)
    aspect_ratio: str = "16:9"  # "16:9", "9:16", "1:1"
    resolution: str = "2560x1440"
    file_path: str = ""  # Relative to workspace root or library
    character_id: Optional[str] = None
    emotion: Optional[str] = None  # e.g., "teaching", "angry", "sigh", "thumbs_up", "calm"
    prompt: str = ""
    used_in_projects: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z")
    license: str = "CC BY-NC-SA 4.0"
    author: str = "ContentFlow Studio"
    source_url: str = ""
    attribution_required: bool = True
    credit_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssetItem:
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class AssetLibrary:
    """Central asset hub managing cataloging, semantic matching, and cross-project reuse."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).resolve().parent.parent
        self.lib_dir = self.root_dir / "library"
        self.registry_file = self.lib_dir / "registry.json"
        self.characters_dir = self.lib_dir / "characters"
        self.scenes_dir = self.lib_dir / "scenes"
        self.props_dir = self.lib_dir / "props"
        self.audio_dir = self.lib_dir / "audio"
        self._ensure_dirs()
        self.assets: Dict[str, AssetItem] = {}
        self.load_registry()

    def _ensure_dirs(self) -> None:
        for d in [self.lib_dir, self.characters_dir, self.scenes_dir, self.props_dir, self.audio_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("assets", []):
                        asset = AssetItem.from_dict(item)
                        self.assets[asset.id] = asset
            except Exception as e:
                print(f"[!] Warning: failed to load asset registry: {e}")
        else:
            self.save_registry()

    def save_registry(self) -> None:
        data = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "total_assets": len(self.assets),
            "assets": [a.to_dict() for a in self.assets.values()],
        }
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_asset(
        self,
        src_path: Path,
        asset_id: str,
        asset_type: str = "image",
        category: str = "character",
        character_id: Optional[str] = None,
        emotion: Optional[str] = None,
        tags: Optional[List[str]] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "2560x1440",
        prompt: str = "",
        project_id: Optional[str] = None,
        license: str = "CC BY-NC-SA 4.0",
        author: str = "ContentFlow Studio",
        source_url: str = "",
        attribution_required: bool = True,
        credit_line: str = "",
    ) -> AssetItem:
        """Copies asset into the centralized library and indexes it."""
        ext = src_path.suffix.lower()
        if category == "character" and character_id:
            dest_dir = self.characters_dir / character_id / (emotion or "general")
        elif category == "scene":
            dest_dir = self.scenes_dir
        elif category == "prop":
            dest_dir = self.props_dir
        elif category == "motion":
            dest_dir = self.lib_dir / "motions"
        else:
            dest_dir = self.lib_dir / "misc"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{asset_id}{ext}"
        dest_path = dest_dir / dest_filename
        if src_path.resolve() != dest_path.resolve():
            shutil.copy2(src_path, dest_path)

        rel_path = dest_path.relative_to(self.root_dir).as_posix()
        existing = self.assets.get(asset_id)
        used_projects = existing.used_in_projects if existing else []
        if project_id and project_id not in used_projects:
            used_projects.append(project_id)

        tag_list = tags or []
        if emotion and emotion not in tag_list:
            tag_list.append(emotion)
        if character_id and character_id not in tag_list:
            tag_list.append(character_id)

        item = AssetItem(
            id=asset_id,
            type=asset_type,
            category=category,
            character_id=character_id,
            emotion=emotion,
            tags=tag_list,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            file_path=rel_path,
            prompt=prompt,
            used_in_projects=used_projects,
            license=license,
            author=author,
            source_url=source_url,
            attribution_required=attribution_required,
            credit_line=credit_line,
        )
        self.assets[asset_id] = item
        self.save_registry()
        print(f"[+] Asset registered in library: {asset_id} -> {rel_path}")
        return item

    def search_assets(
        self,
        character_id: Optional[str] = None,
        emotion: Optional[str] = None,
        tags: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = "16:9",
    ) -> List[AssetItem]:
        """Queries reusable assets by character, emotion, tags, and aspect ratio."""
        results = []
        for item in self.assets.values():
            if character_id and item.character_id != character_id:
                continue
            if emotion and item.emotion != emotion:
                continue
            if aspect_ratio and item.aspect_ratio != aspect_ratio:
                continue
            if tags:
                item_tags = set(t.lower() for t in item.tags)
                match_count = sum(1 for req_t in tags if req_t.lower() in item_tags)
                if match_count == 0:
                    continue
            results.append(item)
        return results

    def get_character_master_reference(self, character_id: str) -> Optional[Path]:
        """Retrieves the master reference anchor image for a character."""
        char_dir = self.characters_dir / character_id
        ref_file = char_dir / "master_reference.jpg"
        if ref_file.exists():
            return ref_file
        # Fallback to any registered asset for this character
        candidates = self.search_assets(character_id=character_id)
        if candidates:
            p = self.root_dir / candidates[0].file_path
            if p.exists():
                return p
        return None

    def set_character_master_reference(self, character_id: str, src_path: Path) -> Path:
        """Sets the official master reference anchor image for a character."""
        char_dir = self.characters_dir / character_id
        char_dir.mkdir(parents=True, exist_ok=True)
        dest = char_dir / "master_reference.jpg"
        shutil.copy2(src_path, dest)
        print(f"[+] Master reference set for character {character_id}: {dest}")
        return dest

    def list_characters(self) -> Dict[str, Dict[str, Any]]:
        """Lists all characters and their poses from library/characters/index.json and registry."""
        index_file = self.characters_dir / "index.json"
        characters: Dict[str, Dict[str, Any]] = {}
        if index_file.exists():
            try:
                raw = json.loads(index_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    chars_data = raw.get("characters", raw)
                    if isinstance(chars_data, dict):
                        for cid, cinfo in chars_data.items():
                            if isinstance(cinfo, dict):
                                characters[cid] = {
                                    "char_id": cid,
                                    "name": cinfo.get("name", cid.replace("_", " ").title()),
                                    "master_ref": cinfo.get("master_ref", ""),
                                    "description": cinfo.get("description", ""),
                                    "poses": dict(cinfo.get("poses", {})),
                                }
            except Exception as e:
                print(f"[!] Warning: failed to read character index.json: {e}")

        # Merge characters from characters_dir subdirectories
        if self.characters_dir.exists():
            for sub in sorted(self.characters_dir.iterdir()):
                if sub.is_dir():
                    cid = sub.name
                    entry = characters.setdefault(
                        cid,
                        {
                            "char_id": cid,
                            "name": cid.replace("_", " ").title(),
                            "master_ref": "",
                            "description": f"Character {cid}",
                            "poses": {},
                        },
                    )
                    master_file = sub / "master_reference.jpg"
                    if master_file.exists() and not entry.get("master_ref"):
                        entry["master_ref"] = master_file.relative_to(self.root_dir).as_posix()
                    for pose_dir in sorted(sub.iterdir()):
                        if pose_dir.is_dir():
                            pose_files = sorted(
                                p
                                for p in pose_dir.iterdir()
                                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                            )
                            if pose_files and pose_dir.name not in entry["poses"]:
                                entry["poses"][pose_dir.name] = pose_files[0].relative_to(self.root_dir).as_posix()

        # Merge character assets from registry
        for asset in self.assets.values():
            if asset.category == "character" and asset.character_id:
                cid = asset.character_id
                entry = characters.setdefault(
                    cid,
                    {
                        "char_id": cid,
                        "name": cid.replace("_", " ").title(),
                        "master_ref": "",
                        "description": asset.prompt or f"Character {cid}",
                        "poses": {},
                    },
                )
                pose_key = asset.emotion or asset.id
                if pose_key and pose_key not in entry["poses"]:
                    entry["poses"][pose_key] = asset.file_path

        # Merge 3D character rigs from library/models subdirectories
        models_dir = self.lib_dir / "models"
        if models_dir.exists():
            for sub in sorted(models_dir.iterdir()):
                if sub.is_dir():
                    pmx_files = sorted(sub.glob("*.pmx"))
                    if pmx_files:
                        cid = sub.name
                        characters.setdefault(
                            cid,
                            {
                                "char_id": cid,
                                "name": cid.replace("_", " ").title(),
                                "master_ref": pmx_files[0].relative_to(self.root_dir).as_posix(),
                                "description": f"3D PMX Rig ({pmx_files[0].name})",
                                "poses": {"3d_rig": pmx_files[0].relative_to(self.root_dir).as_posix()},
                            },
                        )

        return characters

    def register_character(
        self,
        char_id: str,
        name: str,
        master_ref: str = "",
        description: str = "",
        poses: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Registers or updates a character in library/characters/index.json."""
        index_file = self.characters_dir / "index.json"
        characters = self.list_characters()
        char_dir = self.characters_dir / char_id
        char_dir.mkdir(parents=True, exist_ok=True)

        existing = characters.get(char_id, {})
        merged_poses = dict(existing.get("poses", {}))
        if poses:
            merged_poses.update(poses)

        entry: Dict[str, Any] = {
            "char_id": char_id,
            "name": name or char_id.replace("_", " ").title(),
            "master_ref": master_ref or existing.get("master_ref", ""),
            "description": description or existing.get("description", ""),
            "poses": merged_poses,
        }
        characters[char_id] = entry

        index_payload = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "characters": characters,
        }
        index_file.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return entry

    def generate_project_credits(
        self,
        project_id: str,
        extra_credits: Optional[List[str]] = None,
    ) -> str:
        """Generates a complete Bilibili Credits (借物表) and GB 45438-2025 AIGC compliance block."""
        proj_key = project_id.strip()
        matched_assets: List[AssetItem] = []
        for asset in self.assets.values():
            for used in asset.used_in_projects:
                if (
                    used == proj_key
                    or used.startswith(f"{proj_key}_")
                    or proj_key.startswith(f"{used}_")
                    or (len(proj_key) >= 3 and proj_key.lower() in used.lower())
                ):
                    matched_assets.append(asset)
                    break

        credit_lines: List[str] = []
        seen_credits = set()

        for asset in matched_assets:
            if not asset.attribution_required and not asset.credit_line:
                continue
            line = asset.credit_line.strip() if asset.credit_line else ""
            if not line:
                url_part = f" ({asset.source_url})" if asset.source_url else ""
                line = f"{asset.category.upper()} [{asset.id}] — 作者/来源: {asset.author} | 协议: {asset.license}{url_part}"
            if line not in seen_credits:
                seen_credits.add(line)
                credit_lines.append(f"- {line}")

        # Default fallback based on project_id keywords if no registry match yet
        if not credit_lines:
            low_id = proj_key.lower()
            if "dafeiyu" in low_id or "whale" in low_id or "007" in low_id or "006" in low_id:
                credit_lines.append(
                    "- 角色设定：DeepSeek娘（蓝色大肥鱼 / 鲸鱼娘）— 初版拟人设定：@上善无形（溟月）| 模型与三视图设计：@ZipZipPipe（遵循 CC BY-NC-SA 4.0 协议）"
                )
                credit_lines.append(
                    "- MMD动作数据：Phone Number by ureshiiiiii | 3D骨骼基底参考：TDA Luka Dress (TDA / agahat) | 音乐原曲：TAHITI - Phone Number"
                )
            elif "noshiro" in low_id or "005" in low_id:
                credit_lines.append(
                    "- 角色原型：《碧蓝航线》能代 (Noshiro) — 版权归属 Manjuu & Yongshi / 原画设计：ATDAN（非商业同人科普二创）"
                )
            elif "2b" in low_id or "004" in low_id:
                credit_lines.append(
                    "- 角色原型：YoRHa No.2 Type B (2B) — 出自《NieR:Automata》SQUARE ENIX / 角色设计：吉田明彦 (Akihiko Yoshida)"
                )
            elif "yowane" in low_id or "002" in low_id:
                credit_lines.append(
                    "- 角色原型：弱音ハク (Yowane Haku) — 原案设计 CAFFEIN / Crypton Future Media, INC. (Piapro Character License / CC BY-NC 3.0)"
                )

        if extra_credits:
            for ec in extra_credits:
                clean_ec = ec.strip().lstrip("-• ").strip()
                if clean_ec and clean_ec not in seen_credits:
                    seen_credits.add(clean_ec)
                    credit_lines.append(f"- {clean_ec}")

        # Always include compliant typography, TTS voice, and AIGC declaration
        credit_lines.append(
            "- 视觉与视频生成引擎：ContentFlow Studio × 火山方舟 Doubao-Seedream-5.0-Pro / 可灵 Kling AI / Wan2.1"
        )
        credit_lines.append(
            "- 语音合成 (TTS)：100% 使用火山引擎 Seed-TTS 2.0 / Microsoft Edge Neural 官方授权商用合成音色（严禁未经授权克隆真人或声优原声）"
        )
        credit_lines.append(
            "- 字幕与封面字库：Google Noto Sans CJK (SIL Open Font License 1.1) / 文泉驿正黑 WenQuanYi Zen Hei (GPLv2 + Font Exception) 免费商用开源字库"
        )

        block = [
            "### 📜 借物表 (Credits) 与 AIGC 合规声明",
            "",
            *credit_lines,
            "",
            "#### ⚖️ AIGC 标识与法律合规声明",
            "- **合成内容标识**：依据国家标准 **GB 45438-2025《人工智能生成合成内容标识办法》**，本作品包含由人工智能生成合成的画面、语音与分镜编排，已在视频角标、简介及元数据中完成显式与隐式标识。",
            "- **声音权益保护**：依据 **《中华人民共和国民法典》第1023条**，本管线严禁未经授权克隆任何真人或动漫声优原声，全片 100% 采用官方授权合成音色。",
            "- **同人二创声明**：本项目为非商业性技术科普与 AI 创作实验演示，所涉二次元角色形象版权归各自原著作权人所有，衍生资产遵循 CC BY-NC-SA 4.0 或对应同人创作规范。",
        ]
        return "\n".join(block)
