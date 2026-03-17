#!/usr/bin/env python3
"""
build_repo_map.py

Generate an AI-friendly repository snapshot from the project root.

Usage:
    python build_repo_map.py
    python build_repo_map.py --root .
    python build_repo_map.py --output repo_map.txt
    python build_repo_map.py --max-file-lines 40
    python build_repo_map.py --include-hidden

What it does:
- Builds a filtered directory tree
- Detects likely entry points
- Extracts HTTP routes from FastAPI/Django-style route files
- Lists models, repos, services, schemas
- Reads env vars from .env.example / .env
- Produces one text file: repo_map.txt

Safe defaults:
- Hides noisy folders like .git, .idea, .venv, node_modules, __pycache__
- Does not dump source code bodies into the report
- Does not include .env by default unless you pass --include-dotenv
"""

from __future__ import annotations

import argparse
import ast
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".coverage",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".cache",
    ".DS_Store",
}

DEFAULT_EXCLUDE_FILES = {
    ".env",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "repo_map.txt",
}

READ_FIRST_CANDIDATES = [
    "README.md",
    "INDEX.md",
    "AI_CONTEXT.md",
    "AI_ENTRY_POINTS.md",
    "ARCHITECTURE.md",
    "SYSTEM_MAP.md",
    "DOMAIN_MODEL.md",
    "API_CONTRACT.md",
    "USE_CASES.md",
    "MEMORY.md",
    "main.py",
]

ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AI-friendly repo map")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--output", default="repo_map.txt", help="Output text file")
    parser.add_argument(
        "--max-file-lines",
        type=int,
        default=60,
        help="Reserved for future use; kept for compatibility",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files/directories except explicitly excluded ones",
    )
    parser.add_argument(
        "--include-dotenv",
        action="store_true",
        help="Also parse .env variables (off by default for safety)",
    )
    parser.add_argument(
        "--max-tree-entries",
        type=int,
        default=3000,
        help="Safety cap for number of tree lines",
    )
    return parser.parse_args()


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in {".", ".."})


def should_skip(path: Path, root: Path, include_hidden: bool) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)

    if any(part in DEFAULT_EXCLUDE_DIRS for part in parts):
        return True

    if path.name in DEFAULT_EXCLUDE_FILES:
        return True

    if not include_hidden and is_hidden(rel):
        return True

    return False


def iter_paths(root: Path, include_hidden: bool) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        filtered_dirs = []
        for d in dirnames:
            candidate = current / d
            if not should_skip(candidate, root, include_hidden):
                filtered_dirs.append(d)
        dirnames[:] = sorted(filtered_dirs)

        for filename in sorted(filenames):
            candidate = current / filename
            if should_skip(candidate, root, include_hidden):
                continue
            yield candidate


def build_tree(root: Path, include_hidden: bool, max_entries: int) -> list[str]:
    lines: list[str] = []

    def walk(directory: Path, prefix: str = "") -> None:
        nonlocal lines
        if len(lines) >= max_entries:
            return

        children = []
        for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if should_skip(child, root, include_hidden):
                continue
            children.append(child)

        for idx, child in enumerate(children):
            if len(lines) >= max_entries:
                return
            connector = "└── " if idx == len(children) - 1 else "├── "
            rel = child.relative_to(root)
            lines.append(f"{prefix}{connector}{rel.as_posix()}")
            if child.is_dir():
                extension = "    " if idx == len(children) - 1 else "│   "
                walk(child, prefix + extension)

    walk(root)
    return lines


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except Exception:
            return ""
    except Exception:
        return ""


def detect_project_type(root: Path) -> list[str]:
    hints: list[str] = []

    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        hints.append("Python")
    if (root / "main.py").exists():
        hints.append("App entry via main.py")
    if (root / "manage.py").exists():
        hints.append("Django")
    if any((root / "app" / "api").glob("routes*.py")):
        hints.append("FastAPI-style routes")
    if (root / "docker-compose.yml").exists() or (root / "Dockerfile").exists():
        hints.append("Docker")
    if (root / "tests").exists():
        hints.append("Tests")

    return hints


