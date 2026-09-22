"""Data models for ContentFlow.
Represents project facts, storyboard scenes, and multi-channel content packages.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json


@dataclass
class FeatureItem:
    name: str
    headline: str
    detail: str


@dataclass
class FactSheet:
    project_id: str
    name: str
    tagline: str
    category: str
    description: str
    target_audience: List[str] = field(default_factory=list)
    pain_points: List[str] = field(default_factory=list)
    solutions: List[str] = field(default_factory=list)
    key_features: List[FeatureItem] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    call_to_action: str = ""
    links: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FactSheet:
        features = [
            FeatureItem(**f) if isinstance(f, dict) else f
            for f in data.get("key_features", [])
        ]
        return cls(
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
            tagline=data.get("tagline", ""),
            category=data.get("category", "Software"),
            description=data.get("description", ""),
            target_audience=data.get("target_audience", []),
            pain_points=data.get("pain_points", []),
            solutions=data.get("solutions", []),
            key_features=features,
            tech_stack=data.get("tech_stack", []),
            highlights=data.get("highlights", []),
            call_to_action=data.get("call_to_action", ""),
            links=data.get("links", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoryboardScene:
    scene_id: int
    title: str
    narration: str
    visual_description: str
    asset_path: Optional[str] = None
    duration_estimate: float = 4.0


@dataclass
class ContentPackage:
    project_id: str
    wechat_md: str
    wechat_html: str
    xiaohongshu: str
    zhihu: str
    v2ex: str
    release: str
    video_script: str
    scenes: List[StoryboardScene] = field(default_factory=list)
