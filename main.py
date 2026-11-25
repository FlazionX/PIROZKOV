import sys
import random
import re
import math
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QFrame, QMessageBox
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PHOTO_DIR = ASSETS / "photos"
MUSIC = ASSETS / "samo_soboy.mp3"
SUBTITLES = ASSETS / "captions.srt"

PHOTO_URLS = [
    "https://cdn.informator.ua/%40dp/media/kiev/2023/10/12/65281577f0444.jpg",
    "https://salvemusic.com.ua/wp-content/uploads/2019/11/pirozhkov1.jpg",
    "https://www.concert-star.ru/wp-content/uploads/2019/10/13022019-006.jpg",
]


def parse_srt(path):
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    blocks = re.split(r"\n\s*\n", raw.strip())
    result = []

    def to_ms(stamp):
        h, m, rest = stamp.strip().replace(",", ".").split(":")
        sec, milli = rest.split(".")
        return ((int(h) * 60 + int(m)) * 60 + int(sec)) * 1000 + int(milli.ljust(3, "0")[:3])

    for block in blocks:
        lines = block.splitlines()
        time_line = next((line for line in lines if "-->" in line), None)
        if not time_line:
            continue
        try:
            start, end = [to_ms(part.strip().split()[0]) for part in time_line.split("-->")]
            text = " ".join(line.strip() for line in lines[lines.index(time_line) + 1:] if line.strip())
            if text and end > start:
                result.append((start, end, text))
        except (ValueError, IndexError):
            continue
    return sorted(result, key=lambda item: item[0])


