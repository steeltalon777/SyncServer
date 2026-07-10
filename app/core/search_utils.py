from __future__ import annotations

import re

_NON_WORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SPACES_RE = re.compile(r"\s+", flags=re.UNICODE)

__all__ = [
    "normalize_search_text",
    "normalize_for_storage",
    "escape_like_pattern",
    "build_normalized_like_term",
    "build_raw_like_term",
]


def normalize_search_text(value: str) -> str:
    """Нормализация текста для поиска:
    strip → lower → ё→е → удаление пунктуации → сворачивание пробелов.
    Возвращает пустую строку для falsy-ввода.
    """
    text = (value or "").strip().lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


def normalize_for_storage(value: str | None) -> str | None:
    """Нормализация для хранения в normalized_name колонке.
    Возвращает None для None, пустую строку не возвращает (→ None).
    """
    if value is None:
        return None
    result = normalize_search_text(value)
    return result or None


def escape_like_pattern(text: str) -> str:
    """Экранирование LIKE/ILIKE спецсимволов: % и _."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_normalized_like_term(search: str | None) -> str | None:
    """Term для поиска по normalized_name / normalized_key колонкам.
    Pipeline: normalize_search_text → escape → wrap в %...%.
    Возвращает None если ввод пустой после нормализации.
    """
    if not search:
        return None
    normalized = normalize_search_text(search)
    if not normalized:
        return None
    escaped = escape_like_pattern(normalized)
    return f"%{escaped}%"


def build_raw_like_term(search: str | None) -> str | None:
    """Term для поиска по сырым техническим колонкам (sku, code, device_code, description, notes, snapshots).
    Pipeline: strip → escape → wrap в %...%.
    НЕ удаляет пунктуацию, НЕ меняет регистр, НЕ сворачивает пробелы —
    только strip и экранирование LIKE-спецсимволов.
    Возвращает None если ввод пустой после strip.
    """
    if not search:
        return None
    stripped = search.strip()
    if not stripped:
        return None
    escaped = escape_like_pattern(stripped)
    return f"%{escaped}%"
