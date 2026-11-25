import sys
import random
import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPoint, QUrl
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QMessageBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MUSIC = ASSETS / "samo_soboy.mp3"
SUBTITLES = ASSETS / "captions.srt"

# Public image URLs are loaded at runtime; see README for source/attribution.
PHOTO_URLS = [
    "https://cdn.informator.ua/%40dp/media/kiev/2023/10/12/65281577f0444.jpg",
    "https://salvemusic.com.ua/wp-content/uploads/2019/11/pirozhkov1.jpg",
    "https://www.concert-star.ru/wp-content/uploads/2019/10/13022019-006.jpg",
]

def parse_srt(path):
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    blocks = re.split(r"\\n\\s*\\n", raw.strip())
    result = []
    def ms(stamp):
        h, m, rest = stamp.split(":")
        s, milli = rest.replace(",", ".").split(".")
        return ((int(h)*60 + int(m))*60 + int(s))*1000 + int(milli.ljust(3, "0")[:3])
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        try:
            start, end = [ms(x.strip()) for x in lines[1].split("-->")]
            result.append((start, end, " ".join(lines[2:])))
        except Exception:
            continue
    return result

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
            self.image.setText("PIROZHKOV")
            self.image.setStyleSheet("color:#ffdf55;font-size:22px;font-weight:900;")
        self.setFixedSize(200, 240)

class Prank(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PIROZKOV.exe")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setCursor(Qt.BlankCursor)
        self.showFullScreen()
        self.started_at = 0
        self.photos = []
        self.cards = []
        self.captions = parse_srt(SUBTITLES)
        self.last_caption = -1
        self.phase = 0

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.85)
        if MUSIC.exists():
            self.player.setSource(QUrl.fromLocalFile(str(MUSIC)))
            self.player.durationChanged.connect(self.on_duration)
            self.player.play()

        self.icons = []
        names = ["Этот компьютер", "Корзина", "Папка", "PIROZKOV", "Музыка", "Фото", "Игры", "Документы"]
        for i, name in enumerate(names):
            icon = QLabel("🖥️\n" + name, self)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("color:white;background:rgba(15,15,30,145);border:1px solid rgba(255,255,255,90);border-radius:9px;padding:7px;font-size:13px;")
            icon.setFixedSize(104, 72)
            icon.move(35 + (i % 4) * 125, 55 + (i // 4) * 105)
            self.icons.append(icon)

        self.caption = QLabel("", self)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet("color:white;background:rgba(20,10,35,205);border:2px solid #fff;border-radius:14px;padding:12px;font-size:23px;font-weight:900;")
        self.caption.setGeometry(0, self.height()-145, self.width(), 90)

        self.skip = QPushButton("ПРОПУСТИТЬ", self)
        self.skip.setStyleSheet("QPushButton{background:#ffdf3e;color:#16121f;border:0;border-radius:12px;padding:12px 22px;font-size:16px;font-weight:900;} QPushButton:hover{background:white;}")
        self.skip.clicked.connect(self.finish)
        self.skip.adjustSize()
        self.skip.move(self.width()-self.skip.width()-28, 24)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_caption)
        self.caption_timer.start(100)
        QTimer.singleShot(500, self.load_photos)

    def on_duration(self, duration):
        self.duration = duration

    def load_photos(self):
        # Qt's network stack is intentionally not used here; local photos can be
        # placed in assets/photos/ for offline use. Remote images are optional.
        folder = ASSETS / "photos"
        folder.mkdir(parents=True, exist_ok=True)
        for file in list(folder.glob("*.jpg")) + list(folder.glob("*.png")):
            pix = QPixmap(str(file))
            if not pix.isNull():
                self.photos.append(pix)
        if not self.photos:
            self.photos = [QPixmap()]

    def animate(self):
        self.phase += 1
        self.update()
        for i, icon in enumerate(self.icons):
            x = 35 + (i % 4) * 125 + int(9 * __import__("math").sin(self.phase/7 + i))
            y = 55 + (i // 4) * 105 + int(12 * __import__("math").sin(self.phase/5 + i*1.7))
            icon.move(x, y)
            icon.setStyleSheet(f"color:white;background:rgba(15,15,30,145);border:1px solid hsla({(self.phase*3+i*35)%360},100%,75%,0.9);border-radius:9px;padding:7px;font-size:13px;")
        if self.phase % 32 == 0:
            self.spawn_photo()

    def spawn_photo(self):
        if not self.photos:
            return
        pix = random.choice(self.photos)
        card = PhotoCard(pix, self)
        x = random.randint(30, max(31, self.width()-220))
        y = random.randint(80, max(81, self.height()-330))
        card.move(x, y)
        card.show()
        card.raise_()
        self.cards.append(card)
        if len(self.cards) > 7:
            old = self.cards.pop(0)
            old.deleteLater()
        self.skip.raise_()
        self.caption.raise_()

    def update_caption(self):
        if not self.captions:
            return
        pos = self.player.position()
        for idx, (start, end, text) in enumerate(self.captions):
            if start <= pos <= end:
                if idx != self.last_caption:
                    self.caption.setText(text)
                    self.caption.adjustSize()
                    self.caption.setGeometry(80, self.height()-self.caption.height()-35, self.width()-160, self.caption.height())
                    self.caption.raise_()
                    self.last_caption = idx
                return
        self.caption.setText("")

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor.fromHsv((self.phase*2) % 360, 210, 210))
        p.fillRect(self.rect(), QColor(0, 0, 0, 65))

    def finish(self):
        self.timer.stop()
        self.caption_timer.stop()
        self.player.stop()
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_F10):
            self.finish()
        else:
            super().keyPressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    if not MUSIC.exists():
        QMessageBox.information(None, "PIROZKOV.exe", "Добавь свой аудиофайл assets/samo_soboy.mp3, чтобы запустить музыкальный розыгрыш.")
    window = Prank()
    sys.exit(app.exec())
