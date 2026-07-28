from __future__ import annotations

from pathlib import Path

import yaml

from ..errors import ConfigurationError


def load_glossary(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot read glossary {path}: {exc}") from exc
    terms = data.get("terms", data) if isinstance(data, dict) else {}
    if not isinstance(terms, dict):
        raise ConfigurationError("Glossary must be a YAML mapping or contain a 'terms' mapping.")
    result: dict[str, str] = {}
    for source, target in terms.items():
        if not isinstance(source, str) or not isinstance(target, str) or not source.strip():
            raise ConfigurationError(
                "Every glossary entry must map a non-empty string to a string."
            )
        result[source.strip()] = target.strip()
    return result


def glossary_consistency_issues(
    english: list[str],
    chinese: list[str],
    glossary: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    for cue_id, (source_text, target_text) in enumerate(
        zip(english, chinese, strict=True), start=1
    ):
        for source, target in glossary.items():
            if source.casefold() in source_text.casefold() and target not in target_text:
                issues.append(
                    f"Cue {cue_id} contains glossary source {source!r} but not target {target!r}."
                )
    return issues
