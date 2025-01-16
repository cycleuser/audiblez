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
from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread
from PySide6.QtWebEngineWidgets import QWebEngineView
import concurrent.futures
from multiprocessing import set_start_method

# Change working directory to the script's directory
current_file_path = os.path.abspath(__file__)
current_directory = os.path.dirname(current_file_path)
os.chdir(current_directory)


def extract_texts(chapters):
    texts = []
    for chapter in chapters:
        xml = chapter.get_body_content()
        soup = BeautifulSoup(xml, features='lxml')
        chapter_text = ''
        html_content_tags = ['title', 'p', 'h1', 'h2', 'h3', 'h4']
        for child in soup.find_all(html_content_tags):
            inner_text = child.text.strip() if child.text else ""
            if inner_text:
                chapter_text += inner_text + '\n'
        texts.append(chapter_text)
    return texts


def is_chapter(c):
    name = c.get_name().lower()
    part = r"part\d{1,3}"
    if re.search(part, name):
        return True
    ch = r"ch\d{1,3}"
    if re.search(ch, name):
        return True
    if 'chapter' in name:
        return True


def find_chapters(book, verbose=False):
    chapters = [c for c in book.get_items() if c.get_type() == ebooklib.ITEM_DOCUMENT and is_chapter(c)]
    if verbose:
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                print(f"'{item.get_name()}'" + ', #' + str(len(item.get_body_content())))
    if len(chapters) == 0:
        print('Not easy to find the chapters, defaulting to all available documents.')
        chapters = [c for c in book.get_items() if c.get_type() == ebooklib.ITEM_DOCUMENT]
    return chapters


def pick_chapters(book):
    all_chapters_names = [c.get_name() for c in book.get_items()]
    title = 'Select which chapters to read in the audiobook'
    selected_chapters = []
    try:
        selected_chapters_names = pick(all_chapters_names, title, multiselect=True, min_selection_count=1)
        selected_chapters_names = [c[0] for c in selected_chapters_names]
        selected_chapters = [c for c in book.get_items() if c.get_name() in selected_chapters_names]
    except Exception as e:
        print(f"Chapter selection cancelled or failed: {e}")
    return selected_chapters


def strfdelta(tdelta, fmt='{D:02}d {H:02}h {M:02}m {S:02}s'):
    remainder = int(tdelta)
    f = Formatter()
    desired_fields = [field_tuple[1] for field_tuple in f.parse(fmt)]
    possible_fields = ('W', 'D', 'H', 'M', 'S')
    constants = {'W': 604800, 'D': 86400, 'H': 3600, 'M': 60, 'S': 1}
    values = {}
    for field in possible_fields:
        if field in desired_fields and field in constants:
            values[field], remainder = divmod(remainder, constants[field])
    return f.format(fmt, **values)


def create_m4b(chapter_files, filename, title, author):
    tmp_filename = filename.replace('.epub', '.tmp.m4a')
    if not Path(tmp_filename).exists():
        combined_audio = AudioSegment.empty()
        for wav_file in chapter_files:
            audio = AudioSegment.from_wav(wav_file)
            combined_audio += audio
        print('Converting to Mp4...')
        combined_audio.export(tmp_filename, format="mp4", codec="aac", bitrate="64k")
    final_filename = filename.replace('.epub', '.m4b')
    print('Creating M4B file...')
    proc = subprocess.run([
        'ffmpeg', '-i', f'{tmp_filename}', '-c', 'copy', '-f', 'mp4',
        '-metadata', f'title={title}',
        '-metadata', f'author={author}',
        f'{final_filename}'
    ])
    Path(tmp_filename).unlink()
    if proc.returncode == 0:
        print(f'{final_filename} created. Enjoy your audiobook.')
        print('Feel free to delete the intermediary .wav chapter files, the .m4b is all you need.')


def process_chapter(args):
    """
    Processes a single chapter to generate its audio file.
    
    Args:
        args (tuple): Contains all necessary parameters.
        
    Returns:
        str: Filename of the generated audio file.
    """
    i, text, file_path, model_path, voices_path, voice, speed, lang = args
    if len(text) == 0:
        return None
    try:
        kokoro = Kokoro(model_path, voices_path)
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        chapter_filename = file_path.replace('.epub', f'_chapter_{i}.wav')
        sf.write(f'{chapter_filename}', samples, sample_rate)
        return chapter_filename
    except Exception as e:
        print(f"Error processing chapter {i}: {e}")
        return None


