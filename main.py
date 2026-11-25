import sys
import random
import re
import math
import ctypes
import ctypes.wintypes
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFrame, QMessageBox
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
                with urllib.request.urlopen(request, timeout=3) as response:
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
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        if hasattr(Qt, 'WindowTransparentForInput'):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(QApplication.primaryScreen().availableGeometry())
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


        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_captions)
        self.caption_timer.start(100)

        self.photo_loader = PhotoLoader(self)
        self.photo_loader.finished_paths.connect(self.set_photos)
        self.photo_loader.start()

        self.show()
        QTimer.singleShot(400, self.player.play)

    def set_photos(self, paths):
        self.photos.clear()
        for path in paths:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.photos.append(pixmap)

    def animate(self):
        self.phase += 1
        self.update()
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
            try:
                (ROOT / 'PIROZKOV-error.txt').write_text(str(message), encoding='utf-8')
            except Exception:
                pass
            self.finish()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor.fromHsv((self.phase * 2) % 360, 210, 255, 62))
        painter.setPen(QColor(255, 255, 255, 65))
        offset = self.phase % 90
        for x in range(-self.height(), self.width(), 90):
            painter.drawLine(x + offset, 0, x - self.height() + offset, self.height())

    def finish(self):
        self.timer.stop()
        self.caption_timer.stop()
        self.player.stop()
        if self.photo_loader.isRunning():
            self.photo_loader.quit()
            self.photo_loader.wait(9500)
        self.close()

class GlobalExitKeys(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.ids = []

    def register(self):
        if sys.platform == "win32":
            for hotkey_id, key in ((1, 0x1B), (2, 0x79)):
                if ctypes.windll.user32.RegisterHotKey(None, hotkey_id, 0x4000, key):
                    self.ids.append(hotkey_id)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            if msg.message == 0x0312 and msg.wParam in self.ids:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def unregister(self):
        if sys.platform == "win32":
            for hotkey_id in self.ids:
                ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
        self.ids.clear()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if not MUSIC.is_file():
        QMessageBox.information(
            None, "PIROZKOV.exe",
            "Положи аудиофайл «Само собой» в assets/samo_soboy.mp3, затем запусти программу снова."
        )
        sys.exit(0)
    window = Prank()
    hotkeys = GlobalExitKeys(window.finish)
    app.installNativeEventFilter(hotkeys)
    hotkeys.register()
    app.aboutToQuit.connect(hotkeys.unregister)
    sys.exit(app.exec())
