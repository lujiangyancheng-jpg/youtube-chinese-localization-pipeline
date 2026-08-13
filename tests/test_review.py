from __future__ import annotations

from youtube_localizer.config import AppConfig
from youtube_localizer.models import ProjectPaths, SourceMetadata, SubtitleCue
from youtube_localizer.pipeline import save_project_config
from youtube_localizer.review import load_subtitle_review_session, save_reviewed_subtitles
from youtube_localizer.subtitles.parser import parse_subtitle, write_srt
from youtube_localizer.utils.files import atomic_write_json


def _project_with_target(tmp_path, *, direction: str = "en-to-zh", mode: str = "chinese"):
    project = ProjectPaths(tmp_path / "review-project")
    project.create()
    atomic_write_json(
        project.metadata,
        SourceMetadata(
            source_type="local", source_input="owned.mp4", video_id="review", title="Review"
        ).model_dump(mode="json"),
    )
    config = AppConfig(
        subtitle_mode=mode,
        translation={"direction": direction},
        subtitles={"font": "Arial"},
    )
    save_project_config(project, config)
    source_code, target_code = direction.split("-to-")
    source = [SubtitleCue(id=1, start_ms=0, end_ms=1000, text="Hello")]
    target = [SubtitleCue(id=1, start_ms=0, end_ms=1000, text="你好")]
    write_srt(project.subtitle_srt(source_code), source)
    write_srt(project.subtitle_srt(target_code), target)
    return project, config


def test_review_save_rebuilds_target_ass(tmp_path) -> None:
    project, config = _project_with_target(tmp_path)
    session = load_subtitle_review_session(project, config)
    edited = [session.cues[0].model_copy(update={"text": "您好，世界。"})]

    outputs = save_reviewed_subtitles(session, config, edited)

    assert parse_subtitle(project.chinese_srt)[0].text == "您好，世界。"
    assert project.chinese_ass in outputs
    assert "您好，世界。" in project.chinese_ass.read_text(encoding="utf-8")


def test_review_save_rebuilds_bilingual_tracks(tmp_path) -> None:
    project, config = _project_with_target(tmp_path, mode="bilingual_en_zh")
    session = load_subtitle_review_session(project, config)
    edited = [session.cues[0].model_copy(update={"text": "你好，朋友。"})]

    outputs = save_reviewed_subtitles(session, config, edited)

    assert project.bilingual_srt in outputs
    assert project.bilingual_ass in outputs
    assert "你好，朋友。" in project.bilingual_ass.read_text(encoding="utf-8")
