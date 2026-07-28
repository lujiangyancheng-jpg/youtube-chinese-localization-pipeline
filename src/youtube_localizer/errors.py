from __future__ import annotations


class LocalizerError(Exception):
    """Base error with a user-actionable message."""


class ConfigurationError(LocalizerError):
    pass


class InputValidationError(LocalizerError):
    pass


class ExternalToolError(LocalizerError):
    def __init__(self, message: str, *, command: list[str] | None = None) -> None:
        super().__init__(message)
        self.command = command or []


class SubtitleError(LocalizerError):
    pass


class TranslationImportError(LocalizerError):
    pass


class ProjectExistsError(LocalizerError):
    pass


class ProjectNotFoundError(LocalizerError):
    pass
