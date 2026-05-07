from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from xml.sax.saxutils import escape

# Опциональные зависимости для рендеринга
try:  # pragma: no cover
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:  # pragma: no cover
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    select_autoescape = None  # type: ignore[assignment]

try:  # pragma: no cover
    from weasyprint import HTML as WeasyHTML
except Exception:  # pragma: no cover
    WeasyHTML = None  # type: ignore[assignment]

try:  # pragma: no cover
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except Exception:  # pragma: no cover
    colors = None  # type: ignore[assignment]
    A4 = None  # type: ignore[assignment]
    ParagraphStyle = None  # type: ignore[assignment]
    getSampleStyleSheet = None  # type: ignore[assignment]
    mm = None  # type: ignore[assignment]
    pdfmetrics = None  # type: ignore[assignment]
    TTFont = None  # type: ignore[assignment]
    Paragraph = None  # type: ignore[assignment]
    SimpleDocTemplate = None  # type: ignore[assignment]
    Spacer = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    TableStyle = None  # type: ignore[assignment]


class DocumentRenderer:
    """Рендерер документов в HTML/PDF с короткоживущим in-memory кэшем."""

    _cache: dict[str, tuple[float, bytes | str]] = {}
    _cache_lock = Lock()
    _cache_ttl_seconds = 120

    @classmethod
    def render_html(
        cls,
        *,
        document_id: str,
        document_number: str | None,
        template_name: str | None,
        payload: dict[str, Any],
    ) -> str:
        cache_key = cls._cache_key(document_id=document_id, output_format="html")
        cached = cls._cache_get(cache_key)
        if isinstance(cached, str):
            return cached

        html = cls._render_html_internal(
            document_id=document_id,
            document_number=document_number,
            template_name=template_name,
            payload=payload,
        )
        cls._cache_set(cache_key, html)
        return html

    @classmethod
    def render_pdf(
        cls,
        *,
        document_id: str,
        document_number: str | None,
        template_name: str | None,
        payload: dict[str, Any],
    ) -> bytes:
        cache_key = cls._cache_key(document_id=document_id, output_format="pdf")
        cached = cls._cache_get(cache_key)
        if isinstance(cached, bytes):
            return cached

        html = cls.render_html(
            document_id=document_id,
            document_number=document_number,
            template_name=template_name,
            payload=payload,
        )

        try:
            pdf = cls._html_to_pdf(html)
        except RuntimeError:
            pdf = cls._payload_to_pdf(
                document_id=document_id,
                document_number=document_number,
                payload=payload,
            )
        cls._cache_set(cache_key, pdf)
        return pdf

    @classmethod
    def _render_html_internal(
        cls,
        *,
        document_id: str,
        document_number: str | None,
        template_name: str | None,
        payload: dict[str, Any],
    ) -> str:
        template_path = cls._resolve_template_path(template_name)
        if template_path is None:
            return cls._fallback_html(document_number=document_number, payload=payload)

        if Environment is None or FileSystemLoader is None or select_autoescape is None:
            return cls._fallback_html(document_number=document_number, payload=payload)

        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        env.filters["number_format"] = cls._number_format
        env.filters["datetime_format"] = cls._datetime_format

        template = env.get_template(template_path.name)
        document_ctx = {
            "id": document_id,
            "document_number": document_number,
            "template_name": template_name,
            "template_version": "1.0",
            "payload_schema_version": payload.get("payload_schema_version", "1.0.0"),
        }
        return template.render(payload=payload, document=document_ctx)

    @staticmethod
    def _resolve_template_path(template_name: str | None) -> Path | None:
        templates_root = Path("templates") / "documents"
        if not templates_root.exists():
            return None

        if template_name:
            normalized = template_name.replace("_v1", "")
            candidate = templates_root / f"{normalized}.html"
            if candidate.exists():
                return candidate

        default_candidate = templates_root / "waybill.html"
        if default_candidate.exists():
            return default_candidate
        return None

    @staticmethod
    def _number_format(value: Any, digits: int = 2) -> str:
        try:
            return f"{float(value):,.{digits}f}".replace(",", " ")
        except Exception:
            return str(value)

    @staticmethod
    def _datetime_format(value: Any, fmt: str = "%d.%m.%Y") -> str:
        from datetime import datetime

        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return value
        if isinstance(value, datetime):
            return value.strftime(fmt)
        return str(value)

    @staticmethod
    def _fallback_html(*, document_number: str | None, payload: dict[str, Any]) -> str:
        lines = payload.get("lines") or []
        rows = "".join(
            f"<tr><td>{line.get('line_number')}</td><td>{line.get('item_name', '')}</td><td>{line.get('quantity', '')}</td><td>{line.get('unit_symbol', '')}</td></tr>"
            for line in lines
        )
        return (
            "<html><head><meta charset='utf-8'><title>Document</title></head><body>"
            f"<h1>{payload.get('document_title', 'Документ')}</h1>"
            f"<p>№ {document_number or ''}</p>"
            f"<p>Операция: {payload.get('operation_id', '')}</p>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>#</th><th>Наименование</th><th>Количество</th><th>Ед.</th></tr>"
            f"{rows}</table>"
            "</body></html>"
        )

    @staticmethod
    def _html_to_pdf(html: str) -> bytes:
        if WeasyHTML is None:  # pragma: no cover
            raise RuntimeError("PDF rendering backend is unavailable")

        return WeasyHTML(string=html).write_pdf()

    @classmethod
    def _payload_to_pdf(
        cls,
        *,
        document_id: str,
        document_number: str | None,
        payload: dict[str, Any],
    ) -> bytes:
        if (
            SimpleDocTemplate is None
            or Table is None
            or TableStyle is None
            or Paragraph is None
            or Spacer is None
            or getSampleStyleSheet is None
            or ParagraphStyle is None
            or colors is None
            or A4 is None
            or mm is None
        ):
            raise RuntimeError("PDF rendering backend is unavailable")

        font_name = cls._register_pdf_font()
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="WarehouseTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=16,
            leading=20,
            spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            name="WarehouseNormal",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=12,
        ))
        styles.add(ParagraphStyle(
            name="WarehouseSmall",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#666666"),
        ))

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )

        story: list[Any] = [
            Paragraph(
                cls._pdf_text(
                    payload.get("organization", {}).get("full_name")
                    or payload.get("organization", {}).get("legal_name")
                ),
                styles["WarehouseNormal"],
            ),
            Paragraph(
                cls._pdf_text(payload.get("document_heading") or payload.get("document_title")),
                styles["WarehouseTitle"],
            ),
            Paragraph(
                cls._pdf_text(
                    f"№ {document_number or ''} от {cls._datetime_format(payload.get('generated_at'))}"
                ),
                styles["WarehouseNormal"],
            ),
            Spacer(1, 6 * mm),
        ]

        details = [
            ["Тип операции", payload.get("operation_type_label")],
            ["Склад отправки", payload.get("source_label")],
            ["Склад назначения / принимающее лицо", payload.get("destination_label")],
            ["Кладовщик, который выдал", payload.get("warehouse_keeper")],
            ["Операция", f"ID: {payload.get('operation_id')}\nДата: {cls._datetime_format(payload.get('operation_effective_at'))}"],
        ]
        if payload.get("operation_notes"):
            details.append(["Комментарий", payload.get("operation_notes")])
        story.append(cls._pdf_table(details, styles["WarehouseNormal"], col_widths=[52 * mm, 124 * mm]))
        story.append(Spacer(1, 7 * mm))

        is_acceptance = payload.get("document_title") == "Акт приёмки"
        header = ["№", "Позиция", "Артикул", "Количество", "Ед."]
        if is_acceptance:
            header = ["№", "Позиция", "По накладной", "Принято", "Утеряно", "Ед."]

        rows = [header]
        for line in payload.get("lines") or []:
            if is_acceptance:
                rows.append([
                    line.get("line_number"),
                    line.get("item_name"),
                    cls._number_format(line.get("quantity"), 3),
                    cls._number_format(line.get("accepted_qty") or 0, 3),
                    cls._number_format(line.get("lost_qty") or 0, 3),
                    line.get("unit_symbol") or line.get("unit_name"),
                ])
            else:
                rows.append([
                    line.get("line_number"),
                    line.get("item_name"),
                    line.get("item_sku"),
                    cls._number_format(line.get("quantity"), 3),
                    line.get("unit_symbol") or line.get("unit_name"),
                ])

        story.append(cls._pdf_table(rows, styles["WarehouseNormal"]))
        story.extend([
            Spacer(1, 16 * mm),
            cls._pdf_table(
                [
                    ["Выдал", "Принял"],
                    [payload.get("warehouse_keeper") or "", ""],
                ],
                styles["WarehouseNormal"],
                col_widths=[88 * mm, 88 * mm],
            ),
            Spacer(1, 8 * mm),
            Paragraph(cls._pdf_text(f"Документ сформирован системой SyncServer. ID документа: {document_id}"), styles["WarehouseSmall"]),
        ])

        doc.build(story)
        return buffer.getvalue()

    @staticmethod
    def _register_pdf_font() -> str:
        if pdfmetrics is None or TTFont is None:
            return "Helvetica"

        font_candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/ARIAL.TTF"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/local/share/fonts/dejavu/DejaVuSans.ttf"),
        ]
        for font_path in font_candidates:
            if not font_path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont("WarehousePdfFont", str(font_path)))
                return "WarehousePdfFont"
            except Exception:
                continue
        return "Helvetica"

    @classmethod
    def _pdf_table(
        cls,
        rows: list[list[Any]],
        style,
        *,
        col_widths: list[Any] | None = None,
    ):
        table_rows = [
            [Paragraph(cls._pdf_text(cell).replace("\n", "<br/>"), style) for cell in row]
            for row in rows
        ]
        table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), style.fontName),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    @staticmethod
    def _pdf_text(value: Any) -> str:
        if value is None:
            return ""
        return escape(str(value))

    @classmethod
    def _cache_key(
        cls,
        *,
        document_id: str,
        output_format: Literal["html", "pdf"],
    ) -> str:
        return f"{document_id}:{output_format}"

    @classmethod
    def _cache_get(cls, key: str) -> bytes | str | None:
        now = time.time()
        with cls._cache_lock:
            value = cls._cache.get(key)
            if not value:
                return None
            expires_at, payload = value
            if expires_at <= now:
                cls._cache.pop(key, None)
                return None
            return payload

    @classmethod
    def _cache_set(cls, key: str, payload: bytes | str) -> None:
        with cls._cache_lock:
            cls._cache[key] = (time.time() + cls._cache_ttl_seconds, payload)

