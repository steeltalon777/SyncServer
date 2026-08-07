from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.operation_submit_errors import (
    InsufficientIssuedBalanceError,
    InsufficientStockError,
    IssuedStockDeficit,
    OperationInWrongStateError,
    OperationNotFoundError,
    OperationSubmitError,
    RoleNotPermittedError,
    StaleVersionError,
    StockDeficit,
)
from main import create_app


def _stock_deficit(**overrides) -> StockDeficit:
    values = {
        "stock_site_id": 2,
        "stock_site_name": "Склад Чита",
        "item_id": 17,
        "item_name": "Кабель ВВГ 3×2.5",
        "unit_id": 4,
        "unit_name": "метр",
        "unit_symbol": "м",
        "required_qty": Decimal("120.000"),
        "available_qty": Decimal("80.000"),
        "operation_line_ids": [104, 101],
    }
    values.update(overrides)
    return StockDeficit(**values)


def _issued_stock_deficit(**overrides) -> IssuedStockDeficit:
    values = {
        "issue_object_id": 9,
        "issue_object_name": "Иванов Иван",
        "item_id": 42,
        "item_name": "Шуруповёрт",
        "unit_id": None,
        "unit_name": None,
        "unit_symbol": None,
        "required_qty": Decimal("2.000"),
        "available_qty": Decimal("1.000"),
        "operation_line_ids": [7, 8],
    }
    values.update(overrides)
    return IssuedStockDeficit(**values)


def _all_errors() -> list[OperationSubmitError]:
    """Submit-flow errors: every subclass constructed with the submit problem_class."""
    return [
        InsufficientStockError(deficits=[_stock_deficit()], problem_class="operation-submit-rejected"),
        InsufficientIssuedBalanceError(
            deficits=[_issued_stock_deficit()], problem_class="operation-submit-rejected"
        ),
        StaleVersionError(expected_version=3, actual_version=5, problem_class="operation-submit-rejected"),
        OperationInWrongStateError(
            current_state="SUBMITTED", allowed_states=["DRAFT"], problem_class="operation-submit-rejected"
        ),
        OperationNotFoundError(operation_id=uuid4()),
        RoleNotPermittedError(problem_class="operation-submit-rejected"),
    ]


