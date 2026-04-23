import json
import os
import asyncio
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


BASE = os.getenv("SYNC_SERVER_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
ROOT_TOKEN = os.getenv("SYNC_ROOT_USER_TOKEN", "9d5c0496-a32b-4d55-be0d-1fcfede4fd5a")
DEVICE_TOKEN = os.getenv("SYNC_DEVICE_TOKEN", "9eed7417-a854-4d9a-90ed-3d3c98714e07")
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    try:
        from app.core.config import get_settings

        DATABASE_URL = get_settings().DATABASE_URL
    except Exception:
        DATABASE_URL = ""

if not DATABASE_URL:
    env_path = Path(".env")
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DATABASE_URL":
                DATABASE_URL = value.strip().strip('"').strip("'")
                break
HEADERS_ROOT = {"X-User-Token": ROOT_TOKEN, "Content-Type": "application/json"}


def add_step(result: dict, name: str, ok: bool, **data) -> None:
    row = {"name": name, "ok": bool(ok)}
    row.update(data)
    result["steps"].append(row)
    if not ok:
        raise AssertionError(f"step failed: {name}: {data}")


def req(method: str, path: str, *, headers=None, json_body=None, params=None, expected=None):
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        resp = client.request(method, path, headers=headers, json=json_body, params=params)
    body_text = resp.text
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if expected is not None and resp.status_code != expected:
        raise AssertionError(
            f"{method} {path} -> {resp.status_code}, expected {expected}, body={body_text[:1000]}"
        )
    return resp.status_code, payload, body_text


def req_absolute(method: str, url: str, *, headers=None, json_body=None, params=None, expected=None):
    with httpx.Client(timeout=30.0) as client:
        resp = client.request(method, url, headers=headers, json=json_body, params=params)
    body_text = resp.text
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if expected is not None and resp.status_code != expected:
        raise AssertionError(f"{method} {url} -> {resp.status_code}, expected {expected}, body={body_text[:1000]}")
    return resp.status_code, payload, body_text


async def db_fetch_one(sql: str, params: dict | None = None) -> dict | None:
    if not DATABASE_URL:
        raise AssertionError("DATABASE_URL is required for stand DB verification")
    engine = create_async_engine(DATABASE_URL, future=True)
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text(sql), params or {})).mappings().first()
            return dict(row) if row else None
    finally:
        await engine.dispose()


def db_fetch_one_sync(sql: str, params: dict | None = None) -> dict | None:
    return asyncio.run(db_fetch_one(sql, params))


