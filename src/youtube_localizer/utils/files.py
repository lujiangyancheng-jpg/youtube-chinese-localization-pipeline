from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(value: str, *, max_length: int = 100) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = re.sub(r"_+", "_", value)
    if not value:
        value = "untitled"
    if value.upper() in WINDOWS_RESERVED:
        value = f"_{value}"
    value = value[:max_length].rstrip(" .")
    return value or "untitled"


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_within(child: Path, parent: Path) -> Path:
    resolved_child = child.resolve()
    resolved_parent = parent.resolve()
    if resolved_child != resolved_parent and resolved_parent not in resolved_child.parents:
        raise ValueError(f"Refusing operation outside {resolved_parent}: {resolved_child}")
    return resolved_child


def remove_project(project: Path, output_root: Path) -> None:
    target = ensure_within(project, output_root)
    if target == output_root.resolve():
        raise ValueError("Refusing to remove the output root itself.")
    if target.exists():
        shutil.rmtree(target)


def available_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free
