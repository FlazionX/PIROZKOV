import sys
import random
import re
import math
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
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
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        try:
            start, end = [to_ms(part) for part in lines[1].split("-->")]
            result.append((start, end, " ".join(lines[2:])))
        except (ValueError, IndexError):
            pass
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
            self.image.setText("PIROZKOV")
            self.image.setStyleSheet("color:#ffdf55;font-size:22px;font-weight:900;")
        self.setFixedSize(200, 240)

class Prank(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PIROZKOV.exe")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showFullScreen()
        self.phase = 0
        self.photos = []
        self.cards = []
        self.captions = parse_srt(SUBTITLES)
        self.last_caption = -1

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.85)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        if MUSIC.exists():
            self.player.setSource(QUrl.fromLocalFile(str(MUSIC)))
            self.player.play()

        self.icons = []
        names = ["Этот компьютер", "Корзина", "Папка", "PIROZKOV", "Музыка", "Фото", "Игры", "Документы"]
        for i, name in enumerate(names):
            icon = QLabel("🖥️\n" + name, self)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("color:white;background:rgba(15,15,30,145);border:1px solid white;border-radius:9px;padding:7px;font-size:13px;")
            icon.setFixedSize(104, 72)
            icon.move(35 + (i % 4) * 125, 55 + (i // 4) * 105)
            self.icons.append(icon)

        self.caption = QLabel("", self)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet("color:white;background:rgba(20,10,35,210);border:2px solid white;border-radius:14px;padding:12px;font-size:23px;font-weight:900;")

        self.skip = QPushButton("ПРОПУСТИТЬ", self)
        self.skip.setStyleSheet("QPushButton{background:#ffdf3e;color:#16121f;border:0;border-radius:12px;padding:12px 22px;font-size:16px;font-weight:900;} QPushButton:hover{background:white;}")
        self.skip.clicked.connect(self.finish)
        self.skip.adjustSize()
        self.skip.move(self.width() - self.skip.width() - 28, 24)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(35)
        self.caption_timer = QTimer(self)
        self.caption_timer.timeout.connect(self.update_caption)
        self.caption_timer.start(100)
        QTimer.singleShot(100, self.load_photos)

    def load_photos(self):
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        for index, url in enumerate(PHOTO_URLS, 1):
            target = PHOTO_DIR / f"pirozkov_{index}.jpg"
            if not target.exists():
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "PIROZKOV-Prank/1.0"})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        target.write_bytes(response.read())
                except Exception:
                    continue
        for file in sorted(PHOTO_DIR.glob("*")):
            pixmap = QPixmap(str(file))
            if not pixmap.isNull():
                self.photos.append(pixmap)
        if not self.photos:
            self.photos = [QPixmap()]

    def animate(self):
        self.phase += 1
        self.update()
        for i, icon in enumerate(self.icons):
            x = 35 + (i % 4) * 125 + int(12 * math.sin(self.phase / 7 + i))
            y = 55 + (i // 4) * 105 + int(16 * math.sin(self.phase / 5 + i * 1.7))
            icon.move(x, y)
            icon.setStyleSheet(
                f"color:white;background:rgba(15,15,30,145);border:2px solid hsla({(self.phase*3+i*35)%360},100%,75%,0.95);"
                "border-radius:9px;padding:7px;font-size:13px;"
            )
        if self.phase % 30 == 0:
            self.spawn_photo()

    def spawn_photo(self):
        if not self.photos:
            return
        card = PhotoCard(random.choice(self.photos), self)
        card.move(random.randint(25, max(26, self.width()-225)), random.randint(80, max(81, self.height()-330)))
        card.show()
        card.raise_()
        self.cards.append(card)
        if len(self.cards) > 7:
            self.cards.pop(0).deleteLater()
        self.skip.raise_()
        self.caption.raise_()

    def update_caption(self):
        if not self.captions:
            return
        position = self.player.position()
        for index, (start, end, text) in enumerate(self.captions):
            if start <= position <= end:
                if index != self.last_caption:
                    self.caption.setText(text)
                    self.caption.adjustSize()
                    bubble_w, bubble_h = 390, 88
                    self.caption.setGeometry(
                        random.randint(25, max(26, self.width()-bubble_w-25)),
                        random.randint(110, max(111, self.height()-bubble_h-110)),
                        bubble_w, bubble_h
                    )
                    self.caption.raise_()
                    self.last_caption = index
                return
        if self.caption.text():
            self.caption.clear()

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finish()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor.fromHsv((self.phase * 2) % 360, 220, 230))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 55))

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
        QMessageBox.information(None, "PIROZKOV.exe", "Положи свой аудиофайл «Само собой» в assets/samo_soboy.mp3. Затем запусти программу снова.")
    window = Prank()
    sys.exit(app.exec())
