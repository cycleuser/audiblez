# PySide6-based GUI for Audiblez with UI language switching and multi-threaded processing

import argparse
import sys
import time
import shutil
import subprocess
import soundfile as sf
import ebooklib
import warnings
import re
from pathlib import Path
from string import Formatter
from bs4 import BeautifulSoup
from kokoro_onnx import Kokoro
from ebooklib import ITEM_DOCUMENT, epub
from pydub import AudioSegment
from pick import pick
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QSpinBox, QMessageBox, QToolBar, QProgressBar
)

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QFileDialog
from PySide6.QtCore import Qt, QThread, Signal

# Change working directory to the script's directory
current_file_path = os.path.abspath(__file__)
current_directory = os.path.dirname(current_file_path)
os.chdir(current_directory)
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QFileDialog,
    QComboBox, QLineEdit, QProgressBar, QVBoxLayout, QWidget, QHBoxLayout
)
from audiblez import main  # Ensure audiblez.py is importable
from pathlib import Path

class AudiblezGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audiblez - E-book to Audiobook Converter")
        
        # Initialize Kokoro
        if not Path('kokoro-v0_19.onnx').exists() or not Path('voices.json').exists():
            QMessageBox.critical(self, "Error", "kokoro-v0_19.onnx and voices.json must be in the current directory.")
            sys.exit(1)
        self.kokoro = Kokoro('kokoro-v0_19.onnx', 'voices.json')
        self.kokoro.sess.set_providers(['CUDAExecutionProvider', 'CPUExecutionProvider'])
        
        # Get voices
        self.voices = list(self.kokoro.get_voices())
        
        # Layouts
        layout = QVBoxLayout()
        
        # EPUB File Selection
        file_layout = QHBoxLayout()
        self.file_label = QLabel("EPUB File:")
        self.file_input = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_button)
        
        # Language Selection
        lang_layout = QHBoxLayout()
        self.lang_label = QLabel("Language:")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(['en-gb', 'en-us', 'fr-fr', 'ja', 'ko', 'cmn'])
        lang_layout.addWidget(self.lang_label)
        lang_layout.addWidget(self.lang_combo)
        
        # Voice Selection
        voice_layout = QHBoxLayout()
        self.voice_label = QLabel("Voice:")
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.voices)
        voice_layout.addWidget(self.voice_label)
        voice_layout.addWidget(self.voice_combo)
        
        # Speed Selection
        speed_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed:")
        self.speed_input = QLineEdit("1.0")
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.speed_input)
        
        # Conversion Button
        self.convert_button = QPushButton("Start Conversion")
        self.convert_button.clicked.connect(self.start_conversion)
        
        # Progress Bar
        self.progress = QProgressBar()
        
        # Add widgets to layout
        layout.addLayout(file_layout)
        layout.addLayout(lang_layout)
        layout.addLayout(voice_layout)
        layout.addLayout(speed_layout)
        layout.addWidget(self.convert_button)
        layout.addWidget(self.progress)
        
        # Set central widget
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
    
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select EPUB File", "", "EPUB Files (*.epub)")
        if file_path:
            self.file_input.setText(file_path)
    
    def start_conversion(self):
        file_path = self.file_input.text()
        lang = self.lang_combo.currentText()
        voice = self.voice_combo.currentText()
        try:
            speed = float(self.speed_input.text())
        except ValueError:
            self.statusBar().showMessage("Invalid speed value.")
            return
        
        if not Path(file_path).exists():
            self.statusBar().showMessage("EPUB file does not exist.")
            return
        
        try:
            main(self.kokoro, file_path, lang, voice, False, speed)
            self.progress.setValue(100)
            self.statusBar().showMessage("Conversion completed successfully.")
        except Exception as e:
            self.statusBar().showMessage(f"Error: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudiblezGUI()
    window.show()
    sys.exit(app.exec())