# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QTimer, QObject, Slot, QThread
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from PySide6.QtCharts import (
    QChart,
    QStackedBarSeries,
    QBarSet,
    QValueAxis,
    QChartView,
)

from formatting import SliderProxyStyle, HeaderLabel, TitleLabel, FormatLabel
from element_bases import (
    ClickableSlider,
    LineEditDefaultText,
    ytd,
    ReservedRangeSlider,
)
from metadata import write_metadata, check_normalized, read_metadata
from utils import (
    _norm,
    _search_dir,
    sec_to_HMS,
    trim_song,
)

from functools import partial
import random
import os
import time
from interruptable_thread import ThreadWithExc
import yt_dlp
from multiprocessing import Pool, cpu_count, Event, Process
from utils import sec_to_HMS


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_stylesheet(obj):
    with open(os.path.join(SCRIPT_DIR, "stylesheet.css"), "r") as f:
        ss = f.read()
    obj.setStyleSheet(ss)


# DEBUG
# def _norm(*args):
#     time.sleep(0.5)


class SongTable(QTableWidget):
    rclick = Signal(object, object)
    mclick = Signal(object, object)

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
        # Don't change the selection when right-clicking or middle-clicking to edit
        if event.button() == Qt.LeftButton:
            return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            row = self.rowAt(event.position().y())
            sel = [self.item(row, c) for c in range(self.columnCount())]
            self.rclick.emit(sel, self.mapToGlobal(event.position()))
        elif event.button() == Qt.MiddleButton:
            row = self.rowAt(event.position().y())
            sel = [self.item(row, c) for c in range(self.columnCount())]
            self.mclick.emit(sel, self.mapToGlobal(event.position()))
        return super().mouseReleaseEvent(event)

    def connRClick(self, command):
        self.rclick.connect(command)

    def connMClick(self, command):
        self.mclick.connect(command)

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
        if len(indexes) < 1:
            return

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
        if len(indexes) < 1:
            return

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
        if len(indexes) < 1:
            return

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

    def refresh(self):
        self.search_box.textChanged.emit(self.search_box.text())


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
    def __init__(self, horizontal=False, vmin=0, vmax=100, vstep=1):
        super().__init__()

        self.reserved = False

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self._just_char = "\u2007"

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
        self.label.setText(str(value).center(3, self._just_char))


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

        load_stylesheet(self)

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

    def move_to_center(self, parent, override_x=None, override_y=None):
        px = override_x if override_x is not None else parent.x()
        py = override_y if override_y is not None else parent.y()

        pw, ph = parent.width(), parent.height()

        self.move(px + pw / 2 - self.width() / 2, py + ph / 2 - self.height() / 2)

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
            self.msg_label.setText(f"Updated metadata of: {tmp[0]}")

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
    def __init__(self, window, title, hide_on_close=False, close_only=False):
        super().__init__()

        self.hide_on_close = hide_on_close
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
        if self.hide_on_close:
            self.parent.hide()
        else:
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


class NormWorkerThread(QObject):
    done = Signal()
    check_progress = Signal()
    norm_progress = Signal()
    convert_qty = Signal(int)
    finished = Signal()

    def __init__(self, songs, music_folder, interrupt_event) -> None:
        super().__init__()

        self.songs = songs
        self.music_folder = music_folder
        self.interrupt_event = interrupt_event

    @Slot()
    def run(self):
        # TODO: parallelize?
        to_convert = []
        for s in self.songs:
            path = os.path.join(self.music_folder, s)
            if not check_normalized(path):
                to_convert.append(path)
            self.check_progress.emit()
            if self.interrupt_event.is_set():
                self.finished.emit()
                return

        self.convert_qty.emit(len(to_convert))

        if len(to_convert) > 0:
            with Pool(max(1, cpu_count() - 1)) as p:
                for _ in p.imap_unordered(_norm, to_convert):
                    self.norm_progress.emit()
                    if self.interrupt_event.is_set():
                        self.finished.emit()
                        return

        self.done.emit()
        self.finished.emit()


