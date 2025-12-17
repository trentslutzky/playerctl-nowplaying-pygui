#!/usr/bin/env python3

import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QLabel, QHBoxLayout)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QPalette, QBrush, QColor, QKeyEvent
import subprocess
import requests
import sys
from io import BytesIO
from PIL import Image, ImageFilter, ImageEnhance
import colorsys

# Customization constants
AUTO_REFRESH_SECONDS = 0.1  # 100ms refresh

# Background blur and dim settings
BACKGROUND_BLUR_RADIUS = 50
BACKGROUND_DIM_FACTOR = 0.3  # 0.0 = black, 1.0 = full brightness


# Status text customization
STATUS_TEXT = {
    "Playing": "",
    "Paused": "󰏤 PAUSED",
    "Stopped": "STOPPED"
}

CSS_TEMPLATE = """
QMainWindow {{
    background-color: #000000;
}}
QLabel {{
    color: {primary_color};
    font-size: {primary_font_size}px;
    font-family: JetBrainsMono Nerd Font;
    background-color: transparent;
}}
QLabel#status {{
    color: {tertiary_color};
    font-size: {secondary_font_size}px;
    background-color: transparent;
    text-transform: uppercase;
}}
QLabel#info {{
    color: {secondary_color};
    font-size: {tertiary_font_size}px;
    background-color: transparent;
}}
QLabel#artist {{
    color: {tertiary_color};
    font-size: {secondary_font_size}px;
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
        self.setWindowTitle("playerctl-spotify-now-playing")

        self.showFullScreen()

        self.auto_change_workspcace = True
        self.current_workspace = -1

        self.current_window_width = 1920
        self.current_window_height = 1080
        self.album_art_size = self.current_window_width // 3

        self.primary_color = "#ffffff"
        self.secondary_color = "#888888"
        self.tertiary_color = "#555555"
        
        # Sleep inhibit process
        self.inhibit_process = None
        self.is_playing = False
        
        # Default colors
        self.update_css()
        
        # Image cache
        self.image_cache = {}
        self.current_art_url = None
        
        # Create a stacked layout with background
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Base layout for stacking
        base_layout = QVBoxLayout(central_widget)
        base_layout.setContentsMargins(0, 0, 0, 0)
        
        # Background label (bottom layer)
        self.background_label = QLabel(central_widget)
        self.background_label.setScaledContents(True)
        self.background_label.lower()  # Send to back
        
        # Content widget (top layer)
        self.content_widget = QWidget(central_widget)
        self.content_widget.setObjectName("container")
        
        self.main_layout = QHBoxLayout(self.content_widget)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.main_layout.setContentsMargins(60, 60, 60, 60)
        
        # Left side - Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        info_layout.setObjectName("info_layout")
        info_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        
        # Status (Playing/Paused)
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self.status_label)
        
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
        self.album_art.setFixedSize(self.album_art_size, self.album_art_size)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art.setScaledContents(True)
        art_layout.addWidget(self.album_art)
        
        # Add both sides to main layout
        self.main_layout.addLayout(info_layout, 0)
        self.main_layout.addLayout(art_layout, 0)
        
        # Initial load
        self.refresh()
        
        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(int(AUTO_REFRESH_SECONDS * 1000))
        
    def start_inhibit(self):
        """Start systemd-inhibit to prevent sleep"""
        if self.inhibit_process is None:
            try:
                # Start systemd-inhibit with sleep and idle locks
                self.inhibit_process = subprocess.Popen(
                    ['systemd-inhibit',
                     '--what=sleep:idle',
                     '--who=spotify-now-playing',
                     '--why=Music is playing',
                     '--mode=block',
                     'tail', '-f', '/dev/null'],  # Keep process alive
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("Started sleep inhibit")
            except Exception as e:
                print(f"Error starting inhibit: {e}")
    
    def stop_inhibit(self):
        """Stop the systemd-inhibit process"""
        if self.inhibit_process is not None:
            try:
                self.inhibit_process.terminate()
                self.inhibit_process.wait(timeout=2)
                print("Stopped sleep inhibit")
            except subprocess.TimeoutExpired:
                self.inhibit_process.kill()
                print("Forcefully killed sleep inhibit")
            except Exception as e:
                print(f"Error stopping inhibit: {e}")
            finally:
                self.inhibit_process = None
    
    def update_inhibit_state(self, metadata, status):
        """Update sleep inhibit based on playback state"""
        should_inhibit = metadata is not None and status == "Playing"
        
        if should_inhibit and not self.is_playing:
            # Started playing
            self.start_inhibit()
            self.is_playing = True
        elif not should_inhibit and self.is_playing:
            # Stopped playing or paused
            self.stop_inhibit()
            self.is_playing = False
    
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

            if self.auto_change_workspcace and self.current_workspace != 2:
                self.current_workspace = 2
                os.system("hyprctl dispatch workspace 2")
            
            return metadata
        except (subprocess.CalledProcessError, FileNotFoundError):
            if self.auto_change_workspcace and self.current_workspace != 1:
                self.current_workspace = 1
                os.system("hyprctl dispatch workspace 1")
            return None
    
    def get_playerctl_status(self):
        """Get the current playback status"""
        try:
            result = subprocess.run(
                ['playerctl', 'status'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def get_average_color(self, image):
        """Get the most vibrant/saturated color from an image"""
        # Convert to RGB if needed (handles RGBA, P, L modes)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize to small size for faster processing
        small_image = image.resize((50, 50), Image.LANCZOS)
        pixels = list(small_image.getdata())
        
        # Filter out very dark pixels (likely backgrounds)
        bright_pixels = [p for p in pixels if sum(p) > 100]
        
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
    
    def update_css(self):
        """Update the stylesheet with new colors"""
        css = CSS_TEMPLATE.format(
            primary_color=self.primary_color,
            secondary_color=self.secondary_color,
            tertiary_color=self.tertiary_color,
            primary_font_size=max(self.current_window_width // 40, 30),
            secondary_font_size=max(self.current_window_width // 50, 24),
            tertiary_font_size=max(self.current_window_width // 60, 18)
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
            dimmed = dimmed.resize((self.current_window_width, self.current_window_height), Image.LANCZOS)
            
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
            # Check if this is a new URL
            if url == self.current_art_url:
                return  # Already loaded, no need to fetch again
            
            # Check cache first
            if url in self.image_cache:
                print(f"Loading from cache: {url}")
                image = self.image_cache[url]
            else:
                print(f"Fetching new image: {url}")
                response = requests.get(url, timeout=5)
                image = Image.open(BytesIO(response.content))
                
                # Convert to RGB if needed
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Cache the image
                self.image_cache[url] = image.copy()
            
            # Update current URL
            self.current_art_url = url
            
            # Get average color and create color palette
            avg_color = self.get_average_color(image)
            
            # Make primary color brighter (150% brightness)
            primary_rgb = self.adjust_brightness(avg_color, 1.5)
            self.primary_color = f"rgb({primary_rgb[0]}, {primary_rgb[1]}, {primary_rgb[2]})"
            
            # Make secondary color bright (120% brightness)
            secondary_rgb = self.adjust_brightness(avg_color, 1.2)
            self.secondary_color = f"rgb({secondary_rgb[0]}, {secondary_rgb[1]}, {secondary_rgb[2]})"
            
            # Make tertiary color normal brightness (100%)
            self.tertiary_color = f"rgb({avg_color[0]}, {avg_color[1]}, {avg_color[2]})"
            
            # Update colors
            self.update_css()
            
            # Set background
            self.set_background_image(image.copy())
            
            # Then set the album art
            resized = image.resize((self.album_art_size, self.album_art_size), Image.LANCZOS)
            
            # Convert to QPixmap
            image_bytes = BytesIO()
            resized.save(image_bytes, format='PNG')
            image_bytes.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(image_bytes.read())
            self.album_art.setPixmap(pixmap)
        except Exception as e:
            print(f"Error loading album art: {e}")
            self.show_placeholder_art()
    
    def show_placeholder_art(self):
        """Show a placeholder when no art is available"""
        pixmap = QPixmap(self.album_art_size, self.album_art_size)
        pixmap.fill(Qt.GlobalColor.darkGray)
        self.album_art.setPixmap(pixmap)
        
        # Reset background to black
        black_pixmap = QPixmap(self.current_window_width, self.current_window_height)
        black_pixmap.fill(Qt.GlobalColor.black)
        self.background_label.setPixmap(black_pixmap)
        
        # Reset colors to default
        self.update_css()
        
        # Clear current URL
        self.current_art_url = None
    
    def refresh(self):
        """Refresh the now playing information"""
        metadata = self.get_playerctl_metadata()
        status = self.get_playerctl_status()
        
        # Update sleep inhibit state based on playback
        self.update_inhibit_state(metadata, status)

        (width, height) = (self.width(), self.height())
        if (width != self.current_window_width) or (height != self.current_window_height):
            self.current_window_width = width
            self.current_window_height = height
            self.content_widget.setGeometry(0, 0, width, height)
            self.background_label.setGeometry(0, 0, width, height)
            self.album_art_size = width // 3
            self.album_art.setFixedSize(self.album_art_size, self.album_art_size)
            margin = width // 25
            self.main_layout.setContentsMargins(margin, margin, margin, margin)
            self.update_css()
            print(f"Window resized to: {width}x{height}")
        
        if metadata:
            title = metadata.get('xesam:title', 'Unknown Title')
            artist = metadata.get('xesam:artist', 'Unknown Artist')
            album = metadata.get('xesam:album', 'Unknown Album')
            length = metadata.get('mpris:length', '0')
            track_num = metadata.get('xesam:trackNumber', '')
            art_url = metadata.get('mpris:artUrl', '')
            
            # Update status
            if status:
                custom_status = STATUS_TEXT.get(status, status.upper())
                self.status_label.setText(custom_status)
            else:
                self.status_label.setText("")
            
            self.title_label.setText(title)
            self.artist_label.setText(artist)
            self.album_label.setText(f"󰀥 {album}")
            
            if art_url:
                self.load_album_art(art_url)
            else:
                self.show_placeholder_art()
        else:
            self.status_label.setText("")
            self.title_label.setText("No track playing")
            self.artist_label.setText("Open Spotify and play a song")
            self.album_label.setText("")
            self.show_placeholder_art()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events"""
        if event.key() == Qt.Key.Key_Space:
            try:
                subprocess.run(['playerctl', 'play-pause'], check=True)
                print("Toggled play/pause")
            except subprocess.CalledProcessError as e:
                print(f"Error toggling play/pause: {e}")
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Clean up when closing the application"""
        self.stop_inhibit()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    window = SpotifyNowPlaying()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
