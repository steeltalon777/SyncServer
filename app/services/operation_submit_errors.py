from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.schemas.operation_submit_error import (
    IdentityCandidateRef,
    InsufficientIssuedBalanceError as InsufficientIssuedBalanceErrorSchema,
    InsufficientStockError as InsufficientStockErrorSchema,
    IssueObjectRef,
    ItemIdentityDuplicateError as ItemIdentityDuplicateErrorSchema,
    ItemRef,
    OperationInWrongStateError as OperationInWrongStateErrorSchema,
    OperationNotFoundError as OperationNotFoundErrorSchema,
    ProblemEnvelope,
    ProblemError,
    RoleNotPermittedError as RoleNotPermittedErrorSchema,
    SiteRef,
    StaleVersionError as StaleVersionErrorSchema,
    UnitRef,
)


@dataclass
class StockDeficit:
    stock_site_id: int
    stock_site_name: str
    item_id: int
    item_name: str
    unit_id: int | None
    unit_name: str | None
    unit_symbol: str | None
    required_qty: Decimal
    available_qty: Decimal
    operation_line_ids: list[int]


@dataclass
class IssuedStockDeficit:
    issue_object_id: int
    issue_object_name: str
    item_id: int
    item_name: str
    unit_id: int | None
    unit_name: str | None
    unit_symbol: str | None
    required_qty: Decimal
    available_qty: Decimal
    operation_line_ids: list[int]


@dataclass
class IdentityConflict:
    """One blocked line_group (ADR-0033). Candidates are IdentityCandidateRef-
    shaped dicts; an empty list with intra_batch=True means the duplicate was
    produced between lines of the same operation (different client_key)."""

    requested_name: str
    operation_line_ids: list[int]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    intra_batch: bool = False


class OperationSubmitError(Exception):
    """Base for all submit-flow domain errors. Carries HTTP status and problem-class."""

    problem_class: str = "operation-submit-rejected"
    http_status: int = 409

    def to_envelope(self, instance: str | None = None, trace_id: str | None = None) -> ProblemEnvelope:
        return ProblemEnvelope(
            type=f"urn:warehouse:problem:{self.problem_class}",
            title=self._title(),
            status=self.http_status,
            code=self._code(),
            detail=self._detail(),
            instance=instance,
            trace_id=trace_id,
            errors=self._errors(),
        )

    def _title(self) -> str:
        if self.problem_class == "operation-not-found":
            return "Операция не найдена"
        return "Операция не может быть проведена"

    def _code(self) -> str:
        if self.problem_class == "operation-not-found":
            return "operation_not_found"
        if self.problem_class == "operation-cancel-rejected":
            return "operation_cancel_rejected"
        return "operation_submit_rejected"

    def _detail(self) -> str:
        raise NotImplementedError

    def _errors(self) -> list[ProblemError]:
        raise NotImplementedError


def _build_unit_ref(deficit: StockDeficit | IssuedStockDeficit) -> UnitRef | None:
    if deficit.unit_id is None or deficit.unit_name is None or deficit.unit_symbol is None:
        return None
    return UnitRef(id=deficit.unit_id, name=deficit.unit_name, symbol=deficit.unit_symbol)


class InsufficientStockError(OperationSubmitError):
    def __init__(
        self,
        deficits: list[StockDeficit],
        *,
        problem_class: str = "operation-cancel-rejected",
    ) -> None:
        super().__init__()
        self.problem_class = problem_class
        self.deficits = deficits

    def _errors(self) -> list[ProblemError]:
        return [
            InsufficientStockErrorSchema(
                code="insufficient_stock",
                scope="line_group",
                operation_line_ids=list(deficit.operation_line_ids),
                item=ItemRef(id=deficit.item_id, name=deficit.item_name),
                stock_site=SiteRef(id=deficit.stock_site_id, name=deficit.stock_site_name),
                required_qty=str(deficit.required_qty),
                available_qty=str(deficit.available_qty),
                unit=_build_unit_ref(deficit),
            )
            for deficit in self.deficits
        ]

    def _detail(self) -> str:
        first = self.deficits[0]
        return (
            f"Недостаточно товара: {first.item_name} — запрошено {first.required_qty}, "
            f"на складе {first.available_qty}. Всего проблемных групп: {len(self.deficits)}."
        )


