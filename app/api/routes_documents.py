from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response

from app.api.deps import get_request_id, get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.document import (
    DocumentFilter,
    DocumentGenerateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentType,
    DocumentUpdate,
)
from app.services.document_service import DocumentService
from app.services.document_renderer import DocumentRenderer
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/documents")
logger = logging.getLogger(__name__)

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}


def _require_read_site(identity: Identity, site_id: int) -> None:
    """Проверить права на чтение документов площадки."""
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="read documents permission required",
        )
    if not identity.has_site_access(site_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user has no view access to site",
        )


def _require_operate_site(identity: Identity, site_id: int) -> None:
    """Проверить права на операции с документами площадки."""
    if identity.has_global_business_access:
        return
    if identity.role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="operate documents permission required",
        )
    if not identity.can_operate_at_site(site_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user has no operate access to site",
        )


@router.post("/generate", response_model=dict[str, object])
async def generate_document(
    request: Request,
    data: DocumentGenerateRequest,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> dict[str, object]:
    """Сгенерировать документ на основе операции."""
    # Получаем операцию для проверки прав доступа
    operation = await uow.operations.get_operation_by_id(data.operation_id)
    if not operation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"operation with id {data.operation_id} not found",
        )
    
    # Проверяем права на площадку операции
    _require_operate_site(identity, operation.site_id)
    
    # Генерируем документ
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=data.operation_id,
        document_type=data.document_type,
        template_name=data.template_name,
        auto_finalize=data.auto_finalize,
        created_by_user_id=identity.user_id,
        language=data.language,
        basis_type=data.basis_type,
        basis_number=data.basis_number,
        basis_date=data.basis_date,
    )
    
    logger.info(
        "Generated document id=%s for operation id=%s by user id=%s",
        result["document"].id,
        data.operation_id,
        identity.user_id,
    )
    
    return {
        "document": DocumentResponse.model_validate(result["document"]),
        "operation_id": str(data.operation_id),
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    request: Request,
    document_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DocumentResponse:
    """Получить документ по ID."""
    document = await uow.documents.get_document_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"document with id {document_id} not found",
        )
    
    # Проверяем права на площадку документа
    _require_read_site(identity, document.site_id)
    
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/render")
async def render_document(
    request: Request,
    document_id: UUID,
    format: str = Query("html", pattern="^(html|pdf)$"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> Response:
    """Рендеринг документа в HTML или PDF."""
    document = await uow.documents.get_document_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"document with id {document_id} not found",
        )

    _require_read_site(identity, document.site_id)

    if format == "html":
        html = DocumentRenderer.render_html(
            document_id=str(document.id),
            document_number=document.document_number,
            template_name=document.template_name,
            payload=document.payload,
        )
        return HTMLResponse(content=html)

    try:
        pdf_bytes = DocumentRenderer.render_pdf(
            document_id=str(document.id),
            document_number=document.document_number,
            template_name=document.template_name,
            payload=document.payload,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="document_{document.id}.pdf"',
        },
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    site_id: int | None = Query(None, description="Фильтр по площадке"),
    document_type: DocumentType | None = Query(None, description="Тип документа"),
    status: DocumentStatus | None = Query(None, description="Статус документа"),
    created_by_user_id: UUID | None = Query(None, description="ID создателя"),
    date_from: datetime | None = Query(None, description="Дата создания от"),
    date_to: datetime | None = Query(None, description="Дата создания до"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(100, ge=1, le=1000, description="Лимит для пагинации"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DocumentListResponse:
    """Получить список документов с фильтрацией."""
    # Если указана площадка, проверяем права на неё
    if site_id is not None:
        _require_read_site(identity, site_id)
    elif not identity.has_global_business_access:
        # Если площадка не указана и нет глобальных прав, возвращаем только доступные площадки
        # Для упрощения возвращаем пустой список - в реальности нужно получить доступные площадки
        return DocumentListResponse(items=[], total=0, offset=offset, limit=limit)
    
    # Создаём фильтр
    filter_obj = DocumentFilter(
        site_id=site_id,
        document_type=document_type,
        status=status,
        created_by_user_id=created_by_user_id,
        date_from=date_from,
        date_to=date_to,
    )
    
    # Получаем документы
    documents, total = await uow.documents.list_documents(
        filter_obj=filter_obj,
        offset=offset,
        limit=limit,
    )
    
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/{document_id}/status", response_model=DocumentResponse)
async def update_document_status(
    request: Request,
    document_id: UUID,
    update_data: DocumentUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DocumentResponse:
    """Обновить статус документа (финализация, аннулирование и т.д.)."""
    document = await uow.documents.get_document_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"document with id {document_id} not found",
        )
    
    # Проверяем права на площадку документа
    _require_operate_site(identity, document.site_id)
    
    # Проверяем допустимость изменения статуса
    if update_data.status:
        if document.status == "finalized" and update_data.status != "void":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot change status of finalized document",
            )
        
        if update_data.status == "finalized" and document.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="can only finalize draft documents",
            )
    
    # Обновляем документ
    updated = await uow.documents.update_document(
        document_id=document_id,
        status=update_data.status,
        finalized_at=update_data.finalized_at,
        payload=update_data.payload,
        payload_hash=update_data.payload_hash,
    )
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to update document",
        )
    
    logger.info(
        "Updated document id=%s status=%s by user id=%s",
        document_id,
        update_data.status,
        identity.user_id,
    )
    
    return DocumentResponse.model_validate(updated)