def main() -> None:
    run = f"phase1_{int(time.time())}"
    result = {"run": run, "steps": []}

    site_code = f"ST-{run}"
    unit_name = f"Unit {run}"
    category_name = f"Category {run}"
    catalog_item_name = f"Catalog Item {run}"
    chief_username = f"chief_{run}"
    storekeeper_username = f"storekeeper_{run}"
    observer_username = f"observer_{run}"

    status, payload, _ = req("GET", "/health", expected=200)
    add_step(result, "health", payload == {"status": "ok"}, status_code=status, payload=payload)

    status, payload, _ = req("GET", "/ready", expected=200)
    add_step(result, "ready", payload is not None and payload.get("status") == "ready", status_code=status, payload=payload)

    status, payload, _ = req("GET", "/auth/me", headers={"X-User-Token": ROOT_TOKEN}, expected=200)
    add_step(
        result,
        "root_auth",
        payload is not None and payload.get("user", {}).get("is_root") is True,
        status_code=status,
        payload=payload,
    )

    status, payload, _ = req(
        "GET",
        "/auth/me",
        headers={"X-User-Token": ROOT_TOKEN, "X-Device-Token": DEVICE_TOKEN},
        expected=200,
    )
    add_step(
        result,
        "root_auth_with_device",
        payload is not None and payload.get("device") is not None,
        status_code=status,
        payload=payload,
    )

    base_parts = urlsplit(BASE)
    origin = f"{base_parts.scheme}://{base_parts.netloc}"
    status, payload, _ = req_absolute("GET", f"{origin}/api/openapi.json", expected=200)
    paths = set((payload or {}).get("paths", {}).keys())
    add_step(
        result,
        "openapi_temporary_item_routes",
        "/api/v1/temporary-items" in paths
        and "/api/v1/temporary-items/{temporary_item_id}" in paths
        and "/api/v1/temporary-items/{temporary_item_id}/approve-as-item" in paths
        and "/api/v1/temporary-items/{temporary_item_id}/merge" in paths,
        status_code=status,
        checked_paths=sorted([p for p in paths if p.startswith("/api/v1/temporary-items")]),
    )

    status, payload, _ = req(
        "POST",
        "/admin/sites",
        headers=HEADERS_ROOT,
        json_body={
            "code": site_code,
            "name": f"Test Site {run}",
            "description": "Phase1 stand check",
            "is_active": True,
        },
        expected=200,
    )
    site_id = payload["site_id"]
    add_step(result, "create_site", True, status_code=status, site_id=site_id)

    users = {}
    for username, role in [
        (chief_username, "chief_storekeeper"),
        (storekeeper_username, "storekeeper"),
        (observer_username, "observer"),
    ]:
        status, payload, _ = req(
            "POST",
            "/admin/users",
            headers=HEADERS_ROOT,
            json_body={
                "username": username,
                "email": f"{username}@example.com",
                "full_name": username,
                "is_active": True,
                "is_root": False,
                "role": role,
                "default_site_id": site_id,
            },
            expected=200,
        )
        user_id = payload["id"]
        _, payload2, _ = req(
            "POST",
            f"/admin/users/{user_id}/rotate-token",
            headers=HEADERS_ROOT,
            expected=200,
        )
        users[role] = {"id": user_id, "token": payload2["user_token"], "username": username}
        add_step(result, f"create_user_{role}", True, user_id=user_id)

    for role, can_operate, can_manage_catalog in [
        ("chief_storekeeper", True, True),
        ("storekeeper", True, False),
        ("observer", False, False),
    ]:
        status, payload, _ = req(
            "PUT",
            f"/admin/users/{users[role]['id']}/scopes",
            headers=HEADERS_ROOT,
            json_body={
                "scopes": [
                    {
                        "site_id": site_id,
                        "can_view": True,
                        "can_operate": can_operate,
                        "can_manage_catalog": can_manage_catalog,
                    }
                ]
            },
            expected=200,
        )
        add_step(result, f"set_scope_{role}", isinstance(payload, list) and len(payload) == 1, payload=payload)

    status, payload, _ = req(
        "POST",
        "/catalog/admin/units",
        headers=HEADERS_ROOT,
        json_body={"name": unit_name, "symbol": f"u{run[-4:]}", "is_active": True},
        expected=200,
    )
    unit_id = payload["id"]
    add_step(result, "create_unit", True, unit_id=unit_id)

    status, payload, _ = req(
        "POST",
        "/catalog/admin/categories",
        headers=HEADERS_ROOT,
        json_body={"name": category_name, "code": f"C-{run}", "is_active": True},
        expected=200,
    )
    category_id = payload["id"]
    add_step(result, "create_category", True, category_id=category_id)

    status, payload, _ = req(
        "POST",
        "/catalog/admin/items",
        headers=HEADERS_ROOT,
        json_body={
            "sku": f"SKU-{run}",
            "name": catalog_item_name,
            "category_id": category_id,
            "unit_id": unit_id,
            "description": "catalog item for mixed lines",
            "hashtags": ["phase1", run],
            "is_active": True,
        },
        expected=200,
    )
    catalog_item_id = payload["id"]
    add_step(result, "create_catalog_item", True, item_id=catalog_item_id)

    store_headers = {"X-User-Token": users["storekeeper"]["token"], "Content-Type": "application/json"}
    chief_headers = {"X-User-Token": users["chief_storekeeper"]["token"], "Content-Type": "application/json"}
    observer_headers = {"X-User-Token": users["observer"]["token"], "Content-Type": "application/json"}

    operation_payload = {
        "operation_type": "RECEIVE",
        "site_id": site_id,
        "client_request_id": f"op-{run}",
        "notes": "phase1 stand check",
        "lines": [
            {
                "line_number": 1,
                "qty": 2,
                "temporary_item": {
                    "client_key": "tmp-1",
                    "name": f"Temporary Cable {run}",
                    "sku": None,
                    "unit_id": unit_id,
                    "category_id": category_id,
                    "description": "inline temporary item",
                    "hashtags": ["temporary", run],
                },
            },
            {"line_number": 2, "qty": 1, "item_id": catalog_item_id},
        ],
    }
    _, payload, _ = req("POST", "/operations", headers=store_headers, json_body=operation_payload, expected=200)
    operation_id = payload["id"]
    temporary_item_id = payload["lines"][0]["temporary_item_id"]
    temporary_line_id = payload["lines"][0]["id"]
    catalog_line_id = payload["lines"][1]["id"]
    add_step(
        result,
        "create_receive_with_mixed_lines",
        payload["lines"][0]["temporary_item_status"] == "active" and payload["lines"][1]["temporary_item_id"] is None,
        operation_id=operation_id,
        temporary_item_id=temporary_item_id,
        payload=payload,
    )

    _, payload2, _ = req("POST", "/operations", headers=store_headers, json_body=operation_payload, expected=200)
    add_step(
        result,
        "idempotent_replay",
        payload2["id"] == operation_id and payload2["lines"][0]["temporary_item_id"] == temporary_item_id,
        payload=payload2,
    )

    status, _, body = req(
        "POST",
        "/operations",
        headers=store_headers,
        json_body={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-missing-client-request",
                        "name": "Missing request id",
                        "unit_id": unit_id,
                        "category_id": category_id,
                    },
                }
            ],
        },
        expected=422,
    )
    add_step(result, "temporary_requires_client_request_id", "client_request_id" in body, status_code=status, body=body)

    status, _, body = req(
        "POST",
        "/operations",
        headers=observer_headers,
        json_body={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "client_request_id": f"obs-{run}",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-observer",
                        "name": "Observer forbidden",
                        "unit_id": unit_id,
                        "category_id": category_id,
                    },
                }
            ],
        },
        expected=403,
    )
    add_step(
        result,
        "observer_cannot_create_temporary_item",
        "temporary item creation" in body.lower() or "forbidden" in body.lower() or "operate permission required" in body.lower(),
        status_code=status,
        body=body,
    )

    _, payload, _ = req("GET", "/temporary-items", headers=chief_headers, expected=200)
    matched = [x for x in payload["items"] if x["id"] == temporary_item_id]
    add_step(result, "list_temporary_items_as_chief", len(matched) == 1, total_count=payload["total_count"])

    _, payload, _ = req("GET", f"/temporary-items/{temporary_item_id}", headers=chief_headers, expected=200)
    add_step(result, "get_temporary_item_as_chief", payload["status"] == "active" and payload["item_id"] > 0, payload=payload)

    status, _, body = req("GET", "/temporary-items", headers=observer_headers, expected=403)
    add_step(
        result,
        "observer_cannot_list_temporary_items",
        "temporary item moderation" in body.lower() or "catalog management access" in body.lower(),
        status_code=status,
        body=body,
    )

    _, payload, _ = req(
        "POST",
        f"/temporary-items/{temporary_item_id}/approve-as-item",
        headers=chief_headers,
        expected=200,
    )
    add_step(
        result,
        "approve_temporary_item",
        payload["status"] == "approved_as_item" and payload["backing_item_is_active"] is True,
        payload=payload,
    )

    _, payload, _ = req(
        "POST",
        "/operations",
        headers=store_headers,
        json_body={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "client_request_id": f"op-merge-{run}",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-merge",
                        "name": f"Temporary Merge {run}",
                        "sku": None,
                        "unit_id": unit_id,
                        "category_id": category_id,
                        "description": "merge temporary item",
                        "hashtags": ["merge", run],
                    },
                }
            ],
        },
        expected=200,
    )
    merge_temp_id = payload["lines"][0]["temporary_item_id"]
    _, payload, _ = req(
        "POST",
        f"/temporary-items/{merge_temp_id}/merge",
        headers=chief_headers,
        json_body={"target_item_id": catalog_item_id, "comment": "merge check"},
        expected=200,
    )
    add_step(
        result,
        "merge_temporary_item",
        payload["status"] == "merged_to_item" and payload["resolved_item_id"] == catalog_item_id,
        payload=payload,
    )

    _, submit_payload, _ = req(
        "POST",
        f"/operations/{operation_id}/submit",
        headers=chief_headers,
        json_body={"submit": True},
        expected=200,
    )
    add_step(
        result,
        "submit_receive_operation",
        submit_payload.get("status") == "submitted",
        payload=submit_payload,
    )

    line_db = db_fetch_one_sync(
        """
        SELECT id, item_id, inventory_subject_id
        FROM operation_lines
        WHERE id = :line_id
        """,
        {"line_id": temporary_line_id},
    )
    add_step(
        result,
        "db_operation_line_subject_temporary",
        line_db is not None and line_db["inventory_subject_id"] is not None and line_db["item_id"] is not None,
        row=line_db,
    )

    line_db2 = db_fetch_one_sync(
        """
        SELECT id, item_id, inventory_subject_id
        FROM operation_lines
        WHERE id = :line_id
        """,
        {"line_id": catalog_line_id},
    )
    add_step(
        result,
        "db_operation_line_subject_catalog",
        line_db2 is not None and line_db2["inventory_subject_id"] is not None and line_db2["item_id"] is not None,
        row=line_db2,
    )

    balance_db = db_fetch_one_sync(
        """
        SELECT site_id, item_id, inventory_subject_id, qty
        FROM balances
        WHERE site_id = :site_id
          AND inventory_subject_id = :inventory_subject_id
        """,
        {"site_id": site_id, "inventory_subject_id": int(line_db["inventory_subject_id"])},
    )
    add_step(
        result,
        "db_balance_subject_first",
        (balance_db is not None and str(balance_db["qty"]).startswith("2")) or balance_db is None,
        row=balance_db,
    )

    inv_subject_db = db_fetch_one_sync(
        """
        SELECT id, subject_type, item_id, temporary_item_id
        FROM inventory_subjects
        WHERE temporary_item_id = :temporary_item_id
        """,
        {"temporary_item_id": temporary_item_id},
    )
    add_step(
        result,
        "db_inventory_subject_temporary_exists",
        inv_subject_db is not None and inv_subject_db["subject_type"] == "temporary_item",
        row=inv_subject_db,
    )

    pending_reg_db = db_fetch_one_sync(
        """
        SELECT destination_site_id, source_site_id, item_id, inventory_subject_id, qty
        FROM pending_acceptance_balances
        WHERE destination_site_id = :site_id
          AND inventory_subject_id = :inventory_subject_id
        """,
        {"site_id": site_id, "inventory_subject_id": int(line_db["inventory_subject_id"])},
    )
    add_step(
        result,
        "db_pending_acceptance_subject_first",
        pending_reg_db is not None,
        row=pending_reg_db,
    )

    Path("phase1_stand_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("OK")


if __name__ == "__main__":
    main()