class NormalizerWindow(QWidget):
    def __init__(self, music_folder, songs, msg_label, norm_event):
        super().__init__()

        self.music_folder = music_folder
        self.songs = songs
        self.msg_label = msg_label
        self.norm_event = norm_event
        self._check_progress = 0
        self._norm_progress = 0
        self._progress_bar_chars = 50
        self._interrupt_event = Event()
        self._ignore_updates = False

        # Apparently the only "space" character that is consistently wide
        self._just_char = "\u2007"  # "Figure Space"

        self.setFixedWidth(510)
        self.setMinimumHeight(120)

        self.setAutoFillBackground(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setContentsMargins(0, 0, 0, 0)

        load_stylesheet(self)

        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.title_layout)

        self.layout = QVBoxLayout()
        self.layout_widget = QWidget()
        self.layout_widget.setLayout(self.layout)
        self.layout.setContentsMargins(3, 0, 3, 3)
        self.layout.setSpacing(3)

        self.title = TitleBar(self, "Normalize Songs", close_only=True)

        self.title_layout.addWidget(self.title)
        self.title_layout.addWidget(self.layout_widget, stretch=1)

        self.status_label = QLabel(f"Checking {len(songs)} loaded song(s)...")
        self.layout.addWidget(self.status_label)

        self.progress_bar = QLabel("0% | ".rjust(7, self._just_char))
        self.layout.addWidget(self.progress_bar)

        self.status_label2 = QLabel("")
        self.layout.addWidget(self.status_label2)

        self.progress_bar2 = QLabel("0% | ".rjust(7, self._just_char))
        self.layout.addWidget(self.progress_bar2)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(50)
        self.layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.normalize()

    def normalize(self):
        self.worker = NormWorkerThread(
            self.songs, self.music_folder, self._interrupt_event
        )
        self.worker.done.connect(self._done)
        self.worker.check_progress.connect(self._increment_check_progress)
        self.worker.norm_progress.connect(self._increment_norm_progress)
        self.worker.convert_qty.connect(self._to_convert_update)

        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot()
    def _to_convert_update(self, qty):
        if qty > 0:
            self.status_label2.setText(f"Normalizing {qty} songs...")
            self.cancel_button.pressed.connect(self._cancel_thread)
        else:
            self.status_label2.setText("Nothing found to normalize.")
            self.progress_bar2.setText("")

    def _cancel_thread(self):
        self._interrupt_event.set()
        self._ignore_updates = True
        pct = (
            f"{int(self._norm_progress / len(self.songs)*100)}% | ".rjust(
                7, self._just_char
            )
            + "Cancelled"
        )
        self.progress_bar2.setText(pct)
        self._done()

    @Slot()
    def _done(self, *args):
        self.cancel_button.setText("Ok")
        try:
            self.cancel_button.pressed.disconnect()
        except RuntimeError:
            # This will fail at runtime if there is nothing to disconnect
            pass
        self.cancel_button.pressed.connect(self.close)

    @Slot()
    def _increment_check_progress(self, *args):
        if self._ignore_updates:
            return
        self._check_progress += 1
        rat = self._check_progress / len(self.songs)
        pct = f"{int(rat*100)}% | ".rjust(7, self._just_char) + "▒" * int(
            rat * self._progress_bar_chars
        )
        self.progress_bar.setText(pct)

    @Slot()
    def _increment_norm_progress(self, *args):
        if self._ignore_updates:
            return
        self._norm_progress += 1
        rat = self._norm_progress / len(self.songs)
        pct = f"{int(rat*100)}% | ".rjust(7, self._just_char) + "▒" * int(
            rat * self._progress_bar_chars
        )
        self.progress_bar2.setText(pct)

    def close(self):
        self.norm_event.clear()
        try:
            if not self.thread.isFinished():
                self._cancel_thread()
                self.thread.quit()
                self.thread.wait()
        except RuntimeError:
            # Already deleted thread
            pass
        super().close()


