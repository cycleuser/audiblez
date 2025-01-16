# PySide6-based GUI for audiblez with UI language switching

import os
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QSpinBox, QMessageBox
)
from PySide6.QtCore import Qt
from pathlib import Path
from audiblez import main, Kokoro

current_file_path = os.path.abspath(__file__)
current_directory = os.path.dirname(current_file_path)
os.chdir(current_directory)

UI_TEXTS = {
    "en": {
        "window_title": "Audiblez GUI",
        "no_file_selected": "No file selected",
        "select_epub": "Select EPUB File",
        "label_epub": "EPUB file:",
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
        "label_epub": "EPUB文件:",
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

class AudiblezGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_ui_lang = "zh"  # 默认中文
        self.init_kokoro()
        self.init_ui()
        self.set_language(self.current_ui_lang)

    def init_kokoro(self):
        self.kokoro = Kokoro('kokoro-v0_19.onnx', 'voices.json')
        self.kokoro.sess.set_providers(['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.voices = list(self.kokoro.get_voices())

    def init_ui(self):
        self.setWindowTitle("")
        self.setGeometry(200, 200, 400, 260)

        container = QWidget()
        layout = QVBoxLayout(container)

        # 界面语言
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItem("中文", "zh")
        self.ui_lang_combo.addItem("English", "en")
        self.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)

        # EPUB选择
        self.epub_path_label = QLabel("")
        self.select_button = QPushButton()

        # TTS语言选择
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["en-gb", "en-us", "fr-fr", "ja", "ko", "cmn", "zh-CN"])

        # 声音选择
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.voices)

        # 语速设置
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 200)
        self.speed_spin.setValue(100)

        # 开始生成
        self.run_button = QPushButton()

        # 布局
        layout.addWidget(QLabel())       # 放置“界面语言:”Label
        layout.addWidget(self.ui_lang_combo)
        layout.addWidget(QLabel())       # “EPUB文件:”Label
        layout.addWidget(self.epub_path_label)
        layout.addWidget(self.select_button)
        layout.addWidget(QLabel())       # “选择语言:”Label
        layout.addWidget(self.lang_combo)
        layout.addWidget(QLabel())       # “选择声音:”Label
        layout.addWidget(self.voice_combo)
        layout.addWidget(QLabel())       # “语速:”
        layout.addWidget(self.speed_spin)
        layout.addWidget(self.run_button)

        self.setCentralWidget(container)
        self.epub_file_path = None

        # 为按钮绑定事件
        self.select_button.clicked.connect(self.select_epub)
        self.run_button.clicked.connect(self.run_audiobook)

        self.layout_labels = layout.children()  # 后面动态设定文本

    def on_ui_language_changed(self):
        data = self.ui_lang_combo.currentData()
        if data:
            self.set_language(data)

    def set_language(self, lang_code):
        texts = UI_TEXTS.get(lang_code, UI_TEXTS["zh"])
        self.current_ui_lang = lang_code
        self.setWindowTitle(texts["window_title"])

        # layout里的QLabel顺序对照上面init_ui调用顺序
        # 1st QLabel: “界面语言:”
        # 2nd: “EPUB文件:”
        # 3rd: “选择语言:”
        # 4th: “选择声音:”
        # 5th: “语速 (0.5~2.0，对应 50~200):”
        # 依次更新文本
        label_widgets = [w for w in self.layout_labels if isinstance(w, QLabel)]
        if len(label_widgets) >= 5:
            label_widgets[0].setText(texts["label_interface_lang"])
            label_widgets[1].setText(texts["label_epub"])
            label_widgets[2].setText(texts["label_tts_lang"])
            label_widgets[3].setText(texts["label_voice"])
            label_widgets[4].setText(texts["label_speed"])

        self.epub_path_label.setText(texts["no_file_selected"])
        self.select_button.setText(texts["select_epub"])
        self.run_button.setText(texts["generate"])

        self.msg_no_epub = texts["msg_no_epub"]
        self.msg_done = texts["msg_done"]
        self.msg_error = texts["msg_error"]

    def select_epub(self):
        epub_file, _ = QFileDialog.getOpenFileName(
            self, self.select_button.text(), "", "EPUB Files (*.epub)"
        )
        if epub_file:
            self.epub_file_path = epub_file
            self.epub_path_label.setText(Path(epub_file).name)

    def run_audiobook(self):
        if not self.epub_file_path:
            QMessageBox.warning(self, "", self.msg_no_epub)
            return
        lang = self.lang_combo.currentText()
        voice = self.voice_combo.currentText()
        speed_val = float(self.speed_spin.value() / 100.0)

        try:
            main(self.kokoro, self.epub_file_path, lang, voice, pick_manually=False, speed=speed_val)
            QMessageBox.information(self, "", self.msg_done)
        except Exception as e:
            QMessageBox.critical(self, "", f"{self.msg_error}: {str(e)}")

def gui_main():
    app = QApplication(sys.argv)
    window = AudiblezGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    gui_main()