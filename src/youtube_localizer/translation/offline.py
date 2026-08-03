from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx

from ..errors import LocalizerError
from ..models import SubtitleCue
from .base import TranslationContext, TranslationProvider
from .cache import TranslationCache

LOGGER = logging.getLogger(__name__)
MAX_MODEL_DOWNLOAD_BYTES = 1_000_000_000
MODEL_REQUIRED_PATHS = (
    "metadata.json",
    "sentencepiece.model",
    "model/config.json",
    "model/model.bin",
)


def validate_offline_model(
    model_directory: Path,
    *,
    source_code: str = "en",
    target_code: str = "zh",
) -> dict[str, Any] | None:
    """Return validated model metadata, or None when the directory is incomplete."""
    if not model_directory.is_dir():
        return None
    if any(not (model_directory / relative).is_file() for relative in MODEL_REQUIRED_PATHS):
        return None
    try:
        metadata = json.loads((model_directory / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if metadata.get("from_code") != source_code or metadata.get("to_code") != target_code:
        return None
    return metadata


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    total_size = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise LocalizerError("The offline translation model archive contains an unsafe path.")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise LocalizerError("The offline translation model archive contains a symlink.")
        total_size += member.file_size
        if total_size > MAX_MODEL_DOWNLOAD_BYTES:
            raise LocalizerError("The offline translation model archive is unexpectedly large.")


def install_offline_model_archive(
    archive_path: Path,
    destination: Path,
    *,
    source_code: str = "en",
    target_code: str = "zh",
) -> Path:
    """Validate and atomically install an Argos-compatible translation model archive."""
    existing = validate_offline_model(
        destination, source_code=source_code, target_code=target_code
    )
    if existing is not None:
        return destination
    if destination.exists():
        raise LocalizerError(
            f"Offline model directory exists but is incomplete: {destination}. "
            "Rename or remove only that directory, then retry."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.install-", dir=destination.parent)
    )
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                _validate_archive_members(archive)
                archive.extractall(temporary_root)
        except (OSError, zipfile.BadZipFile) as exc:
            raise LocalizerError(f"The offline translation model archive is invalid: {exc}") from exc
        candidates = [
            path
            for path in temporary_root.rglob("metadata.json")
            if validate_offline_model(
                path.parent, source_code=source_code, target_code=target_code
            )
            is not None
        ]
        if len(candidates) != 1:
            raise LocalizerError(
                "The offline translation archive does not contain exactly one valid "
                f"{source_code}-to-{target_code} model."
            )
        candidates[0].parent.replace(destination)
        return destination
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def _download_model_archive(
    url: str,
    destination_parent: Path,
    *,
    source_code: str,
    target_code: str,
) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LocalizerError("Offline model downloads require a valid HTTPS URL.")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".offline-model-", suffix=".argosmodel", dir=destination_parent
    )
    temporary_path = Path(temporary_name)
    downloaded = 0
    try:
        LOGGER.info(
            "Downloading the offline %s-to-%s model for first-time use…",
            source_code,
            target_code,
        )
        timeout = httpx.Timeout(connect=30, read=600, write=30, pool=30)
        with (
            os.fdopen(descriptor, "wb") as output,
            httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response,
        ):
            response.raise_for_status()
            length = int(response.headers.get("content-length") or 0)
            if length > MAX_MODEL_DOWNLOAD_BYTES:
                raise LocalizerError("The offline translation model download is too large.")
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                downloaded += len(chunk)
                if downloaded > MAX_MODEL_DOWNLOAD_BYTES:
                    raise LocalizerError("The offline translation model download is too large.")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if downloaded == 0:
            raise LocalizerError("The offline translation model download was empty.")
        LOGGER.info("Offline translation model downloaded (%.1f MB).", downloaded / 1_048_576)
        return temporary_path
    except httpx.HTTPError as exc:
        temporary_path.unlink(missing_ok=True)
        raise LocalizerError(
            "Could not download the offline translation model. Check the internet connection "
            f"and retry. Details: {exc}"
        ) from exc
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def ensure_offline_model(
    model_directory: Path,
    *,
    model_url: str,
    auto_download: bool,
    source_code: str = "en",
    target_code: str = "zh",
) -> Path:
    if validate_offline_model(
        model_directory, source_code=source_code, target_code=target_code
    ) is not None:
        return model_directory
    if model_directory.exists():
        raise LocalizerError(
            f"Offline model directory exists but is incomplete: {model_directory}."
        )
    if not auto_download:
        raise LocalizerError(
            f"Offline {source_code}-to-{target_code} model is not installed at "
            f"{model_directory}. "
            "Enable translation.offline_auto_download or install the model there."
        )
    model_directory.parent.mkdir(parents=True, exist_ok=True)
    archive = _download_model_archive(
        model_url,
        model_directory.parent,
        source_code=source_code,
        target_code=target_code,
    )
    try:
        installed = install_offline_model_archive(
            archive,
            model_directory,
            source_code=source_code,
            target_code=target_code,
        )
    finally:
        archive.unlink(missing_ok=True)
    LOGGER.info("Offline translation model installed at %s", installed)
    return installed


class LocalOfflineProvider(TranslationProvider):
    """Translate subtitle cues locally with CTranslate2 and SentencePiece."""

    def __init__(
        self,
        *,
        model_directory: Path,
        model_url: str,
        auto_download: bool,
        device: str,
        compute_type: str,
        cache: TranslationCache,
        source_code: str = "en",
        target_code: str = "zh",
    ) -> None:
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise LocalizerError(
                'Offline translation dependencies are missing. Run: python -m pip install -e '
                '".[offline-translation]"'
            ) from exc

        self.model_directory = ensure_offline_model(
            model_directory,
            model_url=model_url,
            auto_download=auto_download,
            source_code=source_code,
            target_code=target_code,
        )
        self.metadata = (
            validate_offline_model(
                self.model_directory,
                source_code=source_code,
                target_code=target_code,
            )
            or {}
        )
        self.source_code = source_code
        self.target_code = target_code
        self.cache = cache
        self._ctranslate2 = ctranslate2
        self._requested_device = device
        self._requested_compute_type = compute_type
        self.processor = spm.SentencePieceProcessor(
            model_proto=(self.model_directory / "sentencepiece.model").read_bytes()
        )

        requested_device = device
        selected_device = device
        if device == "auto":
            selected_device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        selected_compute_type = compute_type
        if compute_type == "auto" and selected_device == "cpu":
            selected_compute_type = "int8"
        try:
            self.translator = ctranslate2.Translator(
                str(self.model_directory / "model"),
                device=selected_device,
                compute_type=selected_compute_type,
            )
        except Exception as exc:
            if requested_device != "auto" or selected_device == "cpu":
                raise LocalizerError(
                    f"Could not load the offline translation model on {selected_device}: {exc}"
                ) from exc
            LOGGER.warning("CUDA translation model load failed; falling back to CPU: %s", exc)
            selected_device = "cpu"
            selected_compute_type = "int8" if compute_type == "auto" else compute_type
            try:
                self.translator = ctranslate2.Translator(
                    str(self.model_directory / "model"),
                    device="cpu",
                    compute_type=selected_compute_type,
                )
            except Exception as fallback_exc:
                raise LocalizerError(
                    f"Could not load the offline translation model on CPU: {fallback_exc}"
                ) from fallback_exc
        self.device = selected_device
        self.compute_type = selected_compute_type
        LOGGER.info(
            "Offline translation ready on %s (%s).",
            self.device,
            self.compute_type,
        )

    def _translate_tokens(self, tokenized: list[list[str]]):
        arguments = {
            "replace_unknowns": True,
            "max_batch_size": 2048,
            "batch_type": "tokens",
            "beam_size": 4,
            "num_hypotheses": 1,
            "length_penalty": 0.2,
        }
        try:
            return self.translator.translate_batch(tokenized, **arguments)
        except Exception:
            if self._requested_device != "auto" or self.device != "cuda":
                raise
            LOGGER.warning(
                "CUDA translation execution failed; reloading the offline model on CPU."
            )
            self.device = "cpu"
            self.compute_type = (
                "int8"
                if self._requested_compute_type == "auto"
                else self._requested_compute_type
            )
            self.translator = self._ctranslate2.Translator(
                str(self.model_directory / "model"),
                device="cpu",
                compute_type=self.compute_type,
            )
            LOGGER.info("Offline translation ready on CPU (%s).", self.compute_type)
            return self.translator.translate_batch(tokenized, **arguments)

    def translate_batch(
        self,
        cues: list[SubtitleCue],
        context: TranslationContext,
    ) -> list[SubtitleCue]:
        payload = {
            "provider": "offline-argos-opus",
            "source_code": self.source_code,
            "target_code": self.target_code,
            "model_version": self.metadata.get("package_version", "unknown"),
            "texts": [cue.text for cue in cues],
            "glossary": context.glossary,
        }
        key = self.cache.key(payload)
        cached = self.cache.get(key)
        translations: list[str]
        if isinstance(cached, dict) and isinstance(cached.get("translations"), list):
            translations = [str(value) for value in cached["translations"]]
            if len(translations) != len(cues) or any(not value.strip() for value in translations):
                translations = []
        else:
            translations = []

        if not translations:
            tokenized = [
                self.processor.encode(cue.text.replace("\n", " "), out_type=str) for cue in cues
            ]
            try:
                results = self._translate_tokens(tokenized)
            except Exception as exc:
                raise LocalizerError(f"Local offline translation failed: {exc}") from exc
            translations = [
                self.processor.decode_pieces(result.hypotheses[0])
                .replace(chr(0x2581), " ")
                .strip()
                for result in results
            ]
            if len(translations) != len(cues) or any(not value for value in translations):
                raise LocalizerError("Local offline translation returned missing subtitle text.")
            self.cache.put(key, {"translations": translations})

        return [
            SubtitleCue(
                id=cue.id,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=translation,
                confidence=cue.confidence,
            )
            for cue, translation in zip(cues, translations, strict=True)
        ]
