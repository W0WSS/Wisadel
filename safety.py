from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileFingerprint:
    device: int
    inode: int
    size: int
    modified_ns: int


def normalized_target(value: str | os.PathLike[str]) -> Path:
    """Return an absolute path without following a final symlink."""
    return Path(os.path.abspath(os.fspath(value)))


def fingerprint(path: Path) -> FileFingerprint:
    stat = path.lstat()
    return FileFingerprint(
        device=stat.st_dev,
        inode=stat.st_ino,
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


def protected_paths(script_path: str | os.PathLike[str]) -> set[Path]:
    protected = {normalized_target(script_path), normalized_target(sys.executable)}
    if getattr(sys, "frozen", False):
        protected.add(normalized_target(sys.executable))
    return protected


def validate_target(
    value: str | os.PathLike[str], script_path: str | os.PathLike[str]
) -> tuple[Path, FileFingerprint]:
    path = normalized_target(value)
    if not os.path.lexists(path):
        raise ValueError("目标不存在，可能已经被移动或删除。")
    if path in protected_paths(script_path):
        raise ValueError("不能把维什戴尔删除器本身设为目标。")
    if path.parent == path:
        raise ValueError("不能删除磁盘根目录。")
    return path, fingerprint(path)


def assert_unchanged(path: Path, expected: FileFingerprint) -> None:
    if not os.path.lexists(path):
        raise ValueError("目标已经不存在。")
    if fingerprint(path) != expected:
        raise ValueError("确认后目标发生了变化，已中止操作。请重新选择。")
