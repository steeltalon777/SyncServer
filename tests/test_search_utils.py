"""Unit tests for app.core.search_utils.

Tests cover: normalize_search_text, normalize_for_storage, escape_like_pattern,
build_normalized_like_term, build_raw_like_term.
"""

from __future__ import annotations

import pytest

from app.core.search_utils import (
    build_normalized_like_term,
    build_raw_like_term,
    escape_like_pattern,
    normalize_for_storage,
    normalize_search_text,
)


class TestNormalizeSearchText:
    def test_empty_string(self):
        assert normalize_search_text("") == ""

    def test_none_input(self):
        assert normalize_search_text(None) == ""  # noqa

    def test_double_spaces(self):
        assert normalize_search_text("  круг   шлифовальный  ") == "круг шлифовальный"

    def test_mixed_case(self):
        assert normalize_search_text("Круг Шлифовальный") == "круг шлифовальный"

    def test_io_to_e(self):
        assert normalize_search_text("ёлка и берёза") == "елка и береза"

    def test_punctuation(self):
        assert normalize_search_text("электр./точил, упак.") == "электр точил упак"

    def test_combined(self):
        result = normalize_search_text("  Круг шлифовальный. для электр./точил, Ёлка  ")
        assert result == "круг шлифовальный для электр точил елка"

    def test_whitespace_only(self):
        assert normalize_search_text("   ") == ""

    def test_special_chars_preserved_inside_words(self):
        # \w includes digits and underscore, so they're preserved
        result = normalize_search_text("item_123")
        assert result == "item_123"


class TestNormalizeForStorage:
    def test_none(self):
        assert normalize_for_storage(None) is None

    def test_empty_string(self):
        assert normalize_for_storage("") is None

    def test_whitespace_only(self):
        assert normalize_for_storage("   ") is None

    def test_normal_text(self):
        assert normalize_for_storage("Круг Шлифовальный") == "круг шлифовальный"

    def test_with_punctuation(self):
        assert normalize_for_storage("Электр./точил") == "электр точил"


class TestEscapeLikePattern:
    def test_percent_sign(self):
        assert escape_like_pattern("25%") == "25\\%"

    def test_underscore(self):
        assert escape_like_pattern("a_b") == "a\\_b"

    def test_backslash(self):
        assert escape_like_pattern("test\\path") == "test\\\\path"

    def test_combined(self):
        assert escape_like_pattern("100%_complete") == "100\\%\\_complete"

    def test_no_special_chars(self):
        assert escape_like_pattern("hello") == "hello"

    def test_empty_string(self):
        assert escape_like_pattern("") == ""


class TestBuildNormalizedLikeTerm:
    def test_none(self):
        assert build_normalized_like_term(None) is None

    def test_empty_string(self):
        assert build_normalized_like_term("") is None

    def test_whitespace_only(self):
        assert build_normalized_like_term("   ") is None

    def test_normal_case(self):
        term = build_normalized_like_term("Круг Шлифовальный")
        assert term == "%круг шлифовальный%"

    def test_with_punctuation(self):
        # дефисы → пробелы
        term = build_normalized_like_term("17М-03-49270-G")
        assert term == "%17м 03 49270 g%"

    def test_with_special_like_chars(self):
        # % is stripped by normalize_search_text (not a \w char),
        # so the escaped result is the same as without it
        term = build_normalized_like_term("25% скидка")
        assert term == "%25 скидка%"

    def test_with_io_replacement(self):
        term = build_normalized_like_term("Ёлка")
        assert term == "%елка%"

    def test_underscore_after_normalize(self):
        # underscore IS a \w char, so it survives normalize
        term = build_normalized_like_term("test_123")
        assert term == "%test\\_123%"


class TestBuildRawLikeTerm:
    def test_none(self):
        assert build_raw_like_term(None) is None

    def test_empty_string(self):
        assert build_raw_like_term("") is None

    def test_whitespace_only(self):
        assert build_raw_like_term("   ") is None

    def test_normal_case(self):
        term = build_raw_like_term("Круг Шлифовальный")
        assert term == "%Круг Шлифовальный%"

    def test_with_hyphens(self):
        # дефисы СОХРАНЯЮТСЯ — отличие от build_normalized_like_term
        term = build_raw_like_term("17М-03-49270-G")
        assert term == "%17М-03-49270-G%"

    def test_with_dots(self):
        term = build_raw_like_term("электр.точил")
        assert term == "%электр.точил%"

    def test_with_slashes(self):
        term = build_raw_like_term("A/B/C")
        assert term == "%A/B/C%"

    def test_with_special_like_chars(self):
        term = build_raw_like_term("test_100%")
        assert term == "%test\\_100\\%%"

    def test_mixed_case_preserved(self):
        assert build_raw_like_term("TestItem") == "%TestItem%"

    def test_double_spaces_only_in_input(self):
        term = build_raw_like_term("a  b")
        assert term == "%a  b%"  # raw сохраняет двойные пробелы


class TestNormalizedVsRawTerm:
    """Критичные тесты: normalized term != raw term для search с дефисами/точками"""

    def test_hyphen_difference(self):
        """normalized превращает дефисы в пробелы, raw сохраняет дефисы"""
        search = "17М-03-49270-G"
        normalized = build_normalized_like_term(search)
        raw = build_raw_like_term(search)
        assert normalized != raw
        assert "-" not in normalized
        assert "-" in raw

    def test_dot_difference(self):
        """normalized убирает точки, raw сохраняет точки"""
        search = "электр.точил"
        normalized = build_normalized_like_term(search)
        raw = build_raw_like_term(search)
        assert normalized != raw
        assert "." not in normalized
        assert "." in raw

    def test_slash_difference(self):
        """normalized убирает слеши, raw сохраняет слеши"""
        search = "A/B/C"
        normalized = build_normalized_like_term(search)
        raw = build_raw_like_term(search)
        assert normalized != raw
        assert "/" not in normalized
        assert "/" in raw


class TestEdgeCases:
    def test_unicode_text(self):
        assert normalize_search_text("αβγ") == "αβγ"

    def test_numbers_only(self):
        assert normalize_search_text("12345") == "12345"

    def test_mixed_unicode_and_punctuation(self):
        result = normalize_search_text("Привет, мир! test-123")
        assert result == "привет мир test 123"
