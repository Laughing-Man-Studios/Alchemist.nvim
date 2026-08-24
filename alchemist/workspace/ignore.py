"""Aider-compatible file ignore and binary detection for shadow workspace copy."""

import fnmatch
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Known binary extensions to always skip
BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".wasm", ".pyc", ".pyo", ".class",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".sqlite", ".db", ".sqlite3",
})

# Max bytes to scan for null-byte heuristic
_BINARY_PROBE_SIZE = 8192


def is_binary_file(path: Path) -> bool:
    """Detect binary files via extension check + null-byte heuristic."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_PROBE_SIZE)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True  # If unreadable, treat as binary


def get_git_tracked_files(project_root: Path) -> list[str]:
    """Get all tracked + untracked-but-not-ignored files via git ls-files.

    Returns relative paths from the project root.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def load_aiderignore_patterns(project_root: Path) -> list[str]:
    """Load glob patterns from .aiderignore if it exists."""
    aiderignore = project_root / ".aiderignore"
    if not aiderignore.is_file():
        return []
    patterns = []
    for line in aiderignore.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def should_ignore_aiderignore(
    rel_path: str, patterns: list[str]
) -> bool:
    """Check if a relative path matches any .aiderignore pattern."""
    return any(fnmatch.fnmatch(rel_path, pat) for pat in patterns)


def collect_files_for_shadow(project_root: Path) -> list[Path]:
    """Collect all files eligible for shadow workspace copy.

    Uses git ls-files for gitignore compliance, then filters
    against .aiderignore patterns and binary detection.

    Returns absolute paths.
    """
    git_files = get_git_tracked_files(project_root)
    aider_patterns = load_aiderignore_patterns(project_root)

    result: list[Path] = []
    for rel_path in git_files:
        if should_ignore_aiderignore(rel_path, aider_patterns):
            logger.debug("Skipping (aiderignore): %s", rel_path)
            continue
        abs_path = project_root / rel_path
        if not abs_path.is_file():
            continue
        if is_binary_file(abs_path):
            logger.debug("Skipping (binary): %s", rel_path)
            continue
        result.append(abs_path)
    return result
