from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DesktopSelectionUnavailable(RuntimeError):
    """Raised when Windows desktop selection cannot be inspected."""


@dataclass(frozen=True)
class DesktopSelection:
    path: Path
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)


def desktop_directories() -> tuple[Path, ...]:
    """Return the current user's real and public Windows desktop folders."""
    candidates: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "Desktop")
            candidates.append(Path(os.path.expandvars(value)))
        except (OSError, ValueError):
            pass

    user_profile = os.environ.get("USERPROFILE")
    one_drive = os.environ.get("OneDrive")
    public_profile = os.environ.get("PUBLIC")
    if user_profile:
        candidates.append(Path(user_profile) / "Desktop")
    if one_drive:
        candidates.append(Path(one_drive) / "Desktop")
    if public_profile:
        candidates.append(Path(public_profile) / "Desktop")

    unique: list[Path] = []
    for candidate in candidates:
        normalized = Path(os.path.abspath(candidate))
        if normalized not in unique and normalized.is_dir():
            unique.append(normalized)
    return tuple(unique)


def resolve_desktop_item(
    display_name: str, directories: Iterable[Path] | None = None
) -> Path | None:
    """Resolve a UI Automation desktop label to one unambiguous real file."""
    label = display_name.strip().casefold()
    if not label:
        return None

    exact: list[Path] = []
    stem_matches: list[Path] = []
    for directory in directories if directories is not None else desktop_directories():
        try:
            entries = list(Path(directory).iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                is_file = entry.is_file() or entry.is_symlink()
            except OSError:
                is_file = False
            if not is_file:
                continue
            if entry.name.casefold() == label:
                exact.append(entry)
            elif entry.stem.casefold() == label:
                stem_matches.append(entry)

    matches = exact or stem_matches
    unique = list(dict.fromkeys(Path(os.path.abspath(path)) for path in matches))
    return unique[0] if len(unique) == 1 else None


def _list_item_ancestor(control, auto):
    current = control
    for _ in range(7):
        if current is None:
            return None
        try:
            if current.ControlType == auto.ControlType.ListItemControl:
                return current
            current = current.GetParentControl()
        except Exception:
            return None
    return None


def _belongs_to_windows_desktop(control) -> bool:
    current = control
    for _ in range(10):
        if current is None:
            return False
        try:
            if current.ClassName in {"Progman", "WorkerW"}:
                return True
            current = current.GetParentControl()
        except Exception:
            return False
    return False


def clicked_desktop_file(x: int, y: int) -> DesktopSelection | None:
    """Return the real desktop file selected by a click at screen coordinates."""
    if sys.platform != "win32":
        raise DesktopSelectionUnavailable("桌面文件选取仅支持 Windows 10/11。")
    try:
        import uiautomation as auto
    except ImportError as error:
        raise DesktopSelectionUnavailable(
            "缺少 uiautomation，请重新运行 pip install -r requirements.txt。"
        ) from error

    try:
        auto.SetGlobalSearchTimeout(0.7)
        item = _list_item_ancestor(auto.ControlFromPoint(x, y), auto)
        if item is None:
            return None
        if not _belongs_to_windows_desktop(item):
            return None
        rectangle = item.BoundingRectangle
        if not (rectangle.left <= x <= rectangle.right and rectangle.top <= y <= rectangle.bottom):
            return None
        try:
            if not item.GetSelectionItemPattern().IsSelected:
                return None
        except Exception:
            return None

        path = resolve_desktop_item(item.Name)
        if path is None:
            return None
        return DesktopSelection(
            path=path,
            left=int(rectangle.left),
            top=int(rectangle.top),
            right=int(rectangle.right),
            bottom=int(rectangle.bottom),
        )
    except DesktopSelectionUnavailable:
        raise
    except Exception as error:
        raise DesktopSelectionUnavailable(f"无法读取桌面选中项：{error}") from error


def _key_down(virtual_key: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)


def left_button_down() -> bool:
    return _key_down(0x01)


def escape_key_down() -> bool:
    return _key_down(0x1B)


def cursor_position() -> tuple[int, int]:
    if sys.platform != "win32":
        raise DesktopSelectionUnavailable("桌面文件选取仅支持 Windows 10/11。")
    import ctypes
    from ctypes import wintypes

    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise DesktopSelectionUnavailable("无法读取鼠标位置。")
    return int(point.x), int(point.y)
