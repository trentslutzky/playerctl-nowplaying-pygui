#!/usr/bin/env python3

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QLabel, QHBoxLayout)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QPalette, QBrush, QColor
import subprocess
import requests
import sys
from io import BytesIO
from PIL import Image, ImageFilter, ImageEnhance
import colorsys

# Customization constants
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
ALBUM_ART_SIZE = 959
AUTO_REFRESH_SECONDS = 1

# Background blur and dim settings
BACKGROUND_BLUR_RADIUS = 50
BACKGROUND_DIM_FACTOR = 0.3  # 0.0 = black, 1.0 = full brightness

CSS_TEMPLATE = """
QMainWindow {{
    background-color: #000000;
}}
QLabel {{
    color: {primary_color};
    font-size: 40px;
    font-family: JetBrainsMono Nerd Font;
    background-color: transparent;
}}
QLabel#info {{
    color: {secondary_color};
    font-size: 30px;
    background-color: transparent;
}}
QLabel#artist {{
    color: {tertiary_color};
    font-size: 35px;
    background-color: transparent;
}}
QLabel#albumArt {{
    background-color: #000000;
}}
QWidget#container {{
    background-color: transparent;
}}
"""

class SpotifyNowPlaying(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Now Playing")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Default colors
        self.update_colors("#ffffff", "#888888", "#555555")
        
        # Create a stacked layout with background
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Base layout for stacking
        base_layout = QVBoxLayout(central_widget)
        base_layout.setContentsMargins(0, 0, 0, 0)
        
        # Background label (bottom layer)
        self.background_label = QLabel(central_widget)
        self.background_label.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.background_label.setScaledContents(True)
        self.background_label.lower()  # Send to back
        
        # Content widget (top layer)
        content_widget = QWidget(central_widget)
        content_widget.setObjectName("container")
        content_widget.setGeometry(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        
        main_layout = QHBoxLayout(content_widget)
        main_layout.setSpacing(60)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        main_layout.setContentsMargins(60, 60, 60, 60)
        
        # Left side - Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        info_layout.setObjectName("info_layout")
        info_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        # Artist
        self.artist_label = QLabel("Unknown Artist")
        self.artist_label.setObjectName("artist")
        self.artist_label.setWordWrap(True)
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.artist_label)
        
        # Title
        self.title_label = QLabel("No track playing")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.title_label)

        # Album
        self.album_label = QLabel("")
        self.album_label.setObjectName("info")
        self.album_label.setWordWrap(True)
        self.album_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.album_label)
        
        # Right side - Album art
        art_layout = QVBoxLayout()
        art_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        self.album_art = QLabel()
        self.album_art.setObjectName("albumArt")
        self.album_art.setFixedSize(ALBUM_ART_SIZE, ALBUM_ART_SIZE)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setScaledContents(True)
        art_layout.addWidget(self.album_art)
        
        # Add both sides to main layout
        main_layout.addLayout(info_layout, 0)
        main_layout.addLayout(art_layout, 0)
        
        # Initial load
        self.refresh_metadata()
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_metadata)
        self.timer.start(AUTO_REFRESH_SECONDS * 1000)
        
    
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
    
    def get_average_color(self, image):
        """Get the most vibrant/saturated color from an image"""
        # Resize to small size for faster processing
        small_image = image.resize((50, 50), Image.LANCZOS)
        pixels = list(small_image.getdata())
        
        # Filter out very dark pixels (likely backgrounds)
        bright_pixels = [p for p in pixels if sum(p[:3]) > 100]
        
        # If we have bright pixels, use those
        if bright_pixels:
            pixels = bright_pixels
        
        # Calculate average RGB
        r_avg = sum(p[0] for p in pixels) // len(pixels)
        g_avg = sum(p[1] for p in pixels) // len(pixels)
        b_avg = sum(p[2] for p in pixels) // len(pixels)
        
        # Check if the result is too dark
        brightness = (r_avg + g_avg + b_avg) / 3
        if brightness < 80:  # Too dark, return white
            return (255, 255, 255)
        
        return (r_avg, g_avg, b_avg)
    
    def adjust_brightness(self, rgb, factor):
        """Adjust the brightness of an RGB color"""
        h, l, s = colorsys.rgb_to_hls(rgb[0]/255, rgb[1]/255, rgb[2]/255)
        l = max(0, min(1, l * factor))
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r * 255), int(g * 255), int(b * 255))
    
    def update_colors(self, primary, secondary, tertiary):
        """Update the stylesheet with new colors"""
        css = CSS_TEMPLATE.format(
            primary_color=primary,
            secondary_color=secondary,
            tertiary_color=tertiary
        )
        self.setStyleSheet(css)
    
    def set_background_image(self, image):
        """Set blurred and dimmed album art as background"""
        try:
            # Blur the image
            blurred = image.filter(ImageFilter.GaussianBlur(radius=BACKGROUND_BLUR_RADIUS))
            
            # Dim the image
            enhancer = ImageEnhance.Brightness(blurred)
            dimmed = enhancer.enhance(BACKGROUND_DIM_FACTOR)
            
            # Resize to window size
            dimmed = dimmed.resize((WINDOW_WIDTH, WINDOW_HEIGHT), Image.LANCZOS)
            
            # Convert to QPixmap
            image_bytes = BytesIO()
            dimmed.save(image_bytes, format='PNG')
            image_bytes.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(image_bytes.read())
            
            # Set as background label
            self.background_label.setPixmap(pixmap)
        except Exception as e:
            print(f"Error setting background: {e}")
    
    def load_album_art(self, url):
        """Download and display album art"""
        try:
            response = requests.get(url, timeout=5)
            image = Image.open(BytesIO(response.content))
            
            # Get average color and create color palette
            avg_color = self.get_average_color(image)
            
            # Make primary color brighter (150% brightness)
            primary_rgb = self.adjust_brightness(avg_color, 1.5)
            primary = f"rgb({primary_rgb[0]}, {primary_rgb[1]}, {primary_rgb[2]})"
            
            # Make secondary color bright (120% brightness)
            secondary_rgb = self.adjust_brightness(avg_color, 1.2)
            secondary = f"rgb({secondary_rgb[0]}, {secondary_rgb[1]}, {secondary_rgb[2]})"
            
            # Make tertiary color normal brightness (100%)
            tertiary = f"rgb({avg_color[0]}, {avg_color[1]}, {avg_color[2]})"
            
            # Update colors
            self.update_colors(primary, tertiary, secondary)
            
            # Set background
            self.set_background_image(image.copy())
            
            # Then set the album art
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
        
        # Reset background to black
        black_pixmap = QPixmap(WINDOW_WIDTH, WINDOW_HEIGHT)
        black_pixmap.fill(Qt.GlobalColor.black)
        self.background_label.setPixmap(black_pixmap)
        
        # Reset colors to default
        self.update_colors("#ffffff", "#888888", "#555555")
    
    def refresh_metadata(self):
        """Refresh the now playing information"""
        metadata = self.get_playerctl_metadata()
        
        if metadata:
            title = metadata.get('xesam:title', 'Unknown Title')
            artist = metadata.get('xesam:artist', 'Unknown Artist')
            album = metadata.get('xesam:album', 'Unknown Album')
            length = metadata.get('mpris:length', '0')
            track_num = metadata.get('xesam:trackNumber', '')
            art_url = metadata.get('mpris:artUrl', '')
            
            self.title_label.setText(title)
            self.artist_label.setText(artist)
            self.album_label.setText(f"󰀥 {album}")
            
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
