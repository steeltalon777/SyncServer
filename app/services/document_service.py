from __future__ import annotations

import hashlib
import json
import structlog
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status

from app.repos.sites_repo import SitesRepo
from app.repos.users_repo import UsersRepo
from app.schemas.document import DocumentGenerateRequest, DocumentType
from app.services.uow import UnitOfWork

logger = structlog.get_logger()

# Версия схемы payload для генерации документов.
# 1.1.0 добавляет печатный номер операции и готовые строки для Django PDF renderer.
PAYLOAD_SCHEMA_VERSION = "1.1.0"

# Шаблоны по умолчанию для каждого типа документа
DEFAULT_TEMPLATES: dict[DocumentType, str] = {
    "waybill": "waybill_v1",
    "acceptance_certificate": "acceptance_certificate_v1",
    "act": "act_v1",
    "invoice": "invoice_v1",
}


# rev. 3: расширено до всех операций движения ТМЦ кроме корректировки.
# ADJUSTMENT — служебная операция (Functional §II.5.5: «корректировка - служебная операция
# которая позволит изменить количество или саму ТМЦ»; OPERATIONS_SCREEN_SCENARIOS.md:530,1285-1286:
# «submit корректировки только root/chief»). Используется для transfer balances
# (temporary_items_resolution_service.py), review items (review_items_service.py), merge batches
# (catalog_admin_service.py). Накладной не имеет по определению.
# Все остальные типы получают draft waybill при create и на каждом update; при submit
# draft waybills войдируются (I3.3 в operations_service.py), а финальный
# acceptance_certificate/act создаётся с актуальным payload.
DRAFT_DOCUMENT_TYPE_BY_OPERATION: dict[str, DocumentType] = {
    "MOVE": "waybill",
    "ISSUE": "waybill",
    "ISSUE_RETURN": "waybill",
    "RECEIVE": "waybill",
    "EXPENSE": "waybill",
    "WRITE_OFF": "waybill",
}


def draft_document_type_for_operation(operation_type: str) -> DocumentType | None:
    """Вернуть draft-документ для операции, или None, если draft не нужен."""
    return DRAFT_DOCUMENT_TYPE_BY_OPERATION.get(operation_type)


# TZ-V3.1I rev. 2 (I3.2/I3.5): submit-карта шире draft-карты — содержит
# финальный document_type для всех поддерживаемых типов операций.
SUBMIT_DOCUMENT_TYPE_BY_OPERATION: dict[str, DocumentType] = {
    "RECEIVE": "acceptance_certificate",
    "MOVE": "waybill",
    "ISSUE": "waybill",
    "ISSUE_RETURN": "waybill",
    "EXPENSE": "act",
    "WRITE_OFF": "act",
    "ADJUSTMENT": "act",
}


def submit_document_type_for_operation(operation_type: str) -> DocumentType | None:
    """Вернуть финальный document_type для операции, или None."""
    return SUBMIT_DOCUMENT_TYPE_BY_OPERATION.get(operation_type)


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


def _compute_operation_display_number(site_id: int | None, created_at: datetime | None) -> str | None:
    """Вернуть номер операции в том же формате, что Django BFF/Angular таблица.

    Формат: ``{site_id}/{HHmm}/{ddMMyy}``.
    """
    if site_id is None or created_at is None:
        return None
    return f"{site_id}/{created_at.strftime('%H%M')}/{created_at.strftime('%d%m%y')}"


def _site_fallback(site_id: int | None) -> str:
    return f"Склад #{site_id}" if site_id else "Склад"


def _site_name(site: Any | None, fallback_site_id: int | None = None) -> str:
    if site is not None:
        return str(getattr(site, "name", None) or getattr(site, "code", None) or _site_fallback(getattr(site, "id", fallback_site_id)))
    return _site_fallback(fallback_site_id)


def _issue_object_name(operation: Any) -> str:
    return str(operation.issue_object_name_snapshot or (f"Объект выдачи #{operation.issue_object_id}" if operation.issue_object_id else "Объект выдачи"))


def _operation_type_label(operation_type: str | None) -> str:
    labels = {
        "MOVE": "Перемещение",
        "RECEIVE": "Приход",
        "ISSUE": "Выдача",
        "ISSUE_RETURN": "Возврат выдачи",
        "WRITE_OFF": "Списание",
        "EXPENSE": "Расход",
        "ADJUSTMENT": "Корректировка",
        "CORRECTION": "Корректировка",
    }
    return labels.get(str(operation_type or "").upper(), str(operation_type or "Операция"))


