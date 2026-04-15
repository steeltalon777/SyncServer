from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status

from app.repos.sites_repo import SitesRepo
from app.repos.users_repo import UsersRepo
from app.schemas.document import DocumentGenerateRequest, DocumentType
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)

# Версия схемы payload для генерации документов
PAYLOAD_SCHEMA_VERSION = "1.0.0"

# Шаблоны по умолчанию для каждого типа документа
DEFAULT_TEMPLATES: dict[DocumentType, str] = {
    "waybill": "waybill_v1",
    "acceptance_certificate": "acceptance_certificate_v1",
    "act": "act_v1",
    "invoice": "invoice_v1",
}


def _compute_payload_hash(payload: dict[str, Any]) -> str:
    """Вычисляет SHA-256 хэш payload для контроля неизменности."""
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def _generate_document_number(
    document_type: DocumentType,
    site_id: int,
) -> str:
    """Генерирует номер документа по сквозной нумерации.

    Формат: {TYPE_PREFIX}-{SITE_ID}-{TIMESTAMP}
    Например: WB-1-20260415-001
    """
    type_prefix_map: dict[DocumentType, str] = {
        "waybill": "WB",
        "acceptance_certificate": "AC",
        "act": "ACT",
        "invoice": "INV",
    }
    prefix = type_prefix_map.get(document_type, "DOC")
    timestamp = datetime.now(UTC).strftime("%Y%m%d")
    # Временный номер — будет заменён на сквозной при финализации
    # Для ahora используем timestamp + random suffix
    import secrets
    suffix = secrets.token_hex(2)  # 4 hex символа
    return f"{prefix}-{site_id}-{timestamp}-{suffix}"


