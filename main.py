from __future__ import annotations

import argparse
import math
import os
import random
import sys
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from safety import FileFingerprint, assert_unchanged, validate_target


APP_NAME = "WisadelDeleter"
MENU_LABEL = "召唤维什戴尔处理此文件"


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
        self.setPixmap(self._frames[0])
        self.show()
        self._timer.start(max(1, 1000 // fps))

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        self._index += 1
        if self._index >= len(self._frames):
            if self._loop:
                self._index = 0
            else:
                self._timer.stop()
                self._index = len(self._frames) - 1
                self.setPixmap(self._frames[self._index])
                self.finished.emit()
                return
        self.setPixmap(self._frames[self._index])
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


class WisadelDeleter(QWidget):
    def __init__(self, initial_target: str | None = None) -> None:
        super().__init__()
        self._target: Path | None = None
        self._fingerprint: FileFingerprint | None = None
        self._bomb_launched = False
        self._deletion_ok = False
        self._initial_target = initial_target

        self.setWindowTitle("维什戴尔的爆破委托")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())

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

        self.target_marker = QLabel("", self)
        self.target_marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_marker.setWordWrap(True)
        self.target_marker.setStyleSheet(
            "color:white; font:700 16px 'Microsoft YaHei'; padding:12px; "
            "background:rgba(17,19,24,225); border:2px solid #d71932; border-radius:24px;"
        )
        self.target_marker.resize(220, 170)
        self.target_marker.hide()

        self.card = self._build_card()
        self.card.hide()
        self.status = QLabel("正在召唤维什戴尔……", self)
        self.status.setStyleSheet(
            "color:white; font: 700 24px 'Microsoft YaHei'; background:rgba(10,11,15,205); padding:14px 24px; border-radius:16px;"
        )
        self.status.adjustSize()

        self._position_widgets()
        QTimer.singleShot(250, self._start_summon)

    def _build_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            """
            QFrame#card { background: rgba(18,20,27,244); border: 1px solid #444957; border-radius: 24px; }
            QLabel { color: #f4f6fb; font-family: 'Microsoft YaHei'; }
            QPushButton { border: 0; border-radius: 14px; padding: 13px 22px; font: 700 16px 'Microsoft YaHei'; }
            QPushButton#choose { background: #3a3f4c; color: white; }
            QPushButton#cancel { background: #30333c; color: #d8dbe4; }
            QPushButton#confirm { background: #d71932; color: white; }
            QPushButton#confirm:disabled { background: #4a4d57; color: #a5a9b4; }
            QPushButton:hover { border: 2px solid white; }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(14)
        title = QLabel("爆破委托确认")
        title.setStyleSheet("font-size: 27px; font-weight: 800;")
        copy = QLabel("维什戴尔将向下列目标投掷炸弹。目标会被移入系统回收站，可尝试恢复。")
        copy.setWordWrap(True)
        copy.setStyleSheet("font-size: 15px; color: #bcc1ce;")
        self.path_label = QLabel("尚未选择文件")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setMinimumHeight(48)
        self.path_label.setStyleSheet(
            "font-family:'Consolas','Microsoft YaHei'; font-size:14px; font-weight:600; "
            "background:#0d0f14; border:1px solid #353945; border-radius:12px; padding:12px;"
        )
        self.warning = QLabel("请确认路径无误。操作只会在炸弹命中时执行。")
        self.warning.setStyleSheet("font-size: 14px; color: #ffbd55;")
        buttons = QHBoxLayout()
        self.choose_button = QPushButton("选择文件")
        self.choose_button.setObjectName("choose")
        self.choose_button.clicked.connect(self._choose_target)
        cancel = QPushButton("取消")
        cancel.setObjectName("cancel")
        cancel.clicked.connect(self.close)
        self.confirm = QPushButton("确认并投掷")
        self.confirm.setObjectName("confirm")
        self.confirm.clicked.connect(self._confirm_attack)
        buttons.addWidget(self.choose_button)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm)
        layout.addWidget(title)
        layout.addWidget(copy)
        layout.addWidget(self.path_label)
        layout.addWidget(self.warning)
        layout.addLayout(buttons)
        card.resize(700, 300)
        return card

    def _position_widgets(self) -> None:
        self.sprite.move(max(30, self.width() // 8), self.height() - 390)
        self.status.move((self.width() - self.status.width()) // 2, 45)
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2 - 20)
        self.target_marker.move(
            self.width() * 3 // 4 - self.target_marker.width() // 2,
            self.height() // 2 - self.target_marker.height() // 2,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._position_widgets()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 5, 8, 150))
        painter.setPen(QPen(QColor(215, 25, 50, 40), 1))
        gap = 52
        for x in range(0, self.width(), gap):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), gap):
            painter.drawLine(0, y, self.width(), y)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()

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
        self.status.setText("维什戴尔已就位：选择爆破目标")
        self.status.adjustSize()
        self._position_widgets()
        if self._initial_target:
            self._set_target(self._initial_target)
        else:
            self._show_waiting_selection()

    def _show_waiting_selection(self) -> None:
        self._target = None
        self._fingerprint = None
        self.path_label.setText("尚未选择文件")
        self.warning.setText("维什戴尔正在等待。请点击“选择文件”，确认目标后才会投掷炸弹。")
        self.choose_button.setText("选择文件")
        self.confirm.setEnabled(False)
        self.confirm.setText("等待选择")
        self.card.show()
        self.card.raise_()

    def _choose_target(self) -> None:
        start_directory = str(self._target.parent) if self._target else str(Path.home())
        # A hidden top-most overlay cannot cover the native Windows picker.
        # The summoned character returns as soon as the picker closes.
        self.hide()
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "选择要移入回收站的文件",
            start_directory,
            "所有文件 (*)",
        )
        self.show()
        self.raise_()
        if not selected:
            if self._target is None:
                self._show_waiting_selection()
            else:
                self.card.show()
                self.card.raise_()
            return
        self._set_target(selected)

    def _set_target(self, selected: str) -> None:
        try:
            target, saved_fingerprint = validate_target(selected, __file__)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法选择目标", str(error))
            if self._target is None:
                self._show_waiting_selection()
            return
        self._target = target
        self._fingerprint = saved_fingerprint
        self.path_label.setText(str(target))
        self.warning.setText("请确认路径无误。目标将移入回收站，而非永久粉碎。")
        self.choose_button.setText("重新选择")
        self.confirm.setEnabled(True)
        self.confirm.setText("确认并投掷")
        self.card.show()
        self.card.raise_()

    def _confirm_attack(self) -> None:
        if self._target is None or self._fingerprint is None:
            return
        try:
            assert_unchanged(self._target, self._fingerprint)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "目标已变化", str(error))
            self._show_waiting_selection()
            return
        self.card.hide()
        self.target_marker.setText(f"📄\n{self._target.name}")
        self.target_marker.show()
        self.status.setText(f"锁定：{self._target.name}")
        self.status.adjustSize()
        self._position_widgets()
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

    def _launch_bomb(self) -> None:
        start = self.sprite.pos() + QPoint(self.sprite.width() - 60, self.sprite.height() // 2)
        target_center = self.target_marker.geometry().center()
        end = target_center - QPoint(self.bomb.width() // 2, self.bomb.height() // 2)
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
        center = self.target_marker.geometry().center()
        self.explosion.move(center - QPoint(self.explosion.width() // 2, self.explosion.height() // 2))
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
            self.warning.setText(f"操作失败：{error}")

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
            self.status.setText("任务中止：文件未被移动")
            self.card.show()
            self.confirm.setEnabled(False)
            self.confirm.setText("操作未执行")
        self.status.adjustSize()
        self._position_widgets()

    def _start_expression_burst(self) -> None:
        center = self.target_marker.geometry().center()
        self.expression_burst.start(center)


def context_menu_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --from-menu'

    interpreter = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = interpreter.with_name("pythonw.exe")
        if pythonw.exists():
            interpreter = pythonw
    return f'"{interpreter}" "{Path(__file__).resolve()}" --from-menu'


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

    hide_console_window()

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    # No launch path may auto-select a target. This also makes old installed
    # context-menu commands safe until the user re-registers the new command.
    window = WisadelDeleter(None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
