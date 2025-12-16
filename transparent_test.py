from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QLabel, QHBoxLayout)
from PyQt6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QPixmap, QPalette, QBrush, QColor, QKeyEvent
import subprocess
import requests
import sys
from io import BytesIO
from PIL import Image, ImageFilter, ImageEnhance
import colorsys

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

CSS_TEMPLATE = """
QMainWindow {{
    background-color: transparent;
}}
"""

class SpotifyNowPlaying(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Now Playing")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.setStyleSheet(CSS_TEMPLATE)
        
        # Make window frameless and stay on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

def main():
    app = QApplication(sys.argv)
    window = SpotifyNowPlaying()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
