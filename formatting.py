# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from PySide6.QtWidgets import QLabel, QProxyStyle, QStyle, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette


class FormatLabel(QLabel):
    # For easier use of the stylesheet
    pass


class TitleLabel(QLabel):
    # For easier use of the stylesheet
    pass


class HeaderLabel(QLabel):
    # For easier use of the stylesheet
    pass


class ColoredTableHeaderStyle(QProxyStyle):
    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.ControlElement.CE_HeaderSection and isinstance(
            widget, QHeaderView
        ):
            fill = option.palette.brush(
                QPalette.ColorRole.Window
            )  # the Qt implementation actually sets the background brush on the Window color role, the default Windows style simply ignores it
            painter.fillRect(
                option.rect, fill
            )  # fill the header section with the background brush
        else:
            self.baseStyle().drawControl(
                element, option, painter, widget
            )  # use the default implementation in all other cases


class SliderProxyStyle(QProxyStyle):
    def drawControl(self, ctl, opt, qp, widget=None):
        if ctl == self.CE_ScrollBarSlider:
            opt = opt.__class__(opt)
            opt.palette.setColor(opt.palette.Button, Qt.green)
        super().drawControl(ctl, opt, qp, widget)
