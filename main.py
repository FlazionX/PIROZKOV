import sys
import random
import re
import ctypes
import ctypes.wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QMessageBox
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
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_PHOTOS_ON_SCREEN = 35
PHOTO_INTERVAL_MS = 900


def parse_srt(path):
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip())
    result = []

    def to_ms(stamp):
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*", stamp)
        if not match:
            raise ValueError("Invalid SRT timestamp")
        hours, minutes, seconds, millis = match.groups()
        return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis.ljust(3, "0"))

    for block in blocks:
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue
        try:
            left, right = lines[time_index].split("-->", 1)
            start = to_ms(left.strip().split()[0])
            end = to_ms(right.strip().split()[0])
            caption = " ".join(line.strip() for line in lines[time_index + 1:] if line.strip())
            caption = re.sub(r"<[^>]+>", "", caption)
            if caption and end > start:
                result.append((start, end, caption))
        except (ValueError, IndexError):
            continue
    return sorted(result, key=lambda item: item[0])


class PhotoLoader(QThread):
    finished_paths = Signal(list)

    def run(self):
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        # Download the starter images only when the user has not supplied them.
        local_images = [p for p in PHOTO_DIR.iterdir() if p.suffix.lower() in PHOTO_EXTENSIONS]
        if len(local_images) < 3:
            import urllib.request
            for index, url in enumerate(PHOTO_URLS, 1):
                target = PHOTO_DIR / f"starter_{index}.jpg"
                if target.exists() and target.stat().st_size > 0:
                    continue
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "PIROZKOV-Prank/1.0"})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        data = response.read(8 * 1024 * 1024 + 1)
                    if 0 < len(data) <= 8 * 1024 * 1024:
                        target.write_bytes(data)
                except Exception:
                    pass

        paths = [
            str(p) for p in sorted(PHOTO_DIR.iterdir())
            if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS and p.stat().st_size > 0
        ][:300]
        self.finished_paths.emit(paths)


class PhotoTile(QLabel):
    def __init__(self, pixmap, size, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: transparent; border: none;")
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = max(0, (scaled.width() - size) // 2)
            y = max(0, (scaled.height() - size) // 2)
            self.setPixmap(scaled.copy(x, y, size, size))


class CaptionPopup(QLabel):
    def __init__(self, caption, parent):
        super().__init__(caption, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(440)
        self.setMargin(13)
        self.setStyleSheet(
            "QLabel { color: #ffffff; background-color: rgba(12, 12, 24, 225);"
            "border: 1px solid rgba(255,255,255,210); border-radius: 12px;"
            "font-family: Segoe UI; font-size: 19px; font-weight: 800; }"
        )
        self.adjustSize()


class Prank(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PIROZKOV.exe")
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        if hasattr(Qt, "WindowTransparentForInput"):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(QApplication.primaryScreen().geometry())

        self.phase = 0
        self.photos = []
        self.tiles = []
        self.caption_popups = []
        self.captions = parse_srt(SUBTITLES)
        self.active_caption_indexes = set()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.85)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.errorOccurred.connect(self.on_media_error)
        self.player.setSource(QUrl.fromLocalFile(str(MUSIC)))

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.animate)
        self.animation_timer.start(40)

        self.photo_timer = QTimer(self)
        self.photo_timer.timeout.connect(self.spawn_photo)
        self.photo_timer.start(PHOTO_INTERVAL_MS)

        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_captions)
        self.caption_timer.start(80)

        self.photo_loader = PhotoLoader(self)
        self.photo_loader.finished_paths.connect(self.set_photos)
        self.photo_loader.start()

        self.show()
        self.apply_no_activate_style()
        QTimer.singleShot(1200, self.start_music)

    def apply_no_activate_style(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            get_long = ctypes.windll.user32.GetWindowLongW
            set_long = ctypes.windll.user32.SetWindowLongW
            style = get_long(hwnd, GWL_EXSTYLE)
            set_long(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            HWND_TOPMOST = -1
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception as exc:
            self.write_log("Не удалось включить режим без активации: " + str(exc))

    def write_log(self, message):
        try:
            (ROOT / "PIROZKOV-error.txt").write_text(str(message), encoding="utf-8")
        except Exception:
            pass

    def start_music(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self.player.play()

    def set_photos(self, paths):
        self.photos = []
        for path in paths:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.photos.append(pixmap)
        if not self.photos:
            self.write_log("Фотографии не найдены. Добавь JPG/PNG в assets/photos.")

    def animate(self):
        self.phase = (self.phase + 1) % 360
        self.update()

    def spawn_photo(self):
        if not self.photos or self.width() < 200 or self.height() < 200:
            return
        size = random.choice((112, 128, 144, 160, 176))
        tile = PhotoTile(random.choice(self.photos), size, self)
        max_x = max(0, self.width() - size)
        max_y = max(0, self.height() - size)
        tile.move(random.randint(0, max_x), random.randint(0, max_y))
        tile.show()
        tile.raise_()
        self.tiles.append(tile)
        if len(self.tiles) > MAX_PHOTOS_ON_SCREEN:
            old = self.tiles.pop(0)
            old.deleteLater()
        for popup in self.caption_popups:
            popup.raise_()

    def update_captions(self):
        position = self.player.position()
        currently_active = set()
        for index, (start, end, caption) in enumerate(self.captions):
            if start <= position < end:
                currently_active.add(index)
                if index not in self.active_caption_indexes:
                    popup = CaptionPopup(caption, self)
                    popup.adjustSize()
                    x = random.randint(20, max(20, self.width() - popup.width() - 20))
                    y = random.randint(70, max(70, self.height() - popup.height() - 70))
                    popup.move(x, y)
                    popup.show()
                    popup.raise_()
                    self.caption_popups.append((index, popup))
        for index, popup in list(self.caption_popups):
            if index not in currently_active:
                popup.deleteLater()
                self.caption_popups.remove((index, popup))
        self.active_caption_indexes = currently_active

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finish()
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                self.player.play()

    def on_media_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            self.write_log("Ошибка музыки: " + str(message))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Subtle colour wash: the desktop remains clearly visible underneath.
        painter.fillRect(self.rect(), QColor.fromHsv((self.phase * 2) % 360, 175, 255, 22))
        painter.setPen(QColor(255, 255, 255, 22))
        offset = self.phase % 120
        for x in range(-self.height(), self.width(), 150):
            painter.drawLine(x + offset, 0, x - self.height() + offset, self.height())

    def finish(self):
        self.animation_timer.stop()
        self.photo_timer.stop()
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
            # Ctrl + Shift + F10
            if ctypes.windll.user32.RegisterHotKey(None, 2, 0x0002 | 0x0004 | 0x4000, 0x79):
                self.ids.append(2)

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
    app.setQuitOnLastWindowClosed(True)
    if not MUSIC.is_file():
        QMessageBox.information(
            None,
            "PIROZKOV.exe",
            "Не найдена музыка.\nПоложи файл сюда:\nassets/samo_soboy.mp3",
        )
        sys.exit(0)

    window = Prank()
    hotkeys = GlobalExitKeys(window.finish)
    app.installNativeEventFilter(hotkeys)
    hotkeys.register()
    app.aboutToQuit.connect(hotkeys.unregister)
    sys.exit(app.exec())