class DocumentService:
    """Сервис для формирования документов из операций."""

    @staticmethod
    async def generate_from_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        document_type: DocumentType = "waybill",
        template_name: str | None = None,
        auto_finalize: bool = False,
        created_by_user_id: UUID | None = None,
        language: str = "ru",
        basis_type: str | None = None,
        basis_number: str | None = None,
        basis_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Сгенерировать документ на основе операции.

        Собирает payload со всеми печатными реквизитами:
        - Данные операции и её строки
        - Исторические снапшоты (item_name_snapshot, recipient_name_snapshot и т.д.)
        - Слепки площадок (название, адрес)
        - Данные ответственных лиц
        - Номер документа по сквозной нумерации

        Args:
            uow: UnitOfWork для транзакции
            operation_id: ID операции-источника
            document_type: Тип документа (waybill, acceptance_certificate, act, invoice)
            template_name: Имя шаблона (если None — используется шаблон по умолчанию)
            auto_finalize: Если True — документ сразу финализируется
            created_by_user_id: ID пользователя-создателя

        Returns:
            Словарь с созданным документом и статусом
        """
        # 1. Получаем операцию
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"operation with id {operation_id} not found",
            )

        # Операция должна быть submitted для генерации документа
        # (допускаем также draft для предварительного просмотра)
        if operation.status not in ("draft", "submitted"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot generate document for operation with status '{operation.status}'",
            )

        # 2. Получаем площадку
        site = await uow.sites.get_by_id(operation.site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"site with id {operation.site_id} not found",
            )

        # Для MOVE — получаем также destination site
        destination_site = None
        if operation.operation_type == "MOVE" and operation.destination_site_id:
            destination_site = await uow.sites.get_by_id(operation.destination_site_id)

        # 3. Получаем пользователя-создателя
        created_by_user = None
        if operation.created_by_user_id:
            created_by_user = await uow.users.get_by_id(operation.created_by_user_id)

        # 4. Получаем пользователя, который submit'ил операцию
        submitted_by_user = None
        if operation.submitted_by_user_id:
            submitted_by_user = await uow.users.get_by_id(operation.submitted_by_user_id)

        # 5. Формируем payload
        payload = DocumentService._build_payload(
            operation=operation,
            site=site,
            destination_site=destination_site,
            created_by_user=created_by_user,
            submitted_by_user=submitted_by_user,
            document_type=document_type,
            language=language,
            basis_type=basis_type,
            basis_number=basis_number,
            basis_date=basis_date,
        )

        # 6. Определяем шаблон
        effective_template = template_name or DEFAULT_TEMPLATES.get(document_type, "default_v1")

        # 7. Генерируем номер документа
        document_number = _generate_document_number(document_type, operation.site_id)

        # 8. Вычисляем хэш payload
        payload_hash = _compute_payload_hash(payload)

        # 9. Определяем статус
        status_value = "finalized" if auto_finalize else "draft"
        now = datetime.now(UTC) if auto_finalize else None

        # 10. Создаём документ
        document = await uow.documents.create_document(
            document_type=document_type,
            site_id=operation.site_id,
            payload=payload,
            created_by_user_id=created_by_user_id or operation.created_by_user_id,
            document_number=document_number,
            revision=0,
            status=status_value,
            template_name=effective_template,
            template_version="1.0",
            payload_schema_version=PAYLOAD_SCHEMA_VERSION,
            payload_hash=payload_hash,
            finalized_at=now,
        )

        # 11. Линкуем документ к операции
        await uow.documents.link_document_to_operation(document.id, operation_id)

        logger.info(
            "Generated document id=%s type=%s for operation id=%s status=%s",
            document.id,
            document_type,
            operation_id,
            status_value,
        )

        return {
            "document": document,
            "operation": operation,
        }

    @staticmethod
    def _build_payload(
        operation,
        site,
        destination_site=None,
        created_by_user=None,
        submitted_by_user=None,
        document_type: DocumentType = "waybill",
        language: str = "ru",
        basis_type: str | None = None,
        basis_number: str | None = None,
        basis_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Собрать самодостаточный payload для печати документа.

        Payload включает все печатные реквизиты:
        - Заголовок документа
        - Данные площадки (отправитель/получатель)
        - Строки документа с историческими снапшотами
        - Подписи ответственных лиц
        - Метаданные операции
        """
        # Заголовок документа
        document_title = DocumentService._get_document_title(document_type)

        # Данные площадки (отправитель)
        sender_organization = {
            "legal_name": site.name,
            "address": site.description,
            "tax_id": None,
            "contacts": None,
        }
        sender_info = {
            "site_id": site.id,
            "site_code": site.code,
            "site_name": site.name,
            "description": site.description,
            "organization": sender_organization,
        }

        # Данные площадки-получателя (для MOVE)
        receiver_info = None
        if destination_site:
            receiver_organization = {
                "legal_name": destination_site.name,
                "address": destination_site.description,
                "tax_id": None,
                "contacts": None,
            }
            receiver_info = {
                "site_id": destination_site.id,
                "site_code": destination_site.code,
                "site_name": destination_site.name,
                "description": destination_site.description,
                "organization": receiver_organization,
            }

        # Ответственные лица
        created_by_info = None
        if created_by_user:
            created_by_info = {
                "user_id": str(created_by_user.id),
                "username": created_by_user.username,
                "full_name": created_by_user.full_name,
                "role": created_by_user.role,
            }

        submitted_by_info = None
        if submitted_by_user:
            submitted_by_info = {
                "user_id": str(submitted_by_user.id),
                "username": submitted_by_user.username,
                "full_name": submitted_by_user.full_name,
                "role": submitted_by_user.role,
            }

        # Строки документа
        lines = []
        for line in operation.lines:
            line_data = {
                "line_number": line.line_number,
                "item_id": line.item_id,
                "item_name": line.item_name_snapshot or "",
                "item_sku": line.item_sku_snapshot or "",
                "quantity": float(line.qty),
                "unit_name": line.unit_name_snapshot or "",
                "unit_symbol": line.unit_symbol_snapshot or "",
                "category_name": line.category_name_snapshot or "",
                "batch": line.batch,
                "comment": line.comment,
            }
            # Для приёмки — добавляем принятые/потерянные количества
            if operation.acceptance_state in ("in_progress", "resolved"):
                line_data["accepted_qty"] = float(line.accepted_qty) if line.accepted_qty else None
                line_data["lost_qty"] = float(line.lost_qty) if line.lost_qty else None
            lines.append(line_data)

        # Получатель (для ISSUE/ISSUE_RETURN)
        recipient_info = None
        if operation.recipient_id or operation.recipient_name_snapshot:
            recipient_info = {
                "recipient_id": operation.recipient_id,
                "recipient_name": operation.recipient_name_snapshot,
            }

        # Выдано лицу
        issued_to_info = None
        if operation.issued_to_user_id or operation.issued_to_name:
            issued_to_info = {
                "user_id": str(operation.issued_to_user_id) if operation.issued_to_user_id else None,
                "name": operation.issued_to_name,
            }

        # Подписи с ролями
        signatures = {
            "created_by": created_by_info["full_name"] if created_by_info else None,
            "submitted_by": submitted_by_info["full_name"] if submitted_by_info else None,
            "roles": {
                "handed_over": submitted_by_info["full_name"] if submitted_by_info else None,
                "accepted_by": None,
                "chief_accountant": "________________",
            },
        }

        # Основание документа (приказ/договор/заявка и т.п.)
        basis = {
            "type": basis_type,
            "number": basis_number,
            "date": basis_date.isoformat() if basis_date else None,
        }

        # Локализационные настройки
        language_normalized = (language or "ru").lower()
        localization_map = {
            "ru": {
                "language": "ru",
                "date_format": "%d.%m.%Y",
                "datetime_format": "%d.%m.%Y %H:%M:%S",
                "number_decimal_separator": ",",
                "thousands_separator": " ",
                "currency": "RUB",
            },
            "en": {
                "language": "en",
                "date_format": "%Y-%m-%d",
                "datetime_format": "%Y-%m-%d %H:%M:%S",
                "number_decimal_separator": ".",
                "thousands_separator": ",",
                "currency": "RUB",
            },
        }
        localization = localization_map.get(language_normalized, localization_map["ru"])

        payload = {
            "document_title": document_title,
            "operation_id": str(operation.id),
            "operation_type": operation.operation_type,
            "operation_status": operation.status,
            "operation_notes": operation.notes,
            "operation_created_at": operation.created_at.isoformat() if operation.created_at else None,
            "operation_submitted_at": operation.submitted_at.isoformat() if operation.submitted_at else None,
            "operation_effective_at": operation.effective_at.isoformat() if operation.effective_at else None,
            "operation_acceptance_state": operation.acceptance_state,
            "sender": sender_info,
            "receiver": receiver_info,
            "recipient": recipient_info,
            "issued_to": issued_to_info,
            "basis": basis,
            "lines": lines,
            "total_lines": len(lines),
            "created_by": created_by_info,
            "submitted_by": submitted_by_info,
            "signatures": signatures,
            "localization": localization,
            "language": localization["language"],
            "generated_at": datetime.now(UTC).isoformat(),
        }

        return payload

    @staticmethod
    def _get_document_title(document_type: DocumentType) -> str:
        """Получить заголовок документа по типу."""
        titles: dict[DocumentType, str] = {
            "waybill": "Товарная накладная",
            "acceptance_certificate": "Акт приёмки",
            "act": "Акт",
            "invoice": "Счёт",
        }
        return titles.get(document_type, "Документ")
