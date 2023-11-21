from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

# from qt_material import apply_stylesheet

from just_playback import Playback
import os

from threading import Event

from formatting import FormatLabel
from GUI_elements import *
from utils import sec_to_HMS, find_songs


import platform

if "Windows" in platform.system():
    from win_volume import volume_controller

    VC = volume_controller()
    set_volume = VC.set_volume
    get_volume = VC.get_volume

    _OS = "WINDOWS"
else:
    from utils import set_volume, get_volume

    _OS = "OTHER"


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class audioplayer:
    def __init__(
        self,
        music_folder,
        extensions=[".mp3", ".wav"],
        cfg_dir=None,
    ):
        self.filepath = music_folder
        self.cfg_dir = music_folder if cfg_dir is None else cfg_dir
        self.extensions = extensions

        if not os.path.exists(self.filepath):
            raise ValueError("ERROR: Music folder path not found!")

        # Initialize the audio player
        self.player = Playback()

    def find_songs(self, printout=None):
        return find_songs(self.filepath, self.extensions, printout=printout)

    def _load_song(self, info, play_on_load=True):
        self.player.load_file(os.path.join(self.filepath, info[0]))
        if play_on_load:
            self.player.play()

    def set_loop(self, state):
        self.player.loop_at_end(state)

    def pause(self, state):
        if callable(state):
            state = not (state())
        # If we have started playing the song
        if self.player.active:
            if self.player.paused and state:
                # Resume if paused
                self.player.resume()
            elif not state:
                # Pause if playing
                self.player.pause()
        elif state:
            # Play if we have not started playing since loading
            self.player.play()

    def seek(self, pct_state):
        self.player.seek(pct_state * self.player.duration)

    def get_seek_pos(self):
        if self.player.duration == 0:
            return 0
        else:
            return self.player.curr_pos / self.player.duration