@router.get("/operations/{operation_id}/documents", response_model=list[DocumentResponse])
async def get_documents_by_operation(
    request: Request,
    operation_id: UUID,
    document_type: DocumentType | None = Query(None, description="Фильтр по типу документа"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> list[DocumentResponse]:
    """Получить список документов по операции."""
    operation = await uow.operations.get_operation_by_id(operation_id)
    if not operation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"operation with id {operation_id} not found",
        )
    
    # Проверяем права на площадку операции
    _require_read_site(identity, operation.site_id)
    
    # Получаем документы
    documents = await uow.documents.get_documents_by_operation(
        operation_id=operation_id,
        document_type=document_type,
    )
    
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.post("/operations/{operation_id}/documents", response_model=dict[str, object])
async def generate_document_for_operation(
    request: Request,
    operation_id: UUID,
    document_type: DocumentType = Query("waybill", description="Тип документа"),
    template_name: str | None = Query(None, description="Имя шаблона"),
    auto_finalize: bool = Query(False, description="Автоматически финализировать"),
    language: str = Query("ru", description="Язык документа (ru/en)"),
    basis_type: str | None = Query(None, description="Тип основания документа"),
    basis_number: str | None = Query(None, description="Номер основания документа"),
    basis_date: datetime | None = Query(None, description="Дата основания документа"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> dict[str, object]:
    """Удобный shortcut для генерации документа определённого типа по операции."""
    # Проверяем существование операции и права
    operation = await uow.operations.get_operation_by_id(operation_id)
    if not operation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"operation with id {operation_id} not found",
        )
    
    _require_operate_site(identity, operation.site_id)
    
    # Генерируем документ
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation_id,
        document_type=document_type,
        template_name=template_name,
        auto_finalize=auto_finalize,
        created_by_user_id=identity.user_id,
        language=language,
        basis_type=basis_type,
        basis_number=basis_number,
        basis_date=basis_date,
    )
    
    logger.info(
        "Generated document id=%s for operation id=%s via shortcut by user id=%s",
        result["document"].id,
        operation_id,
        identity.user_id,
    )
    
    return {
        "document": DocumentResponse.model_validate(result["document"]),
        "operation_id": str(operation_id),
        "generated_at": datetime.now().isoformat(),
    }
