"""Digital Asset Management & Centralized Reuse Library for ContentFlow.
Enables cross-project asset accumulation, semantic tagging, and smart reuse
for characters, scenes, props, and video clips.
"""

from __future__ import annotations
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime


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
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssetItem:
        return cls(**data)


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
            "updated_at": datetime.utcnow().isoformat() + "Z",
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
    ) -> AssetItem:
        """Copies asset into the centralized library and indexes it."""
        ext = src_path.suffix.lower()
        if category == "character" and character_id:
            dest_dir = self.characters_dir / character_id / (emotion or "general")
        elif category == "scene":
            dest_dir = self.scenes_dir
        elif category == "prop":
            dest_dir = self.props_dir
        else:
            dest_dir = self.lib_dir / "misc"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{asset_id}{ext}"
        dest_path = dest_dir / dest_filename
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
