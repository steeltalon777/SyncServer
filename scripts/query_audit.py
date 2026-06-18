#!/usr/bin/env python3
"""
Audit log query tool for SyncServer.

Usage:
  python scripts/query_audit.py --username <username> [options]
  python scripts/query_audit.py --token <UUID> [options]

Examples:
  # Последние 50 записей кладовщика Иванова
  python scripts/query_audit.py --username ivanov --limit 50 --console

  # Фильтр по типу события и дате
  python scripts/query_audit.py --username ivanov --event-type operation.submit \
    --date-from 2026-06-01 --date-to 2026-06-18 --console

  # JSON для пайпа
  python scripts/query_audit.py --username ivanov --format json --console | jq .

  # Поиск по точному токену (когда username неизвестен)
  python scripts/query_audit.py --token <UUID> --console
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

# Ensure project root is on sys.path (same pattern as bootstrap_root.py)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ---------------------------------------------------------------------------
# 1. Core query function (reusable for future API endpoint)
# ---------------------------------------------------------------------------

async def query_audit_events(
    *,
    user_token: UUID | None = None,
    username: str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 15,
) -> list[dict]:
    """
    Query audit events for a user by their token UUID or username.

    Exactly one of user_token or username must be provided.

    Returns list of dicts with keys:
      timestamp, event_type, actor_username, entity_type, entity_id, summary, changes
    """
    if (user_token is None) == (username is None):
        raise ValueError("Exactly one of user_token or username is required")

    from app.core.db import SessionFactory
    from app.repos.audit_events_repo import AuditEventsRepo
    from app.repos.users_repo import UsersRepo

    async with SessionFactory() as session:
        users_repo = UsersRepo(session)
        if user_token is not None:
            user = await users_repo.get_by_user_token(user_token)
            lookup_key = f"token: {user_token}"
        else:
            user = await users_repo.get_by_username(username)
            lookup_key = f"username: {username}"
        if user is None:
            raise ValueError(f"User not found for {lookup_key}")

        audit_repo = AuditEventsRepo(session)
        events, _ = await audit_repo.list_events(
            event_type=event_type,
            actor_user_id=user.id,
            site_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=limit,
        )

        return [
            {
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "actor_username": user.username,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "summary": e.summary,
                "changes": e.changes,
            }
            for e in events
        ]


# ---------------------------------------------------------------------------
# 2. Formatters
# ---------------------------------------------------------------------------

def _ts(iso_str: str | None) -> str:
    """Format ISO timestamp to DD.MM.YYYY HH:MM."""
    if iso_str is None:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return iso_str[:19]


def format_as_markdown(events: list[dict], user_identifier: str, limit: int) -> str:
    """Format audit events as Markdown table."""
    lines = [
        f"# Аудит действий пользователя",
        f"",
        f"**Пользователь:** `{user_identifier}`",
        f"**Найдено записей:** {len(events)} (лимит: {limit})",
        f"",
        f"| Дата | Тип события | Сущность | Описание |",
        f"|------|------------|----------|----------|",
    ]
    for e in events:
        entity = f"{e['entity_type']}#{e['entity_id']}" if e['entity_id'] else "—"
        summary = (e['summary'] or "")[:120]
        lines.append(
            f"| {_ts(e['timestamp'])} | {e['event_type']} | {entity} | {summary} |"
        )
    return "\n".join(lines)


def format_as_jsonlines(events: list[dict]) -> str:
    """Format audit events as JSON lines."""
    import json
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def format_as_table(events: list[dict]) -> str:
    """Format audit events as plain-text table (no markdown)."""
    if not events:
        return "Нет записей."
    header = f"{'Дата':<19} {'Тип':<28} {'Сущность':<24} {'Описание'}"
    sep = "-" * len(header)
    rows = [header, sep]
    for e in events:
        entity = f"{e['entity_type']}#{e['entity_id']}" if e['entity_id'] else "—"
        summary = (e['summary'] or "")[:80]
        rows.append(
            f"{_ts(e['timestamp']):<19} {e['event_type']:<28} {entity:<24} {summary}"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Query SyncServer audit events for a user token.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --token a1b2c3d4-...
  %(prog)s --token a1b2c3d4-... --event-type operation.submit --limit 50 --console
  %(prog)s --token a1b2c3d4-... --format json --console | jq .
        """,
    )
    user_group = parser.add_mutually_exclusive_group(required=True)
    user_group.add_argument("--username", help="Username to query audit for")
    user_group.add_argument("--token", help="User token UUID (use when username is unknown)")
    parser.add_argument("--event-type", help="Filter by event type (e.g. auth.login, operation.submit)")
    parser.add_argument("--entity-type", help="Filter by entity type (e.g. operation, inventory_subject)")
    parser.add_argument("--entity-id", help="Filter by entity ID")
    parser.add_argument("--date-from", help="Start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--date-to", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--limit", type=int, default=15, help="Max records (default: 15)")
    parser.add_argument("--format", choices=["markdown", "json", "table"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--output", help="Write to file (default: auto-generated report file)")
    parser.add_argument("--console", action="store_true", help="Print to stdout instead of file")

    args = parser.parse_args()

    # Parse dates
    date_from = None
    date_to = None
    if args.date_from:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        date_from = datetime.now(timezone.utc) - timedelta(days=30)
    if args.date_to:
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    else:
        date_to = datetime.now(timezone.utc)

    # Parse user identifier
    user_token = None
    username = None
    if args.token:
        try:
            user_token = UUID(args.token)
        except ValueError:
            print(f"Ошибка: невалидный UUID токена: {args.token}", file=sys.stderr)
            sys.exit(1)
    else:
        username = args.username

    # Query
    try:
        events = asyncio.run(query_audit_events(
            user_token=user_token,
            username=username,
            event_type=args.event_type,
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            date_from=date_from,
            date_to=date_to,
            limit=args.limit,
        ))
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        sys.exit(1)

    # Format
    if args.format == "json":
        output = format_as_jsonlines(events)
        ext = ".jsonl"
    elif args.format == "table":
        output = format_as_table(events)
        ext = ".txt"
    else:  # markdown
        output = format_as_markdown(events, username or args.token, args.limit)
        ext = ".md"

    # Output
    if args.console:
        print(output)
    else:
        out_path = args.output or f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        Path(out_path).write_text(output, encoding="utf-8")
        print(f"Отчёт сохранён: {out_path}")
        print(f"Записей: {len(events)} (лимит: {args.limit})")


if __name__ == "__main__":
    main()