def _build_basis_label(operation: Any, site: Any, source_site: Any | None, destination_site: Any | None) -> str:
    """Собрать deterministic `Основание` для печатной накладной."""
    operation_type = str(operation.operation_type or "").upper()
    site_label = _site_name(site, operation.site_id)
    source_label = (
        _site_name(source_site, operation.source_site_id)
        if source_site is not None or operation.source_site_id
        else site_label
    )
    destination_label = (
        _site_name(destination_site, operation.destination_site_id)
        if destination_site is not None or operation.destination_site_id
        else site_label
    )
    issue_object_label = _issue_object_name(operation)

    if operation_type == "MOVE":
        return f"Перемещение {source_label} → {destination_label}"
    if operation_type == "RECEIVE":
        return f"Приход на склад {destination_label or site_label}"
    if operation_type == "ISSUE":
        return f"Выдача {source_label or site_label} → {issue_object_label}"
    if operation_type == "ISSUE_RETURN":
        return f"Возврат выдачи {issue_object_label} → {destination_label or site_label}"
    if operation_type == "WRITE_OFF":
        return f"Списание {source_label or site_label}"
    if operation_type == "EXPENSE":
        return f"Расход {source_label or site_label}"
    if operation_type in {"ADJUSTMENT", "CORRECTION"}:
        return f"Корректировка {site_label}"
    return f"{_operation_type_label(operation_type)} {site_label}"