class LoadingBarWindow(QWidget):
    done = Signal(list)

    def __init__(self, filepath, extensions=[".mp3", ".wav"]):
        super().__init__()
        self.filepath = filepath
        self.extensions = extensions
        self._progress = 0
        self._progress_bar_chars = 50
        self.songs = []
        self._running = False

        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.find_songs()

        self._just_char = "\u2007"  # "Figure Space"

        self.setFixedWidth(510)
        self.setMinimumHeight(120)

        self.setAutoFillBackground(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setContentsMargins(0, 0, 0, 0)

        load_stylesheet(self)

        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.title_layout)

        self.layout = QVBoxLayout()
        self.layout_widget = QWidget()
        self.layout_widget.setLayout(self.layout)
        self.layout.setContentsMargins(3, 3, 3, 3)
        self.layout.setSpacing(3)

        self.title = TitleBar(
            self, "Read Metadata", hide_on_close=True, close_only=True
        )

        self.title_layout.addWidget(self.title)
        self.title_layout.addWidget(self.layout_widget, stretch=1)

        self.status_label = QLabel(f"Loading {len(self.songs)} song(s)...")
        self.layout.addWidget(self.status_label)

        self.progress_bar = QLabel("0% | ".rjust(7, self._just_char))
        self.layout.addWidget(self.progress_bar)

    def reset(self):
        self.find_songs()
        self._progress = 0
        self.status_label.setText(f"Loading {len(self.songs)} song(s)...")
        self.progress_bar.setText("0% | ".rjust(7, self._just_char))

    def find_songs(self):
        if not os.path.exists(self.filepath):
            print("ERROR: Provided directory is not accessible!")
            return

        self.songs = _search_dir(self.filepath, self.extensions)

        if len(self.songs) == 0:
            print(
                f"ERROR: No files with given extension(s) {self.extensions} found in directory!"
            )
            return

        # Sort by title using lowercase characters
        self.songs.sort(key=lambda x: x.lower())

    @Slot()
    def _increment_progress(self, *args):
        self._progress += 1
        rat = self._progress / len(self.songs)
        pct = f"{int(rat*100)}% | ".rjust(7, self._just_char) + "▒" * int(
            rat * self._progress_bar_chars
        )
        self.progress_bar.setText(pct)

    def _done(self, data):
        self._running = False
        self.done.emit(data)

    def load_metadata(self):
        if len(self.songs) > 0:
            self._running = True
            self.worker = MetadataWorkerThread(self.songs, self.filepath)
            self.worker.done.connect(self.hide)
            self.worker.progress.connect(self._increment_progress)
            self.worker.data.connect(self._done)

            self.thread = QThread()
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.start()


class MetadataWorkerThread(QObject):
    done = Signal()
    progress = Signal()
    data = Signal(list)
    finished = Signal()

    def __init__(self, songs, music_folder) -> None:
        super().__init__()

        self.songs = songs
        self.music_folder = music_folder

    @Slot()
    def run(self):
        out = []
        for s in self.songs:
            data = read_metadata(os.path.join(self.music_folder, s))
            out.append([s, sec_to_HMS(data[0])] + data[1:])
            self.progress.emit()
            # time.sleep(0.02)

        self.data.emit(out)
        self.done.emit()
        self.finished.emit()


class TrimWorkerThread(QObject):
    done = Signal()

    def __init__(self, basedir, songname, L, R) -> None:
        super().__init__()
        self.basedir = basedir
        self.songname = songname
        self.L = L
        self.R = R

    @Slot()
    def run(self):
        self.p = Process(
            target=trim_song, args=(self.basedir, self.songname, self.L, self.R)
        )
        self.p.start()
        self.p.join()

        self.done.emit()


