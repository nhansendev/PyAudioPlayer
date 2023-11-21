# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QTimer

from formatting import SliderProxyStyle, HeaderLabel, TitleLabel, FormatLabel
from element_bases import ClickableSlider, LineEditDefaultText, ytd
from metadata import write_metadata

from functools import partial
import random
import os
from functools import partial
from interruptable_thread import ThreadWithExc
import yt_dlp


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class SongTable(QTableWidget):
    rclick = Signal(object, object)

    def __init__(self):
        super(SongTable, self).__init__()

        style = SliderProxyStyle(self.style().objectName())
        self.horizontalScrollBar().setStyle(style)
        self.verticalScrollBar().setStyle(style)

        # Only rows and single selections
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)

    def filter_by(self, get_field, text):
        field = get_field()

        headeridx = None
        for h in range(self.columnCount()):
            if self.horizontalHeaderItem(h).text() == field:
                headeridx = h
                break

        if headeridx is not None:
            for r in range(self.rowCount()):
                if not text.lower() in self.item(r, headeridx).data(0).lower():
                    self.setRowHidden(r, True)
                else:
                    self.setRowHidden(r, False)

    def get_selection(self):
        selected = self.selectedItems()
        if len(selected) > 0:
            return [s.data(0) for s in selected]

    def conn(self, command):
        self.itemSelectionChanged.connect(command)

    def mousePressEvent(self, event):
        # Don't change the selection when right-clicking to edit
        if event.button() != Qt.RightButton:
            return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            row = self.rowAt(event.position().y())
            sel = [self.item(row, c) for c in range(self.columnCount())]
            self.rclick.emit(sel, self.mapToGlobal(event.position()))
        return super().mouseReleaseEvent(event)

    def connRClick(self, command):
        self.rclick.connect(command)

    def set_headers(self, headers, widths=None):
        self.setColumnCount(len(headers))

        if widths is not None:
            for i, w in enumerate(w):
                self.setColumnWidth(i, w)

        self.setHorizontalHeaderLabels(headers)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def add_row(self, data):
        row = self.rowCount()
        self.setRowCount(row + 1)

        for col, d in enumerate(data):
            item = QTableWidgetItem(str(d), type=0)
            self.setItem(row, col, item)

    def get_selected_row_index(self):
        sel = self.selectionModel().selectedRows(0)
        if len(sel) > 0:
            return sel[0].row()
        else:
            return -1

    def get_visible_rows(self):
        indexes = []
        for r in range(self.rowCount()):
            if not self.isRowHidden(r):
                indexes.append(r)
        return indexes

    def next(self):
        indexes = self.get_visible_rows()
        try:
            row = indexes.index(self.get_selected_row_index()) + 1
            if row >= len(indexes):
                row = 0
            row = indexes[row]
        except ValueError:
            row = indexes[0]

        self.selectRow(row)

    def prev(self):
        indexes = self.get_visible_rows()
        try:
            row = indexes.index(self.get_selected_row_index()) - 1
            if row < 0:
                row = len(indexes) - 1
            row = indexes[row]
        except ValueError:
            row = indexes[0]

        self.selectRow(row)

    def rand(self):
        indexes = self.get_visible_rows()
        try:
            curr = indexes.index(self.get_selected_row_index())
        except ValueError:
            curr = None

        for _ in range(5):
            idx = random.randint(0, len(indexes) - 1)
            if idx != curr:
                break
        self.selectRow(indexes[idx])

    def get_songs(self):
        out = []
        for r in range(self.rowCount()):
            tmp = self.item(r, 0)
            if tmp is not None:
                out.append(tmp.text())
        return out


class SearchBar(QWidget):
    def __init__(self):
        super(SearchBar, self).__init__()

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(5, 0, 0, 0)
        self.setLayout(self.layout)

        self.label = QLabel("Search:")
        self.clear_button = QPushButton("X")
        self.clear_button.setFixedWidth(16)
        self.search_box = QLineEdit()
        self.clear_button.pressed.connect(lambda: self.search_box.setText(""))

        self.dropdown = QComboBox()
        self.dropdown.addItems(["Name", "Genre", "Year"])

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.clear_button)
        self.layout.addWidget(self.search_box, 1)
        self.layout.addWidget(self.dropdown)

    def conn(self, command):
        self.search_box.textChanged.connect(partial(command, self.dropdown.currentText))