@pytest.mark.unit
@pytest.mark.fast
class TestOperationSubmitErrorEnvelope:
    def test_envelope_insufficient_stock_serializes_correctly(self) -> None:
        error = InsufficientStockError(
            deficits=[
                _stock_deficit(),
                _stock_deficit(
                    item_id=23,
                    item_name="Труба ПНД 32",
                    stock_site_id=3,
                    stock_site_name="Склад Улан-Удэ",
                    required_qty=Decimal("10.000"),
                    available_qty=Decimal("5.000"),
                    operation_line_ids=[300],
                ),
            ],
            problem_class="operation-submit-rejected",
        )
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-submit-rejected"
        assert payload["title"] == "Операция не может быть проведена"
        assert payload["status"] == 409
        assert payload["code"] == "operation_submit_rejected"
        assert payload["instance"] == "/api/v1/operations/123/submit"
        assert payload["trace_id"] == "trace-1"

        errors = payload["errors"]
        assert len(errors) == 2
        first = errors[0]
        assert first["code"] == "insufficient_stock"
        assert first["scope"] == "line_group"
        assert first["operation_line_ids"] == [104, 101]
        assert first["item"] == {"id": 17, "name": "Кабель ВВГ 3×2.5"}
        assert first["stock_site"] == {"id": 2, "name": "Склад Чита"}
        assert first["required_qty"] == "120.000"
        assert first["available_qty"] == "80.000"
        assert first["unit"] == {"id": 4, "name": "метр", "symbol": "м"}

        second = errors[1]
        assert second["operation_line_ids"] == [300]
        assert second["required_qty"] == "10.000"
        assert second["available_qty"] == "5.000"

    def test_envelope_insufficient_issued_balance_serializes_correctly(self) -> None:
        error = InsufficientIssuedBalanceError(
            deficits=[_issued_stock_deficit(operation_line_ids=[8, 7])],
            problem_class="operation-submit-rejected",
        )
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-submit-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_submit_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "insufficient_issued_balance"
        assert first["scope"] == "line_group"
        assert first["operation_line_ids"] == [8, 7]
        assert first["item"] == {"id": 42, "name": "Шуруповёрт"}
        assert first["issue_object"] == {"id": 9, "name": "Иванов Иван"}
        assert first["required_qty"] == "2.000"
        assert first["available_qty"] == "1.000"
        assert "unit" not in first

    def test_envelope_stale_version_serializes_correctly(self) -> None:
        error = StaleVersionError(expected_version=3, actual_version=5, problem_class="operation-submit-rejected")
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-submit-rejected"
        assert payload["title"] == "Операция не может быть проведена"
        assert payload["status"] == 409
        assert payload["code"] == "operation_submit_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "stale_version"
        assert first["scope"] == "operation"
        assert first["expected_version"] == 3
        assert first["actual_version"] == 5

    def test_envelope_operation_in_wrong_state_serializes_correctly(self) -> None:
        error = OperationInWrongStateError(
            current_state="SUBMITTED", allowed_states=["DRAFT"], problem_class="operation-submit-rejected"
        )
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-submit-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_submit_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "operation_in_wrong_state"
        assert first["scope"] == "operation"
        assert first["current_state"] == "SUBMITTED"
        assert first["allowed_states"] == ["DRAFT"]

    def test_envelope_operation_not_found_serializes_correctly(self) -> None:
        operation_id = uuid4()
        error = OperationNotFoundError(operation_id=operation_id)
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-not-found"
        assert payload["title"] == "Операция не найдена"
        assert payload["status"] == 404
        assert payload["code"] == "operation_not_found"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "operation_not_found"
        assert first["scope"] == "operation"
        assert set(first.keys()) == {"code", "scope"}

    def test_envelope_role_not_permitted_serializes_correctly(self) -> None:
        error = RoleNotPermittedError(problem_class="operation-submit-rejected")
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert payload["type"] == "urn:warehouse:problem:operation-submit-rejected"
        assert payload["title"] == "Операция не может быть проведена"
        assert payload["status"] == 403
        assert payload["code"] == "operation_submit_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "role_not_permitted"
        assert first["scope"] == "operation"
        assert set(first.keys()) == {"code", "scope"}

    def test_envelope_detail_is_string_for_all_codes(self) -> None:
        expected_details = [
            "Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 120.000, на складе 80.000. Всего проблемных групп: 1.",
            "Недостаточно выданного остатка по Шуруповёрт.",
            "Операция была изменена в другой вкладке. Актуальная версия 5.",
            "Операция в статусе «SUBMITTED», для проведения требуется «DRAFT».",
            "Операция не найдена.",
            "Недостаточно прав для проведения операции.",
        ]
        for error, expected in zip(_all_errors(), expected_details):
            detail = error.to_envelope().detail
            assert isinstance(detail, str)
            assert detail == expected

    def test_envelope_type_is_urn_for_all_codes(self) -> None:
        for error in _all_errors():
            envelope = error.to_envelope()
            assert envelope.type.startswith("urn:warehouse:problem:")
            assert envelope.type == f"urn:warehouse:problem:{error.problem_class}"

    def test_envelope_excludes_none_fields(self) -> None:
        error = InsufficientStockError(
            deficits=[_stock_deficit(unit_id=None, unit_name=None, unit_symbol=None)],
            problem_class="operation-submit-rejected",
        )
        payload = error.to_envelope(
            instance="/api/v1/operations/123/submit", trace_id="trace-1"
        ).model_dump(exclude_none=True)

        assert "unit" not in payload["errors"][0]
        assert set(payload["errors"][0].keys()) == {
            "code",
            "scope",
            "operation_line_ids",
            "item",
            "stock_site",
            "required_qty",
            "available_qty",
        }


@pytest.mark.unit
@pytest.mark.fast
class TestOperationSubmitErrorHandler:
    async def _submit_via_app(self, error: OperationSubmitError, *, trace_id: str | None = None) -> dict:
        app = create_app(enable_startup_migrations=False)

        @app.post("/test-submit-error")
        async def raise_submit_error():
            raise error

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-Request-Id": trace_id} if trace_id else None
            response = await client.post("/test-submit-error", headers=headers)

        assert response.status_code == error.http_status
        return response.json()

    async def test_envelope_trace_id_from_request_header(self) -> None:
        error = StaleVersionError(expected_version=3, actual_version=5)
        data = await self._submit_via_app(error, trace_id="req-abc-123")

        assert data["status"] == 409
        assert data["trace_id"] == "req-abc-123"
        assert data["instance"] == "/test-submit-error"
        assert data["errors"][0]["code"] == "stale_version"

    async def test_envelope_has_no_trace_id_without_request_header(self) -> None:
        error = OperationNotFoundError(operation_id=uuid4())
        data = await self._submit_via_app(error)

        assert data["status"] == 404
        assert "trace_id" not in data
        assert data["errors"][0]["code"] == "operation_not_found"

    async def test_envelope_handler_uses_exclude_none(self) -> None:
        error = InsufficientStockError(
            deficits=[_stock_deficit(unit_id=None, unit_name=None, unit_symbol=None)]
        )
        data = await self._submit_via_app(error)

        assert data["status"] == 409
        assert "unit" not in data["errors"][0]
        assert data["errors"][0]["required_qty"] == "120.000"
        assert data["errors"][0]["available_qty"] == "80.000"