class MainWindow(QMainWindow):
    def __init__(
        self,
        music_folder,
        extensions=[".mp3", ".wav"],
        cfg_dir=None,
    ):
        super().__init__()

        self._editing_event = Event()
        self.load_stylesheet()

        self.player = audioplayer(music_folder, extensions, cfg_dir)
        self.edit_window = None
        self.music_folder = music_folder
        self._play_on_load = True

        self.setWindowTitle("Audio Player")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumWidth(800)
        self.resize(800, 600)

        self.icon = QIcon()
        self.icon.addFile(os.path.join(SCRIPT_DIR, "icon.png"))
        self.setWindowIcon(self.icon)

        self.layout = QGridLayout()
        self.layoutWidget = QWidget()
        self.layoutWidget.setLayout(self.layout)
        self.layout.setContentsMargins(3, 10, 3, 0)
        self.layout.setSpacing(5)

        self.title = TitleBar(self, "Audio Player")

        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.title_layout.setSpacing(0)
        self.title_layout.addWidget(self.title)
        self.title_layout.addWidget(self.layoutWidget)

        self.play_buttons = PlayBar()
        self.play_buttons.seek_slider.conn(self.seek_update)

        self.song_table = SongTable()
        self.song_table.set_headers(["Name", "Duration", "Genre", "Year"])
        self.song_table.conn(self.load_selection)
        self.song_table.connRClick(self.edit_popup)

        self.azbar = AZLinks(self.song_table)

        self.search_bar = SearchBar()
        self.search_bar.conn(self.song_table.filter_by)

        self.volume_bar = VolumeSlider()
        self.volume_bar.conn_move(set_volume)

        self.message_label = FormatLabel()

        self.YTD = YTD_Widget(music_folder)

        N = 0
        self.layout.addWidget(self.play_buttons, N, 0)
        N += 1
        self.layout.addWidget(self.search_bar, N, 0)
        N += 1
        self.layout.addWidget(self.azbar, N, 0)
        N += 1
        self.layout.addWidget(self.song_table, N, 0)
        self.layout.setRowStretch(N, 1)
        N += 1
        self.layout.addWidget(
            self.message_label, N, 0, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        N += 1
        self.layout.addWidget(self.YTD, N, 0)
        self.layout.addWidget(self.volume_bar, 0, 1, N, 1)

        self.main_widget = QWidget()
        self.main_widget.setLayout(self.title_layout)
        self.setCentralWidget(self.main_widget)

        self.add_buttons()

        self.add_entries(self.find_songs())
        self._update_loop()

        self.play_buttons.checkables["Play/Pause"].setChecked(False)
        self.player.pause(False)

    def edit_popup(self, selection, mpos):
        if self.edit_window is not None:
            tmp = self._editing_event.is_set()
            self.edit_window.close()
            if tmp:
                self._editing_event.set()

        if (
            self.song_table.get_selection() is not None
            and selection[0].data(0) == self.song_table.get_selection()[0]
        ):
            # Can't edit the currently loaded song on Windows
            # Linux is more flexible
            if _OS == "WINDOWS":
                self._editing_event.set()
                self.player.pause(True)
                self.player.player = Playback()
                self.play_buttons.update_state(None, self._play_on_load)
                self.song_table.clearSelection()
                self.message_label.setText("Warning: Can't rename song while selected.")

        if len(selection) > 0:
            self.edit_window = EditWindow(
                selection, self.music_folder, self.message_label, self._editing_event
            )
            self.edit_window.move(mpos.x(), mpos.y())
            self.edit_window.show()

    def find_songs(self):
        return self.player.find_songs(self.message_label.setText)

    def autoplay(self):
        if self.play_buttons.checkables["Shuffle"].isChecked():
            self.song_table.rand()
        elif self.play_buttons.checkables["AutoPlay"].isChecked():
            self.song_table.next()

    def load_stylesheet(self):
        with open(os.path.join(SCRIPT_DIR, "stylesheet.css"), "r") as f:
            ss = f.read()
        self.setStyleSheet(ss)

    def seek_update(self, value):
        self.player.seek(self.play_buttons.seek_slider.get_slider_pct())

    def refresh_table(self):
        self.song_table.clearContents()
        self.song_table.setRowCount(0)
        self.add_entries(self.find_songs())

    def _update_loop(self):
        if not self.player.player.active and not self._editing_event.is_set():
            self.autoplay()

        self.play_buttons.update_progress(
            f"{sec_to_HMS(self.player.player.curr_pos)} / {sec_to_HMS(self.player.player.duration)}"
        )
        self.volume_bar.set_pos(get_volume())
        self.play_buttons.seek_slider.set_slider_pct(self.player.get_seek_pos())
        QTimer.singleShot(500, self._update_loop)

    def load_selection(self):
        sel = self.song_table.get_selection()
        if sel is not None:
            self.play_buttons.update_state(sel[0], self._play_on_load)
            self.player._load_song(sel, self._play_on_load)

    def add_buttons(self):
        self.play_buttons.add_button("<<<", self.song_table.prev, False, False)
        self.play_buttons.add_button("Play/Pause", self.player.pause, True, False)
        self.play_buttons.add_button(">>>", self.song_table.next, False, False)
        self.play_buttons.add_button("???", self.song_table.rand, False, False)
        self.play_buttons.add_button("Refresh", self.refresh_table, False, False)
        self.play_buttons.add_checkbox("Loop", self.player.set_loop, False)
        self.play_buttons.add_checkbox("AutoPlay", None, True)
        self.play_buttons.add_checkbox("Shuffle", None, False)

    def add_entries(self, data):
        for d in data:
            self.song_table.add_row(d)


if __name__ == "__main__":
    songpaths = [
        "/mnt/StorageM2/Songs",
        "D:\\Songs",
    ]
    foundpath = None
    for path in songpaths:
        if os.path.exists(path):
            foundpath = path
            break

    if foundpath is None:
        print("Error: no valid song folder path found!")

    app = QApplication()

    window = MainWindow(foundpath)
    window.show()

    app.exec()