class PhotoLoader(QThread):
    finished_paths = Signal(list)

    def run(self):
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        for index, url in enumerate(PHOTO_URLS, 1):
            target = PHOTO_DIR / f"pirozkov_{index}.jpg"
            if target.exists() and target.stat().st_size > 0:
                continue
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "PIROZKOV-Prank/1.0"})
                with urllib.request.urlopen(request, timeout=7) as response:
                    data = response.read(8 * 1024 * 1024 + 1)
                if 0 < len(data) <= 8 * 1024 * 1024:
                    target.write_bytes(data)
            except Exception:
                pass
        paths = [str(p) for p in sorted(PHOTO_DIR.iterdir()) if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        self.finished_paths.emit(paths)


class PhotoCard(QFrame):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame{background:#171321;border:3px solid white;border-radius:14px;}")
        self.image = QLabel(self)
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setGeometry(5, 5, 190, 230)
        if pixmap and not pixmap.isNull():
            self.image.setPixmap(pixmap.scaled(190, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.image.setText("PIROZKOV")
            self.image.setStyleSheet("color:#ffdf55;font-size:22px;font-weight:900;")
        self.setFixedSize(200, 240)


class CaptionPopup(QLabel):
    def __init__(self, text, parent):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            "color:white;background:rgba(20,10,35,225);"
            "border:2px solid white;border-radius:14px;padding:10px;"
            "font-size:20px;font-weight:900;"
        )
        self.setFixedWidth(390)
        self.adjustSize()


class Prank(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PIROZKOV.exe")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.phase = 0
        self.photos = []
        self.cards = []
        self.caption_popups = []
        self.captions = parse_srt(SUBTITLES)
        self.shown_captions = set()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.85)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.errorOccurred.connect(self.on_media_error)
        self.player.setSource(QUrl.fromLocalFile(str(MUSIC)))

        self.icons = []
        names = ["Этот компьютер", "Корзина", "Папка", "PIROZKOV", "Музыка", "Фото", "Игры", "Документы"]
        for i, name in enumerate(names):
            icon = QLabel("🖥️\n" + name, self)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("color:white;background:rgba(15,15,30,145);border:1px solid white;border-radius:9px;padding:7px;font-size:13px;")
            icon.setFixedSize(104, 72)
            self.icons.append(icon)

        self.skip = QPushButton("ПРОПУСТИТЬ", self)
        self.skip.setStyleSheet(
            "QPushButton{background:#ffdf3e;color:#16121f;border:0;border-radius:12px;"
            "padding:12px 22px;font-size:16px;font-weight:900;}"
            "QPushButton:hover{background:white;}"
        )
        self.skip.clicked.connect(self.finish)
        self.skip.adjustSize()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_captions)
        self.caption_timer.start(100)

        self.photo_loader = PhotoLoader(self)
        self.photo_loader.finished_paths.connect(self.set_photos)
        self.photo_loader.start()

        self.showFullScreen()
        self.position_icons()
        self.skip.move(self.width() - self.skip.width() - 28, 24)
        QTimer.singleShot(400, self.player.play)

    def position_icons(self):
        for i, icon in enumerate(self.icons):
            icon.move(35 + (i % 4) * 125, 55 + (i // 4) * 105)

    def set_photos(self, paths):
        self.photos.clear()
        for path in paths:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.photos.append(pixmap)

    def animate(self):
        self.phase += 1
        self.update()
        for i, icon in enumerate(self.icons):
            x = 35 + (i % 4) * 125 + int(18 * math.sin(self.phase / 7 + i))
            y = 55 + (i // 4) * 105 + int(20 * math.sin(self.phase / 5 + i * 1.7))
            icon.move(x, y)
            hue = (self.phase * 3 + i * 35) % 360
            icon.setStyleSheet(
                f"color:white;background:rgba(15,15,30,145);border:2px solid hsla({hue},100%,75%,0.95);"
                "border-radius:9px;padding:7px;font-size:13px;"
            )
        if self.phase % 65 == 0:
            self.spawn_photo()

    def spawn_photo(self):
        if not self.photos:
            return
        card = PhotoCard(random.choice(self.photos), self)
        card.move(random.randint(25, max(26, self.width() - 225)), random.randint(80, max(81, self.height() - 260)))
        card.show()
        card.raise_()
        self.cards.append(card)
        if len(self.cards) > 6:
            self.cards.pop(0).deleteLater()
        self.skip.raise_()
        for popup in self.caption_popups:
            popup.raise_()

    def update_captions(self):
        position = self.player.position()
        for index, (start, end, text) in enumerate(self.captions):
            if start <= position <= end and index not in self.shown_captions:
                self.shown_captions.add(index)
                popup = CaptionPopup(text, self)
                popup.move(
                    random.randint(20, max(21, self.width() - popup.width() - 20)),
                    random.randint(100, max(101, self.height() - popup.height() - 100)),
                )
                popup.show()
                popup.raise_()
                self.caption_popups.append(popup)
                QTimer.singleShot(max(500, end - position), popup.deleteLater)
                if len(self.caption_popups) > 8:
                    old = self.caption_popups.pop(0)
                    old.deleteLater()
        self.caption_popups = [p for p in self.caption_popups if not p.isHidden()]

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finish()

    def on_media_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            QMessageBox.warning(self, "PIROZKOV.exe", "Не удалось воспроизвести музыку. Проверь файл assets/samo_soboy.mp3.")
            self.finish()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor.fromHsv((self.phase * 2) % 360, 220, 230))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 55))

    def resizeEvent(self, event):
        if hasattr(self, "skip"):
            self.skip.move(self.width() - self.skip.width() - 28, 24)
        super().resizeEvent(event)

    def finish(self):
        self.timer.stop()
        self.caption_timer.stop()
        self.player.stop()
        if self.photo_loader.isRunning():
            self.photo_loader.quit()
            self.photo_loader.wait(1200)
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_F10):
            self.finish()
        else:
            super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if not MUSIC.is_file():
        QMessageBox.information(
            None, "PIROZKOV.exe",
            "Положи аудиофайл «Само собой» в assets/samo_soboy.mp3, затем запусти программу снова."
        )
        sys.exit(0)
    window = Prank()
    sys.exit(app.exec())
