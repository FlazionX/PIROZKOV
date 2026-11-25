import sys
import math
import random
import re
import ctypes
import ctypes.wintypes
import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QUrl, QThread, Signal, QAbstractNativeEventFilter,
    QPropertyAnimation, QEasingCurve, QSize, QRectF
)
from PySide6.QtGui import (
    QPixmap, QImage, QImageReader, QMovie, QPainter, QColor, QPen,
    QLinearGradient, QRadialGradient, QPainterPath, QPalette
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QMessageBox, QGraphicsOpacityEffect
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PHOTO_DIR = ASSETS / "photos"
GIF_DIR = ASSETS / "gifs"
MUSIC = ASSETS / "samo_soboy.mp3"
SUBTITLES = ASSETS / "captions.srt"
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_PHOTOS_ON_SCREEN = 20
MAX_GIFS_ON_SCREEN = 2
PHOTO_INTERVAL_MS = 420

PHOTO_URLS = [
    "https://cdn.informator.ua/%40dp/media/kiev/2023/10/12/65281577f0444.jpg",
    "https://salvemusic.com.ua/wp-content/uploads/2019/11/pirozhkov1.jpg",
    "https://www.concert-star.ru/wp-content/uploads/2019/10/13022019-006.jpg",
]


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
        h, m, s, ms = match.groups()
        return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms.ljust(3, "0"))

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
    loaded = Signal(object)

    def run(self):
        # Decode and downscale images away from the UI thread so the window
        # stays responsive while the visual assets are being prepared.
        images = []
        gifs = []
        first_batch_sent = False
        try:
            PHOTO_DIR.mkdir(parents=True, exist_ok=True)
            GIF_DIR.mkdir(parents=True, exist_ok=True)

            photo_paths = [
                p for p in sorted(PHOTO_DIR.iterdir())
                if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS
                and p.stat().st_size > 0
            ][:120]

            gifs = [
                str(p) for p in sorted(GIF_DIR.iterdir())
                if p.is_file() and p.suffix.lower() == ".gif" and p.stat().st_size > 0
            ][:40]

            for path in photo_paths:
                if self.isInterruptionRequested():
                    break
                try:
                    reader = QImageReader(str(path))
                    reader.setAutoTransform(True)
                    image = reader.read()
                    if image.isNull():
                        continue
                    image = image.scaled(
                        QSize(256, 256),
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation
                    )
                    left = max(0, (image.width() - 256) // 2)
                    top = max(0, (image.height() - 256) // 2)
                    images.append(image.copy(left, top, 256, 256))
                    # Start the intro after only a few thumbnails are ready;
                    # the remaining photos continue loading in the background.
                    if not first_batch_sent and len(images) >= 8:
                        self.loaded.emit((images.copy(), gifs, True))
                        images.clear()
                        first_batch_sent = True
                except Exception:
                    continue

            if not first_batch_sent:
                self.loaded.emit((images, gifs, True))
            elif images and not self.isInterruptionRequested():
                self.loaded.emit((images, [], False))
            return
        except Exception:
            if not first_batch_sent:
                self.loaded.emit((images, gifs, True))

class DanceDialog(QWidget):
    accepted = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DANCE.EXE")
        self.setFixedSize(340, 155)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(18)

        question = QLabel("Хочешь Танцевать?")
        question.setAlignment(Qt.AlignCenter)
        layout.addWidget(question)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.yes = QPushButton("Да")
        self.no = QPushButton("Нет")
        self.yes.setDefault(True)
        self.yes.clicked.connect(self.start_dance)
        self.no.clicked.connect(self.evade_no)
        buttons.addWidget(self.yes)
        buttons.addWidget(self.no)
        layout.addLayout(buttons)

    def start_dance(self):
        self.accepted.emit()
        self.close()

    def evade_no(self):
        # Keep the classic Windows button, but make it dodge clicks.
        max_x = max(8, self.width() - self.no.width() - 8)
        max_y = max(8, self.height() - self.no.height() - 8)
        self.no.move(random.randint(8, max_x), random.randint(52, max_y))


class DesktopIconDance:
    """Moves actual desktop icons through the supported Windows Shell COM API."""

    def __init__(self):
        self.started = False
        self.attempted = False
        self.stop_event = threading.Event()
        self.worker = None

    def _helper_path(self):
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(Path(getattr(sys, "_MEIPASS", ROOT)) / "desktop_icons.dll")
        candidates.append(ROOT / "desktop_icons.dll")
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def start(self):
        if sys.platform != "win32" or self.attempted:
            return
        self.attempted = True
        helper = self._helper_path()
        if helper is None:
            return
        self.stop_event.clear()
        self.worker = threading.Thread(
            target=self._worker_main,
            args=(str(helper),),
            name="DANCE-DesktopIcons",
            daemon=True
        )
        self.worker.start()

    def _worker_main(self, helper_path):
        dll = None
        initialized = False
        original = []
        count = 0
        try:
            # All COM calls stay on this dedicated STA thread. This avoids
            # conflicts with Qt Multimedia's own COM initialization.
            dll = ctypes.CDLL(helper_path)
            dll.dance_icons_init.argtypes = []
            dll.dance_icons_init.restype = ctypes.c_int
            dll.dance_icons_get_position.argtypes = [
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int)
            ]
            dll.dance_icons_get_position.restype = ctypes.c_int
            dll.dance_icons_set_positions.argtypes = [
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_int
            ]
            dll.dance_icons_set_positions.restype = ctypes.c_int
            dll.dance_icons_shutdown.argtypes = []
            dll.dance_icons_shutdown.restype = None

            count = dll.dance_icons_init()
            if count <= 0:
                return
            initialized = True

            for index in range(count):
                x = ctypes.c_int()
                y = ctypes.c_int()
                if not dll.dance_icons_get_position(index, ctypes.byref(x), ctypes.byref(y)):
                    return
                original.append((x.value, y.value))

            if len(original) != count:
                return

            xs_type = ctypes.c_int * count
            ys_type = ctypes.c_int * count
            base_x = [item[0] for item in original]
            base_y = [item[1] for item in original]
            xs = xs_type()
            ys = ys_type()

            self.started = True
            started_at = time.monotonic()
            while not self.stop_event.wait(0.105):
                elapsed = time.monotonic() - started_at
                for index, (x, y) in enumerate(original):
                    xs[index] = x + int(math.sin(elapsed * 4.2 + index * 1.7) * 11)
                    ys[index] = y + int(math.cos(elapsed * 3.7 + index * 1.3) * 8)
                if not dll.dance_icons_set_positions(xs, ys, count):
                    break
        except Exception:
            pass
        finally:
            if dll is not None and initialized:
                try:
                    if original and len(original) == count:
                        xs_type = ctypes.c_int * count
                        ys_type = ctypes.c_int * count
                        xs = xs_type(*(item[0] for item in original))
                        ys = ys_type(*(item[1] for item in original))
                        dll.dance_icons_set_positions(xs, ys, count)
                except Exception:
                    pass
                try:
                    dll.dance_icons_shutdown()
                except Exception:
                    pass
            self.started = False

    def stop(self):
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=3.0)
        self.started = False


