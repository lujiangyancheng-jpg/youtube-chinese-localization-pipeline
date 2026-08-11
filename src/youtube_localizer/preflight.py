"""Estimate a job before it can exhaust a user's computer or storage."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig, output_directory_advice
from .hardware import (
    NvidiaGPU,
    SystemResources,
    detect_system_resources,
    query_nvidia_gpus,
    recommended_cpu_threads,
)
from .models import SourceMetadata
from .resources import find_bundled_model, package_tier

_GIB = 1024**3


@dataclass(frozen=True)
class JobPreflight:
    """The transparent plan created before source acquisition or model inference."""

    config: AppConfig
    estimated_working_bytes: int
    available_bytes: int | None
    transcription_plan: str
    encoding_plan: str
    package: str
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "package": self.package,
            "estimated_working_bytes": self.estimated_working_bytes,
            "estimated_working_gib": round(self.estimated_working_bytes / _GIB, 2),
            "available_bytes": self.available_bytes,
            "available_gib": (
                round(self.available_bytes / _GIB, 2) if self.available_bytes is not None else None
            ),
            "transcription_plan": self.transcription_plan,
            "encoding_plan": self.encoding_plan,
            "effective_config": self.config.model_dump(mode="json"),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }


def _output_free_bytes(directory: Path) -> int | None:
    candidate = directory.expanduser().resolve()
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    try:
        return shutil.disk_usage(candidate).free
    except OSError:
        return None


def _estimated_source_bytes(metadata: SourceMetadata) -> int:
    source = Path(metadata.source_input).expanduser()
    if metadata.source_type == "local" and source.is_file():
        return source.stat().st_size
    if metadata.duration <= 0:
        return 4 * _GIB
    height = metadata.height or 1080
    megabits_per_second = (
        100 if height > 2160 else 45 if height > 1440 else 24 if height > 1080 else 12 if height > 720 else 6
    )
    return int(metadata.duration * megabits_per_second * 1_000_000 / 8)


def estimate_working_bytes(metadata: SourceMetadata, config: AppConfig) -> int:
    """Return a conservative workspace estimate for a high-quality localized job."""
    source_bytes = _estimated_source_bytes(metadata)
    if config.subtitle_mode == "download_only":
        return max(4 * _GIB, int(source_bytes * 1.35) + 512 * 1024**2)
    # The project temporarily holds a source copy, extracted audio, subtitles, and a final
    # re-encode. The multiplier intentionally reserves room for high-bitrate 4K sources.
    return max(8 * _GIB, int(source_bytes * 2.5) + _GIB)


def _with_safe_bundled_models(config: AppConfig, warnings: list[str]) -> AppConfig:
    if config.subtitle_mode == "download_only":
        return config
    result = config
    is_standard_package = package_tier() == "standard"
    has_medium = find_bundled_model("faster-whisper-medium") is not None
    has_small = find_bundled_model("faster-whisper-small") is not None
    if (
        is_standard_package
        and result.transcription.model == "medium"
        and not has_medium
        and has_small
    ):
        transcription = result.transcription.model_copy(
            update={"model": "small", "beam_size": min(result.transcription.beam_size, 3)}
        )
        result = result.model_copy(update={"transcription": transcription})
        warnings.append(
            "Whisper Medium is not included in this installation; using bundled Whisper Small "
            "so this job stays fully offline."
        )
    if (
        is_standard_package
        and result.translation.provider == "ollama"
        and find_bundled_model("ollama") is None
    ):
        source_code = "zh" if result.translation.direction == "zh-to-en" else "en"
        target_code = "en" if source_code == "zh" else "zh"
        model_name = f"translate-{source_code}_{target_code}-1_9"
        if find_bundled_model(model_name) is not None:
            translation = result.translation.model_copy(update={"provider": "offline"})
            result = result.model_copy(update={"translation": translation})
            warnings.append(
                "Local AI paragraph translation is not included in this installation; using the "
                "bundled fast offline translator instead."
            )
    return result


def _with_resource_safe_fallback(
    config: AppConfig,
    resources: SystemResources,
    gpus: list[NvidiaGPU],
    warnings: list[str],
) -> AppConfig:
    if config.subtitle_mode == "download_only":
        return config
    result = config
    available_vram = [
        gpu.total_memory_mib - gpu.used_memory_mib
        for gpu in gpus
        if gpu.total_memory_mib is not None and gpu.used_memory_mib is not None
    ]
    low_vram = bool(available_vram and max(available_vram) < 6 * 1024)
    low_memory_cpu = (
        not gpus
        and resources.memory_mib is not None
        and resources.memory_mib < 12 * 1024
    )
    if (
        result.transcription.model == "medium"
        and result.transcription.device == "auto"
        and (low_vram or low_memory_cpu)
        and find_bundled_model("faster-whisper-small") is not None
    ):
        transcription = result.transcription.model_copy(
            update={"model": "small", "compute_type": "int8", "beam_size": 3}
        )
        result = result.model_copy(update={"transcription": transcription})
        reason = (
            "available NVIDIA VRAM is below 6 GiB"
            if low_vram
            else "system memory is below 12 GiB"
        )
        warnings.append(
            f"{reason}; auto mode switched to Whisper Small to keep Windows responsive."
        )
    return result


def build_job_preflight(metadata: SourceMetadata, config: AppConfig) -> JobPreflight:
    """Build a hardware-aware, offline-safe processing plan without changing source files."""
    warnings: list[str] = []
    resources = detect_system_resources()
    gpus = [] if config.subtitle_mode == "download_only" else query_nvidia_gpus()
    effective_config = _with_safe_bundled_models(config, warnings)
    effective_config = _with_resource_safe_fallback(effective_config, resources, gpus, warnings)
    estimated = estimate_working_bytes(metadata, effective_config)
    available = _output_free_bytes(effective_config.output_directory)
    blockers: list[str] = []
    if available is not None and available < estimated:
        blockers.append(
            "Insufficient free space for this high-quality job: "
            f"need about {estimated / _GIB:.1f} GiB, but only {available / _GIB:.1f} GiB is available."
        )
    advice = output_directory_advice(effective_config.output_directory)
    if "OneDrive" in advice or "20 GiB" in advice:
        warnings.append(advice)

    if effective_config.subtitle_mode == "download_only":
        transcription_plan = "Not needed for direct download."
        encoding_plan = "Not needed; original streams remain un-reencoded."
    else:
        gpu_detail = "NVIDIA CUDA when the bundled runtime passes its safety check"
        if not gpus:
            gpu_detail = f"CPU int8 using up to {recommended_cpu_threads(resources)} thread(s)"
        transcription_plan = (
            f"Whisper {effective_config.transcription.model} on {gpu_detail}; CPU fallback is automatic."
        )
        encoding_plan = (
            f"{effective_config.render.codec} output; automatic mode verifies NVIDIA, Intel, and AMD "
            "hardware encoding before using fast CPU H.264 fallback."
        )
    tier = package_tier() or "source checkout"
    return JobPreflight(
        config=effective_config,
        estimated_working_bytes=estimated,
        available_bytes=available,
        transcription_plan=transcription_plan,
        encoding_plan=encoding_plan,
        package=tier,
        warnings=tuple(dict.fromkeys(warnings)),
        blockers=tuple(blockers),
    )