class PlayBar(QWidget):
    def __init__(self):
        super(PlayBar, self).__init__()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 0, 0, 0)
        self.layout.setSpacing(1)
        self.setLayout(self.layout)

        self.song_label = FormatLabel("Nothing Playing")

        self.slider_holder = QWidget()
        self.slider_holder_layout = QHBoxLayout()
        self.slider_holder.setLayout(self.slider_holder_layout)

        self.duration_label = QLabel("-")
        self.seek_slider = SeekSlider()
        self.slider_holder_layout.addWidget(self.duration_label)
        self.slider_holder_layout.addWidget(self.seek_slider, 1)

        self.button_holder = QFrame()
        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(5, 0, 0, 0)
        self.button_holder.setLayout(self.button_layout)

        self.layout.addWidget(self.song_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.slider_holder)
        self.layout.addWidget(self.button_holder)

        self.checkables = {}
        self._internal_slider_set = False

    def update_progress(self, duration_text):
        self.duration_label.setText(duration_text)

    def update_state(self, song, playing=True):
        if song is None:
            self.song_label.setText("-")
        else:
            self.song_label.setText(song)

        self.duration_label.setText("-")
        self.seek_slider.setSliderPosition(0)
        self.checkables["Play/Pause"].setChecked(playing)

    def add_button(self, text, command, checkable=False, checked=False):
        tmp = QPushButton(text)
        tmp.setCheckable(checkable)
        tmp.setChecked(checked)
        tmp.setMinimumWidth(60)

        if checkable:
            self.checkables[text] = tmp
            tmp.pressed.connect(partial(command, tmp.isChecked))
        else:
            tmp.pressed.connect(command)

        self.button_layout.addWidget(tmp, len(text))

    def add_checkbox(self, text, command, checked=False):
        tmp = QCheckBox(text)
        tmp.setChecked(checked)
        tmp.toggled.connect(command)
        self.checkables[text] = tmp

        self.button_layout.addWidget(tmp)


class SeekSlider(ClickableSlider):
    touched = Signal(object)

    def __init__(self):
        super().__init__()

        self.setOrientation(Qt.Orientation.Horizontal)
        self.setMinimum(0)
        self.setMaximum(1000)
        self.setSingleStep(50)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self.touched.emit(self.value())

        # return super().mouseReleaseEvent(event)

    def conn(self, command):
        self.touched.connect(command)

    def get_slider_pct(self):
        return (self.value() - self.minimum()) / (self.maximum() - self.minimum())

    def _pct_to_int(self, value):
        value = max(0, min(1, value))
        return int((self.maximum() - self.minimum()) * value) + self.minimum()

    def set_slider_pct(self, value):
        if not self.reserved:
            self.setValue(self._pct_to_int(value))


class VolumeSlider(QWidget):
    def __init__(self, horizontal=False, vmin=0, vmax=100, vstep=5):
        super().__init__()

        self.reserved = False

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.label = QLabel("0")
        self.label.setFixedWidth(26)
        self.layout.addWidget(self.label)

        self.slider = ClickableSlider()
        self.layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.set_label)

        if horizontal:
            self.slider.setOrientation(Qt.Orientation.Horizontal)
        else:
            self.slider.setOrientation(Qt.Orientation.Vertical)

        self.slider.setMinimum(vmin)
        self.slider.setMaximum(vmax)
        self.slider.setSingleStep(vstep)

    def set_pos(self, value):
        if not self.slider.reserved:
            tmp = min(self.slider.maximum(), max(self.slider.minimum(), int(value)))
            if tmp != self.slider.value():
                self.slider.setValue(tmp)

    def conn_move(self, command):
        self.slider.valueChanged.connect(command)

    def set_label(self, value):
        self.label.setText(str(value))


