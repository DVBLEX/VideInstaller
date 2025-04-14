import os, sys, time
from PyQt5.QtWidgets import QApplication, QMainWindow, QStyleFactory, QWidget, QVBoxLayout, QStackedWidget, QLabel, \
    QPushButton
from PyQt5.QtWidgets import QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, QProgressBar
from PyQt5.QtGui import QIcon, QPalette, QColor, QFont, QPixmap
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from pyshortcuts import make_shortcut
import shutil

LOGO_COLOR = "#EC1C5B"
BACKGROUND_COLOR = "#1E1E1E"
BUTTON_COLOR = "#2E2E2E"
HOVER_COLOR = "#3A3A3A"
TEXT_COLOR = "#FFFFFF"
DEEP_PINK = "#EC1C5B"
WHITE = "#FFFFFF"
BLACK = "#000000"


class ProgressThread(QThread):
    progress_updated = pyqtSignal(int)  # Signal to update progress bar

    def run(self):
        for i in range(101):  # Simulate progress from 0 to 100
            time.sleep(0.05)  # Simulate delay
            self.progress_updated.emit(i)  # Emit signal with progress value


class Installer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.comp = False
        self.setWindowTitle("Vide Installer")
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS  # PyInstaller extraction folder
        else:
            base_path = os.path.abspath(".")
        ico_extension = ".ico" if os.name == 'nt' else ".icns"
        icon_path = os.path.join(base_path, f"logo{ico_extension}")
        self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(100, 100, 600, 400)

        self.setup_palette()
        self.setup_ui()

    def setup_palette(self):
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(BACKGROUND_COLOR))
        pal.setColor(QPalette.WindowText, QColor(TEXT_COLOR))
        pal.setColor(QPalette.Base, QColor(BUTTON_COLOR))
        pal.setColor(QPalette.AlternateBase, QColor(BUTTON_COLOR))
        pal.setColor(QPalette.ToolTipBase, QColor(TEXT_COLOR))
        pal.setColor(QPalette.ToolTipText, QColor(TEXT_COLOR))
        pal.setColor(QPalette.Text, QColor(TEXT_COLOR))
        pal.setColor(QPalette.Button, QColor(BUTTON_COLOR))
        pal.setColor(QPalette.ButtonText, QColor(TEXT_COLOR))
        pal.setColor(QPalette.BrightText, QColor(DEEP_PINK))
        pal.setColor(QPalette.Highlight, QColor(DEEP_PINK))
        pal.setColor(QPalette.HighlightedText, QColor(TEXT_COLOR))
        self.setPalette(pal)
        self.setStyle(QStyleFactory.create("Fusion"))

    def setup_ui(self):
        font = QFont("Helvetica Neue", 12)
        self.setFont(font)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        self.welcome_screen = QWidget()
        self.setup_welcome_screen_ui()
        self.stack.addWidget(self.welcome_screen)
        self.settings_screen = QWidget()
        self.setup_settings_screen_ui()
        self.stack.addWidget(self.settings_screen)
        self.progress_screen = QWidget()
        self.setup_progress_screen_ui()
        self.stack.addWidget(self.progress_screen)
        self.stack.setCurrentWidget(self.welcome_screen)

    def setup_welcome_screen_ui(self):
        layout = QVBoxLayout(self.welcome_screen)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS  # PyInstaller extraction folder
        else:
            base_path = os.path.abspath(".")
        self.logo_png_path = os.path.join(base_path, "logo.png")
        logo = QLabel(self)
        pixmap = QPixmap(self.logo_png_path)
        logo.setPixmap(pixmap)
        logo.setAlignment(QtCore.Qt.AlignCenter)
        logo.setScaledContents(True)  # Scale logo to fit
        logo.setFixedSize(150, 100)  # Adjust logo size
        layout.addWidget(logo, alignment=QtCore.Qt.AlignCenter)
        title =  QLabel("You are greeted by the Vide Installer!", self)
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        subtitle = QLabel("Click the button to proceed with the installation process.", self)
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(20)
        start_btn = QPushButton("Start", self)
        start_btn.setFont(QFont("Arial", 11, QFont.Bold))
        start_btn.setStyleSheet(
            "background-color: #e91e63; color: white; padding: 10px; border-radius: 5px;"
        )
        start_btn.clicked.connect(self.start)
        layout.addWidget(start_btn)

    def start(self):
        self.stack.setCurrentWidget(self.settings_screen)
        self.setGeometry(100, 100, 450, 250)

    def setup_settings_screen_ui(self):
        layout = QVBoxLayout(self.settings_screen)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Label
        label = QLabel("Please select folder:")
        label.setFont(QFont("Arial", 11))
        layout.addWidget(label)

        # File selection layout
        file_layout = QHBoxLayout()
        self.folder_path = QLineEdit()
        self.folder_path.setStyleSheet("color: black;")
        self.folder_path.setPlaceholderText("Select installation folder...")
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedSize(80, 30)
        browse_btn.setStyleSheet("background-color: #e91e63; color: white; border-radius: 5px;")
        browse_btn.clicked.connect(self.browse_folder)
        file_layout.addWidget(self.folder_path)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # Checkboxes
        self.desktop_shortcut = QCheckBox("Create desktop shortcut")
        self.run_after_install = QCheckBox("Run after installation")
        layout.addWidget(self.desktop_shortcut)
        layout.addWidget(self.run_after_install)

        # Button Layout
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # Pushes button to the right

        # Continue Button
        continue_btn = QPushButton("Continue")
        continue_btn.setFixedSize(100, 35)
        continue_btn.setFont(QFont("Arial", 10, QFont.Bold))
        continue_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px;")
        btn_layout.addWidget(continue_btn)
        continue_btn.clicked.connect(self.install)
        layout.addLayout(btn_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_path.setText(folder)

    def run_app(self, app_path):
        if os.name == 'nt':  # Windows
            os.startfile(app_path)
        else:  # Mac/Linux
            os.system(f'open "{app_path}"')


    def create_shortcut(self, app_folder_path):
        try:
            app_extension = ".exe" if os.name == 'nt' else ".app"
            ico_extension = ".ico" if os.name == 'nt' else ".icns"
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"logo{ico_extension}")
            app_path = os.path.join(app_folder_path, f"Vide{app_extension}")
            if os.path.exists(icon_path):
                make_shortcut(app_path, name="Vide", desktop=True, icon=icon_path)
        except Exception as e:
            print(e)



    def unzip(self, app_folder_path, create_shortcut_flag, run_flag):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS  # PyInstaller extraction folder
        else:
            base_path = os.path.abspath(".")
        
        app_extension = ".exe" if os.name == 'nt' else ".app"
        source_path = os.path.join(base_path, f"Vide{app_extension}")
        shutil.copy(source_path, f"{app_folder_path}/Vide{app_extension}")

        #Check file size after download
        self.app_path = os.path.join(app_folder_path, f"Vide{app_extension}")
        
        if create_shortcut_flag:
            self.create_shortcut(app_folder_path)

  
    def install(self):
        selected_folder = self.folder_path.text()
        create_shortcut_flag = self.desktop_shortcut.isChecked()
        run_flag = self.run_after_install.isChecked()
        if os.path.isdir(selected_folder):
            self.stack.setCurrentWidget(self.progress_screen)
            self.setGeometry(100, 100, 400, 200)
            self.start_progress()
            app_folder_path = os.path.join(selected_folder, "Vide")
            os.makedirs(app_folder_path, exist_ok=True)
            self.unzip(app_folder_path, create_shortcut_flag, run_flag)
        else:
            pass

    def setup_progress_screen_ui(self):
        layout = QVBoxLayout(self.progress_screen)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        logo = QLabel(self)
        pixmap = QPixmap(self.logo_png_path)
        logo.setPixmap(pixmap)
        logo.setAlignment( QtCore.Qt.AlignCenter)
        logo.setScaledContents(True)  # Scale logo to fit
        logo.setFixedSize(150, 100)  # Adjust logo size
        layout.addWidget(logo, alignment=QtCore.Qt.AlignCenter)
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status Label
        self.status_label = QLabel("Starting installation...")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)
    
    def start_progress(self):
        self.status_label.setText("Installing...")

        self.thread = ProgressThread()
        self.thread.progress_updated.connect(self.update_progress)
        self.thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if value == 100:
            self.status_label.setText("Installation Complete!")
            time.sleep(3)
            if self.run_after_install.isChecked():
                self.run_app(self.app_path)
            self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Installer()
    window.show()
    sys.exit(app.exec_())