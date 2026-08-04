from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from youtube_localizer.config import TranscriptionConfig
from youtube_localizer.transcription.whisper_engine import (
    _is_cuda_runtime_failure,
    transcribe_audio,
)


def test_cuda_runtime_errors_include_missing_cublas() -> None:
    assert _is_cuda_runtime_failure(
        RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
    )
    assert not _is_cuda_runtime_failure(RuntimeError("unsupported audio format"))


def test_transcription_retries_on_cpu_after_lazy_cuda_failure(tmp_path, caplog) -> None:
    calls: list[tuple[str, str]] = []

    class FakeWhisperModel:
        def __init__(
            self,
            _model_reference,
            *,
            device: str,
            compute_type: str,
            local_files_only: bool,
        ) -> None:
            calls.append((device, compute_type))
            self.device = device
            assert local_files_only

        def transcribe(self, _audio_path: str, **_kwargs):
            info = SimpleNamespace(language="en", language_probability=0.99, duration=2.0)
            if self.device == "cuda":

                def fail_during_iteration():
                    yield SimpleNamespace(
                        text="Partial GPU result",
                        avg_logprob=-0.1,
                        no_speech_prob=0.0,
                        words=[],
                        start=0.0,
                        end=1.0,
                    )
                    raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

                return fail_during_iteration(), info
            segment = SimpleNamespace(
                text="Hello world.",
                avg_logprob=-0.1,
                no_speech_prob=0.0,
                words=[],
                start=0.0,
                end=2.0,
            )
            return iter([segment]), info

    output_json = tmp_path / "transcription.json"
    output_srt = tmp_path / "transcription.srt"
    config = TranscriptionConfig(device="auto", compute_type="auto")
    with (
        patch("faster_whisper.WhisperModel", FakeWhisperModel),
        patch(
            "youtube_localizer.transcription.whisper_engine.resolve_whisper_model",
            return_value=(tmp_path / "model", True),
        ),
        patch(
            "youtube_localizer.transcription.whisper_engine.cuda_available",
            return_value=True,
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = transcribe_audio(
            tmp_path / "audio.wav",
            output_json,
            output_srt,
            config,
        )

    assert calls == [("cuda", "float16"), ("cpu", "int8")]
    assert [cue.text for cue in result.cues] == ["Hello world."]
    metadata = json.loads(output_json.read_text(encoding="utf-8"))
    assert metadata["device"] == "cpu"
    assert metadata["compute_type"] == "int8"
    assert metadata["cuda_fallback"] is True
    assert "automatically retrying on CPU" in caplog.text
    assert output_srt.exists()
