"""
Centralized catalog mutation policy for the ``agent`` domain role.

Architecture: ADR-0030 (``docs/adr/0030-agent-domain-role.md``), TZ §5.1–5.2.

The ``agent`` (LLM-assistant of the chief storekeeper) may PATCH existing
catalog entities only through the allow-lists below. A request that contains a
known PATCH field outside the allow-list (e.g. ``is_active``) must be rejected
with 403 *before* the mutation service is called — fields are not silently
filtered out (TZ §5.1).

"Known" fields are exactly the fields of the corresponding UpdateRequest
schemas in ``app/schemas/catalog.py`` (``ItemUpdateRequest``,
``CategoryUpdateRequest``, ``UnitUpdateRequest``). Any field that is not part
of the update schema is not "known": Pydantic itself drops it before this
policy runs, so it cannot reach the mutation service through PATCH.
"""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException, status

from app.schemas.catalog import (
    CategoryUpdateRequest,
    ItemUpdateRequest,
    UnitUpdateRequest,
)

# TZ §5.2 — Item PATCH allow-list.
AGENT_ITEM_PATCH_FIELDS: Final[set[str]] = {
    "name",
    "sku",
    "description",
    "category_id",
    "unit_id",
    "hashtags",
}

# TZ §5.2 — Category PATCH allow-list.
AGENT_CATEGORY_PATCH_FIELDS: Final[set[str]] = {
    "name",
    "code",
    "parent_id",
    "sort_order",
}

# TZ §5.2 — Unit PATCH allow-list.
AGENT_UNIT_PATCH_FIELDS: Final[set[str]] = {
    "name",
    "symbol",
    "sort_order",
}

_ENTITY_KINDS: Final[tuple[str, ...]] = ("item", "category", "unit")

_ALLOW_LISTS: Final[dict[str, set[str]]] = {
    "item": AGENT_ITEM_PATCH_FIELDS,
    "category": AGENT_CATEGORY_PATCH_FIELDS,
    "unit": AGENT_UNIT_PATCH_FIELDS,
}

_KNOWN_UPDATE_FIELDS: Final[dict[str, set[str]]] = {
    "item": set(ItemUpdateRequest.model_fields),
    "category": set(CategoryUpdateRequest.model_fields),
    "unit": set(UnitUpdateRequest.model_fields),
}


def validate_agent_patch(entity_kind: str, payload: dict[str, object]) -> None:
    """
    Reject agent PATCH payloads that contain known fields outside the allow-list.

    Raises HTTPException 403 before any mutation service call (TZ §5.1).
    Payload fields that are not part of the update schema are ignored — Pydantic
    rejects them on its own and they can never reach the service.
    """
    if entity_kind not in _ENTITY_KINDS:
        raise ValueError(f"unknown catalog entity kind: {entity_kind!r}")

    allowed = _ALLOW_LISTS[entity_kind]
    known = _KNOWN_UPDATE_FIELDS[entity_kind]
    forbidden = sorted((known & set(payload)) - allowed)
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"agent is not allowed to modify fields: {', '.join(forbidden)}",
        )