class PhotoTile(QWidget):
    def __init__(self, pixmap, size, parent):
        super().__init__(parent)
        self.setFixedSize(size, size)
        scaled = pixmap.scaled(
            size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        left = max(0, (scaled.width() - size) // 2)
        top = max(0, (scaled.height() - size) // 2)
        self.pixmap = scaled.copy(left, top, size, size)
        self.angle = random.uniform(-9.0, 9.0)
        self.vx = random.uniform(-3.0, 3.0)
        self.vy = random.uniform(-2.5, 2.5)
        self.wobble = random.uniform(0, math.tau)
        self.accent = QColor.fromHsv(random.randrange(360), 185, 255, 255)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.angle)
        rect = QRectF(-self.width() / 2, -self.height() / 2, self.width(), self.height())

        # A soft coloured halo adds depth without a heavy photo frame.
        for width, alpha in ((14, 7), (8, 11), (3, 18)):
            glow = QColor(self.accent)
            glow.setAlpha(alpha)
            p.setPen(QPen(glow, width))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 11, 11)

        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        p.setClipPath(path)
        p.setPen(Qt.NoPen)
        p.drawPixmap(rect.toRect(), self.pixmap)
        p.end()


class GifTile(PhotoTile):
    def __init__(self, path, size, parent):
        placeholder = QPixmap(size, size)
        placeholder.fill(Qt.transparent)
        super().__init__(placeholder, size, parent)
        self.movie = QMovie(path)
        self.movie.setScaledSize(QSize(size, size))
        self.movie.frameChanged.connect(self.update_frame)
        if self.movie.isValid():
            self.movie.start()

    def update_frame(self, frame_number):
        image = self.movie.currentImage()
        if not image.isNull():
            self.pixmap = QPixmap.fromImage(image)
            self.update()

    def stop_movie(self):
        if self.movie:
            self.movie.stop()


class CaptionWindow(QFrame):
    def __init__(self, caption, parent):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(248, 248, 248))
        palette.setColor(QPalette.WindowText, QColor(32, 32, 32))
        self.setPalette(palette)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 9, 12, 10)
        box.setSpacing(5)

        brand = QLabel("DANCE SYSTEM")
        brand_font = brand.font()
        brand_font.setBold(True)
        brand_font.setPointSize(9)
        brand.setFont(brand_font)

        words = QLabel(caption)
        words.setWordWrap(True)
        words.setMaximumWidth(410)
        words_font = words.font()
        words_font.setPointSize(13)
        words.setFont(words_font)

        box.addWidget(brand)
        box.addWidget(words)
        self.adjustSize()