class EditWindow(QWidget):
    def __init__(self, selection, music_folder, msg_label, editing_event):
        super().__init__()

        self.editing_event = editing_event

        self.setFixedWidth(700)
        self.setMinimumHeight(120)

        self.setAutoFillBackground(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setContentsMargins(0, 0, 0, 0)

        self.load_stylesheet()

        self.music_folder = music_folder
        self.msg_label = msg_label

        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.title_layout)

        self.layout = QGridLayout()
        self.layout_widget = QWidget()
        self.layout_widget.setLayout(self.layout)
        self.layout.setContentsMargins(3, 0, 3, 3)
        self.layout.setSpacing(3)

        self.title = TitleBar(self, "Edit Song Info", close_only=True)

        self.title_layout.addWidget(self.title)
        self.title_layout.addWidget(self.layout_widget, stretch=1)

        headers = [" Name", " Genre", " Year"]
        for i, h in enumerate(headers):
            tmp = HeaderLabel(h)
            self.layout.addWidget(tmp, 0, i + 1)

        tmp = HeaderLabel("Current: ")
        self.layout.addWidget(tmp, 1, 0)
        tmp = HeaderLabel("New: ")
        self.layout.addWidget(tmp, 2, 0)

        self.selection = selection

        song_data = [s.data(0) for s in selection]

        idx = 1
        self.editors = []
        self.old_data = song_data
        self.skipped_indexes = [1]
        for i, d in enumerate(song_data):
            # Ignore duration
            if i not in self.skipped_indexes:
                tmp = QLabel(str(d))
                self.layout.addWidget(tmp, 1, idx)

                tmp2 = QLineEdit(str(d))
                tmp2.returnPressed.connect(self.update_values)
                self.layout.addWidget(tmp2, 2, idx)
                idx += 1
                self.editors.append(tmp2)

        self.layout.setColumnStretch(1, 1)

        self.ok_button = QPushButton("Ok")
        self.ok_button.pressed.connect(self.update_values)
        self.layout.addWidget(self.ok_button, 3, 2)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.close)
        self.layout.addWidget(self.cancel_button, 3, 3)

    def load_stylesheet(self):
        with open(os.path.join(SCRIPT_DIR, "stylesheet.css"), "r") as f:
            ss = f.read()
        self.setStyleSheet(ss)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Enter:
            self.update_values()
        event.accept()

    def update_values(self):
        tmp = [e.text() for e in self.editors]
        idx = 0
        for i in range(len(self.old_data)):
            if not i in self.skipped_indexes:
                self.selection[i].setText(tmp[idx])
                idx += 1

        if self.old_data[2] != tmp[1] or self.old_data[3] != tmp[2]:
            write_metadata(
                self.music_folder,
                self.old_data[0],
                genre=tmp[1],
                year=tmp[2],
            )

        if tmp[0] != self.old_data[0]:
            try:
                os.rename(
                    os.path.join(self.music_folder, self.old_data[0]),
                    os.path.join(self.music_folder, tmp[0]),
                )
                self.msg_label.setText(f"Renamed to: {tmp[0]}")
            except FileNotFoundError:
                self.msg_label.setText("Error while renaming. No changes made.")

        self.close()

    def close(self):
        self.editing_event.clear()
        super().close()


class AZLinks(QWidget):
    # For quickly moving the table focus to a given alphabetical position
    # Note: buttons will do nothing if there are no entries starting with the selected letter
    def __init__(self, table):
        super().__init__()

        self.table = table

        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.buttons = []
        for v in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            tmp = QPushButton(v)
            tmp.pressed.connect(self.button_pressed)
            self.layout.addWidget(tmp)

    def button_pressed(self):
        letter = self.sender().text().lower()
        firsts = [s[0].lower() for s in self.table.get_songs()]
        try:
            idx = firsts.index(letter)
            self.table.scrollToItem(self.table.item(idx, 0))
        except (IndexError, ValueError):
            pass