@pytest.mark.unit
@pytest.mark.fast
class TestOperationCancelErrorEnvelope:
    """Cancel-flow envelope (TZ-OPERATION_CANCEL_DOMAIN_ERRORS §3, ADR-0027 §1).

    Every reused subclass is constructed with `problem_class="operation-cancel-rejected"`
    (the new default) and must produce type `urn:warehouse:problem:operation-cancel-rejected`
    and top-level code `operation_cancel_rejected`, except OperationNotFoundError
    which keeps its own class-level `operation-not-found` / `operation_not_found`.
    """

    def _payload(self, error: OperationSubmitError) -> dict:
        return error.to_envelope(instance="/api/v1/operations/123/cancel", trace_id="trace-1").model_dump(
            exclude_none=True
        )

    def test_envelope_insufficient_stock_cancel_flow(self) -> None:
        payload = self._payload(InsufficientStockError(deficits=[_stock_deficit()]))

        assert payload["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_cancel_rejected"
        assert payload["instance"] == "/api/v1/operations/123/cancel"
        assert payload["trace_id"] == "trace-1"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "insufficient_stock"
        assert first["scope"] == "line_group"
        assert first["operation_line_ids"] == [104, 101]
        assert first["item"] == {"id": 17, "name": "Кабель ВВГ 3×2.5"}
        assert first["stock_site"] == {"id": 2, "name": "Склад Чита"}
        assert first["required_qty"] == "120.000"
        assert first["available_qty"] == "80.000"
        assert first["unit"] == {"id": 4, "name": "метр", "symbol": "м"}
        assert payload["detail"] == (
            "Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 120.000, "
            "на складе 80.000. Всего проблемных групп: 1."
        )

    def test_envelope_insufficient_issued_balance_cancel_flow(self) -> None:
        payload = self._payload(InsufficientIssuedBalanceError(deficits=[_issued_stock_deficit()]))

        assert payload["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_cancel_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "insufficient_issued_balance"
        assert first["scope"] == "line_group"
        assert first["operation_line_ids"] == [7, 8]
        assert first["item"] == {"id": 42, "name": "Шуруповёрт"}
        assert first["issue_object"] == {"id": 9, "name": "Иванов Иван"}
        assert first["required_qty"] == "2.000"
        assert first["available_qty"] == "1.000"

    def test_envelope_stale_version_cancel_flow(self) -> None:
        payload = self._payload(StaleVersionError(expected_version=3, actual_version=5))

        assert payload["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_cancel_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "stale_version"
        assert first["expected_version"] == 3
        assert first["actual_version"] == 5

    def test_envelope_operation_in_wrong_state_cancel_flow(self) -> None:
        payload = self._payload(
            OperationInWrongStateError(current_state="cancelled", allowed_states=["draft", "submitted"])
        )

        assert payload["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert payload["status"] == 409
        assert payload["code"] == "operation_cancel_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "operation_in_wrong_state"
        assert first["current_state"] == "cancelled"
        assert first["allowed_states"] == ["draft", "submitted"]

    def test_envelope_operation_not_found_cancel_flow(self) -> None:
        operation_id = uuid4()
        payload = self._payload(OperationNotFoundError(operation_id=operation_id))

        assert payload["type"] == "urn:warehouse:problem:operation-not-found"
        assert payload["status"] == 404
        assert payload["code"] == "operation_not_found"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "operation_not_found"
        assert first["scope"] == "operation"
        assert set(first.keys()) == {"code", "scope"}

    def test_envelope_role_not_permitted_cancel_flow(self) -> None:
        payload = self._payload(RoleNotPermittedError())

        assert payload["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert payload["status"] == 403
        assert payload["code"] == "operation_cancel_rejected"

        errors = payload["errors"]
        assert len(errors) == 1
        first = errors[0]
        assert first["code"] == "role_not_permitted"
        assert first["scope"] == "operation"
        assert set(first.keys()) == {"code", "scope"}

    def test_cancel_problem_class_defaults_for_all_subclasses(self) -> None:
        """All six subclasses default to the cancel-flow problem class (TZ §3.2)."""
        errors: list[OperationSubmitError] = [
            InsufficientStockError(deficits=[_stock_deficit()]),
            InsufficientIssuedBalanceError(deficits=[_issued_stock_deficit()]),
            StaleVersionError(expected_version=3, actual_version=5),
            OperationInWrongStateError(current_state="cancelled", allowed_states=["draft", "submitted"]),
            OperationNotFoundError(operation_id=uuid4()),
            RoleNotPermittedError(),
        ]
        for error in errors:
            if isinstance(error, OperationNotFoundError):
                assert error.problem_class == "operation-not-found"
            else:
                assert error.problem_class == "operation-cancel-rejected"

    async def test_cancel_handler_returns_envelope_via_app(self) -> None:
        """FastAPI exception handler builds the cancel envelope end-to-end."""
        app = create_app(enable_startup_migrations=False)

        @app.post("/test-cancel-error")
        async def raise_cancel_error():
            raise InsufficientStockError(deficits=[_stock_deficit()])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/test-cancel-error")
            assert response.status_code == 409
            data = response.json()

        assert data["type"] == "urn:warehouse:problem:operation-cancel-rejected"
        assert data["code"] == "operation_cancel_rejected"
        assert data["errors"][0]["code"] == "insufficient_stock"
