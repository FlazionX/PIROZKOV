import sys
import math
import random
import re
import ctypes
import ctypes.wintypes
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QUrl, QThread, Signal, QAbstractNativeEventFilter,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QMessageBox, QGraphicsOpacityEffect
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PHOTO_DIR = ASSETS / "photos"
MUSIC = ASSETS / "samo_soboy.mp3"
SUBTITLES = ASSETS / "captions.srt"
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_PHOTOS_ON_SCREEN = 20
PHOTO_INTERVAL_MS = 350

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
    loaded = Signal(list)

    def run(self):
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        local = [p for p in PHOTO_DIR.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS]
        if len(local) < 3:
            import urllib.request
            for i, url in enumerate(PHOTO_URLS, 1):
                target = PHOTO_DIR / f"starter_{i}.jpg"
                if target.exists() and target.stat().st_size:
                    continue
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "DANCE-EXE/1.0"})
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
        self.loaded.emit(paths)


class DanceDialog(QWidget):
    accepted = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DANCE.EXE")
        self.setFixedSize(430, 235)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QWidget { background:#171329; color:white; font-family:'Segoe UI'; }
            QLabel#question { font-size:25px; font-weight:900; }
            QLabel#sub { color:#b9b4d0; font-size:12px; }
            QPushButton { border:0; border-radius:10px; padding:12px 30px; font-size:16px; font-weight:800; }
            QPushButton#yes { background:#ff3d9a; color:white; }
            QPushButton#no { background:#38334d; color:white; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)
        title = QLabel("DANCE.EXE")
        title.setStyleSheet("color:#ff69b4;font-size:13px;font-weight:900;letter-spacing:3px;")
        title.setAlignment(Qt.AlignCenter)
        question = QLabel("Хочешь Танцевать?")
        question.setObjectName("question")
        question.setAlignment(Qt.AlignCenter)
        sub = QLabel("У тебя есть только один правильный ответ")
        sub.setObjectName("sub")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(question)
        layout.addWidget(sub)
        buttons = QHBoxLayout()
        buttons.setSpacing(14)
        self.yes = QPushButton("ДА")
        self.yes.setObjectName("yes")
        self.no = QPushButton("НЕТ")
        self.no.setObjectName("no")
        self.yes.clicked.connect(self.start_dance)
        self.no.clicked.connect(self.evade_no)
        buttons.addWidget(self.yes)
        buttons.addWidget(self.no)
        layout.addLayout(buttons)
        buttons.removeWidget(self.no)
        self.no.setParent(self)
        self.no.setGeometry(292, 177, 112, 42)
        self.no.raise_()

    def start_dance(self):
        self.accepted.emit()
        self.close()

    def evade_no(self):
        max_x = max(12, self.width() - self.no.width() - 12)
        max_y = max(12, self.height() - self.no.height() - 12)
        self.no.move(random.randint(12, max_x), random.randint(12, max_y))


class DesktopIconDance:
    """Temporarily jiggles real Windows desktop icons and restores their original positions."""
    LVM_FIRST = 0x1000
    LVM_GETITEMCOUNT = LVM_FIRST + 4
    LVM_GETITEMPOSITION = LVM_FIRST + 16
    LVM_SETITEMPOSITION = LVM_FIRST + 15

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def __init__(self):
        self.hwnd = None
        self.process = None
        self.remote_point = None
        self.original = []
        self.started = False
        self.attempted = False
        self.tick = 0

    def _find_listview(self):
        user32 = ctypes.windll.user32
        user32.FindWindowExW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        user32.FindWindowExW.restype = ctypes.wintypes.HWND
        user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        user32.FindWindowW.restype = ctypes.wintypes.HWND
        user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.wintypes.LPARAM]
        user32.EnumWindows.restype = ctypes.wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_windows(hwnd, lparam):
            shell = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if shell:
                view = user32.FindWindowExW(shell, None, "SysListView32", "FolderView")
                if view:
                    found.append(view)
            return True

        user32.EnumWindows(enum_windows, 0)
        if not found:
            progman = user32.FindWindowW("Progman", None)
            shell = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
            view = user32.FindWindowExW(shell, None, "SysListView32", "FolderView")
            if view:
                found.append(view)
        return found[0] if found else None

    def start(self):
        if sys.platform != "win32" or self.attempted:
            return
        self.attempted = True
        try:
            self.hwnd = self._find_listview()
            if not self.hwnd:
                return
            pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
            PROCESS_VM_OPERATION = 0x0008
            PROCESS_VM_READ = 0x0010
            PROCESS_VM_WRITE = 0x0020
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
            kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
            kernel32.VirtualAllocEx.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
            kernel32.VirtualAllocEx.restype = ctypes.c_void_p
            kernel32.ReadProcessMemory.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            kernel32.ReadProcessMemory.restype = ctypes.wintypes.BOOL
            kernel32.VirtualFreeEx.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.wintypes.DWORD]
            kernel32.VirtualFreeEx.restype = ctypes.wintypes.BOOL
            kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
            kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
            user32.SendMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            user32.SendMessageW.restype = ctypes.c_ssize_t
            self.process = kernel32.OpenProcess(
                PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, False, pid.value
            )
            if not self.process:
                return
            self.remote_point = ctypes.windll.kernel32.VirtualAllocEx(
                self.process, None, ctypes.sizeof(self.POINT), 0x1000 | 0x2000, 0x04
            )
            if not self.remote_point:
                self.stop()
                return
            count = ctypes.windll.user32.SendMessageW(self.hwnd, self.LVM_GETITEMCOUNT, 0, 0)
            for index in range(min(int(count), 1000)):
                ok = ctypes.windll.user32.SendMessageW(
                    self.hwnd, self.LVM_GETITEMPOSITION, index, ctypes.cast(self.remote_point, ctypes.c_void_p).value
                )
                if not ok:
                    continue
                point = self.POINT()
                read = ctypes.c_size_t()
                if ctypes.windll.kernel32.ReadProcessMemory(
                    self.process, self.remote_point, ctypes.byref(point),
                    ctypes.sizeof(point), ctypes.byref(read)
                ):
                    self.original.append((index, point.x, point.y))
            self.started = bool(self.original)
        except Exception:
            self.stop()

    def animate(self):
        if not self.started:
            return
        self.tick += 1
        for index, x, y in self.original:
            dx = int(math.sin(self.tick * 0.20 + index * 1.7) * 13)
            dy = int(math.cos(self.tick * 0.17 + index * 1.3) * 9)
            packed = ((y + dy) & 0xFFFF) << 16 | ((x + dx) & 0xFFFF)
            ctypes.windll.user32.SendMessageW(self.hwnd, self.LVM_SETITEMPOSITION, index, packed)

    def stop(self):
        if self.hwnd and self.original and self.process:
            for index, x, y in self.original:
                packed = (y & 0xFFFF) << 16 | (x & 0xFFFF)
                try:
                    ctypes.windll.user32.SendMessageW(self.hwnd, self.LVM_SETITEMPOSITION, index, packed)
                except Exception:
                    pass
        if self.process and self.remote_point:
            try:
                ctypes.windll.kernel32.VirtualFreeEx(self.process, self.remote_point, 0, 0x8000)
            except Exception:
                pass
        if self.process:
            try:
                ctypes.windll.kernel32.CloseHandle(self.process)
            except Exception:
                pass
        self.process = None
        self.remote_point = None
        self.started = False


