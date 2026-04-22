from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app


OUT_PATH = Path("docs/API_MAP.md")


def load_spec() -> dict[str, Any]:
    return app.openapi()


def ref_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "allOf" in schema:
        names = [ref_name(part) for part in schema["allOf"]]
        names = [name for name in names if name]
        if names:
            return " + ".join(names)
    return schema.get("title")


def schema_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return ref_name(schema) or ""
    if "enum" in schema:
        return "enum"
    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"
    if "allOf" in schema:
        return ref_name(schema) or "allOf"
    if schema.get("type") == "array":
        item = schema.get("items", {})
        item_name = ref_name(item) or item.get("type", "object")
        return f"array[{item_name}]"
    return schema.get("type", "")


def required_fields(schema: dict[str, Any] | None, components: dict[str, Any]) -> list[str]:
    if not schema:
        return []
    if "$ref" in schema:
        resolved = components.get(ref_name(schema) or "", {})
        return required_fields(resolved, components)
    if "allOf" in schema:
        result: list[str] = []
        for part in schema["allOf"]:
            result.extend(required_fields(part, components))
        result.extend(schema.get("required", []))
        return sorted(set(result))
    return sorted(set(schema.get("required", [])))


def example_from_schema(
    schema: dict[str, Any] | None,
    components: dict[str, Any],
    *,
    seen: set[str] | None = None,
    depth: int = 0,
) -> Any:
    if seen is None:
        seen = set()
    if depth > 5:
        return "..."
    if not schema:
        return {}

    if "$ref" in schema:
        name = ref_name(schema)
        if not name:
            return {}
        if name in seen:
            return {"$ref": name}
        resolved = components.get(name, {})
        return example_from_schema(resolved, components, seen=seen | {name}, depth=depth + 1)

    if "allOf" in schema:
        merged: dict[str, Any] = {}
        parts: list[Any] = []
        for part in schema["allOf"]:
            value = example_from_schema(part, components, seen=seen, depth=depth + 1)
            parts.append(value)
        dict_parts = [value for value in parts if isinstance(value, dict)]
        if dict_parts:
            for value in dict_parts:
                merged.update(value)
            return merged
        return parts[0] if parts else {}

    if "oneOf" in schema:
        return example_from_schema(schema["oneOf"][0], components, seen=seen, depth=depth + 1)

    if "anyOf" in schema:
        non_null = [part for part in schema["anyOf"] if part.get("type") != "null"]
        target = non_null[0] if non_null else schema["anyOf"][0]
        return example_from_schema(target, components, seen=seen, depth=depth + 1)

    if "enum" in schema:
        return schema["enum"][0]

    if "example" in schema:
        return schema["example"]

    schema_type_value = schema.get("type")

    if schema_type_value == "object" or "properties" in schema:
        result: dict[str, Any] = {}
        for name, part in schema.get("properties", {}).items():
            result[name] = example_from_schema(part, components, seen=seen, depth=depth + 1)
        additional = schema.get("additionalProperties")
        if not result and isinstance(additional, dict):
            result["key"] = example_from_schema(additional, components, seen=seen, depth=depth + 1)
        return result

    if schema_type_value == "array":
        return [example_from_schema(schema.get("items", {}), components, seen=seen, depth=depth + 1)]

    if schema_type_value == "integer":
        return 0

    if schema_type_value == "number":
        return 0

    if schema_type_value == "boolean":
        return True

    if schema_type_value == "string":
        fmt = schema.get("format")
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "date":
            return "2026-01-01"
        if fmt == "binary":
            return "<binary>"
        return schema.get("title", "string").lower()

    return {}