def audiblez(kokoro, file_path, lang, voice, pick_manually, speed):
    filename = Path(file_path).name
    with warnings.catch_warnings():
        book = epub.read_epub(file_path)
    title = book.get_metadata('DC', 'title')[0][0]
    creator = book.get_metadata('DC', 'creator')[0][0]
    intro = f'{title} by {creator}'
    print(intro)
    print('Found Chapters:', [c.get_name() for c in book.get_items() if c.get_type() == ebooklib.ITEM_DOCUMENT])
    if pick_manually:
        chapters = pick_chapters(book)
    else:
        chapters = find_chapters(book)
    print('Selected chapters:', [c.get_name() for c in chapters])
    texts = extract_texts(chapters)
    has_ffmpeg = shutil.which('ffmpeg') is not None
    if not has_ffmpeg:
        print('\033[91m' + 'ffmpeg not found. Please install ffmpeg to create mp3 and m4b audiobook files.' + '\033[0m')
    total_chars = sum([len(t) for t in texts])
    print('Started at:', time.strftime('%H:%M:%S'))
    print(f'Total characters: {total_chars:,}')
    print('Total words:', len(' '.join(texts).split(' ')))

    i = 1
    chapter_mp3_files = []
    for text in texts:
        if len(text) == 0:
            continue
        chapter_filename = filename.replace('.epub', f'_chapter_{i}.wav')
        chapter_mp3_files.append(chapter_filename)
        if Path(chapter_filename).exists():
            print(f'File for chapter {i} already exists. Skipping')
            i += 1
            continue
        print(f'Reading chapter {i} ({len(text):,} characters)...')
        if i == 1:
            text = intro + '.\n\n' + text
        start_time = time.time()
        
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        sf.write(f'{chapter_filename}', samples, sample_rate)
        end_time = time.time()
        delta_seconds = end_time - start_time
        chars_per_sec = len(text) / delta_seconds
        remaining_chars = sum([len(t) for t in texts[i - 1:]])
        remaining_time = remaining_chars / chars_per_sec
        print(f'Estimated time remaining: {strfdelta(remaining_time)}')
        print('Chapter written to', chapter_filename)
        print(f'Chapter {i} read in {delta_seconds:.2f} seconds ({chars_per_sec:.0f} characters per second)')
        progress = int((total_chars - remaining_chars) / total_chars * 100)
        print('Progress:', f'{progress}%')
        i += 1
    # if has_ffmpeg:
    #     create_m4b(chapter_mp3_files, filename, title, creator)




# Define UI texts for English and Chinese
UI_TEXTS = {
    "en": {
        "window_title": "Audiblez GUI",
        "no_file_selected": "No file selected",
        "select_epub": "Select EPUB File",
        "label_interface_lang": "Interface language:",
        "label_tts_lang": "Select TTS language:",
        "label_voice": "Select voice:",
        "label_speed": "Speed (0.5~2.0, i.e. 50~200):",
        "generate": "Generate",
        "msg_no_epub": "Please select an EPUB file first",
        "msg_done": "Done, audio files have been generated!",
        "msg_error": "Error occurred",
    },
    "zh": {
        "window_title": "Audiblez图形界面",
        "no_file_selected": "未选择文件",
        "select_epub": "选择EPUB文件",
        "label_interface_lang": "界面语言:",
        "label_tts_lang": "选择语音合成语言:",
        "label_voice": "选择声音:",
        "label_speed": "语速 (0.5~2.0，对应 50~200):",
        "generate": "开始生成",
        "msg_no_epub": "请先选择EPUB文件",
        "msg_done": "转换完成，音频文件已生成！",
        "msg_error": "发生错误",
    },
}


