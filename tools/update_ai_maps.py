from __future__ import annotations

from pathlib import Path
import argparse
import re
from typing import Iterable

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".ruff_cache",
}

EXCLUDED_FILES = {
    ".DS_Store",
}

DEFAULT_DEPTHS = {
    "repo": 2,
    "app": 3,
    "api": 3,
    "services": 3,
    "repos": 3,
    "models": 3,
    "apps": 3,
    "config": 3,
}

ROUTE_PATTERN = re.compile(r'@router\.(get|post|patch|put|delete)\(\s*[ru]?["\']([^"\']+)["\']')
URL_PATTERN = re.compile(r'path\(\s*[ru]?["\']([^"\']+)["\']')
ENV_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")


def should_exclude(path: Path) -> bool:
    if path.name in EXCLUDED_FILES:
        return True
    for part in path.parts:
        if part in EXCLUDED_DIRS:
            return True
    return False


def safe_iterdir(path: Path) -> list[Path]:
    try:
        children = [p for p in path.iterdir() if not should_exclude(p)]
        return sorted(children, key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception:
        return []


def build_tree_lines(root: Path, max_depth: int) -> list[str]:
    lines = [root.name]

    def walk(current: Path, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            return
        children = safe_iterdir(current)
        for idx, child in enumerate(children):
            is_last = idx == len(children) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{child.name}")
            if child.is_dir():
                extension = "    " if is_last else "│   "
                walk(child, prefix + extension, depth + 1)

    if root.exists() and root.is_dir():
        walk(root, "", 0)
    return lines


def write_text(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def write_tree(target: Path, root: Path, depth: int) -> None:
    if not root.exists():
        write_text(target, f"{root} does not exist.\n")
        return
    lines = build_tree_lines(root, depth)
    write_text(target, "\n".join(lines) + "\n")


def iter_py_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if not should_exclude(p)]


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def scan_fastapi_routes(api_dir: Path) -> str:
    if not api_dir.exists():
        return f"{api_dir} does not exist.\n"

    lines: list[str] = []
    for py_file in sorted(iter_py_files(api_dir)):
        rel = py_file.as_posix()
        text = read_text_safe(py_file)
        found = []

        for raw in text.splitlines():
            s = raw.strip()
            m = ROUTE_PATTERN.search(s)
            if m:
                found.append(f"{m.group(1).upper():6} {m.group(2)}")

        if found:
            lines.append(f"# FILE: {rel}")
            lines.extend(found)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def scan_django_urls(repo_root: Path) -> str:
    lines: list[str] = []
    for py_file in sorted(iter_py_files(repo_root)):
        if py_file.name != "urls.py":
            continue
        rel = py_file.relative_to(repo_root).as_posix()
        text = read_text_safe(py_file)
        found = []

        for raw in text.splitlines():
            s = raw.strip()
            m = URL_PATTERN.search(s)
            if m:
                found.append(m.group(1))

        if found:
            lines.append(f"# FILE: {rel}")
            for route in found:
                lines.append(route)
            lines.append("")
    if not lines:
        return "No Django urls.py routes found.\n"
    return "\n".join(lines).rstrip() + "\n"


def scan_env_map(repo_root: Path) -> str:
    interesting_files = []
    for p in repo_root.rglob("*"):
        if should_exclude(p) or not p.is_file():
            continue
        if p.suffix.lower() in {".py", ".md", ".txt", ".env", ".example", ".sample"} or p.name.endswith(
            (".env.example", ".env.sample")
        ):
            interesting_files.append(p)

    found: dict[str, set[str]] = {}
    for file_path in interesting_files:
        text = read_text_safe(file_path)
        for match in ENV_PATTERN.findall(text):
            if any(k in match for k in ("SECRET", "TOKEN", "URL", "HOST", "PORT", "DEBUG", "DB", "POSTGRES", "SYNC", "API")):
                rel = file_path.relative_to(repo_root).as_posix()
                found.setdefault(match, set()).add(rel)

    if not found:
        return "No env-like variables found.\n"

    lines = []
    for key in sorted(found):
        lines.append(key)
        for location in sorted(found[key]):
            lines.append(f"  - {location}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def scan_python_entry_points(repo_root: Path) -> str:
    candidates = []
    for py_file in iter_py_files(repo_root):
        text = read_text_safe(py_file)
        rel = py_file.relative_to(repo_root).as_posix()

        if "__main__" in text or "FastAPI(" in text or "urlpatterns" in text or "include_router" in text:
            candidates.append(rel)

    if not candidates:
        return "No obvious Python entry points found.\n"

    lines = ["Potential entry points and routing files:"]
    for item in sorted(set(candidates)):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def generate_syncserver_maps(repo_root: Path) -> list[Path]:
    docs = repo_root / "docs"
    outputs: list[Path] = []

    mapping = [
        ("tree_repo.txt", repo_root, DEFAULT_DEPTHS["repo"]),
        ("tree_app.txt", repo_root / "app", DEFAULT_DEPTHS["app"]),
        ("tree_api.txt", repo_root / "app" / "api", DEFAULT_DEPTHS["api"]),
        ("tree_services.txt", repo_root / "app" / "services", DEFAULT_DEPTHS["services"]),
        ("tree_repos.txt", repo_root / "app" / "repos", DEFAULT_DEPTHS["repos"]),
        ("tree_models.txt", repo_root / "app" / "models", DEFAULT_DEPTHS["models"]),
    ]

    for filename, root, depth in mapping:
        target = docs / filename
        write_tree(target, root, depth)
        outputs.append(target)

    api_routes = docs / "api_routes.txt"
    write_text(api_routes, scan_fastapi_routes(repo_root / "app" / "api"))
    outputs.append(api_routes)

    env_map = docs / "env_map.txt"
    write_text(env_map, scan_env_map(repo_root))
    outputs.append(env_map)

    entry_points = docs / "entry_points.txt"
    write_text(entry_points, scan_python_entry_points(repo_root))
    outputs.append(entry_points)

    return outputs


def generate_django_maps(repo_root: Path) -> list[Path]:
    docs = repo_root / "docs"
    outputs: list[Path] = []

    mapping = [
        ("tree_repo.txt", repo_root, DEFAULT_DEPTHS["repo"]),
        ("tree_apps.txt", repo_root / "apps", DEFAULT_DEPTHS["apps"]),
        ("tree_config.txt", repo_root / "config", DEFAULT_DEPTHS["config"]),
    ]

    for filename, root, depth in mapping:
        target = docs / filename
        write_tree(target, root, depth)
        outputs.append(target)

    django_routes = docs / "django_routes.txt"
    write_text(django_routes, scan_django_urls(repo_root))
    outputs.append(django_routes)

    env_map = docs / "env_map.txt"
    write_text(env_map, scan_env_map(repo_root))
    outputs.append(env_map)

    entry_points = docs / "entry_points.txt"
    write_text(entry_points, scan_python_entry_points(repo_root))
    outputs.append(entry_points)

    return outputs


def detect_repo_type(repo_root: Path) -> str:
    if (repo_root / "app" / "api").exists():
        return "syncserver"
    if (repo_root / "manage.py").exists() or (repo_root / "apps").exists():
        return "django"
    return "generic"


def generate_generic_maps(repo_root: Path) -> list[Path]:
    docs = repo_root / "docs"
    outputs: list[Path] = []

    target = docs / "tree_repo.txt"
    write_tree(target, repo_root, DEFAULT_DEPTHS["repo"])
    outputs.append(target)

    env_map = docs / "env_map.txt"
    write_text(env_map, scan_env_map(repo_root))
    outputs.append(env_map)

    entry_points = docs / "entry_points.txt"
    write_text(entry_points, scan_python_entry_points(repo_root))
    outputs.append(entry_points)

    return outputs


def process_repo(repo_root: Path) -> list[Path]:
    repo_type = detect_repo_type(repo_root)
    if repo_type == "syncserver":
        return generate_syncserver_maps(repo_root)
    if repo_type == "django":
        return generate_django_maps(repo_root)
    return generate_generic_maps(repo_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI-friendly tree/maps for repository structure.")
    parser.add_argument(
        "--repo",
        action="append",
        help="Path to repository. Can be passed multiple times. Default: current directory.",
    )
    args = parser.parse_args()

    repo_args = args.repo if args.repo else ["."]
    repos = [Path(p).resolve() for p in repo_args]

    all_outputs: list[Path] = []

    for repo in repos:
        print(f"[INFO] Processing repo: {repo}")
        outputs = process_repo(repo)
        all_outputs.extend(outputs)

    print("\nDone. Generated files:")
    for path in all_outputs:
        print(f" - {path}")


if __name__ == "__main__":
    main()