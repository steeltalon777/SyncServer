"""ADR-0033 Item Identity Guard v1 — единственный владелец политики дублей ТМЦ.

Identity-ключ = ``normalize_for_storage(name)`` (только точное равенство,
без fuzzy). Кандидатом считается только alive-запись
(``deleted_at IS NULL AND merged_into_id IS NULL``).

Классификация (в сервисе, не в SQL):
- EXACT   — unit_id и category_id переданы и равны, ``is_active=True``,
            ``requires_review=False``: детерминированный дубль, BLOCK;
- PARTIAL — любой другой alive-кандидат: CREATE + FLAG, решение за человеком.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from app.core.search_utils import normalize_for_storage
from app.models.item import Item
from app.services.uow import UnitOfWork

logger = structlog.get_logger()

MatchTier = Literal["exact", "partial"]


@dataclass(frozen=True)
class IdentityCandidate:
    item_id: int
    name: str
    sku: str | None
    unit_id: int | None
    unit_name: str | None
    unit_symbol: str | None
    category_id: int | None
    category_name: str | None
    is_active: bool
    requires_review: bool
    match: MatchTier

    @classmethod
    def from_item(cls, item: Item, match: MatchTier) -> "IdentityCandidate":
        unit = item.unit
        category = item.category
        return cls(
            item_id=int(item.id),
            name=item.name,
            sku=item.sku,
            unit_id=item.unit_id,
            unit_name=unit.name if unit is not None else None,
            unit_symbol=unit.symbol if unit is not None else None,
            category_id=item.category_id,
            category_name=category.name if category is not None else None,
            is_active=bool(item.is_active),
            requires_review=bool(item.requires_review),
            match=match,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.item_id,
            "name": self.name,
            "sku": self.sku,
            "unit": (
                None
                if self.unit_id is None or self.unit_name is None or self.unit_symbol is None
                else {"id": self.unit_id, "name": self.unit_name, "symbol": self.unit_symbol}
            ),
            "category": (
                None
                if self.category_id is None or self.category_name is None
                else {"id": self.category_id, "name": self.category_name}
            ),
            "is_active": self.is_active,
            "requires_review": self.requires_review,
            "match": self.match,
        }
        return payload


@dataclass(frozen=True)
class IdentityCheckResult:
    requested_name: str
    normalized_name: str | None
    exact: list[IdentityCandidate] = field(default_factory=list)
    partial: list[IdentityCandidate] = field(default_factory=list)

    @property
    def has_exact(self) -> bool:
        return bool(self.exact)

    @property
    def has_candidates(self) -> bool:
        return bool(self.exact or self.partial)

    @property
    def candidates(self) -> list[IdentityCandidate]:
        return [*self.exact, *self.partial]

    def candidate_ids(self) -> list[int]:
        return [candidate.item_id for candidate in self.candidates]


class ItemIdentityConflictError(Exception):
    """Внутренняя (не HTTP) ошибка детерминированного дубля.

    Каждый вход транслирует её в свой контракт: submit — в ProblemEnvelope
    (ADR-0025), admin/review — в структурированный HTTPException(detail=...).
    """

    def __init__(
        self,
        *,
        requested_name: str,
        normalized_name: str | None,
        candidates: list[IdentityCandidate],
    ) -> None:
        super().__init__(f"item identity conflict for {requested_name!r}")
        self.requested_name = requested_name
        self.normalized_name = normalized_name
        self.candidates = candidates


DEFAULT_CONFLICT_MESSAGE = (
    "Товар с таким наименованием, единицей измерения и категорией уже существует. "
    "Используйте существующий товар или измените наименование."
)


def identity_conflict_detail(
    exc: ItemIdentityConflictError,
    *,
    message: str = DEFAULT_CONFLICT_MESSAGE,
) -> dict[str, Any]:
    """Структурированный 409-detail по конвенции HTTPException(detail={...})."""
    return {
        "code": "item_identity_duplicate",
        "message": message,
        "candidates": [candidate.to_dict() for candidate in exc.candidates],
    }


class ItemIdentityService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def find_candidates(
        self,
        name: str | None,
        *,
        unit_id: int | None = None,
        category_id: int | None = None,
        exclude_item_id: int | None = None,
    ) -> IdentityCheckResult:
        normalized = normalize_for_storage(name)
        requested = (name or "").strip()
        if normalized is None:
            return IdentityCheckResult(
                requested_name=requested,
                normalized_name=None,
            )

        items = await self.uow.catalog.find_identity_candidates(
            normalized,
            exclude_item_id=exclude_item_id,
        )
        exact: list[IdentityCandidate] = []
        partial: list[IdentityCandidate] = []
        for item in items:
            if self._is_exact(item, unit_id=unit_id, category_id=category_id):
                exact.append(IdentityCandidate.from_item(item, "exact"))
            else:
                partial.append(IdentityCandidate.from_item(item, "partial"))
        return IdentityCheckResult(
            requested_name=requested,
            normalized_name=normalized,
            exact=exact,
            partial=partial,
        )

    async def assert_can_create(
        self,
        name: str | None,
        *,
        unit_id: int | None,
        category_id: int | None,
        exclude_item_id: int | None = None,
        entry_point: str = "unknown",
    ) -> IdentityCheckResult:
        """BLOCK при >=1 EXACT; иначе возвращает результат (для FLAG-ветки)."""
        result = await self.find_candidates(
            name,
            unit_id=unit_id,
            category_id=category_id,
            exclude_item_id=exclude_item_id,
        )
        if result.has_exact:
            logger.warning(
                "item_identity.block",
                entry_point=entry_point,
                requested_name=result.requested_name,
                candidate_ids=[candidate.item_id for candidate in result.exact],
                exclude_item_id=exclude_item_id,
            )
            raise ItemIdentityConflictError(
                requested_name=result.requested_name,
                normalized_name=result.normalized_name,
                candidates=result.candidates,
            )
        return result

    @staticmethod
    def _is_exact(
        item: Item,
        *,
        unit_id: int | None,
        category_id: int | None,
    ) -> bool:
        # ADR-0033 §5.5: missing identity-параметр трактуется как «неизвестно»
        # и понижает tier до PARTIAL.
        if unit_id is None or category_id is None:
            return False
        return (
            item.unit_id == unit_id
            and item.category_id == category_id
            and bool(item.is_active)
            and not bool(item.requires_review)
        )