class TitleBar(QWidget):
    def __init__(self, window, title, close_only=False):
        super().__init__()

        self.parent = window
        self.maxNormal = False
        self.setAutoFillBackground(True)
        self.setFixedHeight(30)

        self.setAttribute(Qt.WA_StyledBackground, True)

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(3, 0, 3, 0)
        self.layout.setSpacing(3)
        self.setLayout(self.layout)

        self.title = TitleLabel(title)
        if not close_only:
            self.minButton = QPushButton("-")
            self.minButton.setFixedWidth(30)
            self.maxButton = QPushButton("■")
            self.maxButton.setFixedWidth(30)

            self.minButton.pressed.connect(self._minimize)
            self.maxButton.pressed.connect(self._maximize)

        self.closeButton = QPushButton("x")
        self.closeButton.setFixedWidth(30)
        self.closeButton.pressed.connect(self._close)

        self.layout.addWidget(
            self.title, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        if not close_only:
            self.layout.addWidget(self.minButton)
            self.layout.addWidget(self.maxButton)
        self.layout.addWidget(self.closeButton)

    def _minimize(self):
        self.parent.showMinimized()

    def _maximize(self):
        if self.maxNormal:
            self.parent.showNormal()
            self.maxNormal = False
        else:
            self.parent.showMaximized()
            self.maxNormal = True

    def _close(self):
        self.parent.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.moving = True
            self.parent.offset = event.scenePosition()

    def mouseMoveEvent(self, event):
        if self.parent.moving:
            self.parent.move(
                event.globalPosition().toPoint() - self.parent.offset.toPoint()
            )


class YTD_Widget(QWidget):
    def __init__(self, dir=None, parallel_lim=3, autoclose=False):
        super().__init__()

        self.dir = dir
        self.URLs = set()
        self.dl_frames = []
        self.parallel_lim = parallel_lim
        self.autoclose = autoclose

        self.layout_stack = QVBoxLayout()
        self.layout_stack.setContentsMargins(5, 0, 0, 0)
        self.setLayout(self.layout_stack)

        self.holder = QWidget()
        self.layout = QHBoxLayout()
        self.holder.setLayout(self.layout)
        self.layout_stack.addWidget(self.holder)

        self.clearButton = QPushButton("X")
        self.clearButton.setFixedWidth(24)
        self.layout.addWidget(self.clearButton)

        self.default_text = "Enter one or more URLs to download (separate with commas)"
        self.URL_box = LineEditDefaultText(self.default_text)
        self.layout.addWidget(self.URL_box, 1)
        self.URL_box.return_conn(self.add_download)
        self.clearButton.pressed.connect(self.URL_box.clear)

        self.download_button = QPushButton("Download")
        self.download_button.pressed.connect(self.add_download)
        self.layout.addWidget(self.download_button)

        self._check_loop()

    def add_download(self):
        URLstr = [s.strip() for s in self.URL_box.text().split(",")]
        for URL in URLstr:
            if len(URL) > 0:
                self.URLs.add(URL)

    def _check_runnable(self):
        self._qty_running = 0
        for F in self.dl_frames:
            if F.started and not F.finished:
                self._qty_running += 1
        return self._qty_running < self.parallel_lim

    def _check_loop(self):
        for URL in self.URLs:
            unique = True
            for F in self.dl_frames:
                if F.URL == URL:
                    unique = False
                    break

            if unique:
                tmp = DLFrame(
                    self.dir,
                    URL,
                    start_immediately=self._check_runnable(),
                    autoclose=self.autoclose,
                )
                self.layout_stack.addWidget(tmp)
                self.dl_frames.append(tmp)
        self.URLs = set()

        for F in self.dl_frames:
            if F.finished and F.can_close:
                if not F.closed:
                    F.close()
                self.layout_stack.removeWidget(F)
                self.dl_frames.remove(F)
                del F

            elif not F.started:
                if self._check_runnable():
                    F._retry()

        QTimer.singleShot(1000, self._check_loop)


class DLFrame(QWidget):
    # Shows progress and queue of yt_dlp requests
    def __init__(self, dir, URL, start_immediately=True, autoclose=False):
        super().__init__()

        self.URL = URL
        self.dir = dir
        self.can_run = True
        self.can_close = autoclose
        self.started = False
        self.finished = False
        self.downloaded_title = None

        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.label = QLabel(f"In Queue: {self.URL}")
        self.layout.addWidget(self.label, 1)

        self.button = QPushButton("Start")
        self.button.pressed.connect(self._retry)
        self.layout.addWidget(self.button)

        if start_immediately:
            self._retry()

    def _retry(self):
        if not self.can_run:
            return
        self.started = True

        def _dl():
            try:
                ytd(self.URL, logger=self, dir=self.dir)
                self.label.setText(f"Downloaded: {self.downloaded_title}")
                self.finished = True
            except yt_dlp.utils.DownloadError:
                self.started = False

            if self.finished:
                self.button.setText("OK")
                self.button.pressed.disconnect()
                self.button.pressed.connect(self.close)

        self.downloaded_title = []
        th = ThreadWithExc(target=_dl, daemon=True)
        th.start()

        self.button.setText("Cancel")
        self.button.pressed.disconnect()
        self.button.pressed.connect(partial(self._cancel_thread, th))

    def _cancel_thread(self, th):
        th.raiseExc(KeyboardInterrupt)
        self.label.setText("Download Cancelled")
        self.button.setText("OK")
        self.button.pressed.disconnect()
        self.button.pressed.connect(self.close)

    def debug(self, msg):
        if "Destination" in msg and "ExtractAudio" in msg:
            self.downloaded_title = msg.split("/")[-1]
        self.label.setText(msg.replace("\x1b[K", ""))

    def warning(self, msg):
        self.label.setText(msg)

    def error(self, msg):
        self.label.setText(msg.replace("\x1b[0;31mERROR:\x1b[0m", "ERROR:"))
        if "unable" in msg:
            self.button.setText("Retry")
        elif "ERROR" in msg:
            self.button.setText("Cancel")
            self.button.pressed.disconnect()
            self.button.pressed.connect(self.close)
            self.can_run = False
            self.finished = True
        else:
            self.button.setText("Retry")

    def close(self):
        self.closed = True
        self.finished = True
        self.can_close = True