class InsufficientIssuedBalanceError(OperationSubmitError):
    def __init__(
        self,
        deficits: list[IssuedStockDeficit],
        *,
        problem_class: str = "operation-cancel-rejected",
    ) -> None:
        super().__init__()
        self.problem_class = problem_class
        self.deficits = deficits

    def _errors(self) -> list[ProblemError]:
        return [
            InsufficientIssuedBalanceErrorSchema(
                code="insufficient_issued_balance",
                scope="line_group",
                operation_line_ids=list(deficit.operation_line_ids),
                item=ItemRef(id=deficit.item_id, name=deficit.item_name),
                issue_object=IssueObjectRef(id=deficit.issue_object_id, name=deficit.issue_object_name),
                required_qty=str(deficit.required_qty),
                available_qty=str(deficit.available_qty),
                unit=_build_unit_ref(deficit),
            )
            for deficit in self.deficits
        ]

    def _detail(self) -> str:
        first = self.deficits[0]
        return f"Недостаточно выданного остатка по {first.item_name}."


class ItemIdentityDuplicateError(OperationSubmitError):
    """ADR-0033: детерминированный дубль inline-ТМЦ при submit (BLOCK)."""

    def __init__(self, conflicts: list[IdentityConflict]) -> None:
        super().__init__()
        self.conflicts = conflicts

    def _errors(self) -> list[ProblemError]:
        return [
            ItemIdentityDuplicateErrorSchema(
                code="item_identity_duplicate",
                scope="line_group",
                operation_line_ids=list(conflict.operation_line_ids),
                requested_name=conflict.requested_name,
                candidates=[IdentityCandidateRef(**candidate) for candidate in conflict.candidates],
            )
            for conflict in self.conflicts
        ]

    def _detail(self) -> str:
        first = self.conflicts[0]
        if first.intra_batch:
            return (
                f"Товар «{first.requested_name}» задан в строках операции под разными client_key. "
                "Используйте один client_key для одинаковых строк или различите наименования."
            )
        candidate_ref = ""
        if first.candidates:
            candidate_id = first.candidates[0].get("id")
            if candidate_id is not None:
                candidate_ref = f" (id={candidate_id})"
        return (
            f"Товар «{first.requested_name}» уже существует в каталоге{candidate_ref}. "
            "Используйте существующий товар или измените наименование."
        )


class StaleVersionError(OperationSubmitError):
    def __init__(
        self,
        expected_version: int,
        actual_version: int,
        *,
        problem_class: str = "operation-cancel-rejected",
    ) -> None:
        super().__init__()
        self.problem_class = problem_class
        self.expected_version = expected_version
        self.actual_version = actual_version

    def _errors(self) -> list[ProblemError]:
        return [
            StaleVersionErrorSchema(
                code="stale_version",
                scope="operation",
                expected_version=self.expected_version,
                actual_version=self.actual_version,
            )
        ]

    def _detail(self) -> str:
        return f"Операция была изменена в другой вкладке. Актуальная версия {self.actual_version}."


class OperationInWrongStateError(OperationSubmitError):
    def __init__(
        self,
        current_state: str,
        allowed_states: list[str],
        *,
        problem_class: str = "operation-cancel-rejected",
    ) -> None:
        super().__init__()
        self.problem_class = problem_class
        self.current_state = current_state
        self.allowed_states = allowed_states

    def _errors(self) -> list[ProblemError]:
        return [
            OperationInWrongStateErrorSchema(
                code="operation_in_wrong_state",
                scope="operation",
                current_state=self.current_state,
                allowed_states=list(self.allowed_states),
            )
        ]

    def _detail(self) -> str:
        return (
            f"Операция в статусе «{self.current_state}», "
            f"для проведения требуется «{self.allowed_states[0]}»."
        )


class OperationNotFoundError(OperationSubmitError):
    problem_class = "operation-not-found"
    http_status = 404

    def __init__(self, operation_id: UUID) -> None:
        super().__init__()
        self.operation_id = operation_id

    def _errors(self) -> list[ProblemError]:
        return [OperationNotFoundErrorSchema(code="operation_not_found", scope="operation")]

    def _detail(self) -> str:
        return "Операция не найдена."


class RoleNotPermittedError(OperationSubmitError):
    http_status = 403

    def __init__(self, *, problem_class: str = "operation-cancel-rejected") -> None:
        super().__init__()
        self.problem_class = problem_class

    def _errors(self) -> list[ProblemError]:
        return [RoleNotPermittedErrorSchema(code="role_not_permitted", scope="operation")]

    def _detail(self) -> str:
        return "Недостаточно прав для проведения операции."
