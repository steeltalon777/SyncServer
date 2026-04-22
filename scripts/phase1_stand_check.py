import json
import time
from pathlib import Path

import httpx


BASE = "http://127.0.0.1:8000"
ROOT_TOKEN = "9d5c0496-a32b-4d55-be0d-1fcfede4fd5a"
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

    status, payload, _ = req("GET", "/api/v1/health", expected=200)
    add_step(result, "health", payload == {"status": "ok"}, status_code=status, payload=payload)

    status, payload, _ = req("GET", "/api/v1/ready", expected=200)
    add_step(result, "ready", payload is not None and payload.get("status") == "ready", status_code=status, payload=payload)

    status, payload, _ = req("GET", "/api/v1/auth/me", headers={"X-User-Token": ROOT_TOKEN}, expected=200)
    add_step(
        result,
        "root_auth",
        payload is not None and payload.get("user", {}).get("is_root") is True,
        status_code=status,
        payload=payload,
    )

    status, payload, _ = req(
        "POST",
        "/api/v1/admin/sites",
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
            "/api/v1/admin/users",
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
            f"/api/v1/admin/users/{user_id}/rotate-token",
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
            f"/api/v1/admin/users/{users[role]['id']}/scopes",
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
        "/api/v1/catalog/admin/units",
        headers=HEADERS_ROOT,
        json_body={"name": unit_name, "symbol": f"u{run[-4:]}", "is_active": True},
        expected=200,
    )
    unit_id = payload["id"]
    add_step(result, "create_unit", True, unit_id=unit_id)

    status, payload, _ = req(
        "POST",
        "/api/v1/catalog/admin/categories",
        headers=HEADERS_ROOT,
        json_body={"name": category_name, "code": f"C-{run}", "is_active": True},
        expected=200,
    )
    category_id = payload["id"]
    add_step(result, "create_category", True, category_id=category_id)

    status, payload, _ = req(
        "POST",
        "/api/v1/catalog/admin/items",
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
    _, payload, _ = req("POST", "/api/v1/operations", headers=store_headers, json_body=operation_payload, expected=200)
    operation_id = payload["id"]
    temporary_item_id = payload["lines"][0]["temporary_item_id"]
    add_step(
        result,
        "create_receive_with_mixed_lines",
        payload["lines"][0]["temporary_item_status"] == "active" and payload["lines"][1]["temporary_item_id"] is None,
        operation_id=operation_id,
        temporary_item_id=temporary_item_id,
        payload=payload,
    )

    _, payload2, _ = req("POST", "/api/v1/operations", headers=store_headers, json_body=operation_payload, expected=200)
    add_step(
        result,
        "idempotent_replay",
        payload2["id"] == operation_id and payload2["lines"][0]["temporary_item_id"] == temporary_item_id,
        payload=payload2,
    )

    status, _, body = req(
        "POST",
        "/api/v1/operations",
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
        "/api/v1/operations",
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

    _, payload, _ = req("GET", "/api/v1/temporary-items", headers=chief_headers, expected=200)
    matched = [x for x in payload["items"] if x["id"] == temporary_item_id]
    add_step(result, "list_temporary_items_as_chief", len(matched) == 1, total_count=payload["total_count"])

    _, payload, _ = req("GET", f"/api/v1/temporary-items/{temporary_item_id}", headers=chief_headers, expected=200)
    add_step(result, "get_temporary_item_as_chief", payload["status"] == "active" and payload["item_id"] > 0, payload=payload)

    status, _, body = req("GET", "/api/v1/temporary-items", headers=observer_headers, expected=403)
    add_step(
        result,
        "observer_cannot_list_temporary_items",
        "temporary item moderation" in body.lower() or "catalog management access" in body.lower(),
        status_code=status,
        body=body,
    )

    _, payload, _ = req(
        "POST",
        f"/api/v1/temporary-items/{temporary_item_id}/approve-as-item",
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
        "/api/v1/operations",
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
        f"/api/v1/temporary-items/{merge_temp_id}/merge",
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

    Path("phase1_stand_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK")


if __name__ == "__main__":
    main()
