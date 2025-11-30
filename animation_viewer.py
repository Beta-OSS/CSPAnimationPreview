import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog,
    QVBoxLayout, QWidget, QPushButton, QHBoxLayout
)
from PyQt6.QtGui import QPixmap, QAction
from PyQt6.QtCore import Qt, QTimer
from pathlib import Path


class AnimationViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CSP Animation Viewer")
        self.setMinimumSize(1244, 700)

        # --- MENU BAR ----------------------------------------------------
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        open_action = QAction("Open Clip File...", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")

        # --- CENTRAL WIDGET ----------------------------------------------
        central = QWidget()
        self.setCentralWidget(central)
        self.central_layout = QHBoxLayout(central)
        self.central_layout.setContentsMargins(0, 0, 0, 0)

        # --- MAIN IMAGE AREA --------------------------------------------
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.addWidget(self.main_widget, 1)

        self.image_label = QLabel("Open a file to view frames")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #FCFBFA; color: white;")
        self.main_layout.addWidget(self.image_label)

        # Playback buttons
        button_row = QHBoxLayout()
        self.main_layout.addLayout(button_row)
        self.prev_btn = QPushButton("◀ Prev Frame")
        self.play_btn = QPushButton("▶ Play")
        self.next_btn = QPushButton("Next Frame ▶")
        button_row.addWidget(self.prev_btn)
        button_row.addWidget(self.play_btn)
        button_row.addWidget(self.next_btn)

        self.prev_btn.clicked.connect(self.prev_frame)
        self.play_btn.clicked.connect(self.toggle_play)
        self.next_btn.clicked.connect(self.next_frame)

        # --- SIDEBAR -----------------------------------------------------
        self.sidebar_width = 250
        self.sidebar = QWidget(self)
        self.sidebar.setStyleSheet("background-color: #E0E0E0;")
        self.sidebar.setFixedWidth(self.sidebar_width)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.addWidget(QLabel("Sidebar / Controls / Info"))
        self.central_layout.addWidget(self.sidebar)

        # --- HAMBURGER TOGGLE BUTTON ------------------------------------
        self.toggle_sidebar_btn = QPushButton("≡", self)
        self.toggle_sidebar_btn.setFixedSize(40, 40)
        self.toggle_sidebar_btn.setStyleSheet(
            "font-size: 24px; border-radius: 5px; background-color: #FCFBFA;"
        )
        self.toggle_sidebar_btn.raise_()
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar)
        
        # --- FRAME TRACKING & TIMER -------------------------------------
        self.frames = []
        self.current_frame = 0
        self.is_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.frame_interval_ms = 100  # 10 fps default

        # Temporary directory holder
        self._temp_dir = None

    # --- Menu / File Actions -------------------------------------------
    def open_file(self):
        from extract_frames import extract_layers

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Clip File",
            "",
            "Clip Studio Files (*.clip);;All Files (*)"
        )
        if not file_path:
            return

        output_dir, temp_dir_obj = extract_layers(file_path)
        output_path = Path(output_dir)
        if output_path.exists() and output_path.is_dir():
            self.frames = sorted(output_path.glob("*.png"))
            self.frames = [str(f) for f in self.frames]
        else:
            print("Output directory does not exist.")
            return

        self.current_frame = 0
        self.show_frame()
        self._temp_dir = temp_dir_obj  # keep temp alive

    # --- Playback Functions --------------------------------------------
    def show_frame(self):
        if not self.frames:
            return
        pix = QPixmap(self.frames[self.current_frame])
        # Scale only to main widget size, not sidebar
        pix = pix.scaled(
            self.main_widget.width(),
            self.main_widget.height() - 50,  # leave space for buttons
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.show_frame()
        self.update_toggle_button_position()

    def showEvent(self, event):
        super().showEvent(event)  # call default showEvent
        self.update_toggle_button_position()  # position button correctly at start

    def prev_frame(self):
        if not self.frames:
            return
        self.current_frame = (self.current_frame - 1) % len(self.frames)
        self.show_frame()

    def next_frame(self):
        if not self.frames:
            return
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        self.show_frame()

    def toggle_play(self):
        if self.is_playing:
            self.timer.stop()
            self.play_btn.setText("▶ Play")
        else:
            self.timer.start(self.frame_interval_ms)
            self.play_btn.setText("⏸ Pause")
        self.is_playing = not self.is_playing

    # --- Sidebar Toggle -----------------------------------------------
    def toggle_sidebar(self):
        if self.sidebar.isVisible():
            self.sidebar.hide()
            self.toggle_sidebar_btn.setStyleSheet(
                "font-size: 24px; border-radius: 5px; background-color: #E0E0E0;"
            )
        else:
            self.sidebar.show()
            self.toggle_sidebar_btn.setStyleSheet(
                "font-size: 24px; border-radius: 5px; background-color: #FCFBFA;"
            )
        self.update_toggle_button_position()

    def update_toggle_button_position(self):
        if self.sidebar.isVisible():
            # top-left inside sidebar
            x = self.sidebar.x() + 10
        else:
            # right edge of main content
            x = self.width() - 50
        y = 40
        self.toggle_sidebar_btn.move(x, y)


# ------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = AnimationViewer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
