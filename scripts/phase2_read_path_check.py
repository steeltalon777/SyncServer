import os

import httpx


BASE = os.getenv("SYNC_SERVER_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
ROOT_TOKEN = os.getenv("SYNC_ROOT_USER_TOKEN", "")


def _get(path: str, params: dict | None = None) -> tuple[int, dict]:
    headers = {"X-User-Token": ROOT_TOKEN} if ROOT_TOKEN else {}
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        response = client.get(path, params=params, headers=headers)
    return response.status_code, response.json() if response.headers.get("content-type", "").startswith("application/json") else {}


def _assert_subject_first_row(row: dict, *, name: str) -> None:
    required = [
        "inventory_subject_id",
        "subject_type",
        "item_id",
        "temporary_item_id",
        "resolved_item_id",
    ]
    for key in required:
        if key not in row:
            raise AssertionError(f"{name}: missing key '{key}'")


def main() -> None:
    if not ROOT_TOKEN:
        raise SystemExit("SYNC_ROOT_USER_TOKEN is required")

    checks = [
        ("/balances", "items"),
        ("/operations", "items"),
        ("/pending-acceptance", "items"),
        ("/lost-assets", "items"),
        ("/issued-assets", "items"),
        ("/reports/item-movement", "items"),
        ("/reports/stock-summary", "items"),
    ]

    for path, items_key in checks:
        status, payload = _get(path, params={"page": 1, "page_size": 5})
        if status != 200:
            raise AssertionError(f"GET {path} -> {status}")
        items = payload.get(items_key, [])
        if items:
            first = items[0]
            if path == "/operations":
                lines = first.get("lines", [])
                if lines:
                    _assert_subject_first_row(lines[0], name=f"{path}.lines[0]")
            else:
                _assert_subject_first_row(first, name=f"{path}.items[0]")

    print("phase2_read_path_check: OK")


if __name__ == "__main__":
    main()