def json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_parameters(parameters: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    lines.append("**Parameters**")
    lines.append("")
    if not parameters:
        lines.append("_None_")
        lines.append("")
        return lines

    lines.append("| Name | In | Required | Type | Description |")
    lines.append("| --- | --- | --- | --- | --- |")
    for param in parameters:
        param_schema = param.get("schema", {})
        param_type = schema_type(param_schema)
        required = "yes" if param.get("required") else "no"
        description_text = (param.get("description") or "").replace("\n", " ")
        lines.append(
            f"| `{param.get('name', '')}` | `{param.get('in', '')}` | {required} | `{param_type}` | {description_text} |"
        )
    lines.append("")
    return lines


def render_request_body(request_body: dict[str, Any] | None, components: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append("**Request body**")
    lines.append("")
    if not request_body:
        lines.append("_No request body_")
        lines.append("")
        return lines

    required_text = "yes" if request_body.get("required") else "no"
    lines.append(f"- Required: {required_text}")
    content = request_body.get("content", {})
    for media_type, media in content.items():
        schema = media.get("schema", {})
        schema_label = ref_name(schema) or schema_type(schema) or "inline"
        top_required = required_fields(schema, components)
        lines.append(f"- Content-Type: `{media_type}`")
        lines.append(f"- Schema: `{schema_label}`")
        if top_required:
            lines.append(f"- Required top-level fields: `{', '.join(top_required)}`")
        lines.append("")
        lines.append(json_block(example_from_schema(schema, components)))
        lines.append("")
    return lines


def render_responses(responses: dict[str, Any], components: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append("**Expected responses**")
    lines.append("")

    def status_sort_key(value: str) -> tuple[int, int | str]:
        if value.isdigit():
            return (0, int(value))
        return (1, value)

    for status_code in sorted(responses.keys(), key=status_sort_key):
        response = responses[status_code]
        description_text = response.get("description", "")
        lines.append(f"#### {status_code}")
        lines.append("")
        if description_text:
            lines.append(f"- Description: {description_text}")
        content = response.get("content", {})
        if content:
            for media_type, media in content.items():
                schema = media.get("schema", {})
                schema_label = ref_name(schema) or schema_type(schema) or "inline"
                top_required = required_fields(schema, components)
                lines.append(f"- Content-Type: `{media_type}`")
                lines.append(f"- Schema: `{schema_label}`")
                if top_required:
                    lines.append(f"- Required top-level fields: `{', '.join(top_required)}`")
                lines.append("")
                lines.append(json_block(example_from_schema(schema, components)))
                lines.append("")
        else:
            lines.append("_No response body_")
            lines.append("")
    return lines


def build_markdown(spec: dict[str, Any]) -> str:
    components = spec.get("components", {}).get("schemas", {})
    paths = spec.get("paths", {})
    preferred_order = [
        "system",
        "auth",
        "admin",
        "catalog",
        "catalog-admin",
        "operations",
        "balances",
        "asset-register",
        "documents",
        "reports",
        "recipients",
        "sync",
        "health",
        "misc",
    ]
    method_order = {"get": 0, "post": 1, "put": 2, "patch": 3, "delete": 4}

    def group_rank(tag: str) -> int:
        return preferred_order.index(tag) if tag in preferred_order else len(preferred_order) + 1

    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    operations_count = 0

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            method_lower = method.lower()
            if method_lower not in method_order:
                continue
            tag = (operation.get("tags") or [None])[0]
            if not tag:
                tag = "system" if path in ["/", "/db_check"] else "misc"
            grouped[tag].append((path, method_lower, operation))
            operations_count += 1

    lines: list[str] = []
    lines.append("# API MAP")
    lines.append("")
    lines.append(
        f"Generated from FastAPI OpenAPI schema on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}."
    )
    lines.append("")
    lines.append("Source of truth: mounted routers in `main.py` and schemas registered in FastAPI OpenAPI.")
    lines.append("")
    lines.append("## Global notes")
    lines.append("")
    lines.append("- Primary API prefix: `/api/v1`")
    lines.append("- This file includes all OpenAPI-exposed HTTP endpoints, including service-level routes like `/` and `/db_check`.")
    lines.append("- Request and response examples below are schema-shaped examples generated from the OpenAPI contract.")
    lines.append(f"- Total paths: `{len(paths)}`")
    lines.append(f"- Total operations: `{operations_count}`")
    lines.append("")

    for tag in sorted(grouped.keys(), key=lambda value: (group_rank(value), value)):
        title = tag.replace("-", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        for path, method, operation in sorted(grouped[tag], key=lambda item: (item[0], method_order[item[1]])):
            summary = operation.get("summary") or operation.get("operationId") or f"{method.upper()} {path}"
            description = operation.get("description")
            operation_id = operation.get("operationId")
            lines.append(f"### {method.upper()} {path}")
            lines.append("")
            lines.append(f"- Summary: {summary}")
            if operation_id:
                lines.append(f"- Operation ID: `{operation_id}`")
            if description:
                lines.append(f"- Description: {description.strip()}")
            lines.append("")

            lines.extend(render_parameters(operation.get("parameters", [])))
            lines.extend(render_request_body(operation.get("requestBody"), components))
            lines.extend(render_responses(operation.get("responses", {}), components))

            lines.append("---")
            lines.append("")

    lines.append("## Component Schemas")
    lines.append("")
    lines.append("Полные JSON Schema definitions для именованных request/response моделей из OpenAPI.")
    lines.append("")
    for schema_name in sorted(components):
        lines.append(f"### {schema_name}")
        lines.append("")
        lines.append(json_block(components[schema_name]))
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    spec = load_spec()
    content = build_markdown(spec)
    OUT_PATH.write_text(content, encoding="utf-8")
    print(f"Generated {OUT_PATH} with {len(spec.get('paths', {}))} paths.")


if __name__ == "__main__":
    main()
