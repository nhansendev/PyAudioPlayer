# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from just_playback import Playback, ma_result
import os
from threading import Event
from formatting import FormatLabel
from element_bases import TimedMessageLabel
from GUI_elements import *
from utils import sec_to_HMS, song_to_numeric, max_amplitude_binning
import sys
from pydub.exceptions import CouldntDecodeError

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
    def __init__(self, music_folder):
        self.filepath = music_folder

        if not os.path.exists(self.filepath):
            raise ValueError("ERROR: Music folder path not found!")

        # Initialize the audio player
        self.player = Playback()

    def _load_song(self, info, play_on_load=True):
        try:
            self.player.load_file(os.path.join(self.filepath, info[0]))
            if play_on_load:
                self.player.play()
            return True
        except (ma_result.MiniaudioError, FileNotFoundError):
            # print(f"Can't load:", os.path.join(self.filepath, info[0]))
            return False

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


# Cause of "Failed to initialize COM library (Cannot change thread mode after it is set.)" error?


class MainWindow(QMainWindow):
    def __init__(
        self,
        music_folder,
        extensions=[".mp3", ".wav"],
    ):
        super().__init__()

        self.meta_loadingbar = LoadingBarWindow(music_folder, extensions)
        self.meta_loadingbar.done.connect(self.add_entries)

        self._editing_event = Event()
        self._trimming_event = Event()
        self._normalize_event = Event()
        self.load_stylesheet()

        self.player = audioplayer(music_folder)
        self.edit_window = None
        self.trim_window = None
        self.norm_window = None
        self.music_folder = music_folder
        self._play_on_load = True
        self.manual_unpause = True

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
        self.song_table.connMClick(self.trim_popup)

        self.azbar = AZLinks(self.song_table)

        self.search_bar = SearchBar()
        self.search_bar.conn(self.song_table.filter_by)

        self.volume_bar = VolumeSlider()
        self.volume_bar.conn_move(set_volume)

        # self.message_label = FormatLabel()
        self.message_label = TimedMessageLabel()

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

        self.norm_button = QPushButton("Norm")
        self.norm_button.pressed.connect(self.normalize_popup)
        self.layout.addWidget(self.norm_button, N, 1)

        self.main_widget = QWidget()
        self.main_widget.setLayout(self.title_layout)
        self.setCentralWidget(self.main_widget)

        self.add_buttons()

        self.meta_loadingbar.raise_()
        self.meta_loadingbar.show()
        self.meta_loadingbar.activateWindow()
        self.find_songs()
        self._update_loop()

        self.play_buttons.checkables["Play/Pause"].setChecked(False)
        self.player.pause(False)

    def normalize_popup(self):
        if not self._normalize_event.is_set():
            self._normalize_event.set()
            self.message_label.setText("See Volume Normalization Window")

            self.norm_window = NormalizerWindow(
                self.music_folder,
                self.song_table.get_songs(),
                self.message_label,
                self._normalize_event,
            )
            self.norm_window.show()
        else:
            self.message_label.setText("Close existing normalization window first!")

    def edit_popup(self, selection, mpos):
        if self.edit_window is not None:
            tmp = self._editing_event.is_set()
            self.edit_window.close()
            if tmp:
                self._editing_event.set()

        # TODO: Nothing stops the user from re-selecting the song with the window open
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
            self.edit_window.move_to_center(self, override_y=mpos.y())
            self.edit_window.show()

    def trim_popup(self, selection, mpos):
        if self.trim_window is not None:
            tmp = self._trimming_event.is_set()
            self.trim_window.close()
            if tmp:
                self._trimming_event.set()

        # TODO: Nothing stops the user from re-selecting the song with the window open
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
                self.message_label.setText("Warning: Can't edit song while selected.")

        if len(selection) > 0:
            try:
                data, duration = song_to_numeric(
                    self.music_folder, selection[0].data(0)
                )
            except CouldntDecodeError:
                self.message_label.setText(f"Unable to edit: {selection[0].data(0)}")
                self._trimming_event.clear()
                return

            bins = max_amplitude_binning(data, 300)
            self.trim_window = TrimSongWindow(
                self.music_folder,
                selection,
                bins,
                duration,
                self.message_label,
                self._trimming_event,
            )
            self.trim_window.move_to_center(self, override_y=mpos.y())
            self.trim_window.show()

    def find_songs(self):
        self.meta_loadingbar.raise_()
        self.meta_loadingbar.show()
        self.meta_loadingbar.activateWindow()
        self.meta_loadingbar.reset()
        self.meta_loadingbar.load_metadata()
        self.message_label.setText(f"Found {len(self.meta_loadingbar.songs)} song(s)")
        # return self.player.find_songs(self.message_label.setText)

    def autoplay(self):
        if self.play_buttons.checkables["Shuffle"].isChecked():
            self.song_table.rand()
        elif self.play_buttons.checkables["AutoPlay"].isChecked():
            self.song_table.next()

    def load_stylesheet(self):
        with open(os.path.join(SCRIPT_DIR, "stylesheet.css"), "r") as f:
            ss = f.read()
        self.setStyleSheet(ss)

    def seek_update(self, *args):
        self.player.seek(self.play_buttons.seek_slider.get_slider_pct())

    def refresh_table(self):
        if not self.meta_loadingbar._running:
            self.song_table.clearContents()
            self.song_table.setRowCount(0)
            self.find_songs()
            # Without this the search would ignore the existing text after refresh
            QTimer.singleShot(500, self.search_bar.refresh)

    def _update_loop(self):
        if (
            not self.player.player.active
            and not self._editing_event.is_set()
            and not self.manual_unpause
        ):
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
            if not self.player._load_song(sel, self._play_on_load):
                self.message_label.setText(
                    f"ERROR: Can't load song: {sel[0]}. Check filename."
                )
            else:
                self.manual_unpause = False

    def add_buttons(self):
        self.play_buttons.add_button("<<<", self.song_table.prev, False, False)
        self.play_buttons.add_button("Play/Pause", self._pause, True, False)
        self.play_buttons.add_button(">>>", self.song_table.next, False, False)
        self.play_buttons.add_button("???", self.song_table.rand, False, False)
        self.play_buttons.add_button("Refresh", self.refresh_table, False, False)
        self.play_buttons.add_checkbox("Loop", self.player.set_loop, False)
        self.play_buttons.add_checkbox("AutoPlay", None, True)
        self.play_buttons.add_checkbox("Shuffle", None, False)

    def _pause(self, state):
        self.manual_unpause = False  # unnecessary now?
        self.player.pause(state)

    def add_entries(self, data):
        if data is not None:
            for d in data:
                self.song_table.add_row(d)

    def closeEvent(self, event):
        # Ensure all sub-windows close with the main window
        for window in QApplication.topLevelWidgets():
            window.close()


if __name__ == "__main__":
    try:
        path = sys.argv[1]
        if not os.path.exists(path):
            raise ValueError("ERROR: Music folder path not found!")
    except IndexError:
        path = ""

    app = QApplication()

    window = MainWindow(path)
    window.show()

    window.meta_loadingbar.raise_()
    window.meta_loadingbar.show()
    window.meta_loadingbar.activateWindow()

    app.exec()
