"""File ingestion helpers for survey exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from charset_normalizer import from_path


@dataclass
class Question:
    """Question metadata persisted by the engine."""

    q_no: str
    q_type: str
    source_text_en: str
    order_index: int
    section: str = "official"  # "screen_out" | "official" | "background" | "platform_auto"
    meta: dict = field(default_factory=dict)


def detect_encoding(path: str) -> str:
    """Detect a text file's encoding, with common survey-export fallbacks."""

    original_error: Exception | None = None
    try:
        match = from_path(path).best()
        if match is not None and match.encoding:
            return match.encoding
        original_error = UnicodeError(f"Could not detect encoding for {path}")
    except Exception as exc:  # charset-normalizer errors become the original error.
        original_error = exc

    for encoding in ("utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                handle.read()
            return encoding
        except (UnicodeDecodeError, LookupError, OSError):
            continue

    assert original_error is not None
    raise original_error


def load_csv(path: str) -> pd.DataFrame:
    """Load a CSV without changing its columns or cell values."""

    return pd.read_csv(path, encoding=detect_encoding(path))


def load_xlsx(path: str, sheet_name=0) -> pd.DataFrame:
    """Load one worksheet from an xlsx file with openpyxl."""

    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")


def load_file(path: str) -> pd.DataFrame:
    """Dispatch supported survey files by their case-insensitive suffix."""

    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".xlsx":
        return load_xlsx(path)
    raise ValueError(f"Unsupported file format: {suffix or '<none>'}")