class Worker(QObject):
    progress = Signal(int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, file_path, lang, voice, pick_manually, speed):
        super().__init__()
        self.file_path = file_path
        self.lang = lang
        self.voice = voice
        self.pick_manually = pick_manually
        self.speed = speed

    @Slot()
    def run(self):
        
        kokoro = Kokoro('kokoro-v0_19.onnx', 'voices.json')
        kokoro.sess.set_providers(['CUDAExecutionProvider', 'CPUExecutionProvider'])

        voices = list(kokoro.get_voices())
        voices_str = ', '.join(voices)
        try:
            audiblez(
                kokoro,
                file_path=self.file_path,
                lang=self.lang,
                voice=self.voice,
                pick_manually=self.pick_manually,
                speed=self.speed
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def update_progress(self, value):
        if value == -1:
            self.error.emit("An error occurred during audiobook generation.")
        else:
            self.progress.emit(value)


class AudiblezGUI(QMainWindow):
    """
    Main GUI class for Audiblez.
    """
    def __init__(self):
        super().__init__()
        self.current_ui_lang = "en"
        self.setWindowTitle(UI_TEXTS[self.current_ui_lang]["window_title"])
        self.setGeometry(200, 200, 1024, 600)

        # Initialize Kokoro model
        if not (Path('kokoro-v0_19.onnx').exists() and Path('voices.json').exists()):
            QMessageBox.critical(self, "Error", "Kokoro model files not found. Please ensure 'kokoro-v0_19.onnx' and 'voices.json' are in the current directory.")
            sys.exit(1)

        # Initialize Kokoro is no longer necessary here since multiprocessing handles it
        # self.kokoro = Kokoro('kokoro-v0_19.onnx', 'voices.json')
        # self.kokoro.sess.set_providers(['CUDAExecutionProvider', 'CPUExecutionProvider'])
        # self.voices = list(self.kokoro.get_voices())

        # Fetch voices once to populate the combo box
        try:
            temp_kokoro = Kokoro('kokoro-v0_19.onnx', 'voices.json')
            temp_kokoro.sess.set_providers(['CUDAExecutionProvider', 'CPUExecutionProvider'])
            self.voices = list(temp_kokoro.get_voices())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize Kokoro: {e}")
            sys.exit(1)
        del temp_kokoro  # Clean up the temporary Kokoro instance

        # 创建并配置工具栏
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        
        # 选择EPUB按钮
        self.select_button = QPushButton(UI_TEXTS[self.current_ui_lang]["select_epub"])
        self.select_button.clicked.connect(self.select_epub)
        self.toolbar.addWidget(self.select_button)

        # 界面语言下拉
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItem("English", "en")
        self.ui_lang_combo.addItem("中文", "zh")
        self.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)
        self.toolbar.addWidget(QLabel(UI_TEXTS[self.current_ui_lang]["label_interface_lang"] + " "))
        self.toolbar.addWidget(self.ui_lang_combo)

        # TTS语言选择
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["en-gb", "en-us", "fr-fr", "ja", "ko", "cmn", "zh-CN"])
        self.toolbar.addWidget(QLabel(UI_TEXTS[self.current_ui_lang]["label_tts_lang"] + " "))
        self.toolbar.addWidget(self.lang_combo)

        # 声音选择
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.voices)
        self.toolbar.addWidget(QLabel(UI_TEXTS[self.current_ui_lang]["label_voice"] + " "))
        self.toolbar.addWidget(self.voice_combo)

        # 语速选择
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(50, 200)  # Corresponding to 0.5~2.0
        self.speed_spin.setValue(100)      # Default 1.0x speed
        self.toolbar.addWidget(QLabel(UI_TEXTS[self.current_ui_lang]["label_speed"] + " "))
        self.toolbar.addWidget(self.speed_spin)

        # 生成按钮
        self.run_button = QPushButton(UI_TEXTS[self.current_ui_lang]["generate"])
        self.run_button.clicked.connect(self.run_audiobook)
        self.toolbar.addWidget(self.run_button)

        # 页面主体：EPUB文本显示 + 进度
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 使用 QWebEngineView 显示 EPUB 内容
        self.web_view = QWebEngineView()
        main_layout.addWidget(self.web_view)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.epub_file_path = None

        # 多语言相关文本
        self.set_language(self.current_ui_lang)

        # Initialize thread and worker
        self.thread = None
        self.worker = None

    def on_ui_language_changed(self):
        """
        Slot to handle interface language changes.
        """
        data = self.ui_lang_combo.currentData()
        if data:
            self.set_language(data)

    def set_language(self, lang_code):
        """
        Update UI texts based on the selected language.
        """
        texts = UI_TEXTS.get(lang_code, UI_TEXTS["zh"])
        self.current_ui_lang = lang_code
        self.setWindowTitle(texts["window_title"])
        self.select_button.setText(texts["select_epub"])
        self.run_button.setText(texts["generate"])

        self.msg_no_epub = texts["msg_no_epub"]
        self.msg_done = texts["msg_done"]
        self.msg_error = texts["msg_error"]

        # Update tooltips
        self.ui_lang_combo.setToolTip(texts["label_interface_lang"])
        self.lang_combo.setToolTip(texts["label_tts_lang"])
        self.voice_combo.setToolTip(texts["label_voice"])
        self.speed_spin.setToolTip(texts["label_speed"])

        # Update labels in the toolbar
        toolbar_labels = self.toolbar.findChildren(QLabel)
        if len(toolbar_labels) >= 4:
            toolbar_labels[0].setText(texts["label_interface_lang"] + ":")
            toolbar_labels[1].setText(texts["label_tts_lang"] + ":")
            toolbar_labels[2].setText(texts["label_voice"] + ":")
            toolbar_labels[3].setText(texts["label_speed"] + ":")
        
        # Update static texts if necessary
        if not self.epub_file_path:
            no_file_html = f"<html><body><p>{texts['no_file_selected']}</p></body></html>"
            self.web_view.setHtml(no_file_html)
            self.progress_bar.setValue(0)

    def select_epub(self):
        """
        Opens a file dialog to select an EPUB file and displays its content.
        """
        self.web_view.setHtml("<html><body></body></html>")
        epub_file, _ = QFileDialog.getOpenFileName(
            self,
            self.select_button.text(),
            "",
            "EPUB Files (*.epub)"
        )
        if epub_file:
            self.epub_file_path = epub_file
            full_text = self.extract_epub_text(epub_file)
            self.web_view.setHtml(full_text)

    def extract_epub_text(self, epub_file):
        """
        Extracts text from an EPUB file and converts it to HTML for display.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                book = epub.read_epub(epub_file)
            html_buf = ['<html><head><meta charset="UTF-8"></head><body style="font-family: sans-serif;">']
            for item in book.get_items():
                if item.get_type() == ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_body_content(), 'lxml')
                    html_buf.append(str(soup))
            html_buf.append('</body></html>')
            return '\n'.join(html_buf)
        except Exception as e:
            print(f"Failed to parse EPUB: {e}")
            error_html = f"<html><body><p>Failed to parse EPUB:<br>{e}</p></body></html>"
            return error_html

    def run_audiobook(self):
        """
        Starts the audiobook generation process in a separate thread.
        """
        if not self.epub_file_path:
            QMessageBox.warning(self, "", self.msg_no_epub)
            return

        lang = self.lang_combo.currentText()
        voice = self.voice_combo.currentText()
        speed_val = float(self.speed_spin.value()) / 100.0  # Convert back to 0.5~2.0

        self.progress_bar.setValue(0)

        # 禁用生成按钮以防止重复点击
        self.run_button.setEnabled(False)

        # Set up worker and thread
        self.thread = QThread()
        self.worker = Worker(
            file_path=self.epub_file_path,
            lang=lang,
            voice=voice,
            pick_manually=False,  # Set based on your requirements
            speed=speed_val
        )
        self.worker.moveToThread(self.thread)

        # Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Start the thread
        self.thread.start()

    @Slot()
    def on_finished(self):
        """
        Slot to handle the completion of audiobook generation.
        """
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "", self.msg_done)
        self.run_button.setEnabled(True)

    @Slot(str)
    def on_error(self, error_message):
        """
        Slot to handle errors during audiobook generation.
        """
        QMessageBox.critical(self, "", f"{self.msg_error}: {error_message}")
        self.run_button.setEnabled(True)

    @Slot(int)
    def update_progress(self, value):
        """
        Updates the progress bar with the given value.
        """
        if value == -1:
            # An error has already been emitted
            return
        self.progress_bar.setValue(value)

    def closeEvent(self, event):
        """
        Ensure that threads are properly terminated when the application is closed.
        """
        if self.thread:
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait()
        event.accept()


def gui_main():
    """
    Entry point for the GUI application.
    """
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass  # Start method has already been set

    app = QApplication(sys.argv)
    window = AudiblezGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    gui_main()