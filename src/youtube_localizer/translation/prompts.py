from __future__ import annotations

from .base import TranslationContext


def translation_rules(source_code: str = "en", target_code: str = "zh") -> str:
    source_name = "English" if source_code == "en" else "Simplified Chinese"
    target_name = "English" if target_code == "en" else "natural Simplified Chinese"
    return f"""Translate every {source_name} subtitle cue into {target_name}.
Return every cue exactly once. Preserve each id, start, and end exactly.
Do not omit, summarize, invent, censor, or add explanatory notes.
Do not translate URLs, code, commands, paths, or variable names.
Preserve numbers and units accurately. Keep uncertain names in Latin script.
Use concise, natural spoken language suitable for subtitles and keep terminology consistent.
Output JSONL only: one JSON object per line with keys id, start, end, {source_code}, {target_code}."""


TRANSLATION_RULES = translation_rules()


def context_prompt(context: TranslationContext) -> str:
    glossary = ", ".join(f"{source} => {target}" for source, target in context.glossary.items())
    description = context.description[:1200].replace("\n", " ")
    return (
        f"Video title: {context.title}\n"
        f"Creator/channel: {context.channel}\n"
        f"Description context: {description}\n"
        f"Confirmed glossary: {glossary or '(none)'}"
    )