class TrimSongWindow(QWidget):
    def __init__(
        self, basedir, selection, bins, duration, message_label, trimming_event
    ):
        super().__init__()
        self.basedir = basedir
        self.songname = selection[0].data(0)
        self.selection = selection
        self._message_label = message_label
        self._trimming_event = trimming_event
        self._busy_event = Event()

        self.setFixedWidth(1000)
        self.setMinimumHeight(500)

        self.setAutoFillBackground(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setContentsMargins(0, 0, 0, 0)

        self.title_layout = QVBoxLayout()
        self.title_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.title_layout)

        self.layout = QVBoxLayout()
        self.layout_widget = QWidget()
        self.layout_widget.setLayout(self.layout)
        self.layout.setContentsMargins(3, 0, 3, 3)
        self.layout.setSpacing(3)

        self.title = TitleBar(self, "Trim Song Length", close_only=True)
        self.title_layout.addWidget(self.title)
        self.title_layout.addWidget(self.layout_widget, stretch=1)
        load_stylesheet(self.title)

        self.graph = SongBarGraph(bins, duration)
        self.layout.addWidget(self.graph, stretch=1)

        self.song_label = QLabel(f"     Trimming: {self.songname}")
        self.song_label.setStyleSheet(
            "background-color: rgb(220, 220, 220); color: black; font-weight: bold; font-size: 15px;"
        )
        self.layout.addWidget(self.song_label)

        self.processing_label = QLabel("Processing...")
        self.processing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processing_label.setStyleSheet("font-weight: bold; font-size: 50px;")
        self.processing_label.setFixedHeight(110)
        self.layout.addWidget(self.processing_label)
        self.processing_label.hide()

        self.pos_slider = ReservedRangeSlider()
        self.pos_slider.setOrientation(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(-1, self.graph.duration + 1)
        self.pos_slider.setBarIsRigid(False)
        self.pos_slider.setValue((0, self.graph.duration))

        self.slider_frame = QFrame()
        self.slider_frame.setContentsMargins(40, 0, 40, 0)
        self.frame_layout = QVBoxLayout()
        self.slider_frame.setLayout(self.frame_layout)
        self.frame_layout.addWidget(self.pos_slider)
        self.layout.addWidget(self.slider_frame)

        self.spinbox_frame = QFrame()
        self.spinbox_layout = QHBoxLayout()
        self.spinbox_frame.setLayout(self.spinbox_layout)
        self.frame_layout.addWidget(self.spinbox_frame)

        self.spinbox_label = QLabel("Keep: ")
        self.spinbox_layout.addWidget(self.spinbox_label)

        self.left_spinbox = QDoubleSpinBox()
        self.left_spinbox.setMinimum(0)
        self.left_spinbox.setMaximum(self.graph.duration)
        self.right_spinbox = QDoubleSpinBox()
        self.right_spinbox.setMinimum(0)
        self.right_spinbox.setMaximum(self.graph.duration)
        self.left_spinbox.valueChanged.connect(self._left_spin_changed)
        self.right_spinbox.valueChanged.connect(self._right_spin_changed)

        self.spinbox_label2 = QLabel(" to ")
        self.spinbox_layout.addWidget(self.left_spinbox, stretch=1)
        self.spinbox_layout.addWidget(self.spinbox_label2)
        self.spinbox_layout.addWidget(self.right_spinbox, stretch=1)

        self.pos_slider.sliderMoved.connect(self._moved_event)
        self.pos_slider.sliderPressed.connect(self._slider_clicked)

        self.button_frame = QFrame()
        self.button_layout = QHBoxLayout()
        self.button_frame.setLayout(self.button_layout)
        self.frame_layout.addWidget(self.button_frame)

        self.confirm_button = QPushButton("OK")
        self.confirm_button.pressed.connect(self._trim_song)
        self.button_layout.addWidget(self.confirm_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.pressed.connect(self.close)
        self.button_layout.addWidget(self.cancel_button)

        self._slider_clicked()

    def _slider_clicked(self):
        self._moved_event(self.pos_slider.value())

    def _moved_event(self, event):
        L, R = event
        self.graph.set_highlighted(L, R)
        self.left_spinbox.setValue(L)
        self.right_spinbox.setValue(R)

    def _left_spin_changed(self, val):
        if not self.pos_slider.reserved:
            self.pos_slider.setValue((val, self.right_spinbox.value()))
            self.graph.set_highlighted(val, self.right_spinbox.value())

    def _right_spin_changed(self, val):
        if not self.pos_slider.reserved:
            self.pos_slider.setValue((self.left_spinbox.value(), val))
            self.graph.set_highlighted(self.left_spinbox.value(), val)

    def _trim_song(self):
        L, R = self.pos_slider.value()
        if L <= 0 and R >= self.graph.duration:
            self._message_label.setText(
                f"No trimming performed: zero trim length selected"
            )
            self.close()
            return

        self._show_processing()

        self.worker = TrimWorkerThread(self.basedir, self.songname, L, R)
        self.worker.done.connect(self._done)

        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _show_processing(self):
        self.slider_frame.hide()
        self.processing_label.show()

    def _done(self):
        # Finished processing
        L, R = self.pos_slider.value()
        self.selection[1].setText(sec_to_HMS(R - L))
        self._message_label.setText(f"Trimmed: {self.songname}")
        self.close()

    def move_to_center(self, parent, override_x=None, override_y=None):
        px = override_x if override_x is not None else parent.x()
        py = override_y if override_y is not None else parent.y()

        pw, ph = parent.width(), parent.height()

        self.move(px + pw / 2 - self.width() / 2, py + ph / 2 - self.height() / 2)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Enter:
            self._trim_song()
        event.accept()

    def close(self):
        self._trimming_event.clear()
        super().close()


class SongBarGraph(QWidget):
    def __init__(self, bins, duration):
        super().__init__()

        self.duration = duration
        self.bins = bins

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.dataset = QBarSet("data")
        self.dataset.append(bins)
        self.dataset.setColor("black")
        self.dataset.setBorderColor("gray")
        self.dataset.setSelectedColor("red")
        self.neg_dataset = QBarSet("-data")
        self.neg_dataset.setColor("black")
        self.neg_dataset.setBorderColor("black")
        self.neg_dataset.setSelectedColor("red")
        self.neg_dataset.append([-b for b in bins])

        self._series = QStackedBarSeries()
        self._series.setBarWidth(1)
        self._series.append(self.dataset)
        self._series.append(self.neg_dataset)

        self.chart = QChart()
        self.chart.legend().setVisible(False)

        self._x_axs = QValueAxis()
        self._x_axs.setRange(0, duration)
        self._x_axs.setTickCount(duration // 15)
        self._x_axs.applyNiceNumbers()
        self._x_axs.setTitleText("Seconds")

        # Note: will produce a warning: "Series not in the chart. Please addSeries to chart first."
        # The warning should be ignored. The current order is necessary for the custom axis ticks
        # and bars to sync up automatically
        self.chart.addAxis(self._x_axs, Qt.AlignmentFlag.AlignBottom)
        self._series.attachAxis(self._x_axs)
        self.chart.addSeries(self._series)

        self._chart_view = QChartView(self.chart)
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.layout.addWidget(self._chart_view)

    def set_highlighted(self, L, R):
        idx = int(len(self.bins) * (L / self.duration))
        idx2 = int(len(self.bins) * (R / self.duration))

        sel_idx = [i for i in range(len(self.bins)) if i < idx or i >= idx2]

        self.dataset.deselectAllBars()
        self.neg_dataset.deselectAllBars()
        self.dataset.selectBars(sel_idx)
        self.neg_dataset.selectBars(sel_idx)


if __name__ == "__main__":

    app = QApplication()

    basedir = "D:\\Songs\\Meh"
    songname = "Kid Rock - Born Free.mp3"
    TW = TrimSongWindow(basedir, songname)
    TW.show()

    app.exec()