def detect_entry_points(root: Path) -> list[str]:
    entries: list[str] = []

    for candidate in [
        root / "main.py",
        root / "manage.py",
        root / "app" / "__init__.py",
    ]:
        if candidate.exists():
            entries.append(candidate.relative_to(root).as_posix())

    for folder_name in ["scripts", "tools"]:
        folder = root / folder_name
        if folder.exists():
            for path in sorted(folder.glob("*.py")):
                entries.append(path.relative_to(root).as_posix())

    api_dir = root / "app" / "api"
    if api_dir.exists():
        for path in sorted(api_dir.glob("routes*.py")):
            entries.append(path.relative_to(root).as_posix())

    seen = set()
    unique = []
    for item in entries:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def summarize_path(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    name = Path(p).name

    if "/api/" in p and name.startswith("routes"):
        return "HTTP routes / API handlers"
    if "/services/" in p:
        return "Business logic / orchestration"
    if "/repos/" in p:
        return "Data access / repository layer"
    if "/models/" in p:
        return "ORM or domain model"
    if "/schemas/" in p:
        return "Pydantic / DTO schemas"
    if "/core/" in p:
        return "Core config / infrastructure"
    if p.startswith("tests/"):
        return "Tests"
    if p.startswith("docs/adr/"):
        return "Architecture decision record"
    if p.startswith("docs/"):
        return "Project documentation"
    if p.startswith("db/"):
        return "Database schema / bootstrap"
    if p.endswith(".sql"):
        return "SQL schema or migration"
    if name == "README.md":
        return "Project overview"
    if name.startswith("AI_") or name in {
        "ARCHITECTURE.md",
        "SYSTEM_MAP.md",
        "DOMAIN_MODEL.md",
        "API_CONTRACT.md",
        "USE_CASES.md",
        "INDEX.md",
        "MEMORY.md",
        "PROJECT_BRAIN.md",
    }:
        return "AI/project guidance document"
    return "Project file"


def collect_module_map(root: Path) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)

    for path in iter_paths(root, include_hidden=False):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            continue

        if rel.startswith("app/api/"):
            groups["API"].append(rel)
        elif rel.startswith("app/services/"):
            groups["Services"].append(rel)
        elif rel.startswith("app/repos/"):
            groups["Repositories"].append(rel)
        elif rel.startswith("app/models/"):
            groups["Models"].append(rel)
        elif rel.startswith("app/schemas/"):
            groups["Schemas"].append(rel)
        elif rel.startswith("app/core/"):
            groups["Core"].append(rel)
        elif rel.startswith("db/"):
            groups["Database"].append(rel)
        elif rel.startswith("docs/"):
            groups["Docs"].append(rel)
        elif rel.startswith("tests/"):
            groups["Tests"].append(rel)
        elif rel.endswith(".py"):
            groups["Python files"].append(rel)

    return dict(groups)


def parse_python_routes(file_path: Path, root: Path) -> list[dict[str, str]]:
    text = read_text_safe(file_path)
    if not text.strip():
        return []

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    router_prefixes: dict[str, str] = {}

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            try:
                if isinstance(node.value, ast.Call):
                    func = node.value.func
                    if isinstance(func, ast.Name) and func.id == "APIRouter":
                        prefix = ""
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                prefix = str(kw.value.value)
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                router_prefixes[target.id] = prefix
            except Exception:
                pass
            self.generic_visit(node)

    Visitor().visit(tree)

    routes: list[dict[str, str]] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            func = decorator.func
            router_name = None
            method_name = None

            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                router_name = func.value.id
                method_name = func.attr.lower()

            if router_name is None or method_name not in ROUTE_DECORATORS:
                continue

            path_value = ""
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path_value = str(decorator.args[0].value)

            full_path = f"{router_prefixes.get(router_name, '')}{path_value}" or "/"
            routes.append(
                {
                    "method": method_name.upper(),
                    "path": full_path,
                    "handler": node.name,
                    "file": file_path.relative_to(root).as_posix(),
                }
            )

    return routes


def collect_api_map(root: Path) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    for path in root.rglob("*.py"):
        if should_skip(path, root, include_hidden=False):
            continue
        rel = path.relative_to(root).as_posix()
        if "/api/" in rel or Path(rel).name.startswith("routes"):
            routes.extend(parse_python_routes(path, root))

    routes.sort(key=lambda x: (x["path"], x["method"], x["handler"]))
    return routes


