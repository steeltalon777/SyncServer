from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any, Literal

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

        pdf = cls._html_to_pdf(html)
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

