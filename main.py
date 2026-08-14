from __future__ import annotations

import argparse
import math
import os
import random
import signal
import sys
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from desktop_selection import (
    DesktopSelection,
    DesktopSelectionUnavailable,
    clicked_desktop_file,
    cursor_position,
    escape_key_down,
    left_button_down,
)
from safety import FileFingerprint, assert_unchanged, validate_target


APP_NAME = "WisadelDeleter"
MENU_LABEL = "召唤维什戴尔"


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


class SpriteAnimator(QLabel):
    finished = pyqtSignal()
    frame_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._all_frames: list[QPixmap] = []
        self._frames: list[QPixmap] = []
        self._index = 0
        self._loop = False
        self._flipped = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    def load_sheet(self, path: Path, columns: int = 5, rows: int = 3) -> None:
        image = QImage(str(path))
        if image.isNull():
            raise RuntimeError(f"无法加载角色序列帧：{path}")
        width, height = image.width() // columns, image.height() // rows
        self._all_frames = []
        for row in range(rows):
            for column in range(columns):
                pixmap = QPixmap.fromImage(image.copy(column * width, row * height, width, height))
                self._all_frames.append(
                    pixmap.scaledToHeight(330, Qt.TransformationMode.SmoothTransformation)
                )

    def play(self, indices: list[int], fps: int = 8, loop: bool = False) -> None:
        self._timer.stop()
        self._frames = [self._all_frames[index] for index in indices]
        self._index = 0
        self._loop = loop
        if not self._frames:
            self.finished.emit()
            return
        self.resize(self._frames[0].size())
        self._render_frame()
        self.show()
        self._timer.start(max(1, 1000 // fps))

    def stop(self) -> None:
        self._timer.stop()

    def set_flipped(self, flipped: bool) -> None:
        self._flipped = flipped
        self._render_frame()

    def _render_frame(self) -> None:
        if not self._frames:
            return
        frame = self._frames[self._index]
        if self._flipped:
            frame = frame.transformed(
                QTransform().scale(-1, 1),
                Qt.TransformationMode.SmoothTransformation,
            )
        self.setPixmap(frame)

    def _advance(self) -> None:
        self._index += 1
        if self._index >= len(self._frames):
            if self._loop:
                self._index = 0
            else:
                self._timer.stop()
                self._index = len(self._frames) - 1
                self._render_frame()
                self.finished.emit()
                return
        self._render_frame()
        self.frame_changed.emit(self._index)


class BombWidget(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.resize(76, 76)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._spin)

    def start(self) -> None:
        self._timer.start(35)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _spin(self) -> None:
        self._angle = (self._angle + 17) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.setPen(QPen(QColor("#2d3038"), 4))
        painter.setBrush(QColor("#111318"))
        painter.drawEllipse(QRectF(-24, -20, 48, 48))
        painter.setPen(QPen(QColor("#d9dde8"), 4))
        painter.drawArc(QRectF(4, -31, 25, 25), 10 * 16, 90 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffb11b"))
        painter.drawEllipse(QRectF(24, -32, 12, 12))
        painter.setBrush(QColor("#f5f7fb"))
        painter.drawEllipse(QRectF(-12, -5, 9, 9))
        painter.drawEllipse(QRectF(4, -5, 9, 9))


class ExplosionWidget(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.resize(480, 480)
        self._frame = 0
        self._total_frames = 25
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        self._frame = 0
        self.show()
        self.raise_()
        QApplication.beep()
        self._timer.start(40)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._frame += 1
        if self._frame > self._total_frames:
            self._timer.stop()
            self.hide()
            self.finished.emit()
            return
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        progress = self._frame / self._total_frames
        fade = max(0.0, 1.0 - progress)
        shake_x = int(math.sin(self._frame * 4.7) * 8 * fade)
        shake_y = int(math.cos(self._frame * 5.3) * 6 * fade)
        blast_center = center + QPoint(shake_x, shake_y)

        # A short white flash makes the impact read before the fireball blooms.
        if progress < 0.20:
            flash = 1.0 - progress / 0.20
            painter.setOpacity(flash * 0.92)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#fffdf2"))
            radius = int(45 + (1.0 - flash) * 95)
            painter.drawEllipse(blast_center, radius, radius)

        # Jagged yellow/orange/red fireball.
        fire_progress = min(1.0, progress / 0.55)
        fire_fade = max(0.0, 1.0 - max(0.0, progress - 0.48) / 0.30)
        for layer, (color, base_radius) in enumerate(
            (("#d71932", 145), ("#ff5b22", 112), ("#ffd43b", 78), ("#fff6b0", 42))
        ):
            radius = base_radius * (0.24 + fire_progress * 0.76)
            path = QPainterPath()
            points = 28
            for index in range(points):
                angle = math.tau * index / points
                spike = 1.0 if index % 2 == 0 else 0.62 + 0.08 * math.sin(index * 5.1)
                point_radius = radius * spike
                x = blast_center.x() + math.cos(angle) * point_radius
                y = blast_center.y() + math.sin(angle) * point_radius
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            painter.setOpacity(fire_fade * (0.94 - layer * 0.08))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawPath(path)

        # Expanding shockwaves stay visible after the bright core has faded.
        shock_progress = min(1.0, progress / 0.82)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, color in enumerate(("#ffffff", "#ffd43b", "#ff4b35")):
            ring_progress = max(0.0, min(1.0, shock_progress - index * 0.08))
            ring_fade = max(0.0, 1.0 - ring_progress)
            radius = int(32 + ring_progress * (170 + index * 26))
            painter.setOpacity(ring_fade * 0.85)
            painter.setPen(QPen(QColor(color), max(2, 13 - index * 3)))
            painter.drawEllipse(blast_center, radius, radius)

        # Sparks and fragments shoot outward at different speeds.
        for index in range(24):
            angle = math.radians((index * 137.5 + 17) % 360)
            speed = 115 + (index % 7) * 17
            distance = 22 + progress * speed
            length = 12 + (index % 5) * 5
            spark_fade = max(0.0, 1.0 - progress * (0.85 + (index % 3) * 0.12))
            start = QPoint(
                blast_center.x() + int(math.cos(angle) * distance),
                blast_center.y() + int(math.sin(angle) * distance),
            )
            end = QPoint(
                start.x() + int(math.cos(angle) * length),
                start.y() + int(math.sin(angle) * length),
            )
            painter.setOpacity(spark_fade)
            painter.setPen(QPen(QColor("#fff07a" if index % 3 else "#ff542e"), 3 + index % 3))
            painter.drawLine(start, end)

        # Dark smoke is deliberately last so the blast transitions cleanly
        # into the large expression overlay.
        smoke_progress = max(0.0, (progress - 0.34) / 0.66)
        for index in range(12):
            angle = math.radians(index * 31 + 9)
            distance = 35 + smoke_progress * (55 + (index % 4) * 18)
            radius = int(18 + smoke_progress * (24 + index % 3 * 7))
            smoke_center = QPoint(
                blast_center.x() + int(math.cos(angle) * distance),
                blast_center.y() + int(math.sin(angle) * distance - smoke_progress * 34),
            )
            painter.setOpacity(smoke_progress * max(0.0, 1.0 - progress) * 1.5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#25242a" if index % 2 else "#4b3a3d"))
            painter.drawEllipse(smoke_center, radius, radius)

        # Final debris rays punctuate the end of the effect.
        painter.setOpacity(fade)
        painter.setPen(QPen(QColor("#ffb11b"), 5))
        for angle_degrees in range(0, 360, 30):
            radians = math.radians(angle_degrees + 7)
            inner = 75 + progress * 55
            outer = 105 + progress * 115
            painter.drawLine(
                QPoint(blast_center.x() + int(math.cos(radians) * inner), blast_center.y() + int(math.sin(radians) * inner)),
                QPoint(blast_center.x() + int(math.cos(radians) * outer), blast_center.y() + int(math.sin(radians) * outer)),
            )


class ExpressionBurst(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.resize(560, 560)
        self._frame = 0
        self._pixmap = QPixmap()
        self._expressions = [
            resource_path(f"assets/expressions/face-{index}.png")
            for index in range(1, 9)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def start(self, center: QPoint) -> None:
        # Prefer the seven extreme faces; keep the normal face as a rare gag.
        path = random.choice(self._expressions + self._expressions[1:])
        full_expression = QPixmap(str(path))
        # The reference sheet includes a tiny body, but the post-explosion gag
        # in the video is a face close-up. Crop before scaling so no torso or
        # legs can appear in the overlay.
        head_height = max(1, int(full_expression.height() * 0.69))
        self._pixmap = full_expression.copy(0, 0, full_expression.width(), head_height)
        self._frame = 0
        self.move(center - QPoint(self.width() // 2, self.height() // 2))
        self.show()
        self.raise_()
        self._timer.start(42)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._frame += 1
        if self._frame > 20:
            self._timer.stop()
            self.hide()
            self.finished.emit()
            return
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        progress = self._frame / 20
        if progress < 0.28:
            scale = 0.38 + (progress / 0.28) * 0.78
        elif progress < 0.72:
            scale = 1.16 + math.sin(progress * 38) * 0.035
        else:
            scale = max(0.0, 1.16 * (1.0 - (progress - 0.72) / 0.28))
        opacity = 1.0 if progress < 0.72 else max(0.0, 1.0 - (progress - 0.72) / 0.28)

        painter.setOpacity(opacity * 0.72)
        for index, color in enumerate(("#050509", "#7d0019", "#e31b36")):
            radius = int((150 + index * 34) * scale)
            painter.setPen(QPen(QColor(color), 24 - index * 5))
            painter.drawEllipse(center, radius, radius)

        if self._pixmap.isNull():
            return
        shake_x = int(math.sin(self._frame * 3.7) * 9 * opacity)
        shake_y = int(math.cos(self._frame * 4.4) * 7 * opacity)
        target_height = max(1, int(350 * scale))
        face = self._pixmap.scaledToHeight(target_height, Qt.TransformationMode.SmoothTransformation)
        painter.setOpacity(opacity)
        painter.drawPixmap(
            center.x() - face.width() // 2 + shake_x,
            center.y() - face.height() // 2 + shake_y,
            face,
        )


class TargetReticle(QWidget):
    """A highlight around the real desktop icon, never a fabricated file icon."""

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor(255, 44, 70, 230), 4))
        painter.setBrush(QColor(215, 25, 50, 35))
        painter.drawRoundedRect(QRectF(area), 17, 17)
        painter.setPen(QPen(QColor("#fff4a3"), 3))
        center = area.center()
        painter.drawLine(center.x() - 14, center.y(), center.x() + 14, center.y())
        painter.drawLine(center.x(), center.y() - 14, center.x(), center.y() + 14)


def united_screen_geometry(rectangles: list[QRect]) -> QRect:
    """Return one geometry covering every monitor, including negative origins."""
    if not rectangles:
        return QRect(0, 0, 1, 1)
    geometry = QRect(rectangles[0])
    for rectangle in rectangles[1:]:
        geometry = geometry.united(rectangle)
    return geometry


def virtual_desktop_geometry() -> QRect:
    rectangles = [screen.geometry() for screen in QApplication.screens()]
    return united_screen_geometry(rectangles)


def choose_attack_staging_position(
    target: QPoint,
    current: QPoint,
    actor_width: int,
    actor_height: int,
    area: QRect,
) -> tuple[QPoint, int]:
    """Choose a nearby in-bounds position and horizontal throw direction."""
    margin = 24
    gap = 72
    minimum_x = area.left() + margin
    minimum_y = area.top() + margin
    maximum_x = max(minimum_x, area.right() + 1 - actor_width - margin)
    maximum_y = max(minimum_y, area.bottom() + 1 - actor_height - margin)
    target_y = min(maximum_y, max(minimum_y, target.y() - actor_height // 2))

    left_x = target.x() - gap - actor_width
    right_x = target.x() + gap
    candidates: list[tuple[QPoint, int]] = []
    if minimum_x <= left_x <= maximum_x:
        candidates.append((QPoint(left_x, target_y), 1))
    if minimum_x <= right_x <= maximum_x:
        candidates.append((QPoint(right_x, target_y), -1))

    if not candidates:
        if target.x() < area.center().x():
            candidates.append(
                (QPoint(min(maximum_x, max(minimum_x, right_x)), target_y), -1)
            )
        else:
            candidates.append(
                (QPoint(min(maximum_x, max(minimum_x, left_x)), target_y), 1)
            )

    return min(
        candidates,
        key=lambda option: (
            (option[0].x() - current.x()) ** 2
            + (option[0].y() - current.y()) ** 2
        ),
    )


class WisadelDeleter(QWidget):
    def __init__(self, initial_target: str | None = None) -> None:
        super().__init__()
        self._target: Path | None = None
        self._fingerprint: FileFingerprint | None = None
        self._target_center = QPoint()
        self._target_global: QPoint | None = None
        self._bomb_launched = False
        self._deletion_ok = False
        self._last_error = ""
        self._waiting_for_desktop = False
        self._left_was_down = False
        self._escape_was_down = False
        self._actor_is_staged = False
        self._throw_direction = 1

        self.setWindowTitle("维什戴尔的爆破委托")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(virtual_desktop_geometry())

        self.sprite = SpriteAnimator(self)
        self.sprite.load_sheet(resource_path("assets/wisadel_april_fools_spritesheet-v3.png"))
        self.sprite.finished.connect(self._summon_finished)

        self.bomb = BombWidget(self)
        self.bomb.hide()
        self.explosion = ExplosionWidget(self)
        self.explosion.hide()
        self.explosion.finished.connect(self._start_expression_burst)
        self.expression_burst = ExpressionBurst(self)
        self.expression_burst.finished.connect(self._show_result)

        self.target_marker = TargetReticle(self)
        self.target_marker.resize(110, 110)
        self.target_marker.hide()

        self.status = QLabel("正在召唤维什戴尔……", self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(
            "color:white; font:700 24px 'Microsoft YaHei'; "
            "background:rgba(10,11,15,215); padding:14px 24px; border-radius:16px;"
        )
        self.status.adjustSize()

        self._input_timer = QTimer(self)
        self._input_timer.setInterval(35)
        self._input_timer.timeout.connect(self._poll_global_input)
        self._input_timer.start()

        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._screen_added)
            app.screenRemoved.connect(self._sync_virtual_geometry)
            for screen in app.screens():
                self._connect_screen(screen)

        self._position_widgets()
        QTimer.singleShot(250, self._start_summon)

    def _position_widgets(self) -> None:
        if not self._actor_is_staged:
            self.sprite.move(max(30, self.width() // 8), self.height() - 390)
        self.status.move((self.width() - self.status.width()) // 2, 45)

    def _position_target_marker(self) -> None:
        if self._target_global is None:
            return
        self._target_center = self.mapFromGlobal(self._target_global)
        self.target_marker.move(
            self._target_center
            - QPoint(self.target_marker.width() // 2, self.target_marker.height() // 2)
        )

    def _connect_screen(self, screen) -> None:
        try:
            screen.geometryChanged.connect(self._sync_virtual_geometry)
        except (AttributeError, TypeError):
            pass

    def _screen_added(self, screen) -> None:
        self._connect_screen(screen)
        self._sync_virtual_geometry()

    def _sync_virtual_geometry(self, *args) -> None:
        geometry = virtual_desktop_geometry()
        if self.geometry() != geometry:
            self.setGeometry(geometry)
        self._position_widgets()
        self._position_target_marker()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._position_widgets()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        opacity = 48 if self._waiting_for_desktop else 115
        painter.fillRect(self.rect(), QColor(4, 5, 8, opacity))
        painter.setPen(QPen(QColor(215, 25, 50, 24), 1))
        for y in range(0, self.height(), 64):
            painter.drawLine(0, y, self.width(), y)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._input_timer.stop()
        self.sprite.stop()
        self.bomb.stop()
        self.explosion.stop()
        self.expression_burst.stop()
        for animation_name in ("actor_move_animation", "bomb_animation"):
            animation = getattr(self, animation_name, None)
            if animation is not None:
                animation.stop()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _start_summon(self) -> None:
        self.show()
        self.raise_()
        self.sprite.play([0, 1, 2, 3, 4], fps=7)

    def _summon_finished(self) -> None:
        try:
            self.sprite.finished.disconnect(self._summon_finished)
        except TypeError:
            pass
        self.sprite.play([4], fps=1, loop=True)
        self._show_waiting_selection()

    def _set_click_through(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        flags = self.windowFlags()
        transparent = Qt.WindowType.WindowTransparentForInput
        already_enabled = bool(flags & transparent)
        if already_enabled == enabled:
            return
        # setWindowFlags recreates a native top-level window on Windows and can
        # reset it to the primary monitor. Always restore the complete virtual
        # desktop geometry immediately afterwards.
        self.setWindowFlags(flags | transparent if enabled else flags & ~transparent)
        self.setGeometry(virtual_desktop_geometry())
        self.show()
        self.raise_()
        self._position_widgets()
        self._position_target_marker()

    def _show_waiting_selection(self, message: str | None = None) -> None:
        self._target = None
        self._fingerprint = None
        self._target_global = None
        self._bomb_launched = False
        self._deletion_ok = False
        self._last_error = ""
        self._waiting_for_desktop = True
        self._left_was_down = False
        self._actor_is_staged = False
        self._throw_direction = 1
        self.sprite.set_flipped(False)
        self.target_marker.hide()
        self.status.setText(message or "请选择桌面上的文件图标 · 单击后立即投弹 · Esc 取消")
        self.status.adjustSize()
        self._position_widgets()
        self.update()

        if sys.platform == "win32":
            self._set_click_through(True)
        else:
            self.status.setText("桌面文件选取需要在 Windows 10/11 上运行")
            self.status.adjustSize()
            self._position_widgets()

    def _poll_global_input(self) -> None:
        escape_pressed = escape_key_down()
        if escape_pressed and not self._escape_was_down:
            self._escape_was_down = True
            self.close()
            return
        self._escape_was_down = escape_pressed
        if not self._waiting_for_desktop:
            return
        pressed = left_button_down()
        if pressed:
            self._left_was_down = True
            return
        if not self._left_was_down:
            return

        self._left_was_down = False
        try:
            x, y = cursor_position()
        except DesktopSelectionUnavailable as error:
            self.status.setText(str(error))
            self.status.adjustSize()
            self._position_widgets()
            return
        # QCursor uses Qt's DPI-aware coordinates while UI Automation expects
        # native screen coordinates. Keep both so effects stay aligned at 125%+
        # Windows display scaling.
        qt_click = QCursor.pos()
        QTimer.singleShot(
            120,
            lambda x=x, y=y, qt_click=qt_click: self._capture_desktop_click(
                x, y, qt_click
            ),
        )

    def _capture_desktop_click(self, x: int, y: int, qt_click: QPoint | None = None) -> None:
        if not self._waiting_for_desktop:
            return
        try:
            selection = clicked_desktop_file(x, y)
        except DesktopSelectionUnavailable as error:
            self.status.setText(str(error))
            self.status.adjustSize()
            self._position_widgets()
            return
        if selection is None:
            self.status.setText("没有识别到桌面文件，请单击真实文件图标（不支持文件夹或系统图标）")
            self.status.adjustSize()
            self._position_widgets()
            return
        self._lock_target(selection, qt_click)

    def _lock_target(
        self, selection: DesktopSelection, qt_click: QPoint | None = None
    ) -> None:
        try:
            target, saved_fingerprint = validate_target(selection.path, __file__)
        except (OSError, ValueError) as error:
            self._show_waiting_selection(f"无法锁定：{error} 请重新选择桌面文件")
            return

        self._waiting_for_desktop = False
        self._set_click_through(False)
        self._target = target
        self._fingerprint = saved_fingerprint

        self._target_global = qt_click if qt_click is not None else QPoint(*selection.center)
        self._target_center = self.mapFromGlobal(self._target_global)
        marker_width = 110
        marker_height = 110
        self.target_marker.resize(marker_width, marker_height)
        self._position_target_marker()
        self.target_marker.show()
        self.target_marker.raise_()
        self.status.setText(f"锁定：{target.name} · 正在调整投掷位置")
        self.status.adjustSize()
        self._actor_is_staged = True
        self._position_widgets()
        self._approach_target()

    def _approach_target(self) -> None:
        screen = (
            QApplication.screenAt(self._target_global)
            if self._target_global is not None
            else None
        )
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            screen_geometry = screen.geometry()
            local_screen_geometry = QRect(
                self.mapFromGlobal(screen_geometry.topLeft()), screen_geometry.size()
            )
        else:
            local_screen_geometry = self.rect()
        destination, direction = choose_attack_staging_position(
            target=self._target_center,
            current=self.sprite.pos(),
            actor_width=self.sprite.width(),
            actor_height=self.sprite.height(),
            area=local_screen_geometry,
        )
        self._throw_direction = direction
        self.sprite.set_flipped(direction < 0)

        distance = math.hypot(
            destination.x() - self.sprite.x(), destination.y() - self.sprite.y()
        )
        if distance < 4:
            self.sprite.move(destination)
            QTimer.singleShot(0, self._start_attack)
            return

        self.actor_move_animation = QPropertyAnimation(self.sprite, b"pos", self)
        self.actor_move_animation.setDuration(min(900, max(280, int(distance * 1.1))))
        self.actor_move_animation.setStartValue(self.sprite.pos())
        self.actor_move_animation.setEndValue(destination)
        self.actor_move_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.actor_move_animation.finished.connect(self._start_attack)
        self.actor_move_animation.start()

    def _start_attack(self) -> None:
        if self._target is None or self._fingerprint is None:
            return
        try:
            assert_unchanged(self._target, self._fingerprint)
        except (OSError, ValueError) as error:
            self._show_waiting_selection(f"目标已变化：{error} 请重新选择")
            return
        self._bomb_launched = False
        self.sprite.stop()
        try:
            self.sprite.frame_changed.disconnect()
        except TypeError:
            pass
        self.sprite.frame_changed.connect(self._attack_frame)
        self.sprite.play([5, 6, 7, 8, 9], fps=5)

    def _attack_frame(self, frame_index: int) -> None:
        if frame_index == 4 and not self._bomb_launched:
            self._bomb_launched = True
            self._launch_bomb()

    def _bomb_start_position(self) -> QPoint:
        hand_x = self.sprite.width() - 55 if self._throw_direction > 0 else 55
        hand_y = self.sprite.height() // 2
        return self.sprite.pos() + QPoint(
            hand_x - self.bomb.width() // 2,
            hand_y - self.bomb.height() // 2,
        )

    def _launch_bomb(self) -> None:
        start = self._bomb_start_position()
        end = self._target_center - QPoint(self.bomb.width() // 2, self.bomb.height() // 2)
        self.bomb.move(start)
        self.bomb.start()
        self.bomb.raise_()
        self.bomb_animation = QPropertyAnimation(self.bomb, b"pos", self)
        self.bomb_animation.setDuration(760)
        self.bomb_animation.setStartValue(start)
        self.bomb_animation.setEndValue(end)
        self.bomb_animation.setEasingCurve(QEasingCurve.Type.InQuad)
        self.bomb_animation.finished.connect(self._bomb_hit)
        self.bomb_animation.start()

    def _bomb_hit(self) -> None:
        self.bomb.stop()
        self.explosion.move(
            self._target_center
            - QPoint(self.explosion.width() // 2, self.explosion.height() // 2)
        )
        self.target_marker.hide()
        self._delete_target()
        self.explosion.start()

    def _delete_target(self) -> None:
        try:
            if self._target is None or self._fingerprint is None:
                raise ValueError("没有有效目标。")
            assert_unchanged(self._target, self._fingerprint)
            from send2trash import send2trash

            send2trash(str(self._target))
            self._deletion_ok = not os.path.lexists(self._target)
            if not self._deletion_ok:
                raise OSError("系统没有确认目标已移入回收站。")
        except Exception as error:  # Keep the UI alive and show the exact failure.
            self._deletion_ok = False
            self._last_error = str(error)

    def _show_result(self) -> None:
        try:
            self.sprite.frame_changed.disconnect(self._attack_frame)
        except TypeError:
            pass
        if self._deletion_ok:
            self.status.setText("任务完成：目标已移入回收站")
            self.sprite.play([10, 11, 12, 10, 11, 12], fps=6)
            QTimer.singleShot(2300, self.close)
        else:
            self.status.setText(f"任务中止：{self._last_error or '文件未被移动'}")
            self.sprite.play([4], fps=1, loop=True)
            QTimer.singleShot(2200, self._show_waiting_selection)
        self.status.adjustSize()
        self._position_widgets()

    def _start_expression_burst(self) -> None:
        self.expression_burst.start(self._target_center)


def context_menu_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --from-menu'

    interpreter = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = interpreter.with_name("pythonw.exe")
        if pythonw.exists():
            interpreter = pythonw
    return f'"{interpreter}" "{Path(__file__).resolve()}" --from-menu'


def configure_windows_dpi_awareness() -> None:
    """Use per-monitor DPI coordinates before Qt creates its first window."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
    except ImportError:
        return

    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
        per_monitor_v2 = ctypes.c_void_p((-4) & ((1 << pointer_bits) - 1))
        if set_context(per_monitor_v2):
            return
    except (AttributeError, OSError):
        pass

    try:
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        # S_OK means this call configured DPI awareness. E_ACCESSDENIED means
        # a manifest or Qt already configured it, which is also acceptable.
        if result in (0, -2147024891):
            return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def hide_console_window() -> None:
    """Hide a console inherited by a Windows context-menu launch."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)
    except Exception:
        # A --windowed PyInstaller build has no console and needs no action.
        pass


def install_interrupt_handlers(app: QApplication) -> QTimer:
    """Keep Python signal handling alive so Ctrl+C exits terminal runs."""

    def quit_application(*args) -> None:
        app.quit()

    for signal_name in ("SIGINT", "SIGBREAK"):
        interrupt = getattr(signal, signal_name, None)
        if interrupt is not None:
            try:
                signal.signal(interrupt, quit_application)
            except (OSError, ValueError):
                pass

    timer = QTimer(app)
    timer.setInterval(100)
    timer.timeout.connect(lambda: None)
    timer.start()
    return timer


def update_context_menu(install: bool) -> None:
    if sys.platform != "win32":
        raise RuntimeError("右键菜单集成仅支持 Windows。")
    import winreg

    roots = (r"Software\Classes\*\shell\SummonWisadel",)
    for key_path in roots:
        if install:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValue(key, "", winreg.REG_SZ, MENU_LABEL)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, context_menu_command())
        else:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="召唤维什戴尔，把选定文件移入回收站。")
    parser.add_argument("target", nargs="?", help="兼容旧右键菜单的路径参数（不会自动选中）")
    menu = parser.add_mutually_exclusive_group()
    menu.add_argument("--install-menu", action="store_true", help="安装 Windows 文件右键菜单")
    menu.add_argument("--uninstall-menu", action="store_true", help="卸载 Windows 文件右键菜单")
    parser.add_argument("--from-menu", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.install_menu or args.uninstall_menu:
        try:
            update_context_menu(args.install_menu)
            print("右键菜单已安装。" if args.install_menu else "右键菜单已卸载。")
            return 0
        except Exception as error:
            print(f"右键菜单操作失败：{error}", file=sys.stderr)
            return 1

    # A terminal launch must keep its console so Ctrl+C and diagnostics work.
    # Only the explicit Explorer context-menu launch suppresses it.
    if args.from_menu:
        hide_console_window()

    configure_windows_dpi_awareness()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    interrupt_timer = install_interrupt_handlers(app)
    # No launch path may auto-select a target. This also makes old installed
    # context-menu commands safe until the user re-registers the new command.
    window = WisadelDeleter(None)
    window.show()
    result = app.exec()
    interrupt_timer.stop()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
