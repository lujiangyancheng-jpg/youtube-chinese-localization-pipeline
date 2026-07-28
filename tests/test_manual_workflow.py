from __future__ import annotations

import json

from youtube_localizer.config import AppConfig
from youtube_localizer.models import ProjectPaths, SourceMetadata, SubtitleCue
from youtube_localizer.pipeline import export_manual_translation, save_project_config
from youtube_localizer.state import PipelineState
from youtube_localizer.subtitles.parser import parse_subtitle, write_srt
from youtube_localizer.translation.manual import import_translation_file
from youtube_localizer.utils.files import atomic_write_json, atomic_write_text
from youtube_localizer.utils.text import ms_to_srt


def _translation_response(cue: SubtitleCue, translated: str) -> str:
    return json.dumps(
        {
            "id": cue.id,
            "start": ms_to_srt(cue.start_ms),
            "end": ms_to_srt(cue.end_ms),
            "en": cue.text,
            "zh": translated,
        },
        ensure_ascii=False,
    )


def test_offline_manual_export_import_workflow(tmp_path) -> None:
    project = ProjectPaths(tmp_path / "demo_project")
    project.create()
    metadata = SourceMetadata(
        source_type="local",
        source_input=str(tmp_path / "owned.mp4"),
        video_id="demo123",
        title="Owned demo",
        duration=3,
    )
    atomic_write_json(project.metadata, metadata.model_dump(mode="json"))
    PipelineState(project.state_file, source_input=metadata.source_input)
    config = AppConfig(
        translation={"provider": "manual", "batch_size": 1},
        subtitles={"font": "Arial"},
    )
    save_project_config(project, config)
    english = [
        SubtitleCue(id=1, start_ms=0, end_ms=1200, text="Hello"),
        SubtitleCue(id=2, start_ms=1300, end_ms=2600, text="Goodbye"),
    ]
    write_srt(project.english_srt, english)

    chunks = export_manual_translation(project, config, metadata)
    assert len(chunks) == 2
    assert (project.translation_chunks / "manifest.json").is_file()

    response_one = tmp_path / "translated_001.txt"
    atomic_write_text(response_one, _translation_response(english[0], "你好"))
    imported, total, _ = import_translation_file(
        project,
        response_one,
        subtitle_mode="chinese",
        subtitle_config=config.subtitles,
    )
    assert (imported, total) == (1, 2)
    assert not project.chinese_srt.exists()

    response_two = tmp_path / "translated_002.txt"
    atomic_write_text(response_two, _translation_response(english[1], "再见"))
    imported, total, _ = import_translation_file(
        project,
        response_two,
        subtitle_mode="chinese",
        subtitle_config=config.subtitles,
    )
    assert (imported, total) == (2, 2)
    chinese = parse_subtitle(project.chinese_srt)
    assert [cue.text for cue in chinese] == ["你好", "再见"]
    assert [(cue.start_ms, cue.end_ms) for cue in chinese] == [
        (cue.start_ms, cue.end_ms) for cue in english
    ]
