from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRECTORIES = {
    ".git", ".idea", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv",
    "__pycache__", "build", "dist", "node_modules", "postgres-data", "_planes",
}
TEXT_EXTENSIONS = {
    ".c", ".cpp", ".css", ".go", ".h", ".html", ".java", ".js", ".json",
    ".kt", ".md", ".php", ".properties", ".py", ".rb", ".rs", ".sh", ".sql",
    ".toml", ".ts", ".tsx", ".xml", ".yaml", ".yml",
}


@dataclass(frozen=True)
class SourceChunk:
    ordinal: int
    start_line: int
    end_line: int
    text: str


def validate_repository_path(path: Path, allowed_roots: list[Path]) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"La ruta no es un directorio: {resolved}")
    roots = [root.expanduser().resolve(strict=True) for root in allowed_roots]
    if roots and not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise ValueError("La ruta solicitada está fuera de TRUCHA_ALLOWED_ROOTS")
    return resolved


def iter_source_files(root: Path, max_file_bytes: int):
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            try:
                if path.stat().st_size <= max_file_bytes:
                    yield path
            except OSError:
                continue


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, size: int = 80, overlap: int = 10) -> list[SourceChunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("El tamaño debe ser positivo y el solapamiento menor al tamaño")
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[SourceChunk] = []
    step = size - overlap
    for ordinal, start in enumerate(range(0, len(lines), step)):
        selected = lines[start : start + size]
        if not selected:
            break
        chunks.append(SourceChunk(ordinal, start + 1, start + len(selected), "\n".join(selected)))
        if start + size >= len(lines):
            break
    return chunks


def detect_language(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "text"