class HeroSplash(QWidget):
    def __init__(self, pixmap, parent):
        super().__init__(parent)
        self.pixmap = pixmap
        self.hue = random.randrange(360)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(
            parent.width() // 2 - 105, parent.height() // 2 - 105, 210, 210
        )
        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity)

        self.zoom = QPropertyAnimation(self, b"geometry", self)
        self.zoom.setDuration(3600)
        self.zoom.setStartValue(self.geometry())
        self.zoom.setEndValue(parent.rect().adjusted(
            parent.width() // 2 - 205, parent.height() // 2 - 205,
            -parent.width() // 2 + 205, -parent.height() // 2 + 205
        ))
        self.zoom.setEasingCurve(QEasingCurve.OutCubic)

        self.fade = QPropertyAnimation(self.opacity, b"opacity", self)
        self.fade.setDuration(1200)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)
        self.zoom.finished.connect(self.fade.start)
        self.fade.finished.connect(self.deleteLater)
        self.zoom.start()

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        halo = QRadialGradient(self.width() / 2, self.height() / 2, self.width() * 0.62)
        halo.setColorAt(0.0, QColor(255, 255, 255, 80))
        halo.setColorAt(0.45, QColor.fromHsv(self.hue, 210, 255, 62))
        halo.setColorAt(1.0, QColor.fromHsv((self.hue + 65) % 360, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(0, 0, self.width(), self.height()))

        photo_rect = QRectF(13, 13, self.width() - 26, self.height() - 26)
        path = QPainterPath()
        path.addRoundedRect(photo_rect, 18, 18)
        p.setClipPath(path)
        scaled = self.pixmap.scaled(
            photo_rect.size().toSize(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        left = max(0, (scaled.width() - int(photo_rect.width())) // 2)
        top = max(0, (scaled.height() - int(photo_rect.height())) // 2)
        p.drawPixmap(photo_rect.toRect(), scaled, QRectF(
            left, top, photo_rect.width(), photo_rect.height()
        ).toRect())
        p.end()

class Prank(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DANCE.EXE")
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        if hasattr(Qt, "WindowTransparentForInput"):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(QApplication.primaryScreen().geometry())

        self.phase = 0
        self.music_started = False
        self.photos = []
        self.gif_paths = []
        self.tiles = []
        self.caption_popups = []
        self.captions = parse_srt(SUBTITLES)
        self.active_caption_indexes = set()
        self.last_gif_position = -10000
        self.icon_dance = DesktopIconDance()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.88)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.errorOccurred.connect(self.on_media_error)
        self.player.setSource(QUrl.fromLocalFile(str(MUSIC)))

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.animate)
        self.animation_timer.start(40)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_captions)
        self.caption_timer.start(80)
        self.photo_timer = QTimer(self)
        self.photo_timer.timeout.connect(self.spawn_photo)

        self.photo_loader = PhotoLoader(self)
        self.photo_loader.loaded.connect(self.set_photos)
        self.photo_loader.start()

        self.show()
        self.apply_no_activate_style()

    def apply_no_activate_style(self):
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = ctypes.wintypes.HWND(int(self.winId()))
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            set_long.restype = ctypes.c_ssize_t

            GWL_EXSTYLE = -20
            style = int(get_long(hwnd, GWL_EXSTYLE))
            style |= 0x00000020 | 0x00000080 | 0x08000000 | 0x00080000
            set_long(hwnd, GWL_EXSTYLE, style)

            user32.SetWindowPos.argtypes = [
                ctypes.wintypes.HWND, ctypes.wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.wintypes.UINT
            ]
            user32.SetWindowPos.restype = ctypes.wintypes.BOOL
            user32.SetWindowPos(
                hwnd, ctypes.wintypes.HWND(-1), 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010 | 0x0020
            )
        except Exception as exc:
            self.write_log("Overlay style error: " + str(exc))

    def write_log(self, message):
        try:
            (ROOT / "PIROZKOV-error.txt").write_text(str(message), encoding="utf-8")
        except Exception:
            pass

    def start_music(self):
        if self.music_started:
            return
        self.music_started = True
        self.player.play()
        self.icon_dance.start()
        self.photo_timer.start(PHOTO_INTERVAL_MS)

    def set_photos(self, payload):
        images, gifs, is_initial_batch = payload
        loaded = [QPixmap.fromImage(image) for image in images if not image.isNull()]
        if not is_initial_batch:
            self.photos.extend(loaded)
            return

        self.gif_paths = gifs
        self.photos = loaded
        if self.photos:
            splash = HeroSplash(random.choice(self.photos), self)
            splash.show()
            QTimer.singleShot(4700, self.start_music)
        else:
            self.write_log("Фотографии не найдены. Положи JPG/PNG в assets/photos.")
            QTimer.singleShot(500, self.start_music)

    def spawn_photo(self):
        if not self.photos or len(self.tiles) >= MAX_PHOTOS_ON_SCREEN:
            return
        size = random.choice((112, 124, 136, 148))
        tile = PhotoTile(random.choice(self.photos), size, self)
        self.place_tile(tile)

    def spawn_gif(self):
        if not self.gif_paths:
            return
        active_gifs = sum(1 for tile in self.tiles if isinstance(tile, GifTile))
        if active_gifs >= MAX_GIFS_ON_SCREEN:
            return
        if len(self.tiles) >= MAX_PHOTOS_ON_SCREEN:
            return

        path = random.choice(self.gif_paths)
        size = random.randint(178, 218)
        tile = GifTile(path, size, self)
        if not tile.movie.isValid():
            tile.deleteLater()
            return
        self.place_tile(tile)
        QTimer.singleShot(6800, lambda current=tile: self.remove_tile(current))

    def place_tile(self, tile):
        size = tile.width()
        edge = random.choice(("left", "right", "top", "bottom"))
        if edge == "left":
            x, y = -size, random.randint(55, max(55, self.height() - size - 50))
            tile.vx = random.uniform(2.0, 4.0)
        elif edge == "right":
            x, y = self.width(), random.randint(55, max(55, self.height() - size - 50))
            tile.vx = random.uniform(-4.0, -2.0)
        elif edge == "top":
            x, y = random.randint(0, max(0, self.width() - size)), -size
            tile.vy = random.uniform(2.0, 4.0)
        else:
            x, y = random.randint(0, max(0, self.width() - size)), self.height()
            tile.vy = random.uniform(-4.0, -2.0)

        tile.move(x, y)
        tile.show()
        tile.raise_()
        self.tiles.append(tile)
        for _, popup in self.caption_popups:
            popup.raise_()

    def remove_tile(self, tile):
        if tile in self.tiles:
            self.tiles.remove(tile)
        if isinstance(tile, GifTile):
            tile.stop_movie()
        tile.deleteLater()

    def animate(self):
        self.phase += 1
        for tile in list(self.tiles):
            x = tile.x() + tile.vx
            y = tile.y() + tile.vy
            tile.wobble += 0.055
            tile.angle = math.sin(tile.wobble) * 11
            if x < 0 and tile.vx < 0:
                tile.vx *= -1
            if x + tile.width() > self.width() and tile.vx > 0:
                tile.vx *= -1
            if y < 0 and tile.vy < 0:
                tile.vy *= -1
            if y + tile.height() > self.height() and tile.vy > 0:
                tile.vy *= -1
            x = min(max(0, x), max(0, self.width() - tile.width()))
            y = min(max(0, y), max(0, self.height() - tile.height()))
            tile.move(int(x + math.sin(tile.wobble * 0.7) * 0.7), int(y + math.cos(tile.wobble) * 0.7))
            tile.update()
        self.update()

    def update_captions(self):
        position = self.player.position()
        active = set()
        for index, (start, end, words) in enumerate(self.captions):
            if start <= position < end:
                if not self.icon_dance.started:
                    self.icon_dance.start()
                active.add(index)
                if index not in self.active_caption_indexes:
                    popup = CaptionWindow(words, self)
                    x = random.randint(25, max(25, self.width() - popup.width() - 25))
                    y = random.randint(70, max(70, self.height() - popup.height() - 90))
                    popup.move(x, y)
                    popup.show()
                    popup.raise_()
                    self.caption_popups.append((index, popup))
                    if self.gif_paths and position - self.last_gif_position >= 10000:
                        self.spawn_gif()
                        self.last_gif_position = position
        for index, popup in list(self.caption_popups):
            if index not in active:
                popup.deleteLater()
                self.caption_popups.remove((index, popup))
        self.active_caption_indexes = active

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        offset = self.phase * 0.42

        # Low-opacity rainbow wash over the entire desktop and active windows.
        wash = QLinearGradient(0, 0, w, h)
        for step in range(7):
            hue = int((step * 60 + offset) % 360)
            wash.setColorAt(step / 6.0, QColor.fromHsv(hue, 205, 255, 7))
        p.fillRect(self.rect(), wash)

        # Slow moving light rays start at the disco ball instead of flashing
        # from the screen centre. Their hue and opacity change gradually.
        cx = w // 2
        ball_y = 74
        for i in range(30):
            angle = (i / 30.0) * math.tau - math.pi / 2 + self.phase * 0.006
            reach = max(w, h) * 1.05
            x2 = int(cx + math.cos(angle) * reach)
            y2 = int(ball_y + math.sin(angle) * reach)
            hue = int((i * 12 + offset) % 360)
            alpha = 10 + int((math.sin(self.phase * 0.025 + i) + 1) * 3)
            p.setPen(QPen(QColor.fromHsv(hue, 245, 255, alpha), 2))
            p.drawLine(cx, ball_y + 18, x2, y2)

        # A small, glossy disco ball with a soft highlight.
        ball = QRectF(cx - 31, ball_y - 31, 62, 62)
        ball_path = QPainterPath()
        ball_path.addEllipse(ball)
        ball_gradient = QRadialGradient(cx - 13, ball_y - 13, 66)
        ball_gradient.setColorAt(0.0, QColor(255, 255, 255, 235))
        ball_gradient.setColorAt(0.25, QColor(220, 238, 255, 205))
        ball_gradient.setColorAt(0.62, QColor(100, 125, 165, 190))
        ball_gradient.setColorAt(1.0, QColor(25, 35, 62, 170))
        p.setPen(QPen(QColor(255, 255, 255, 145), 1))
        p.setBrush(ball_gradient)
        p.drawEllipse(ball)

        p.save()
        p.setClipPath(ball_path)
        p.setPen(QPen(QColor(255, 255, 255, 105), 1))
        for line in range(-2, 3):
            x = cx + line * 11
            p.drawLine(x, ball_y - 34, x, ball_y + 34)
            y = ball_y + line * 11
            p.drawLine(cx - 34, y, cx + 34, y)
        p.restore()

        # Bright but translucent rainbow ribbon precisely over the bottom
        # taskbar area; input remains passed through to Windows underneath.
        band_y = max(0, h - 46)
        band = QLinearGradient(
            (self.phase * 2.1) % (w + 180) - 90, band_y,
            (self.phase * 2.1) % (w + 180) - 90 + w, band_y
        )
        for step in range(7):
            hue = int((step * 60 + offset * 1.35) % 360)
            band.setColorAt(step / 6.0, QColor.fromHsv(hue, 255, 255, 76))
        p.fillRect(0, band_y, w, h - band_y, band)

        # A slow narrow highlight gives the taskbar strip a moving light sweep.
        sweep_x = int((self.phase * 3.0) % (w + 160)) - 80
        sweep = QLinearGradient(sweep_x - 55, band_y, sweep_x + 55, band_y)
        sweep.setColorAt(0.0, QColor(255, 255, 255, 0))
        sweep.setColorAt(0.5, QColor(255, 255, 255, 34))
        sweep.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(0, band_y, w, h - band_y, sweep)

        p.setPen(QPen(QColor(255, 255, 255, 35), 1))
        p.drawLine(0, band_y, w, band_y)
        p.end()

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finish()

    def on_media_error(self, error, message):
        if error != QMediaPlayer.Error.NoError:
            self.write_log("Ошибка воспроизведения музыки: " + str(message))

    def finish(self):
        self.animation_timer.stop()
        self.caption_timer.stop()
        self.photo_timer.stop()
        self.player.stop()
        self.icon_dance.stop()
        for tile in list(self.tiles):
            if isinstance(tile, GifTile):
                tile.stop_movie()
            tile.deleteLater()
        self.tiles.clear()
        if self.photo_loader.isRunning():
            self.photo_loader.requestInterruption()
            self.photo_loader.wait()
        self.close()


class GlobalExitKeys(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.ids = []

    def register(self):
        if sys.platform == "win32":
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
    dialog = DanceDialog()
    dialog.move(
        QApplication.primaryScreen().geometry().center().x() - dialog.width() // 2,
        QApplication.primaryScreen().geometry().center().y() - dialog.height() // 2,
    )

    def launch_dance():
        if not MUSIC.is_file():
            QMessageBox.information(
                None, "DANCE.EXE",
                "Не найдена музыка.\nПоложи файл сюда:\nassets/samo_soboy.mp3"
            )
            return
        global prank_window, exit_hotkeys
        prank_window = Prank()
        exit_hotkeys = GlobalExitKeys(prank_window.finish)
        app.installNativeEventFilter(exit_hotkeys)
        exit_hotkeys.register()
        app.aboutToQuit.connect(exit_hotkeys.unregister)

    dialog.accepted.connect(launch_dance)
    dialog.show()
    sys.exit(app.exec())