def _build_consignee_label(operation: Any, site: Any, destination_site: Any | None) -> str:
    """Получатель для шапки накладной без персональных подписантов."""
    operation_type = str(operation.operation_type or "").upper()
    if operation_type in {"ISSUE", "ISSUE_RETURN"} and (operation.issue_object_name_snapshot or operation.issue_object_id):
        return _issue_object_name(operation)
    if destination_site is not None:
        return _site_name(destination_site, operation.destination_site_id)
    return _site_name(site, operation.site_id)


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

        # Для MOVE и печатного основания получаем source/destination site, если они заданы.
        source_site = site
        if operation.source_site_id and operation.source_site_id != operation.site_id:
            source_site = await uow.sites.get_by_id(operation.source_site_id)

        destination_site = None
        if operation.destination_site_id:
            destination_site = await uow.sites.get_by_id(operation.destination_site_id)

        # 3. Получаем пользователя-создателя
        created_by_user = None
        if operation.created_by_user_id:
            created_by_user = await uow.users.get_by_id(operation.created_by_user_id)

        # 4. Получаем пользователя, который submit'ил операцию
        submitted_by_user = None
        if operation.submitted_by_user_id:
            submitted_by_user = await uow.users.get_by_id(operation.submitted_by_user_id)

        # 5. Определяем шаблон
        effective_template = template_name or DEFAULT_TEMPLATES.get(document_type, "default_v1")

        # 6. Для черновиков — всегда создаём новый документ (войдируем старый).
        #    Для проведённых — сохраняем идемпотентность.
        if operation.status == "draft":
            await DocumentService._void_existing_documents(
                uow=uow,
                operation_id=operation_id,
                document_type=document_type,
                template_name=effective_template,
            )
            # Документы черновика всегда draft, независимо от auto_finalize.
            effective_auto_finalize = False
        else:
            existing_document = await DocumentService._find_reusable_document(
                uow=uow,
                operation_id=operation_id,
                document_type=document_type,
                template_name=effective_template,
                auto_finalize=auto_finalize,
            )
            if existing_document is not None:
                logger.info(
                    "reused_document",
                    document_id=existing_document.id,
                    document_type=document_type,
                    operation_id=str(operation_id),
                    status=existing_document.status,
                )
                return {
                    "document": existing_document,
                    "operation": operation,
                    "created": False,
                }
            effective_auto_finalize = auto_finalize

        # 7. Формируем payload
        payload = DocumentService._build_payload(
            operation=operation,
            site=site,
            source_site=source_site,
            destination_site=destination_site,
            created_by_user=created_by_user,
            submitted_by_user=submitted_by_user,
            document_type=document_type,
            language=language,
            basis_type=basis_type,
            basis_number=basis_number,
            basis_date=basis_date,
        )

        # 8. Генерируем технический номер документа
        document_number = _generate_document_number(document_type, operation.site_id)

        # 9. Вычисляем хэш payload
        payload_hash = _compute_payload_hash(payload)

        # 10. Определяем статус
        status_value = "finalized" if effective_auto_finalize else "draft"
        now = datetime.now(UTC) if effective_auto_finalize else None

        # 11. Создаём документ
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

        # 12. Линкуем документ к операции
        await uow.documents.link_document_to_operation(document.id, operation_id)

        logger.info(
            "generated_document",
            document_id=document.id,
            document_type=document_type,
            operation_id=str(operation_id),
            status=status_value,
        )

        return {
            "document": document,
            "operation": operation,
            "created": True,
        }

    @staticmethod
    async def _find_reusable_document(
        uow: UnitOfWork,
        operation_id: UUID,
        document_type: DocumentType,
        template_name: str,
        auto_finalize: bool,
    ):
        """Найти уже созданный документ текущей схемы для идемпотентной генерации."""
        documents = await uow.documents.get_documents_by_operation(operation_id, document_type=document_type)
        reusable = None
        for document in documents:
            if document.status in {"void", "superseded"}:
                continue
            if document.template_name != template_name:
                continue
            if document.payload_schema_version != PAYLOAD_SCHEMA_VERSION:
                continue
            reusable = document
            break

        if reusable is None:
            return None

        if auto_finalize and reusable.status == "draft":
            updated = await uow.documents.update_document_status(reusable.id, "finalized")
            if updated:
                refreshed = await uow.documents.get_document_by_id(reusable.id)
                return refreshed or reusable
        return reusable

    @staticmethod
    async def _void_existing_documents(
        uow: UnitOfWork,
        operation_id: UUID,
        document_type: DocumentType,
        template_name: str,
    ) -> None:
        """Войдировать все не-void документы операции (для пересоздания черновика)."""
        documents = await uow.documents.get_documents_by_operation(operation_id, document_type=document_type)
        for doc in documents:
            if doc.status in ("void", "superseded"):
                continue
            if doc.template_name != template_name:
                continue
            await uow.documents.update_document_status(doc.id, "void")
            logger.info(
                "voided_document",
                document_id=doc.id,
                document_type=document_type,
                operation_id=str(operation_id),
            )

    @staticmethod
    def _build_payload(
        operation,
        site,
        source_site=None,
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

        operation_display_number = _compute_operation_display_number(operation.site_id, operation.created_at)

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

        source_site_info = sender_info
        if source_site and getattr(source_site, "id", None) != site.id:
            source_site_info = {
                "site_id": source_site.id,
                "site_code": source_site.code,
                "site_name": source_site.name,
                "description": source_site.description,
                "organization": {
                    "legal_name": source_site.name,
                    "address": source_site.description,
                    "tax_id": None,
                    "contacts": None,
                },
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
        if operation.issue_object_id or operation.issue_object_name_snapshot:
            recipient_info = {
                "recipient_id": operation.issue_object_id,
                "recipient_name": operation.issue_object_name_snapshot,
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
        basis_label = _build_basis_label(operation, site, source_site, destination_site)
        consignee_label = _build_consignee_label(operation, site, destination_site)
        operation_type_label = _operation_type_label(operation.operation_type)
        basis = {
            "type": basis_type,
            "number": basis_number,
            "date": basis_date.isoformat() if basis_date else None,
            "label": basis_label,
            "operation_type_label": operation_type_label,
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
            "operation_display_number": operation_display_number,
            "basis_label": basis_label,
            "consignee_label": consignee_label,
            "operation_id": str(operation.id),
            "operation_type": operation.operation_type,
            "operation_type_label": operation_type_label,
            "operation_status": operation.status,
            "operation_notes": operation.notes,
            "operation_created_at": operation.created_at.isoformat() if operation.created_at else None,
            "operation_submitted_at": operation.submitted_at.isoformat() if operation.submitted_at else None,
            "operation_effective_at": operation.effective_at.isoformat() if operation.effective_at else None,
            "operation_acceptance_state": operation.acceptance_state,
            "operation": {
                "id": str(operation.id),
                "display_number": operation_display_number,
                "type": operation.operation_type,
                "type_label": operation_type_label,
                "status": operation.status,
                "site_id": operation.site_id,
                "source_site_id": operation.source_site_id,
                "destination_site_id": operation.destination_site_id,
                "issue_object_id": operation.issue_object_id,
                "issue_object_name": operation.issue_object_name_snapshot,
                "created_at": operation.created_at.isoformat() if operation.created_at else None,
                "submitted_at": operation.submitted_at.isoformat() if operation.submitted_at else None,
                "effective_at": operation.effective_at.isoformat() if operation.effective_at else None,
            },
            "sender": sender_info,
            "source_site": source_site_info,
            "destination_site": receiver_info,
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
