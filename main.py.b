#!/usr/bin/env python3

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QLabel, QHBoxLayout)
from PyQt6.QtCore import QTimer, Qt, QFileSystemWatcher
from PyQt6.QtGui import QPixmap
import subprocess
import requests
import sys
import os
from io import BytesIO
from PIL import Image

# Customization constants
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
ALBUM_ART_SIZE = 800
AUTO_REFRESH_SECONDS = 5

# CSS file path
CSS_FILE = os.path.join(os.path.dirname(__file__), 'style.css')

class SpotifyNowPlaying(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Now Playing")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Load stylesheet
        self.load_stylesheet()
        
        # Central widget and layout
        central_widget = QWidget()
        central_widget.setObjectName("container")
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        main_layout.setSpacing(40)
        main_layout.setContentsMargins(40, 40, 40, 40)
        central_widget.setLayout(main_layout)
        
        # Left side - Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(20)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Title
        self.title_label = QLabel("No track playing")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.title_label)
        
        # Artist
        self.artist_label = QLabel("Unknown Artist")
        self.artist_label.setObjectName("artist")
        self.artist_label.setWordWrap(True)
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.artist_label)
        
        # Album
        self.album_label = QLabel("")
        self.album_label.setObjectName("info")
        self.album_label.setWordWrap(True)
        self.album_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.album_label)
        
        info_layout.addStretch()
        
        # Right side - Album art
        art_layout = QVBoxLayout()
        art_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.album_art = QLabel()
        self.album_art.setObjectName("albumArt")
        self.album_art.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setScaledContents(True)
        art_layout.addWidget(self.album_art)
        
        # Add both sides to main layout
        main_layout.addLayout(info_layout, 1)  # Stretch factor 1
        main_layout.addLayout(art_layout, 0)   # No stretch
        
        # Initial load
        self.refresh_metadata()
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_metadata)
        self.timer.start(AUTO_REFRESH_SECONDS * 1000)
        
        # Watch CSS file for changes
        if os.path.exists(CSS_FILE):
            self.css_watcher = QFileSystemWatcher([CSS_FILE])
            self.css_watcher.fileChanged.connect(self.reload_stylesheet)
            print(f"Watching {CSS_FILE} for changes...")
        else:
            self.css_watcher = None
    
    def load_stylesheet(self):
        """Load CSS stylesheet"""
        if os.path.exists(CSS_FILE):
            print(f"Loading CSS from: {CSS_FILE}")
            with open(CSS_FILE, 'r') as f:
                self.setStyleSheet(f.read())
        else:
            print(f"CSS file not found at: {CSS_FILE}, using fallback")
            # Fallback inline CSS
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #000000;
                }
                #container {
                    background-color: #000000;
                }
                #albumArt {
                    background-color: #000000;
                }
                #title {
                    color: #FFFFFF;
                    font-size: 18pt;
                    font-weight: bold;
                    background-color: #000000;
                }
                #artist {
                    color: #FFFFFF;
                    font-size: 14pt;
                    background-color: #000000;
                }
                #info {
                    color: #888888;
                    font-size: 10pt;
                    background-color: #000000;
                }
            """)
    
    def reload_stylesheet(self, path):
        """Reload stylesheet when CSS file changes"""
        print(f"CSS file changed, reloading...")
        # Re-add the file to the watcher (some editors remove the file on save)
        if self.css_watcher and path not in self.css_watcher.files():
            self.css_watcher.addPath(path)
        self.load_stylesheet()
    
    def get_playerctl_metadata(self):
        """Fetch metadata from playerctl"""
        try:
            result = subprocess.run(
                ['playerctl', 'metadata'],
                capture_output=True,
                text=True,
                check=True
            )
            
            metadata = {}
            for line in result.stdout.strip().split('\n'):
                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    key = parts[1]
                    value = parts[2]
                    metadata[key] = value
            
            return metadata
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def load_album_art(self, url):
        """Download and display album art"""
        try:
            response = requests.get(url, timeout=5)
            image = Image.open(BytesIO(response.content))
            image = image.resize((ALBUM_ART_SIZE, ALBUM_ART_SIZE), Image.LANCZOS)
            
            # Convert to QPixmap
            image_bytes = BytesIO()
            image.save(image_bytes, format='PNG')
            image_bytes.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(image_bytes.read())
            self.album_art.setPixmap(pixmap)
        except Exception as e:
            print(f"Error loading album art: {e}")
            self.show_placeholder_art()
    
    def show_placeholder_art(self):
        """Show a placeholder when no art is available"""
        pixmap = QPixmap(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        pixmap.fill(Qt.GlobalColor.darkGray)
        self.album_art.setPixmap(pixmap)
    
    def refresh_metadata(self):
        """Refresh the now playing information"""
        metadata = self.get_playerctl_metadata()
        
        if metadata:
            title = metadata.get('xesam:title', 'Unknown Title')
            artist = metadata.get('xesam:artist', 'Unknown Artist')
            album = metadata.get('xesam:album', 'Unknown Album')
            art_url = metadata.get('mpris:artUrl', '')
            
            self.title_label.setText(title)
            self.artist_label.setText(artist)
            self.album_label.setText(f"Album: {album}")
            
            if art_url:
                self.load_album_art(art_url)
            else:
                self.show_placeholder_art()
        else:
            self.title_label.setText("No track playing")
            self.artist_label.setText("Open Spotify and play a song")
            self.album_label.setText("")
            self.show_placeholder_art()

def main():
    app = QApplication(sys.argv)
    window = SpotifyNowPlaying()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
