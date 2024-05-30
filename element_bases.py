# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QTimer
import os
from PySide6.QtWidgets import QWidget
import yt_dlp
from superqt import QDoubleRangeSlider


class TimedMessageLabel(QLabel):
    def __init__(self, delay_ms=10000):
        super().__init__()
        self.delay_ms = delay_ms

    def setText(self, msg, auto_clear=True):
        super().setText(msg)

        if auto_clear:
            QTimer.singleShot(self.delay_ms, self.clear)

    def clear(self):
        super().setText("")


class ReservedSlider(QSlider):
    # Tracks whether the user is interacting with the slider
    # Useful for preventing self-updates to the slider position at the wrong time
    def __init__(self, unreserve_delay=1000):
        super().__init__()

        self.unreserve_delay = unreserve_delay
        self.reserved = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reserved = False

        return super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reserved = True

        return super().mousePressEvent(event)


class ReservedRangeSlider(QDoubleRangeSlider):
    # Tracks whether the user is interacting with the slider
    # Useful for preventing self-updates to the slider position at the wrong time
    def __init__(self, unreserve_delay=1000):
        super().__init__()

        self.unreserve_delay = unreserve_delay
        self.reserved = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reserved = False

        return super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reserved = True

        return super().mousePressEvent(event)


class ClickableSlider(ReservedSlider):
    # On click the slider position will be set to where the user clicked

    def mouseReleaseEvent(self, event):
        super(ClickableSlider, self).mouseReleaseEvent(event)

        if event.button() == Qt.LeftButton:
            val = self.pixelPosToRangeValue(event.position())
            self.setValue(val)

    def pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
        )
        sr = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
        )

        if self.orientation() == Qt.Horizontal:
            sliderLength = sr.width()
            sliderMin = gr.x()
            sliderMax = gr.right() - sliderLength + 1
        else:
            sliderLength = sr.height()
            sliderMin = gr.y()
            sliderMax = gr.bottom() - sliderLength + 1
        pr = pos - sr.center() + sr.topLeft()
        p = pr.x() if self.orientation() == Qt.Horizontal else pr.y()
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            p - sliderMin,
            sliderMax - sliderMin,
            opt.upsideDown,
        )


class DefaultLogger:
    def debug(self, msg):
        print(msg)

    def warning(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)


def ytd(URL, dir, logger=DefaultLogger()):
    # yt-dlp configured for audio-only downloads
    outformat = os.path.join(dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": '251/bestaudio/"bestvideo[height<=?720]"',
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "5",
            }
        ],
        "logger": logger,
        "outtmpl": outformat,
        # "verbose": True,
        # "no-cache-dir": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([u for u in URL.replace(" ", "").split(",") if len(u) > 0])


class LineEditDefaultText(QLineEdit):
    # Adds default text to a LineEdit widget which disappers when it gains focus
    clicked = Signal()

    def __init__(self, default_text):
        super().__init__()

        self.default_text = default_text
        self.setText(self.default_text)
        self.setStyleSheet("color: rgb(150, 150, 150);")
        self.clicked.connect(self.prepare_for_edit)

    def clear(self):
        if self.text() != self.default_text:
            self.setText(self.default_text)
            self.setStyleSheet("color: rgb(150, 150, 150);")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if len(self.text()) == 0:
            self.setText(self.default_text)
            self.setStyleSheet("color: rgb(150, 150, 150);")

    def focusInEvent(self, event):
        self.setStyleSheet("color: rgb(250, 250, 250);")
        super().focusInEvent(event)

    def prepare_for_edit(self):
        if self.text() == self.default_text:
            self.setText("")

    def return_conn(self, command):
        self.returnPressed.connect(command)


class LabelSpinBox(QWidget):
    def __init__(self, text="", minimum=0, maximum=1):
        super().__init__()

        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.label = QLabel(text)
        self.layout.addWidget(self.label)

        self.spinbox = QDoubleSpinBox()
        self.spinbox.setMinimum(minimum)
        self.spinbox.setMaximum(maximum)
        self.layout.addWidget(self.spinbox)

    def set_value(self, value):
        self.spinbox.setValue(value)

    def get_value(self):
        return self.spinbox.value()


# TODO: WIP
class WindowOverlay(QWidget):
    def __init__(self, text):
        super().__init__()

        self.setAutoFillBackground(True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet("background-color: black;")

        self.label = QLabel(text)
