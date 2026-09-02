from __future__ import annotations

import re
from pathlib import Path

from ..config import PublishingConfig, RightsConfig
from ..models import SourceMetadata
from ..utils.files import atomic_write_json, atomic_write_text
from .rights import attribution_for


def _keywords(metadata: SourceMetadata) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", metadata.title)
    candidates = ["中文字幕", "简体中文", metadata.channel, *words]
    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        cleaned = item.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result[:20]


def generate_publishing_assets(
    metadata: SourceMetadata,
    output_dir: Path,
    config: PublishingConfig,
    rights: RightsConfig | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    faithful = f"{metadata.title}（忠实中文标题待人工确认）"
    natural = f"{metadata.title}｜中文字幕"
    concise = metadata.title
    titles = f"1. 忠实版：{faithful}\n2. 平台自然版：{natural}\n3. 精简版：{concise}\n"
    source_url = (
        metadata.source_input
        if metadata.source_type == "webpage_media"
        else metadata.source_url or metadata.source_input
    )
    attribution = (
        attribution_for(metadata, rights)
        if rights is not None and rights.basis != "unspecified"
        else config.attribution_template.format(
            channel=metadata.channel or "（请填写原作者）",
            source_url=source_url,
        )
    )
    permission_note = config.permission_note
    if rights is not None and rights.permission_reference.strip():
        permission_note = rights.permission_reference.strip()
    description = (
        f"本视频为《{metadata.title}》的简体中文本地化版本。\n\n"
        f"{attribution}\n\n"
        f"许可说明：{permission_note}\n\n"
        "发布前请人工核对中文标题、许可范围、专有名词及平台规则。"
    )
    tags = _keywords(metadata)
    title_path = output_dir / "title.txt"
    description_path = output_dir / "description.txt"
    tags_path = output_dir / "tags.txt"
    json_path = output_dir / "metadata_localized.json"
    atomic_write_text(title_path, titles)
    atomic_write_text(description_path, description + "\n")
    atomic_write_text(tags_path, ", ".join(tags) + "\n")
    atomic_write_json(
        json_path,
        {
            "requires_human_review": True,
            "titles": {
                "faithful": faithful,
                "platform_natural": natural,
                "concise": concise,
            },
            "description": description,
            "tags": tags,
            "rights_basis": rights.basis if rights is not None else "unspecified",
            "platform_variants": {
                platform: {"title": natural, "description": description, "tags": tags}
                for platform in ("YouTube", "Bilibili", "Douyin", "Xiaohongshu")
            },
        },
    )
    return [title_path, description_path, tags_path, json_path]