class PhotoTile(QWidget):
    def __init__(self, pixmap, size, parent):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.pixmap = pixmap
        self.angle = random.uniform(-10, 10)
        self.vx = random.uniform(-3.0, 3.0)
        self.vy = random.uniform(-2.5, 2.5)
        self.wobble = random.uniform(0, math.tau)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self.pixmap.scaled(self.width(), self.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        sx = max(0, (scaled.width() - self.width()) // 2)
        sy = max(0, (scaled.height() - self.height()) // 2)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.angle)
        p.drawPixmap(-self.width() // 2, -self.height() // 2, scaled.copy(sx, sy, self.width(), self.height()))


class CaptionWindow(QFrame):
    def __init__(self, caption, parent):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background:rgba(13,10,28,225); border:1px solid rgba(255,255,255,210); border-radius:12px; }
            QLabel#brand { color:#ff4fa3; font-size:11px; font-weight:900; letter-spacing:2px; }
            QLabel#words { color:white; font-size:19px; font-weight:800; }
        """)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 9, 14, 12)
        box.setSpacing(5)
        brand = QLabel("DANCE SYSTEM")
        brand.setObjectName("brand")
        words = QLabel(caption)
        words.setObjectName("words")
        words.setWordWrap(True)
        words.setMaximumWidth(410)
        box.addWidget(brand)
        box.addWidget(words)
        self.adjustSize()


class HeroSplash(QWidget):
    def __init__(self, pixmap, parent):
        super().__init__(parent)
        self.pixmap = pixmap
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(
            parent.width() // 2 - 95, parent.height() // 2 - 95, 190, 190
        )
        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity)
        self.zoom = QPropertyAnimation(self, b"geometry", self)
        self.zoom.setDuration(3600)
        self.zoom.setStartValue(self.geometry())
        self.zoom.setEndValue(parent.rect().adjusted(
            parent.width() // 2 - 190, parent.height() // 2 - 190,
            -parent.width() // 2 + 190, -parent.height() // 2 + 190
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
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        p.drawPixmap(self.rect(), scaled, scaled.rect().adjusted(x, y, -x, -y))


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
        self.photos = []
        self.tiles = []
        self.caption_popups = []
        self.captions = parse_srt(SUBTITLES)
        self.active_caption_indexes = set()
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
        self.animation_timer.start(35)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_captions)
        self.caption_timer.start(80)
        self.photo_timer = QTimer(self)
        self.photo_timer.timeout.connect(self.spawn_photo)
        self.photo_timer.start(PHOTO_INTERVAL_MS)
        self.icon_timer = QTimer(self)
        self.icon_timer.timeout.connect(self.icon_dance.animate)
        self.icon_timer.start(70)

        self.photo_loader = PhotoLoader(self)
        self.photo_loader.loaded.connect(self.set_photos)
        self.photo_loader.start()

        self.show()
        self.apply_no_activate_style()

    def apply_no_activate_style(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= 0x00000020 | 0x00000080 | 0x08000000
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception as exc:
            self.write_log("Overlay style error: " + str(exc))

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
            image = QPixmap(path)
            if not image.isNull():
                self.photos.append(image)
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
        edge = random.choice(("left", "right", "top", "bottom"))
        if edge == "left":
            x, y = -size, random.randint(0, max(0, self.height() - size))
            tile.vx = random.uniform(2.0, 4.0)
        elif edge == "right":
            x, y = self.width(), random.randint(0, max(0, self.height() - size))
            tile.vx = random.uniform(-4.0, -2.0)
        elif edge == "top":
            x, y = random.randint(0, max(0, self.width() - size)), -size
            tile.vy = random.uniform(2.0, 4.0)
        else:
            x, y = random.randint(0, max(0, self.width() - size)), self.height()
            tile.vy = random.uniform(-4.0, -2.0)
        tile.move(x, y)
        tile.show()
        self.tiles.append(tile)
        for _, popup in self.caption_popups:
            popup.raise_()

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
                    y = random.randint(70, max(70, self.height() - popup.height() - 80))
                    popup.move(x, y)
                    popup.show()
                    popup.raise_()
                    self.caption_popups.append((index, popup))
        for index, popup in list(self.caption_popups):
            if index not in active:
                popup.deleteLater()
                self.caption_popups.remove((index, popup))
        self.active_caption_indexes = active

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # Low-opacity disco wash reaches the full screen, including the taskbar.
        p.fillRect(self.rect(), QColor.fromHsv((self.phase * 2) % 360, 180, 255, 18))
        cx, cy = w // 2, h // 2
        p.setPen(Qt.NoPen)
        for i in range(48):
            angle = (i / 48.0) * math.tau + self.phase * 0.012
            reach = max(w, h) * 1.2
            x2 = int(cx + math.cos(angle) * reach)
            y2 = int(cy + math.sin(angle) * reach)
            hue = (i * 7 + self.phase * 2) % 360
            p.setPen(QPen(QColor.fromHsv(hue, 255, 255, 35), 3))
            p.drawLine(cx, cy, x2, y2)
        # Coloured disco strip over the taskbar area.
        gradient = QLinearGradient(0, h - 30, w, h)
        gradient.setColorAt(0.0, QColor(255, 0, 130, 50))
        gradient.setColorAt(0.5, QColor(80, 70, 255, 55))
        gradient.setColorAt(1.0, QColor(0, 230, 255, 50))
        p.fillRect(0, h - 30, w, 30, gradient)

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
        self.icon_timer.stop()
        self.player.stop()
        self.icon_dance.stop()
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
