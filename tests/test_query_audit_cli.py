"""Tests for scripts/query_audit.py CLI script."""

import json
import pytest
from datetime import datetime, timezone

from scripts.query_audit import (
    format_as_markdown,
    format_as_jsonlines,
    format_as_table,
    _ts,
)


class TestTimestampFormatter:
    def test_format_iso_timestamp(self):
        result = _ts("2026-06-18T14:30:00+00:00")
        assert result == "18.06.2026 14:30"

    def test_format_invalid_timestamp(self):
        result = _ts("not-a-timestamp")
        assert result == "not-a-timestamp"

    def test_format_none_timestamp(self):
        result = _ts(None)
        assert result == ""


class TestFormatMarkdown:
    def test_empty_events(self):
        result = format_as_markdown([], "test-token", 15)
        assert "Аудит действий пользователя" in result
        assert "test-token" in result
        assert "0" in result  # 0 records

    def test_with_events(self):
        events = [
            {
                "timestamp": "2026-06-18T10:00:00+00:00",
                "event_type": "auth.login",
                "entity_type": "auth",
                "entity_id": "user-123",
                "summary": "User test: вход",
            }
        ]
        result = format_as_markdown(events, "tok-1", 15)
        assert "auth.login" in result
        assert "auth#user-123" in result
        assert "User test: вход" in result
        assert "|" in result  # table format

    def test_event_without_entity_id(self):
        events = [
            {
                "timestamp": "2026-06-18T10:00:00+00:00",
                "event_type": "auth.login",
                "entity_type": "auth",
                "entity_id": None,
                "summary": "test",
            }
        ]
        result = format_as_markdown(events, "tok-1", 15)
        assert "\u2014" in result  # em dash for missing entity


class TestFormatJsonlines:
    def test_empty_events(self):
        result = format_as_jsonlines([])
        assert result == ""

    def test_multiple_events(self):
        events = [
            {"timestamp": "2026-06-18T10:00:00+00:00", "event_type": "auth.login", "actor_username": "user1", "entity_type": "auth", "entity_id": "1", "summary": "test1", "changes": None},
            {"timestamp": "2026-06-18T11:00:00+00:00", "event_type": "auth.logout", "actor_username": "user1", "entity_type": "auth", "entity_id": "1", "summary": "test2", "changes": {}},
        ]
        result = format_as_jsonlines(events)
        lines = result.split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "event_type" in parsed
            assert "actor_username" in parsed


class TestFormatTable:
    def test_empty_events(self):
        result = format_as_table([])
        assert "Нет записей" in result

    def test_with_events(self):
        events = [
            {
                "timestamp": "2026-06-18T10:00:00+00:00",
                "event_type": "auth.login",
                "entity_type": "auth",
                "entity_id": "user-123",
                "summary": "User test: вход",
            }
        ]
        result = format_as_table(events)
        assert "auth.login" in result
        # Plain text table - no markdown pipe syntax for headers
        assert "auth#user-123" in result


class TestQueryAuditEvents:
    """Integration tests for query_audit_events with real DB."""

    @pytest.mark.asyncio
    async def test_query_nonexistent_token_raises(self):
        """Non-existent user token → ValueError."""
        from uuid import uuid4
        from scripts.query_audit import query_audit_events

        with pytest.raises(ValueError, match="User not found for token:"):
            await query_audit_events(user_token=uuid4(), limit=5)

    def test_missing_both_identifiers_raises(self):
        """Neither token nor username → ValueError."""
        from scripts.query_audit import query_audit_events
        import asyncio

        with pytest.raises(ValueError, match="Exactly one of"):
            asyncio.run(query_audit_events(limit=5))
