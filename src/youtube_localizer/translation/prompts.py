from __future__ import annotations

from .base import TranslationContext

TRANSLATION_RULES = """Translate every English subtitle cue into natural Simplified Chinese.
Return every cue exactly once. Preserve each id, start, and end exactly.
Do not omit, summarize, invent, censor, or add explanatory notes.
Do not translate URLs, code, commands, paths, or variable names.
Preserve numbers and units accurately. Keep uncertain names in Latin script.
Use concise, spoken Chinese suitable for subtitles and keep terminology consistent.
Output JSONL only: one JSON object per line with keys id, start, end, en, zh."""


def context_prompt(context: TranslationContext) -> str:
    glossary = ", ".join(f"{source} => {target}" for source, target in context.glossary.items())
    description = context.description[:1200].replace("\n", " ")
    return (
        f"Video title: {context.title}\n"
        f"Creator/channel: {context.channel}\n"
        f"Description context: {description}\n"
        f"Confirmed glossary: {glossary or '(none)'}"
    )