def parse_env_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []

    rows: list[tuple[str, str]] = []
    for raw_line in read_text_safe(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            continue

        preview = "<set>" if value else "<empty>"
        rows.append((key, preview))

    return rows


def collect_env_map(root: Path, include_dotenv: bool) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []

    for candidate in [root / ".env.example", root / ".env"]:
        if candidate.name == ".env" and not include_dotenv:
            continue
        for key, preview in parse_env_file(candidate):
            result.append((key, candidate.name, preview))

    config_py = root / "app" / "core" / "config.py"
    if config_py.exists():
        text = read_text_safe(config_py)
        found = sorted(set(re.findall(r'\b([A-Z][A-Z0-9_]{2,})\b', text)))
        for key in found:
            if key in {"API", "HTTP", "UUID", "SQL", "ORM"}:
                continue
            result.append((key, "app/core/config.py", "referenced"))

    dedup: dict[str, tuple[str, str, str]] = {}
    for key, source, preview in result:
        dedup[key] = (key, source, preview)

    return sorted(dedup.values(), key=lambda x: x[0])


def collect_domain_entities(root: Path) -> list[str]:
    models_dir = root / "app" / "models"
    entities: list[str] = []
    if not models_dir.exists():
        return entities

    for path in sorted(models_dir.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        entities.append(path.stem)
    return entities


def collect_read_first(root: Path) -> list[str]:
    result = []
    for name in READ_FIRST_CANDIDATES:
        path = root / name
        if path.exists():
            result.append(name)

    for fallback in [
        "app/api/routes_admin.py",
        "app/api/routes_sync.py",
        "app/services/access_service.py",
        "app/services/uow.py",
        "app/models/user.py",
        "app/schemas/admin.py",
    ]:
        path = root / fallback
        if path.exists():
            result.append(fallback)

    seen = set()
    unique = []
    for item in result:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def format_section(title: str) -> str:
    line = "=" * 72
    return f"{line}\n{title}\n{line}"


def build_report(root: Path, include_hidden: bool, include_dotenv: bool, max_tree_entries: int) -> str:
    project_name = root.resolve().name
    project_type = ", ".join(detect_project_type(root)) or "Unknown"
    tree_lines = build_tree(root, include_hidden=include_hidden, max_entries=max_tree_entries)
    entry_points = detect_entry_points(root)
    module_map = collect_module_map(root)
    api_map = collect_api_map(root)
    env_map = collect_env_map(root, include_dotenv=include_dotenv)
    entities = collect_domain_entities(root)
    read_first = collect_read_first(root)

    lines: list[str] = []

    lines.append(format_section("PROJECT META"))
    lines.append(f"Name: {project_name}")
    lines.append(f"Root: {root.resolve()}")
    lines.append(f"Detected stack/hints: {project_type}")
    lines.append("Generated by: build_repo_map.py")
    lines.append("Notes: Auto-generated snapshot for AI/context sharing.")
    lines.append("")

    lines.append(format_section("DIRECTORY TREE"))
    if tree_lines:
        lines.extend(tree_lines)
    else:
        lines.append("(no visible files found)")
    lines.append("")

    lines.append(format_section("ENTRY POINTS"))
    if entry_points:
        for item in entry_points:
            lines.append(f"- {item}")
    else:
        lines.append("(none detected)")
    lines.append("")

    lines.append(format_section("MODULE MAP"))
    if module_map:
        for group_name, files in module_map.items():
            lines.append(f"[{group_name}]")
            for rel in files[:200]:
                lines.append(f"- {rel} :: {summarize_path(rel)}")
            if len(files) > 200:
                lines.append(f"- ... {len(files) - 200} more")
            lines.append("")
    else:
        lines.append("(no modules detected)")
        lines.append("")

    lines.append(format_section("DOMAIN MODEL"))
    if entities:
        for entity in entities:
            lines.append(f"- {entity}")
    else:
        lines.append("(no app/models entities detected)")
    lines.append("")

    lines.append(format_section("API MAP"))
    if api_map:
        for route in api_map:
            lines.append(
                f"- {route['method']:6s} {route['path']} :: {route['handler']} [{route['file']}]"
            )
    else:
        lines.append("(no routes detected)")
    lines.append("")

    lines.append(format_section("ENV / CONFIG MAP"))
    if env_map:
        for key, source, preview in env_map:
            lines.append(f"- {key} :: source={source} :: value={preview}")
    else:
        lines.append("(no env variables detected from .env.example/config)")
    lines.append("")

    lines.append(format_section("IMPORTANT FLOWS (AUTO-GUESSED)"))
    guesses = []

    if any("routes_admin.py" in ep for ep in entry_points):
        guesses.append(
            "Admin flow: routes_admin.py -> services/* -> repos/* -> models/*"
        )
    if any("routes_sync.py" in ep for ep in entry_points):
        guesses.append(
            "Sync flow: routes_sync.py -> sync_service/event_ingest -> repos -> DB"
        )
    if (root / "app" / "services" / "uow.py").exists():
        guesses.append("Transaction flow: route/service -> UnitOfWork -> repos -> session flush/commit")
    if (root / "app" / "models" / "user.py").exists() and (root / "app" / "models" / "user_site_role.py").exists():
        guesses.append("Access flow: user -> user_site_role -> access_service/access_guard")

    if guesses:
        for item in guesses:
            lines.append(f"- {item}")
    else:
        lines.append("- Add manual flow notes here if needed.")
    lines.append("")

    lines.append(format_section("KNOWN ISSUES / TODO"))
    lines.append("- Auto-generator does not infer business rules from code bodies.")
    lines.append("- Review API/auth/security details manually before sharing externally.")
    lines.append("- Add manual notes here for architecture constraints and sharp edges.")
    lines.append("")

    lines.append(format_section("FILES TO READ FIRST"))
    if read_first:
        for idx, item in enumerate(read_first, start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("(no priority files detected)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root directory not found: {root}")

    report = build_report(
        root=root,
        include_hidden=args.include_hidden,
        include_dotenv=args.include_dotenv,
        max_tree_entries=args.max_tree_entries,
    )

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path

    output_path.write_text(report, encoding="utf-8")
    print(f"repo map written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
