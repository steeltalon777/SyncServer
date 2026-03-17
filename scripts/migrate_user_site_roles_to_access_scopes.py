from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.core.db import SessionFactory


@dataclass
class ScopeAggregate:
    user_id: UUID
    site_id: int
    can_view: bool
    can_operate: bool
    can_manage_catalog: bool
    is_active: bool


ROLE_TO_PERMS: dict[str, tuple[bool, bool, bool]] = {
    "observer": (True, False, False),
    "storekeeper": (True, True, False),
    "chief_storekeeper": (True, True, True),
    "root": (True, True, True),
}


def load_mapping(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    mapping: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"legacy_id", "new_id"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"Mapping {path} must contain columns: legacy_id,new_id"
            )
        for row in reader:
            legacy = (row.get("legacy_id") or "").strip()
            new = (row.get("new_id") or "").strip()
            if legacy and new:
                mapping[legacy] = new
    return mapping


def parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    return None


def merge_scope(dst: ScopeAggregate, src: ScopeAggregate) -> ScopeAggregate:
    return ScopeAggregate(
        user_id=dst.user_id,
        site_id=dst.site_id,
        can_view=dst.can_view or src.can_view,
        can_operate=dst.can_operate or src.can_operate,
        can_manage_catalog=dst.can_manage_catalog or src.can_manage_catalog,
        is_active=dst.is_active or src.is_active,
    )


async def migrate(user_map_path: str | None, site_map_path: str | None) -> None:
    user_map = load_mapping(user_map_path)
    site_map = load_mapping(site_map_path)

    async with SessionFactory() as session:
        table_exists = await session.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM information_schema.tables
                  WHERE table_schema = current_schema()
                    AND table_name = 'user_site_roles'
                )
                """
            )
        )
        if not table_exists.scalar_one():
            print("user_site_roles table not found in current schema, nothing to migrate.")
            return

        columns_result = await session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'user_site_roles'
                """
            )
        )
        columns = {row[0] for row in columns_result.all()}
        role_column = "role" if "role" in columns else "role_code"
        active_expr = "is_active" if "is_active" in columns else "TRUE"

        rows = await session.execute(
            text(
                f"""
                SELECT
                    user_id::text AS legacy_user_id,
                    site_id::text AS legacy_site_id,
                    {role_column}::text AS legacy_role,
                    {active_expr}::boolean AS legacy_is_active
                FROM user_site_roles
                """
            )
        )

        scopes: dict[tuple[UUID, int], ScopeAggregate] = {}
        root_users: set[UUID] = set()
        skipped = 0

        for row in rows.mappings():
            legacy_user_id = (row["legacy_user_id"] or "").strip()
            legacy_site_id = (row["legacy_site_id"] or "").strip()
            role = (row["legacy_role"] or "").strip()
            is_active = bool(row["legacy_is_active"])

            user_candidate = user_map.get(legacy_user_id, legacy_user_id)
            site_candidate = site_map.get(legacy_site_id, legacy_site_id)

            user_uuid = parse_uuid(user_candidate)
            site_id = parse_int(site_candidate)

            if user_uuid is None or site_id is None:
                skipped += 1
                continue

            can_view, can_operate, can_manage_catalog = ROLE_TO_PERMS.get(
                role, (False, False, False)
            )

            scope = ScopeAggregate(
                user_id=user_uuid,
                site_id=site_id,
                can_view=can_view,
                can_operate=can_operate,
                can_manage_catalog=can_manage_catalog,
                is_active=is_active,
            )
            key = (user_uuid, site_id)
            scopes[key] = merge_scope(scopes[key], scope) if key in scopes else scope

            if role == "root":
                root_users.add(user_uuid)

        migrated = 0
        for scope in scopes.values():
            await session.execute(
                text(
                    """
                    INSERT INTO user_access_scopes
                    (user_id, site_id, can_view, can_operate, can_manage_catalog, is_active)
                    VALUES
                    (:user_id, :site_id, :can_view, :can_operate, :can_manage_catalog, :is_active)
                    ON CONFLICT (user_id, site_id) DO UPDATE
                    SET
                        can_view = EXCLUDED.can_view,
                        can_operate = EXCLUDED.can_operate,
                        can_manage_catalog = EXCLUDED.can_manage_catalog,
                        is_active = EXCLUDED.is_active,
                        updated_at = NOW()
                    """
                ),
                {
                    "user_id": scope.user_id,
                    "site_id": scope.site_id,
                    "can_view": scope.can_view,
                    "can_operate": scope.can_operate,
                    "can_manage_catalog": scope.can_manage_catalog,
                    "is_active": scope.is_active,
                },
            )
            migrated += 1

        for user_id in root_users:
            await session.execute(
                text(
                    """
                    UPDATE users
                    SET is_root = TRUE, role = 'root', updated_at = NOW()
                    WHERE id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

        await session.commit()

        print("Migration finished.")
        print(f"- scopes upserted: {migrated}")
        print(f"- root users promoted: {len(root_users)}")
        print(f"- skipped rows (unmapped IDs): {skipped}")
        if skipped:
            print("Provide --user-map/--site-map CSV files to migrate skipped rows.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy user_site_roles into user_access_scopes and "
            "promote legacy root users into users.is_root."
        )
    )
    parser.add_argument(
        "--user-map",
        default=None,
        help="CSV with columns legacy_id,new_id for user id mapping",
    )
    parser.add_argument(
        "--site-map",
        default=None,
        help="CSV with columns legacy_id,new_id for site id mapping",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(migrate(args.user_map, args.site_map))
