"""IT Records - PyQt5 desktop app.  Run with:  python main.py"""

from __future__ import annotations

import re
import sys
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

_log = logging.getLogger("itrecords.ui")

from PyQt5.QtCore import (Qt, QAbstractAnimation, QDate, QEasingCurve, QEvent, QObject,
                          QPropertyAnimation, QSettings, QTimer)
from PyQt5.QtGui import QColor, QCursor, QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QCalendarWidget,
                             QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QFrame, QGraphicsOpacityEffect, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                             QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                             QScrollArea, QSplitter, QStackedWidget, QStyle,
                             QStyledItemDelegate, QTableWidget, QTableWidgetItem,
                             QTextBrowser, QTextEdit, QVBoxLayout, QWidget, QWidgetAction)

import core
from core import (ASSET_LABELS, ASSET_META, CHOICES, COLUMNS, FIELDS, GROUPS, LABELS, ROLES,
                  Store, Denied, Invalid, export_excel, export_pdf, export_record_pdf,
                  local_time, read_excel)

# ------------------------------------------------------------------ theme

LIGHT = {
    "bg": "#f3f6f5", "surface": "#ffffff", "border": "#dbe4e2", "text": "#14211f",
    "muted": "#5f7472", "brand": "#006a63", "brand_dark": "#004f49", "brand_soft": "#e2f1ee",
    "accent": "#ffd100", "danger": "#d7282f", "danger_dark": "#b01d23", "alt_row": "#f7faf9",
    "hover_row": "#eaf5f3",
    "sidebar": "#0b3b37", "side_text": "#b9d3cf", "side_hover": "#13504a",
    "banner_bg": "#fff8d6", "banner_text": "#6b5900", "disabled": "#b9c6c4",
}
DARK = {
    "bg": "#101716", "surface": "#18211f", "border": "#2a3735", "text": "#e3ecea",
    "muted": "#8fa39f", "brand": "#1a9488", "brand_dark": "#137a70", "brand_soft": "#1b3431",
    "accent": "#ffd100", "danger": "#e0474d", "danger_dark": "#c2353b", "alt_row": "#1c2624",
    "hover_row": "#223330",
    "sidebar": "#0a100f", "side_text": "#93aaa6", "side_hover": "#16211f",
    "banner_bg": "#3a3312", "banner_text": "#f1dc8a", "disabled": "#3a4846",
}
PALETTE = dict(LIGHT)       # the palette in use - the dashboard charts read it too


def build_style(p: dict) -> str:
    return f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {p['text']}; }}
QMainWindow, QDialog, #page {{ background: {p['bg']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; }}

#sidebar {{ background: {p['sidebar']}; }}
#sidebar QLabel {{ color: {p['side_text']}; background: transparent; }}
#sidebar #brand {{ color: #ffffff; font-size: 17pt; font-weight: 800; }}
#sidebar #brandDot {{ color: {p['accent']}; font-size: 17pt; font-weight: 800; }}
#brand {{ color: {p['brand']}; font-size: 16pt; font-weight: 800; }}
#brandDot {{ color: {p['accent']}; font-size: 16pt; font-weight: 800; }}
#navScroll, #navScroll > QWidget, #navScroll > QWidget > QWidget {{ background: transparent; }}
#navSection {{ font-size: 8pt; font-weight: 700; padding: 12px 10px 3px 10px; }}
QPushButton#nav {{ background: transparent; color: {p['side_text']}; border: none;
                   border-left: 3px solid transparent; border-radius: 0; text-align: left;
                   padding: 6px 12px; font-weight: 600; }}
QPushButton#nav:hover {{ background: {p['side_hover']}; color: #ffffff; }}
QPushButton#nav:checked {{ background: {p['side_hover']}; color: #ffffff;
                           border-left: 3px solid {p['accent']}; }}
#userCard {{ background: {p['side_hover']}; border-radius: 8px; }}
#sidebar #userName {{ color: #ffffff; font-weight: 700; }}
QPushButton#side {{ background: transparent; color: #ffffff; border: 1px solid {p['side_text']};
                    border-radius: 6px; padding: 6px 10px; font-weight: 600; }}
QPushButton#side:hover {{ background: {p['brand']}; border-color: {p['brand']}; }}

#pageTitle {{ font-size: 17pt; font-weight: 700; }}
#subtitle, #who {{ color: {p['muted']}; }}
#banner {{ background: {p['banner_bg']}; border-left: 4px solid {p['accent']}; padding: 8px 10px;
           color: {p['banner_text']}; }}

QPushButton {{ background: {p['brand']}; color: #ffffff; border: 1px solid {p['brand']};
               border-radius: 6px; padding: 6px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {p['brand_dark']}; border-color: {p['brand_dark']}; }}
QPushButton:disabled {{ background: {p['disabled']}; border-color: {p['disabled']}; color: {p['surface']}; }}
QPushButton#ghost {{ background: {p['surface']}; color: {p['brand']}; border-color: {p['border']}; }}
QPushButton#ghost:hover {{ background: {p['brand_soft']}; border-color: {p['brand']}; }}
QPushButton#ghost:disabled {{ background: {p['surface']}; color: {p['disabled']}; border-color: {p['border']}; }}
QPushButton:pressed {{ background: {p['brand_dark']}; padding-top: 7px; padding-bottom: 5px; }}
QPushButton#ghost:pressed {{ background: {p['brand_soft']}; }}
QPushButton#danger {{ background: {p['danger']}; color: #ffffff; border-color: {p['danger']}; }}
QPushButton#danger:hover {{ background: {p['danger_dark']}; border-color: {p['danger_dark']}; }}
QPushButton#danger:pressed {{ background: {p['danger_dark']}; }}
QPushButton#danger:disabled {{ background: {p['surface']}; color: {p['disabled']}; border-color: {p['border']}; }}
QPushButton#menuDanger {{ background: transparent; color: {p['danger']}; border: none; border-radius: 4px;
                          text-align: left; padding: 6px 22px; font-weight: 600; }}
QPushButton#menuDanger:hover {{ background: {p['danger']}; color: #ffffff; }}
QPushButton#more {{ background: {p['surface']}; color: {p['text']}; border-color: {p['border']};
                    padding-right: 24px; }}
QPushButton#more:hover {{ background: {p['brand_soft']}; }}
QPushButton#more::menu-indicator {{ subcontrol-position: right center; right: 8px; }}
#divider {{ background: {p['border']}; }}

QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['brand_soft']}; color: {p['text']}; }}
QMenu::item:disabled {{ color: {p['disabled']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 6px; }}

QLineEdit, QComboBox, QDateEdit, QTextEdit {{ background: {p['surface']}; border: 1px solid {p['border']};
                                              border-radius: 6px; padding: 6px 8px; }}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover {{ border: 1px solid {p['muted']}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{ border: 1px solid {p['brand']}; }}
QTextBrowser {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 8px; }}
QDateEdit::drop-down {{ width: 26px; border: none; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {p['brand']}; }}
QCalendarWidget QToolButton {{ color: #ffffff; background: transparent; font-weight: 700;
                               padding: 4px 8px; border-radius: 4px; }}
QCalendarWidget QToolButton:hover {{ background: {p['brand_dark']}; }}
QCalendarWidget QMenu {{ background: {p['surface']}; }}
QCalendarWidget QSpinBox {{ background: {p['surface']}; color: {p['text']}; }}
QCalendarWidget QAbstractItemView {{ background: {p['surface']}; color: {p['text']};
                                     selection-background-color: {p['brand']}; selection-color: #ffffff;
                                     outline: 0; }}
QCalendarWidget QAbstractItemView:disabled {{ color: {p['disabled']}; }}
QSplitter::handle {{ background: transparent; width: 10px; }}
QLineEdit:read-only {{ background: {p['bg']}; color: {p['muted']}; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; selection-background-color: {p['brand_soft']};
                               selection-color: {p['text']}; }}

QTableWidget {{ background: {p['surface']}; alternate-background-color: {p['alt_row']};
                border: 1px solid {p['border']}; border-radius: 8px; gridline-color: {p['border']};
                selection-background-color: {p['brand_soft']}; selection-color: {p['text']}; }}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView {{ background: {p['surface']}; }}
QHeaderView::section {{ background: {p['surface']}; color: {p['muted']}; font-weight: 700;
                        padding: 7px 6px; border: none; border-bottom: 2px solid {p['brand']};
                        border-right: 1px solid {p['border']}; }}
QTableCornerButton::section {{ background: {p['surface']}; border: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {p['border']};
                                                             border-radius: 5px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {p['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QGroupBox {{ border: 1px solid {p['border']}; border-radius: 8px; margin-top: 14px;
             background: {p['surface']}; padding-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px;
                    color: {p['brand']}; font-weight: 700; }}
#tile {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; }}
#tile:hover {{ border: 1px solid {p['brand']}; background: {p['alt_row']}; }}
#tileValue {{ font-size: 20pt; font-weight: 700; color: {p['brand']}; }}
#tileLabel {{ color: {p['muted']}; font-weight: 600; }}
QLabel#error {{ color: {p['danger']}; }}
QLabel#ok {{ color: {p['brand']}; font-weight: 700; }}
QLabel#count {{ background: {p['brand_soft']}; color: {p['brand']}; border-radius: 10px;
                padding: 4px 12px; font-weight: 700; }}
QStatusBar {{ background: {p['surface']}; color: {p['muted']}; border-top: 1px solid {p['border']}; }}
"""


STYLE = build_style(LIGHT)


def apply_theme(name: str) -> None:
    """Switch the whole app between the light and dark palettes."""
    PALETTE.clear()
    PALETTE.update(DARK if name == "dark" else LIGHT)
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(build_style(PALETTE))


class SortItem(QTableWidgetItem):
    """A cell that sorts the way people read: 2 before 10, and 'b' next to 'B'."""

    def __lt__(self, other):
        a, b = self.text().strip(), other.text().strip()
        if a.isdigit() and b.isdigit():
            return int(a) < int(b)
        if a.isdigit() != b.isdigit():
            return a.isdigit()              # numbers ahead of text
        return a.lower() < b.lower()


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedSize(1, 24)
    return line


def page_title(box: QVBoxLayout, title: str, subtitle: str = "", right: QWidget | None = None):
    """The heading every page opens with."""
    row = QHBoxLayout()
    text = QVBoxLayout()
    text.setSpacing(0)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    text.addWidget(heading)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("subtitle")
        text.addWidget(sub)
    row.addLayout(text)
    row.addStretch()
    if right is not None:
        row.addWidget(right, 0, Qt.AlignBottom)
    box.addLayout(row)


def search_box(placeholder: str) -> QLineEdit:
    box = QLineEdit(placeholderText=placeholder)
    box.setClearButtonEnabled(True)
    box.setMinimumWidth(320)
    return box


def make_table(multi: bool = True) -> QTableWidget:
    table = QTableWidget()
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection if multi
                           else QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(32)
    table.horizontalHeader().setHighlightSections(False)
    RowHover(table)
    return table


# ------------------------------------------------------------------ email
#
# The sender account for "Send Email". Kept in QSettings (per Windows user) and
# editable from Email Settings. A fresh PC starts from EMAIL_DEFAULTS plus an
# optional email.json beside the database - the app password lives there (or in
# Email Settings), never in the source.

EMAIL_DEFAULTS = {
    "smtp_server": "smtp.gmail.com",      # bipl.io mail is hosted on Google Workspace
    "smtp_port": "587",
    "smtp_email": "kawish.iftikhar@bipl.io",
    "smtp_password": "",
}
_RETIRED_SENDERS = {"hammadalamgir778@gmail.com"}


def _email_file_defaults() -> dict:
    """email.json next to the database (or next to the exe), if one exists."""
    import json
    folders = [core.default_db_path().parent, Path(sys.executable).parent, Path(__file__).parent]
    for folder in folders:
        path = folder / "email.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            return {k: str(data[k]) for k in EMAIL_DEFAULTS if data.get(k)}
    return {}


def email_config() -> dict:
    """The saved sender settings. A PC with nothing saved yet, or still on the
    old built-in sender, is moved onto the current defaults."""
    settings = QSettings("ITRecords", "Settings")
    saved = str(settings.value("smtp_email", "") or "").strip().lower()
    if not saved or saved in _RETIRED_SENDERS or not settings.value("smtp_password", ""):
        for key, value in (EMAIL_DEFAULTS | _email_file_defaults()).items():
            settings.setValue(key, value)
    return {key: str(settings.value(key, default) or "")
            for key, default in EMAIL_DEFAULTS.items()}


def _smtp(config: dict) -> smtplib.SMTP:
    """A signed-in SMTP connection (STARTTLS on 587, SSL on 465)."""
    port = int(config["smtp_port"])
    if port == 465:
        server = smtplib.SMTP_SSL(config["smtp_server"], port, timeout=20)
    else:
        server = smtplib.SMTP(config["smtp_server"], port, timeout=20)
        server.starttls()
    server.login(config["smtp_email"], config["smtp_password"].replace(" ", ""))
    return server


def brand_mark(subtitle: str = "") -> QWidget:
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    name = QLabel("IT Records")
    name.setObjectName("brand")
    dot = QLabel(".")
    dot.setObjectName("brandDot")
    row.addWidget(name)
    row.addWidget(dot)
    if subtitle:
        sub = QLabel("   |   " + subtitle)
        sub.setObjectName("subtitle")
        row.addWidget(sub)
    row.addStretch()
    return box


def warn(parent, text: str, title: str = "IT Records"):
    QMessageBox.warning(parent, title, text)


# ----------------------------------------------------------------- sign in

class LoginDialog(QDialog):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.username = ""
        self.role = ""
        self.setWindowTitle("IT Records - Sign in")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(brand_mark())
        hint = QLabel("Sign in to continue")
        hint.setObjectName("subtitle")
        layout.addWidget(hint)

        self.user_box = QLineEdit(placeholderText="Username")
        self.pass_box = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        layout.addWidget(self.user_box)
        layout.addWidget(self.pass_box)

        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        button = QPushButton("Sign in")
        button.clicked.connect(self.try_login)
        layout.addWidget(button)
        self.pass_box.returnPressed.connect(self.try_login)
        self.user_box.returnPressed.connect(self.pass_box.setFocus)

    def try_login(self):
        try:
            self.role = self.store.login(self.user_box.text(), self.pass_box.text())
        except Invalid as exc:
            self.error.setText(str(exc))
            self.pass_box.clear()
            self.pass_box.setFocus()
            return
        self.username = self.user_box.text().strip().lower()
        self.accept()


# ----------------------------------------------------------- window helpers

def fit_to_screen(window: QWidget, width: float, height: float):
    """Size a window to a share of the screen it opens on, and centre it."""
    screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
    area = screen.availableGeometry()
    window.resize(int(area.width() * width), int(area.height() * height))
    frame = window.frameGeometry()
    frame.moveCenter(area.center())
    window.move(frame.topLeft())


def confirm_danger(parent, title: str, text: str, action: str = "Delete") -> bool:
    """A red, cancel-by-default confirmation for anything that destroys data."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(f"<b>{title}</b>")
    box.setInformativeText(text)
    go = box.addButton(action, QMessageBox.DestructiveRole)
    go.setObjectName("danger")
    cancel = box.addButton(QMessageBox.Cancel)
    cancel.setObjectName("ghost")
    for button in (go, cancel):                  # re-style now the names are set
        button.style().unpolish(button)
        button.style().polish(button)
    box.setDefaultButton(cancel)
    box.exec_()
    return box.clickedButton() is go


class FadeIn(QObject):
    """App-wide: every window and dialog fades in instead of popping up."""

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Show and obj.isWidgetType() and obj.isWindow()
                and isinstance(obj, (QDialog, QMainWindow))):
            obj.setWindowOpacity(0.0)
            anim = QPropertyAnimation(obj, b"windowOpacity", obj)
            anim.setDuration(170)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start(QAbstractAnimation.DeleteWhenStopped)
        return False


class RowHover(QStyledItemDelegate):
    """Tints the whole row under the mouse, so it is clear which record a
    double-click will open."""

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table
        self.row = -1
        table.setMouseTracking(True)
        table.setItemDelegate(self)
        table.entered.connect(self._enter)
        table.viewport().installEventFilter(self)

    def _enter(self, index):
        if index.row() != self.row:
            self.row = index.row()
            self.table.viewport().update()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Leave and self.row != -1:
            self.row = -1
            self.table.viewport().update()
        return False

    def paint(self, painter, option, index):
        if index.row() == self.row and not (option.state & QStyle.State_Selected):
            painter.fillRect(option.rect, QColor(PALETTE["hover_row"]))
        super().paint(painter, option, index)


# ------------------------------------------------------------ employee form

class DatePopup(QDateEdit):
    """A date box that may be blank ('Not set'). Opening the calendar on a
    blank date shows this month, not the year 1900 that stands for blank."""

    BLANK = QDate(1900, 1, 1)

    def __init__(self):
        super().__init__()
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd MMM yyyy")
        self.setMinimumDate(self.BLANK)
        self.setSpecialValueText("Not set")
        self.setDate(self.BLANK)
        cal = self.calendarWidget()
        cal.setGridVisible(False)
        cal.setFirstDayOfWeek(Qt.Monday)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.date() == self.BLANK:
            today = QDate.currentDate()
            QTimer.singleShot(0, lambda: self.calendarWidget().setCurrentPage(
                today.year(), today.month()))


class DateField(QWidget):
    """Date of joining: a calendar, plus Today and Clear. The value is stored
    as yyyy-MM-dd; a value in some other layout is read if it can be, and kept
    untouched if it cannot - opening a record must never change it."""

    FORMATS = ("yyyy-MM-dd", "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy",
               "dd.MM.yyyy", "dd MMM yyyy", "d MMM yyyy", "dd-MMM-yyyy", "d-MMM-yy",
               "MMM d, yyyy", "yyyy/MM/dd")

    def __init__(self, value: str = ""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.edit = DatePopup()
        row.addWidget(self.edit, 1)
        for text, slot in (("Today", lambda: self.edit.setDate(QDate.currentDate())),
                           ("Clear", lambda: self.edit.setDate(DatePopup.BLANK))):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            row.addWidget(b)
        self._raw = ""
        value = (value or "").strip()
        if value:
            parsed = next((d for d in (QDate.fromString(value, f) for f in self.FORMATS)
                           if d.isValid()), None)
            if parsed:
                self.edit.setDate(parsed)
            else:
                self._raw = value
                self.edit.setToolTip(f"Saved as '{value}' - not a date the calendar can "
                                     "read. It is kept unless you pick a new date.")
        self.edit.dateChanged.connect(lambda _: setattr(self, "_raw", ""))

    def text(self) -> str:
        if self._raw:
            return self._raw
        d = self.edit.date()
        return "" if d == DatePopup.BLANK else d.toString("yyyy-MM-dd")


class EmployeeDialog(QDialog):
    """Add or edit one employee. Every field of the entity is on this one form."""

    def __init__(self, parent, record: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit employee" if record else "Add employee")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        fit_to_screen(self, 0.8, 0.85)
        self.inputs: dict[str, QWidget] = {}
        labels = dict((f[0], f[1]) for f in FIELDS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 14)
        who = (f"{record.get('emp_name') or record.get('emp_id')}  ·  SNO {record.get('sno')}"
               if record else "A new employee joins the end of the register")
        page_title(outer, "Edit employee" if record else "Add employee", who)

        scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        holder = QWidget()
        holder.setObjectName("page")
        body = QVBoxLayout(holder)
        body.setContentsMargins(0, 0, 8, 0)

        for group_name, keys in GROUPS:
            group = QGroupBox(group_name)
            grid = QGridLayout(group)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            for index, key in enumerate(keys):
                row, column = divmod(index, 2)
                value = str(record.get(key, "")) if record else ""
                if key == "sno":
                    widget = QLineEdit(value)
                    widget.setReadOnly(True)
                    widget.setPlaceholderText("Given automatically")
                elif key == "join_date":
                    widget = DateField(value)
                elif key in CHOICES:
                    widget = QComboBox()
                    widget.addItems(CHOICES[key])
                    if value:
                        widget.setCurrentText(value)
                else:
                    widget = QLineEdit(value)
                self.inputs[key] = widget
                grid.addWidget(QLabel(labels[key]), row, column * 2)
                grid.addWidget(widget, row, column * 2 + 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            body.addWidget(group)

        note = QLabel("Only Employee ID is required. Anything not known yet can be left blank "
                      "and filled in later. A serial number that an asset is already issued "
                      "under will be refused.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        body.addWidget(note)
        body.addStretch()
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setObjectName("ghost")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.inputs["emp_id"].setFocus()

    def values(self) -> dict:
        result = {}
        for key, w in self.inputs.items():
            result[key] = w.currentText() if isinstance(w, QComboBox) else w.text()
        return result

    def accept(self):
        """Validate before closing."""
        emp_id_widget = self.inputs.get("emp_id")
        if emp_id_widget and not emp_id_widget.text().strip():
            emp_id_widget.setStyleSheet(f"border: 2px solid {PALETTE['danger']};")
            emp_id_widget.setPlaceholderText("Employee ID is required!")
            warn(self, "Employee ID cannot be empty. Please enter a valid Employee ID.")
            emp_id_widget.setFocus()
            return
        if emp_id_widget:
            emp_id_widget.setStyleSheet("")
        super().accept()


class PasswordDialog(QDialog):
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        self.box = QLineEdit(echoMode=QLineEdit.Password)
        self.again = QLineEdit(echoMode=QLineEdit.Password)
        form.addRow(f"New password ({core.MIN_PASSWORD}+ characters)", self.box)
        form.addRow("Repeat it", self.again)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def check(self):
        if self.box.text() != self.again.text():
            warn(self, "The two passwords are not the same.")
            return
        self.accept()


class EmailConfigDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Email Settings")
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        config = email_config()
        self.server = QLineEdit(config["smtp_server"])
        self.port = QLineEdit(config["smtp_port"])
        self.email = QLineEdit(config["smtp_email"])
        self.password = QLineEdit(config["smtp_password"], echoMode=QLineEdit.Password)
        form.addRow("SMTP Server", self.server)
        form.addRow("SMTP Port", self.port)
        form.addRow("Sender Email", self.email)
        form.addRow("App Password", self.password)
        hint = QLabel("For Google Workspace / Gmail use smtp.gmail.com, port 587 and an "
                      "app password (Google Account → Security → App passwords).")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        test = buttons.addButton("Test connection", QDialogButtonBox.ActionRole)
        test.setObjectName("ghost")
        test.clicked.connect(self.test)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {"smtp_server": self.server.text().strip(), "smtp_port": self.port.text().strip(),
                "smtp_email": self.email.text().strip(), "smtp_password": self.password.text()}

    def test(self):
        """Sign in to the mail server without sending anything."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with _smtp(self.values()):
                pass
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Email Settings", f"Could not sign in:\n{exc}")
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Email Settings", "Signed in to the mail server - "
                                "these settings work.")

    def save(self):
        values = self.values()
        if not all(values.values()) or not values["smtp_port"].isdigit():
            warn(self, "Fill in every field (the port is a number, usually 587).")
            return
        settings = QSettings("ITRecords", "Settings")
        for key, value in values.items():
            settings.setValue(key, value)
        self.accept()


# Email templates. {placeholders} are filled in for each employee; a line whose
# placeholders are all blank for that person is left out, and so is a block
# (e.g. 'Equipment issued to you') that ends up with nothing in it.

MAIL_FIELDS = [
    ("name", "Full name"), ("first_name", "First name"), ("emp_id", "Employee ID"),
    ("sno", "Serial no (SNO)"), ("designation", "Designation"), ("department", "Department"),
    ("join_date", "Date of joining"), ("user_id", "User ID"), ("email", "Email"),
    ("contact_no", "Contact no"), ("location", "Location"), ("region", "Region"),
    ("laptop", "Laptop"), ("mobile", "Mobile"), ("ip_phone", "IP phone"),
    ("sim_number", "SIM number"), ("company", "Company"), ("today", "Today's date"),
]

_DETAILS = """    Employee ID      : {emp_id}
    Serial No (SNO)  : {sno}
    Designation      : {designation}
    Department       : {department}
    Date of joining  : {join_date}
    User ID          : {user_id}
    Official email   : {email}
    Location         : {location}"""

_EQUIPMENT = """Equipment issued to you:
    Laptop           : {laptop}
    Mobile           : {mobile}
    SIM number       : {sim_number}
    IP phone         : {ip_phone}"""

_SIGN_OFF = """Best regards,
IT Department
{company_sig}"""

EMAIL_TEMPLATES = {
    "Welcome new employee": (
        "Welcome to {company}, {first_name}!",
        "Dear {name},\n\n"
        "Welcome to {company}! We are glad to have you with us and wish you every success "
        "in your new role.\n\n"
        "The IT department has set up your records. Please keep this email for reference:\n\n"
        + _DETAILS + "\n\n" + _EQUIPMENT + "\n\n"
        "If any of these details are wrong, or you need help with your equipment or "
        "accounts, simply reply to this email.\n\n" + _SIGN_OFF),
    "Your IT records & equipment": (
        "Your IT records - {name} ({emp_id})",
        "Dear {name},\n\n"
        "Here is a summary of the details the IT department holds for you:\n\n"
        + _DETAILS + "\n\n" + _EQUIPMENT + "\n\n"
        "Please reply to this email if anything needs correcting.\n\n" + _SIGN_OFF),
    "Custom message": (
        "",
        "Dear {name},\n\n\n\n" + _SIGN_OFF),
}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def mail_fields(record: dict | None, company: str, address: str = "") -> dict:
    """The values an email template can use, for one employee."""
    r = record or {}

    def pair(name, serial):
        name, serial = (r.get(name) or "").strip(), (r.get(serial) or "").strip()
        return f"{name} (S/N {serial})" if name and serial else name or serial

    name = (r.get("emp_name") or "").strip()
    join = (r.get("join_date") or "").strip()
    parsed = QDate.fromString(join, "yyyy-MM-dd")
    return {
        "name": name or "Colleague",
        "first_name": name.split()[0] if name else "Colleague",
        "emp_id": r.get("emp_id", ""), "sno": r.get("sno", ""),
        "designation": r.get("designation", ""), "department": r.get("department", ""),
        "join_date": parsed.toString("dd MMMM yyyy") if parsed.isValid() else join,
        "user_id": r.get("user_id", ""), "email": r.get("email", "") or address,
        "contact_no": r.get("contact_no", ""), "location": r.get("location", ""),
        "region": r.get("region", ""),
        "laptop": pair("laptop_name_type", "laptop_serial"),
        "mobile": pair("mobile_name_type", "mobile_serial"),
        "ip_phone": r.get("ip_phone", ""), "sim_number": r.get("sim_number", ""),
        "company": company or "the team",
        "company_sig": company,
        "today": QDate.currentDate().toString("dd MMMM yyyy"),
    }


def render_mail(text: str, fields: dict) -> str:
    """Fill a template for one person, dropping lines and blocks left empty."""
    out_blocks = []
    for block in text.split("\n\n"):
        lines, had_fields, kept_fields = [], False, False
        for line in block.split("\n"):
            keys = _PLACEHOLDER.findall(line)
            known = [k for k in keys if k in fields]
            if known:
                had_fields = True
                if not any(str(fields[k]).strip() for k in known):
                    continue                              # nothing to say on this line
                kept_fields = True
            lines.append(_PLACEHOLDER.sub(
                lambda m: str(fields.get(m.group(1), m.group(0))), line))
        if had_fields and not kept_fields and len(lines) <= 1:
            continue                                      # a heading with nothing under it
        out_blocks.append("\n".join(lines))
    return "\n\n".join(out_blocks).strip() + "\n"


def mail_html(text: str) -> str:
    """The same message as tidy HTML: 'Label : value' lines become a table."""
    from html import escape
    row = re.compile(r"^\s{2,}(.+?)\s*:\s(.*)$")
    parts = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        rows = [row.match(l) for l in lines]
        if rows and all(rows[1:]) and (len(lines) > 1 or rows[0]):
            head = "" if rows[0] else f"<p style='margin:0 0 6px 0'><b>{escape(lines[0])}</b></p>"
            cells = [m for m in rows if m]
            table = "".join(
                f"<tr><td style='padding:5px 14px 5px 0;color:#5f7472;white-space:nowrap'>"
                f"{escape(m.group(1))}</td><td style='padding:5px 0'><b>{escape(m.group(2))}</b>"
                f"</td></tr>" for m in cells)
            parts.append(f"{head}<table style='border-collapse:collapse;border-left:3px solid "
                         f"#006a63;padding-left:12px;margin:0 0 16px 4px'>{table}</table>")
        else:
            parts.append("<p style='margin:0 0 14px 0'>" +
                         "<br>".join(escape(l) for l in lines) + "</p>")
    return ("<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#14211f;"
            "line-height:1.5'>" + "".join(parts) + "</div>")


class ComposeEmailDialog(QDialog):
    """Send a template or a custom message to one or more employees. Everyone
    gets their own copy, filled in with their own details."""

    def __init__(self, parent, records: list[dict], company: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Send Email")
        fit_to_screen(self, 0.72, 0.8)
        self.records = records
        self.company = company
        self.by_address = {(r.get("email") or "").strip().lower(): r for r in records}
        self.sent: list[str] = []
        config = email_config()

        box = QVBoxLayout(self)
        box.setContentsMargins(20, 16, 20, 14)
        box.setSpacing(10)
        page_title(box, "Send Email", f"From {config['smtp_email']}")

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        self.template = QComboBox()
        self.template.addItems(list(EMAIL_TEMPLATES))
        self.template.currentTextChanged.connect(self.use_template)
        form.addRow("Template", self.template)
        self.to = QLineEdit(", ".join(r["email"].strip() for r in records))
        self.to.setPlaceholderText("name@company.com, another@company.com")
        self.to.textChanged.connect(self._fill_preview_choices)
        form.addRow("To", self.to)
        self.subject = QLineEdit()
        self.subject.textChanged.connect(self.update_preview)
        form.addRow("Subject", self.subject)
        box.addLayout(form)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(0, 0, 0, 0)
        lhead = QHBoxLayout()
        lhead.addWidget(QLabel("<b>Message</b>"))
        lhead.addStretch()
        insert = QPushButton("Insert field")
        insert.setObjectName("more")
        menu = QMenu(insert)
        for key, label in MAIL_FIELDS:
            menu.addAction(label, lambda k=key: self.body.insertPlainText("{" + k + "}"))
        insert.setMenu(menu)
        lhead.addWidget(insert)
        lcol.addLayout(lhead)
        self.body = QTextEdit()
        self.body.setAcceptRichText(False)
        self.body.setFont(QFont("Consolas", 10))
        self.body.textChanged.connect(self.update_preview)
        lcol.addWidget(self.body, 1)
        hint = QLabel("Fields in {braces} are filled in for each person. A line whose "
                      "fields are empty for someone is left out of their copy.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        lcol.addWidget(hint)
        split.addWidget(left)

        right = QWidget()
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(0, 0, 0, 0)
        rhead = QHBoxLayout()
        rhead.addWidget(QLabel("<b>Preview for</b>"))
        self.preview_for = QComboBox()
        self.preview_for.currentIndexChanged.connect(self.update_preview)
        rhead.addWidget(self.preview_for, 1)
        rcol.addLayout(rhead)
        self.preview_subject = QLabel()
        self.preview_subject.setWordWrap(True)
        rcol.addWidget(self.preview_subject)
        self.preview = QTextBrowser()
        rcol.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setSizes([1, 1])
        box.addWidget(split, 1)

        self.progress = QLabel()
        self.progress.setObjectName("subtitle")
        box.addWidget(self.progress)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.send_button = btns.button(QDialogButtonBox.Ok)
        btns.button(QDialogButtonBox.Cancel).setObjectName("ghost")
        btns.accepted.connect(self.send)
        btns.rejected.connect(self.reject)
        box.addWidget(btns)

        self._fill_preview_choices()
        self.use_template(self.template.currentText())

    # -- recipients and preview -------------------------------------------

    def recipients(self) -> list[str]:
        parts = self.to.text().replace(";", ",").split(",")
        seen, out = set(), []
        for p in (p.strip() for p in parts):
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        return out

    def _fields_for(self, address: str) -> dict:
        return mail_fields(self.by_address.get(address.lower()), self.company, address)

    def _fill_preview_choices(self):
        current = self.preview_for.currentData()
        self.preview_for.blockSignals(True)
        self.preview_for.clear()
        for address in self.recipients():
            r = self.by_address.get(address.lower())
            self.preview_for.addItem(f"{r['emp_name'] or r['emp_id']}  <{address}>" if r
                                     else address, address)
        index = self.preview_for.findData(current)
        self.preview_for.setCurrentIndex(max(index, 0))
        self.preview_for.blockSignals(False)
        self.send_button.setText(f"Send to {len(self.recipients())}")
        self.update_preview()

    def use_template(self, name: str):
        subject, body = EMAIL_TEMPLATES[name]
        self.subject.setText(subject)
        self.body.setPlainText(body)
        if name == "Custom message":
            self.subject.setFocus()

    def update_preview(self):
        address = self.preview_for.currentData()
        if not address:
            self.preview.setHtml("<p style='color:gray'>Add a recipient to see the preview.</p>")
            self.preview_subject.setText("")
            return
        fields = self._fields_for(address)
        subject = render_mail(self.subject.text(), fields).strip()
        self.preview_subject.setText(f"<b>Subject:</b> {subject or '(no subject)'}")
        self.preview.setHtml(mail_html(render_mail(self.body.toPlainText(), fields)))

    # -- sending ------------------------------------------------------------

    def send(self):
        to = self.recipients()
        bad = [a for a in to if not re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", a)]
        if not to or bad:
            warn(self, "Enter at least one valid email address." if not to
                 else "These addresses do not look right:\n" + "\n".join(bad))
            return
        if not self.subject.text().strip():
            warn(self, "Give the email a subject.")
            self.subject.setFocus()
            return
        config = email_config()
        if not config["smtp_password"]:
            warn(self, "No app password is set for the sender.\n\n"
                 "Open More → Email Settings and enter it first.")
            return
        failed: list[str] = []
        self.send_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with _smtp(config) as server:
                for n, address in enumerate(to, start=1):
                    self.progress.setText(f"Sending {n} of {len(to)} - {address} ...")
                    QApplication.processEvents()
                    fields = self._fields_for(address)
                    text = render_mail(self.body.toPlainText(), fields)
                    msg = EmailMessage()
                    msg["Subject"] = render_mail(self.subject.text(), fields).strip()
                    msg["From"] = config["smtp_email"]
                    msg["To"] = address
                    msg.set_content(text)
                    msg.add_alternative(mail_html(text), subtype="html")
                    try:
                        server.send_message(msg)
                        self.sent.append(address)
                    except smtplib.SMTPException as exc:
                        failed.append(f"{address}: {exc}")
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self.send_button.setEnabled(True)
            self.progress.setText("")
            _log.error("Email send failed: %s", exc)
            QMessageBox.critical(self, "Send Email", f"Could not send:\n{exc}\n\n"
                                 "Check More → Email Settings (Test connection).")
            return
        QApplication.restoreOverrideCursor()
        self.send_button.setEnabled(True)
        _log.info("Email '%s' sent to %d recipient(s)", self.template.currentText(), len(self.sent))
        if failed:
            QMessageBox.warning(self, "Send Email", f"Sent {len(self.sent)} of {len(to)}.\n\n"
                                "Not sent:\n" + "\n".join(failed))
        else:
            QMessageBox.information(self, "Send Email", f"Email sent to {len(self.sent)} "
                                    f"recipient{'' if len(self.sent) == 1 else 's'}.")
        self.accept()


class NewUserDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add user")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.username = QLineEdit()
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        self.role = QComboBox()
        for name, description in ROLES.items():
            self.role.addItem(description, name)
        form.addRow("Username", self.username)
        form.addRow(f"Password ({core.MIN_PASSWORD}+ characters)", self.password)
        form.addRow("Role", self.role)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class ImportPreview(QDialog):
    """Shows exactly what an import would do, before a single row is written."""

    def __init__(self, parent, path, rows, new_count, update_count, ignored, problems):
        super().__init__(parent)
        self.setWindowTitle("Import from Excel")
        self.resize(900, 600)
        box = QVBoxLayout(self)

        box.addWidget(QLabel(f"<b>{Path(path).name}</b>"))
        summary = QLabel(
            f"{len(rows)} row(s) read &nbsp;·&nbsp; <b>{new_count}</b> new employee(s) "
            f"&nbsp;·&nbsp; <b>{update_count}</b> already on file")
        box.addWidget(summary)

        self.overwrite = QComboBox()
        self.overwrite.addItem("Update the employees already on file", True)
        self.overwrite.addItem("Leave the employees already on file untouched", False)
        if update_count:
            box.addWidget(QLabel("For Employee IDs that already exist:"))
            box.addWidget(self.overwrite)

        if ignored:
            note = QLabel("Columns in the sheet that are not employee fields, and will be "
                          "ignored:  " + ", ".join(ignored))
            note.setObjectName("subtitle")
            note.setWordWrap(True)
            box.addWidget(note)

        if problems:
            trouble = QLabel("<b>Rows that will be skipped:</b><br>" +
                             "<br>".join(problems[:10]) +
                             (f"<br>... and {len(problems) - 10} more" if len(problems) > 10 else ""))
            trouble.setObjectName("error")
            trouble.setWordWrap(True)
            box.addWidget(trouble)

        box.addWidget(QLabel("Preview of what will be imported:"))
        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        filled = [c for c in COLUMNS if any(r.get(c) for r in rows)]
        table.setColumnCount(len(filled) + 1)
        table.setHorizontalHeaderLabels(["Sheet row"] + [LABELS[c] for c in filled])
        shown = rows[:200]
        table.setRowCount(len(shown))
        for r, row in enumerate(shown):
            table.setItem(r, 0, QTableWidgetItem(str(row.get("_row", ""))))
            for c, col in enumerate(filled, start=1):
                table.setItem(r, c, QTableWidgetItem(row.get(col, "")))
        table.resizeColumnsToContents()
        box.addWidget(table, 1)
        if len(rows) > len(shown):
            box.addWidget(QLabel(f"Showing the first {len(shown)} of {len(rows)} rows."))

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        go = buttons.addButton(f"Import {len(rows)} row(s)", QDialogButtonBox.AcceptRole)
        go.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def update_existing(self) -> bool:
        return bool(self.overwrite.currentData())


# ------------------------------------------------------------- asset forms

class AssetDialog(QDialog):
    """Add or edit one laptop / mobile / IP phone / printer. The form is built from
    the kind's field list, so the register and the dialog can never drift apart."""

    def __init__(self, parent, kind: str, record: dict | None = None):
        super().__init__(parent)
        self.kind = kind
        meta = ASSET_META[kind]
        self.setWindowTitle(f"{'Edit' if record else 'Add'} {meta['label']}")
        fit_to_screen(self, 0.55, 0.7)
        self.inputs: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        holder = QWidget()
        holder.setObjectName("page")
        body = QVBoxLayout(holder)
        group = QGroupBox(meta["label"])
        grid = QGridLayout(group)
        for index, (key, label, choices) in enumerate(meta["fields"]):
            row, column = divmod(index, 2)
            if choices:
                widget = QComboBox()
                widget.addItems(choices)
                if record and record.get(key):
                    widget.setCurrentText(record[key])
            else:
                widget = QLineEdit(record.get(key, "") if record else "")
            self.inputs[key] = widget
            grid.addWidget(QLabel(label), row, column * 2)
            grid.addWidget(widget, row, column * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        body.addWidget(group)

        note = QLabel("The serial / IMEI / MAC number is what ties an item to its "
                      "history. Leave it blank and the app issues one of its own "
                      "(LAP-0001...).")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        body.addWidget(note)
        body.addStretch()
        scroll.setWidget(holder)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict:
        return {
            key: (w.currentText() if isinstance(w, QComboBox) else w.text())
            for key, w in self.inputs.items()
        }


class AssignDialog(QDialog):
    """Give an asset to an employee (or hand it from one employee to another)."""

    def __init__(self, parent, store: Store, kind: str, asset: dict):
        super().__init__(parent)
        self.store = store
        meta = ASSET_META[kind]
        self.setWindowTitle(f"Assign {meta['label']} · {asset['identity']}")
        self.setMinimumWidth(460)
        form = QFormLayout(self)

        holder = asset["current_emp_name"] or asset["current_emp_id"]
        form.addRow("Currently with", QLabel(holder or "(nobody - unassigned)"))

        self.employee = QComboBox()
        self.employee.addItem("— choose an employee —", "")
        for emp in store.employees():
            self.employee.addItem(f"{emp['emp_id']} — {emp['emp_name'] or '(no name)'}",
                                  emp["emp_id"])
        form.addRow("Give it to", self.employee)

        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd MMM yyyy")
        form.addRow("From date", self.date)

        self.note = QLineEdit(placeholderText="Optional - e.g. 'handover', 'new joiner', a DC no")
        form.addRow("Note", self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def chosen(self) -> str:
        return self.employee.currentData() or ""

    def note(self) -> str:
        return self.note.text().strip()

    def on_date(self) -> str:
        return self.date.date().toString("yyyy-MM-dd")


class AssetHistoryDialog(QDialog):
    """Who had this item, and when - the whole chain of custody."""

    def __init__(self, parent, kind: str, asset: dict, history: list[dict]):
        super().__init__(parent)
        meta = ASSET_META[kind]
        self.setWindowTitle(f"{meta['label']} history · {asset['identity']}")
        self.resize(820, 460)
        box = QVBoxLayout(self)

        detail = (f"<b>{asset['identity']}</b> · {asset['name_type'] or 'no model'}"
                  f" · status {asset['status'] or '?'}"
                  + (f" · <b>with {asset['current_emp_name']}</b>" if asset["current_emp_name"]
                     else " · not assigned"))
        box.addWidget(QLabel(detail))
        hint = QLabel("Who it was issued to, and when. The most recent open line "
                      "(no release date) is the current holder.")
        hint.setObjectName("subtitle")
        box.addWidget(hint)

        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        headers = ["Employee", "From", "Until", "Note", "Recorded by", "At"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(history))
        for r, entry in enumerate(history):
            values = [f"{entry['emp_name'] or ''} ({entry['emp_id']})".strip(),
                      local_time(entry["assigned_on"] + "T00:00:00+00:00").split("  ")[0],
                      ("present" if not entry["released_on"]
                       else local_time(entry["released_on"] + "T00:00:00+00:00").split("  ")[0]),
                      entry["note"], entry["actor"], local_time(entry["at"])]
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        box.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.reject)
        box.addWidget(buttons)


class EmployeeAssetsDialog(QDialog):
    """Everything ever issued to one employee, across all four registers."""

    def __init__(self, parent, employee: dict, rows: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Assets & history · {employee['emp_name'] or employee['emp_id']}")
        self.resize(860, 480)
        box = QVBoxLayout(self)
        box.addWidget(QLabel(
            f"<b>{employee['emp_name'] or employee['emp_id']}</b> ({employee['emp_id']})"
            " - every asset this person has held, and when."))
        if not rows:
            box.addWidget(QLabel("No assets have ever been issued to this employee."))
        else:
            table = QTableWidget()
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.verticalHeader().setVisible(False)
            headers = ["Kind", "Asset ID", "From", "Until", "Note"]
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(rows))
            for r, entry in enumerate(rows):
                values = [entry["kind_label"], entry["asset_identity"],
                          local_time(entry["assigned_on"] + "T00:00:00+00:00").split("  ")[0],
                          ("present" if not entry["released_on"]
                           else local_time(entry["released_on"] + "T00:00:00+00:00").split("  ")[0]),
                          entry["note"]]
                for c, value in enumerate(values):
                    table.setItem(r, c, QTableWidgetItem(value))
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)
            box.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.reject)
        box.addWidget(buttons)


# ------------------------------------------------------------- main window

PAGE_NAMES = {0: "Employees", 1: "Laptops", 2: "Mobiles", 3: "IP Phones", 4: "Printers",
              5: "Challan", 6: "Activity Log", 7: "Users", 8: "My Account", 9: "Dashboard"}
ASSET_INDEX = {"laptop": 1, "mobile": 2, "ip_phone": 3, "printer": 4, "challan": 5}
INDEX_KIND = {v: k for k, v in ASSET_INDEX.items()}


def _asset_labels(meta: dict) -> dict:
    """Register labels, with the identity column's own name for that register
    (a Challan register's 'Asset ID' column reads as 'Challan ID')."""
    labels = dict(ASSET_LABELS)
    labels["identity"] = meta.get("identity_label", labels["identity"])
    return labels


class MainWindow(QMainWindow):
    def __init__(self, store: Store, username: str = "", role: str = "viewer"):
        super().__init__()
        self.store = store
        self.username = username
        self.role = role
        self.rows: list[dict] = []
        self.asset_rows: dict[str, list[dict]] = {k: [] for k in ASSET_META}
        self.asset_export_buttons: dict[str, list] = {k: [] for k in ASSET_META}
        self.search = None
        # SNO 1, 2, 3 ... on every start; a header click re-sorts for the session.
        self.emp_sort = (0, Qt.AscendingOrder)

        self.setWindowTitle("IT Records")
        self.settings = QSettings("ITRecords", "IT Records")
        geometry = self.settings.value("geometry")
        self.restoreGeometry(geometry) if geometry else self.resize(1440, 820)
        self.setMinimumSize(1100, 640)

        page = QWidget()
        page.setObjectName("page")
        self.setCentralWidget(page)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header_widget = self._header()
        outer.addWidget(self.header_widget)

        self.stack = None
        self._build_pages()
        outer.addWidget(self.stack, 1)

        self.status = self.statusBar()
        self.status.showMessage(
            f"Signed in as {self.username} - {ROLES.get(self.role, self.role)}."
            if Store.may(self.role, "edit")
            else "Open read-only. Sign in as super admin to make changes.")
        self._shortcuts()
        self.refresh()
        for kind in ASSET_META:
            self.refresh_assets(kind)
        self.show_page(0)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def _shortcuts(self):
        """Keys act on the page in front: Ctrl+N adds a laptop on the Laptops
        page and an employee on the Employees page."""
        keys = [
            ("Ctrl+F", self._focus_search),
            ("F5", self._refresh_current),
            ("Ctrl+N", lambda: self._on_page(self.add_employee, self.add_asset)),
            ("Ctrl+E", lambda: self._on_page(self.edit_employee, self.edit_asset)),
            ("Delete", self._delete_current),
            ("Ctrl+Q", self.close),
        ]
        for key, slot in keys:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _on_page(self, employee_slot, asset_slot):
        index = self.stack.currentIndex()
        if index == 0:
            employee_slot()
        elif index in INDEX_KIND:
            asset_slot(INDEX_KIND[index])

    def _focus_search(self):
        index = self.stack.currentIndex()
        box = (self.asset_search[INDEX_KIND[index]] if index in INDEX_KIND
               else self.log_search if index == 6 else None)
        if box is None:
            self.show_page(0)
            box = self.search
        box.setFocus()
        box.selectAll()

    def _refresh_current(self):
        index = self.stack.currentIndex()
        if index == 0:
            self.refresh()
        self.show_page(index)          # reloads whatever that page shows
        self.status.showMessage("Refreshed.", 2000)

    def _delete_current(self):
        index = self.stack.currentIndex()
        if index == 0:
            self.delete_employee()
        elif index in INDEX_KIND:
            self.delete_asset(INDEX_KIND[index])

    # -- session ----------------------------------------------------------

    def ensure(self, right: str, message: str) -> bool:
        """True when the current session may do `right`. If the app is open
        read-only it offers the sign-in dialog; on a successful sign-in the window
        is upgraded and True returns so the caller can proceed. A signed-in account
        that still lacks the right is simply told and refused."""
        if Store.may(self.role, right):
            return True
        if self.role != "viewer":
            warn(self, message)
            return False
        dialog = LoginDialog(self.store)
        if dialog.exec_() != QDialog.Accepted:
            return False
        if not Store.may(dialog.role if dialog.role else "", right):
            self.upgrade(dialog.role, dialog.username)
            warn(self, message)
            return False
        self.upgrade(dialog.role, dialog.username)
        return True

    def _build_pages(self):
        """(Re)build the whole tab stack for the current role. Pages decide at
        build time which buttons and banners they show, so the stack must be
        rebuilt when the session role changes - signing in as super admin has to
        reveal Add/Edit/Delete/Import/Export and the admin tabs, signing out has
        to take them away again."""
        self.stack = QStackedWidget()
        self.stack.addWidget(self._employees_page())
        for kind in ASSET_META:                       # laptops, mobiles, ip phones, printers
            self.stack.addWidget(self._asset_page(kind))
        self.stack.addWidget(self._logs_page())
        self.stack.addWidget(self._users_page())
        self.stack.addWidget(self._account_page())
        self.stack.addWidget(self._dashboard_page())

    def _rebuild_stack(self, index: int):
        """Swap the fresh stack in where the old one was, keep the search text
        and stay on the same tab."""
        search = self.search.text() if self.search is not None else ""
        outer = self.centralWidget().layout()
        old = self.stack
        outer.removeWidget(old)
        old.setParent(None)        # out of the window's tree immediately - the
        old.deleteLater()          # old pages must not linger for a delayed delete
        self._build_pages()
        outer.addWidget(self.stack, 1)
        old.deleteLater()
        if search:
            self.search.setText(search)
        self.refresh()
        for kind in ASSET_META:
            self.refresh_assets(kind)
        self.show_page(index)

    def upgrade(self, role: str, username: str):
        self.role = role
        self.username = username
        self._rebuild_header()
        self._rebuild_stack(self.stack.currentIndex())
        self.status.showMessage(f"Signed in as {username}.", 4000)

    def sign_in(self):
        dialog = LoginDialog(self.store)
        if dialog.exec_() == QDialog.Accepted:
            self.upgrade(dialog.role, dialog.username)

    def sign_out(self):
        if self.role != "viewer":
            self.store.log(self.username, "logout", "user", self.username, "signed out")
        self.role = "viewer"
        self.username = ""
        self._rebuild_header()
        self._rebuild_stack(self.stack.currentIndex())
        self.status.showMessage("Signed out - the register is read-only again.", 4000)

    # -- chrome ----------------------------------------------------------

    NAV = [("REGISTERS", [("Employees", 0), ("Laptops", 1), ("Mobiles", 2), ("IP Phones", 3),
                          ("Printers", 4), ("Challan", 5)]),
           ("OVERVIEW", [("Dashboard", 9), ("Activity Log", 6)]),
           ("ACCOUNT", [("Users", 7), ("My Account", 8)])]

    def _may_see(self, index: int) -> bool:
        if index == 6:
            return Store.may(self.role, "logs")
        if index == 7:
            return Store.may(self.role, "users")
        return True

    def _header(self) -> QWidget:
        """The navigation sidebar: brand, grouped pages, who is signed in."""
        bar = QWidget()
        bar.setObjectName("sidebar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFixedWidth(220)
        col = QVBoxLayout(bar)
        col.setContentsMargins(12, 16, 12, 12)
        col.setSpacing(6)
        brand = brand_mark()
        brand.layout().setContentsMargins(10, 0, 0, 0)
        col.addWidget(brand)

        # The page list scrolls on a short screen rather than squeezing the
        # account card below it.
        holder = QWidget()
        nav = QVBoxLayout(holder)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(1)
        self.tabs: list[QPushButton] = []
        for section, items in self.NAV:
            shown = [(text, index) for text, index in items if self._may_see(index)]
            if not shown:
                continue
            heading = QLabel(section)
            heading.setObjectName("navSection")
            nav.addWidget(heading)
            for text, index in shown:
                button = QPushButton(text)
                button.setObjectName("nav")
                button.setCheckable(True)
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(lambda _, i=index: self.show_page(i))
                nav.addWidget(button)
                self.tabs.append(button)
        nav.addStretch()
        scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        scroll.setObjectName("navScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        col.addWidget(scroll, 1)

        card = QWidget()
        card.setObjectName("userCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(12, 10, 12, 12)
        inner.setSpacing(4)
        viewer = self.role == "viewer"
        name = QLabel("Not signed in" if viewer else self.username)
        name.setObjectName("userName")
        who = QLabel("Read-only view" if viewer else ROLES[self.role].split(" - ")[0])
        who.setObjectName("who")
        sign = QPushButton("Sign in" if viewer else "Sign out")
        sign.setObjectName("side")
        sign.setCursor(Qt.PointingHandCursor)
        sign.clicked.connect(self.sign_in if viewer else self.sign_out)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("side")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("Switch between light and dark mode")
        self._update_theme_btn_icon()
        self.theme_btn.clicked.connect(self.toggle_theme)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(sign, 1)
        buttons.addWidget(self.theme_btn, 1)
        inner.addWidget(name)
        inner.addWidget(who)
        inner.addSpacing(6)
        inner.addLayout(buttons)
        col.addWidget(card)
        return bar

    def _update_theme_btn_icon(self):
        dark = self.settings.value("theme", "light") == "dark"
        self.theme_btn.setText("Light" if dark else "Dark")

    def toggle_theme(self):
        new_theme = "light" if self.settings.value("theme", "light") == "dark" else "dark"
        self.settings.setValue("theme", new_theme)
        apply_theme(new_theme)
        self._update_theme_btn_icon()
        if self.stack.currentIndex() == 9:
            self.load_dashboard()          # the charts are drawn in the palette's colours
        self.status.showMessage(f"{new_theme.capitalize()} mode on.", 3000)

    def _rebuild_header(self):
        outer = self.centralWidget().layout()
        outer.removeWidget(self.header_widget)
        self.header_widget.setParent(None)
        self.header_widget.deleteLater()
        self.header_widget = self._header()
        outer.insertWidget(0, self.header_widget)

    def show_page(self, index: int):
        if index != self.stack.currentIndex() and self.isVisible():
            self._fade(self.stack.widget(index))
        self.stack.setCurrentIndex(index)
        wanted = PAGE_NAMES[index]
        for button in self.tabs:
            button.setChecked(button.text() == wanted)
        if index == 6:
            self.load_logs()
        elif index == 7:
            self.load_users()
        elif index == 9:
            self.load_dashboard()
        elif index in INDEX_KIND:
            self.refresh_assets(INDEX_KIND[index])

    @staticmethod
    def _fade(page: QWidget):
        """A short fade as a page comes in; the effect is removed afterwards so
        the page renders at full speed."""
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: page.setGraphicsEffect(None))
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    # -- employees -------------------------------------------------------

    def _toolbar_button(self, bar, text, slot, name="ghost", right=None, needs_row=None):
        """A toolbar button. Hidden when the session lacks `right`; listed in
        `needs_row` when it only makes sense with a row selected."""
        b = QPushButton(text)
        b.clicked.connect(slot)
        if name:
            b.setObjectName(name)
        b.setCursor(Qt.PointingHandCursor)
        if right and not Store.may(self.role, right):
            b.hide()
        if needs_row is not None:
            needs_row.append(b)
        bar.addWidget(b)
        return b

    def _more_button(self, bar, entries) -> QPushButton | None:
        """A 'More' drop-down for the rarely used actions. Entries are
        (text, slot, right) or None for a separator; only permitted ones show."""
        allowed = [e for e in entries if e is None or not e[2] or Store.may(self.role, e[2])]
        while allowed and allowed[0] is None:
            allowed.pop(0)
        while allowed and allowed[-1] is None:
            allowed.pop()
        if not allowed:
            return None
        menu = QMenu(self)
        for entry in allowed:
            if entry is None:
                menu.addSeparator()
            elif len(entry) > 3 and entry[3]:            # destructive - shown in red
                action = QWidgetAction(menu)
                button = QPushButton(entry[0])
                button.setObjectName("menuDanger")
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(lambda _=False, m=menu, f=entry[1]: (m.close(), f()))
                action.setDefaultWidget(button)
                menu.addAction(action)
            else:
                menu.addAction(entry[0], entry[1])
        more = QPushButton("More")
        more.setObjectName("more")
        more.setCursor(Qt.PointingHandCursor)
        more.setMenu(menu)
        bar.addWidget(more)
        return more

    def _employees_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)

        self.count = QLabel("0 records")
        self.count.setObjectName("count")
        page_title(box, "Employees", "Everyone on file and the equipment issued to them",
                   self.count)

        if not Store.may(self.role, "edit"):
            banner = QLabel("Read-only - you can search, view and print, but not change "
                            "records. Sign in as super admin to add or edit.")
            banner.setObjectName("banner")
            box.addWidget(banner)

        self.search = search_box("Search anything - name, Emp ID, department, serial number, "
                                 "IMEI, vendor, DC no...")
        self.search.textChanged.connect(self.refresh)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self.search, 1)
        files = lambda *a, **k: self._toolbar_button(top, *a, **k)     # noqa: E731
        files("Import Excel", self.import_excel, right="import")
        self.export_buttons = [
            files("Export Excel", self.export_excel, right="export"),
            files("Export PDF", self.export_pdf, right="export"),
        ]
        box.addLayout(top)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.row_actions: list[QPushButton] = []
        tb = lambda *a, **k: self._toolbar_button(bar, *a, **k)        # noqa: E731
        tb("Add Employee", self.add_employee, None, right="edit")
        tb("Edit", self.edit_employee, right="edit", needs_row=self.row_actions)
        tb("Delete", self.delete_employee, "danger", right="delete", needs_row=self.row_actions)
        bar.addWidget(divider())
        tb("Asset History", self.show_employee_assets, needs_row=self.row_actions)
        tb("Send Email", self.compose_email, needs_row=self.row_actions)
        tb("Print Record", self.record_employee, right="export", needs_row=self.row_actions)
        bar.addStretch()
        self._more_button(bar, [
            ("Select all rows", self.select_all_employees, None),
            None,
            ("Delete selected...", self.delete_selected_employees, "delete", True),
            ("Delete all...", self.delete_all_employees, "delete", True),
            None,
            ("Email Settings...", self.email_settings, "users"),
        ])
        box.addLayout(bar)

        self.table = make_table()
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._open_employee)
        self.table.itemSelectionChanged.connect(self._update_row_actions)
        self.table.horizontalHeader().sortIndicatorChanged.connect(
            lambda col, order: self.table.isSortingEnabled()
            and setattr(self, "emp_sort", (col, order)))
        self.table.setToolTip("Double-click a row to open it. Shift/Ctrl+click to multi-select.")
        box.addWidget(self.table, 1)
        return page

    def _open_employee(self):
        """Double-click: edit for an editor, the asset history for everyone else."""
        if Store.may(self.role, "edit"):
            self.edit_employee()
        else:
            self.show_employee_assets()

    def _update_row_actions(self):
        picked = bool(self.table.selectionModel() and self.table.selectionModel().selectedRows())
        for button in self.row_actions:
            button.setEnabled(picked)

    @staticmethod
    def _fill(table: QTableWidget, headers: list[str], rows: list[list[str]]):
        """Load a table. Row 0's cells carry their index into the source list,
        so a header-click sort still maps back to the right record."""
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = SortItem(value)
                if c == 0:
                    item.setData(Qt.UserRole, r)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for c in range(table.columnCount()):          # a long remark must not eat the screen
            if table.columnWidth(c) > 320:
                table.setColumnWidth(c, 320)

    def refresh(self):
        search = self.search.text()
        self.rows = self.store.employees(search)
        headers = [LABELS[c] for c in COLUMNS] + ["Last Updated", "Updated By"]
        self._fill(self.table, headers,
                   [[str(row[c]) for c in COLUMNS] + [local_time(row["updated"]), row["updated_by"]]
                    for row in self.rows])
        self._show_order(self.table, search, self.emp_sort)
        n = len(self.rows)
        if search.strip():
            self.count.setText(f"{n} of {self.store.employee_count()} records")
        else:
            self.count.setText(f"{n} record{'' if n == 1 else 's'}")
        for button in self.export_buttons:
            button.setEnabled(bool(self.rows))
            button.setToolTip("" if self.rows else "Nothing to export - the list is empty")
        self._update_row_actions()

    @staticmethod
    def _show_order(table: QTableWidget, search: str, sort: tuple):
        """Browsing: the chosen column order (SNO 1, 2, 3 by default).
        Searching: best match on top, matched cells highlighted, and the view
        jumps to the first hit so it is never lost at the bottom."""
        header = table.horizontalHeader()
        words = [w.lower() for w in search.split()]
        if not words:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(*sort)
            table.setSortingEnabled(True)
            return
        table.setSortingEnabled(False)            # keep the relevance order
        header.setSortIndicatorShown(False)
        # Highlight where a word *starts* with the search ('Hammad'), not where
        # it is buried inside another word ('Muhammad') - the real hits stand out.
        starts = [re.compile(r"(?<![a-z0-9])" + re.escape(w)) for w in words]
        bold = QFont(table.font())
        bold.setBold(True)
        brand = QColor(PALETTE["brand"])
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                text = item.text().lower() if item else ""
                if text and any(p.search(text) for p in starts):
                    item.setFont(bold)
                    item.setForeground(brand)
        table.scrollToTop()
        if table.rowCount():
            table.selectRow(0)

    @staticmethod
    def _record_at(table, source: list, view_row: int) -> dict | None:
        """The record a visual row stands for. Clicking a column header reorders
        the table, so the row number on screen is not an index into the list the
        rows were built from; the index is carried on the row itself."""
        item = table.item(view_row, 0)
        index = item.data(Qt.UserRole) if item is not None else None
        if index is None:
            index = view_row
        return source[index] if 0 <= index < len(source) else None

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            warn(self, "Select an employee row first.")
            return None
        return self._record_at(self.table, self.rows, rows[0].row())

    def selected_records(self) -> list[dict]:
        model = self.table.selectionModel()
        if not model:
            return []
        picked = (self._record_at(self.table, self.rows, idx.row())
                  for idx in model.selectedRows())
        return [r for r in picked if r is not None]

    def select_all_employees(self):
        self.table.setFocus()
        self.table.selectAll()

    def add_employee(self):
        if not self.ensure("edit", "Sign in as a super admin to add employees."):
            return
        dialog = EmployeeDialog(self)
        result = dialog.exec_()
        while result == QDialog.Accepted:
            try:
                self.store.add_employee(dialog.values(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                result = dialog.exec_()
                continue
            self.refresh()
            self.status.showMessage("Employee added.", 4000)
            return

    def edit_employee(self):
        if not self.ensure("edit", "Sign in as a super admin to edit employees."):
            return
        record = self.selected()
        if not record:
            return
        dialog = EmployeeDialog(self, record)
        result = dialog.exec_()
        while result == QDialog.Accepted:
            try:
                self.store.update_employee(record["id"], dialog.values(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                result = dialog.exec_()
                continue
            self.refresh()
            self.status.showMessage("Employee updated.", 4000)
            return

    def delete_employee(self):
        if not self.ensure("delete", "Sign in as a super admin to delete employees."):
            return
        if len(self.selected_records()) > 1:
            self.delete_selected_employees()
            return
        row = self.selected()
        if not row:
            return
        if not confirm_danger(self, "Delete employee",
                              f"Delete the record for {row['emp_name'] or row['emp_id']} "
                              f"({row['emp_id']}, SNO {row['sno']})?\n\n"
                              "The Activity Log keeps a copy of the deleted record."):
            return
        try:
            self.store.delete_employee(row["id"], self.username, self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.refresh()
        self.status.showMessage("Employee deleted.", 4000)

    def email_settings(self):
        if not self.ensure("users", "Only the super admin can change the email settings."):
            return
        if EmailConfigDialog(self).exec_() == QDialog.Accepted:
            self.status.showMessage("Email settings saved.", 4000)

    def compose_email(self):
        records = self.selected_records()
        if not records:
            warn(self, "Select one or more employee rows first.")
            return
        if not self.ensure("edit", "Sign in as a super admin to send email."):
            return
        with_mail = [r for r in records if (r.get("email") or "").strip()]
        missing = [r["emp_name"] or r["emp_id"] for r in records if r not in with_mail]
        if not with_mail:
            warn(self, "The selected employee(s) have no email address on file.\n\n"
                 "Add one with Edit, then try again.")
            return
        if missing:
            self.status.showMessage(f"No email address for: {', '.join(missing[:5])}"
                                    f"{' ...' if len(missing) > 5 else ''} - left out.", 8000)
        dialog = ComposeEmailDialog(self, with_mail, self.store.company().get("name", ""))
        if dialog.exec_() == QDialog.Accepted and dialog.sent:
            self.store.log(self.username, "email", "employee",
                           ", ".join(r["emp_id"] for r in with_mail)[:200],
                           f"'{dialog.template.currentText()}' sent to "
                           f"{len(dialog.sent)} recipient(s)")

    def delete_selected_employees(self):
        if not self.ensure("delete", "Sign in as a super admin to delete employees."):
            return
        records = self.selected_records()
        if not records:
            warn(self, "Select at least one employee row first.")
            return
        names = ", ".join((r['emp_name'] or r['emp_id']) for r in records[:5])
        if len(records) > 5:
            names += f" ... and {len(records) - 5} more"
        if not confirm_danger(self, "Delete selected employees",
                              f"Permanently delete {len(records)} employee(s)?\n\n{names}\n\n"
                              "The Activity Log will keep a copy of every deleted record.",
                              f"Delete {len(records)}"):
            return
        self._delete_many([r["id"] for r in records], 6000)

    def _delete_many(self, ids: list[int], ms: int):
        """One transaction: either every chosen record goes, or none does."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            deleted = self.store.delete_employees(ids, self.username, self.role)
        except (Invalid, Denied) as exc:
            QApplication.restoreOverrideCursor()
            warn(self, f"Nothing was deleted:\n{exc}")
            return
        QApplication.restoreOverrideCursor()
        self.refresh()
        self.status.showMessage(f"Deleted {deleted} employee(s).", ms)

    def delete_all_employees(self):
        if not self.ensure("delete", "Sign in as a super admin to delete employees."):
            return
        if not self.rows:
            warn(self, "There are no records to delete.")
            return
        total = len(self.rows)
        filtered = self.search.text().strip()
        scope = f"matching '{filtered}'" if filtered else "in the entire database"
        if not confirm_danger(
                self, "Delete ALL employees",
                f"You are about to permanently delete ALL {total} employee record(s) {scope}.\n\n"
                "This cannot be undone, though the Activity Log will keep a copy.",
                "Continue"):
            return
        if not confirm_danger(self, "Final confirmation",
                              f"Delete {total} record(s)? This is your last chance to cancel.",
                              f"Delete all {total}"):
            return
        self._delete_many([r["id"] for r in list(self.rows)], 8000)

    def show_employee_assets(self):
        record = self.selected()
        if not record:
            return
        rows = self.store.employee_assets(record["emp_id"])
        dialog = EmployeeAssetsDialog(self, record, rows)
        dialog.exec_()

    # -- asset registers ------------------------------------------------

    def _asset_page(self, kind: str) -> QWidget:
        meta = ASSET_META[kind]
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)

        count = QLabel("0 assets")
        count.setObjectName("count")
        self.asset_count = getattr(self, "asset_count", {})
        self.asset_count[kind] = count
        page_title(box, meta["tab"], f"Every {meta['label'].lower()} on file, who holds it "
                   "and its history", count)

        search = search_box(f"Search {meta['tab'].lower()} - serial, model, owner, vendor...")
        search.textChanged.connect(lambda _=None, k=kind: self.refresh_assets(k))
        self.asset_search = getattr(self, "asset_search", {})
        self.asset_search[kind] = search
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(search, 1)
        for fmt in ("Excel", "PDF"):
            self.asset_export_buttons[kind].append(self._toolbar_button(
                top, f"Export {fmt}", lambda _=None, k=kind, f=fmt: self.export_assets(k, f),
                right="export"))
        box.addLayout(top)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        needs = []
        self.asset_row_actions = getattr(self, "asset_row_actions", {})
        self.asset_row_actions[kind] = needs
        tb = lambda *a, **k: self._toolbar_button(bar, *a, **k)        # noqa: E731
        tb(f"Add {meta['label']}", lambda _=None, k=kind: self.add_asset(k), None, right="edit")
        tb("Edit", lambda _=None, k=kind: self.edit_asset(k), right="edit", needs_row=needs)
        tb("Delete", lambda _=None, k=kind: self.delete_asset(k), "danger", right="delete",
           needs_row=needs)
        bar.addWidget(divider())
        tb("Assign", lambda _=None, k=kind: self.assign_asset(k), right="edit", needs_row=needs)
        tb("Release", lambda _=None, k=kind: self.release_asset(k), right="edit",
           needs_row=needs)
        tb("History", lambda _=None, k=kind: self.show_asset_history(k), needs_row=needs)
        tb("Print Record", lambda _=None, k=kind: self.record_asset(k), right="export",
           needs_row=needs)
        bar.addStretch()
        box.addLayout(bar)

        table = make_table()
        table.setSortingEnabled(True)
        table.doubleClicked.connect(lambda _=None, k=kind: self._open_asset(k))
        table.itemSelectionChanged.connect(lambda k=kind: self._update_asset_actions(k))
        table.setToolTip("Double-click a row to open it. Shift/Ctrl+click to multi-select.")
        self.asset_table = getattr(self, "asset_table", {})
        self.asset_table[kind] = table
        self.asset_sort = getattr(self, "asset_sort", {})
        table.horizontalHeader().sortIndicatorChanged.connect(
            lambda col, order, k=kind, t=table: t.isSortingEnabled()
            and self.asset_sort.__setitem__(k, (col, order)))
        box.addWidget(table, 1)
        return page

    def _open_asset(self, kind: str):
        if Store.may(self.role, "edit"):
            self.edit_asset(kind)
        else:
            self.show_asset_history(kind)

    def _update_asset_actions(self, kind: str):
        model = self.asset_table[kind].selectionModel()
        picked = bool(model and model.selectedRows())
        for button in self.asset_row_actions[kind]:
            button.setEnabled(picked)

    def refresh_assets(self, kind: str):
        table = self.asset_table[kind]
        rows = self.store.assets(kind, self.asset_search[kind].text())
        self.asset_rows[kind] = rows
        meta = ASSET_META[kind]
        labels = _asset_labels(meta)
        headers = ["Sno"] + [labels[c] for c in meta["columns"]] + ["Last Updated", "Updated By"]
        self._fill(table, headers,
                   [[str(r + 1)] + [row[c] for c in meta["columns"]] +
                    [local_time(row["updated"]), row["updated_by"]]
                    for r, row in enumerate(rows)])
        self._show_order(table, self.asset_search[kind].text(),
                         self.asset_sort.get(kind, (0, Qt.AscendingOrder)))
        self.asset_count[kind].setText(f"{len(rows)} asset{'' if len(rows) == 1 else 's'}")
        for button in self.asset_export_buttons[kind]:
            button.setEnabled(bool(rows))
        self._update_asset_actions(kind)

    def _selected_asset(self, kind: str) -> dict | None:
        table = self.asset_table[kind]
        selected_rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not selected_rows:
            warn(self, "Select an asset row first.")
            return None
        return self._record_at(table, self.asset_rows[kind], selected_rows[0].row())


    def add_asset(self, kind: str):
        if not self.ensure("edit", "Sign in as a super admin to add assets."):
            return
        dialog = AssetDialog(self, kind)
        while dialog.exec_() == QDialog.Accepted:
            try:
                self.store.add_asset(kind, dialog.values(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                continue
            self.refresh_assets(kind)
            self.status.showMessage(f"{ASSET_META[kind]['label']} added.", 4000)
            return

    def edit_asset(self, kind: str):
        if not self.ensure("edit", "Sign in as a super admin to edit assets."):
            return
        record = self._selected_asset(kind)
        if not record:
            return
        dialog = AssetDialog(self, kind, record)
        while dialog.exec_() == QDialog.Accepted:
            try:
                self.store.update_asset(record["id"], dialog.values(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                continue
            self.refresh_assets(kind)
            self.status.showMessage(f"{ASSET_META[kind]['label']} updated.", 4000)
            return

    def assign_asset(self, kind: str):
        if not self.ensure("edit", "Sign in as a super admin to assign assets."):
            return
        record = self._selected_asset(kind)
        if not record:
            return
        dialog = AssignDialog(self, self.store, kind, record)
        if dialog.exec_() != QDialog.Accepted:
            return
        if not dialog.chosen():
            warn(self, "Choose the employee to give it to.")
            return
        if kind == "challan":
            # A challan line is a delivery the machine came in on. Issuing it
            # books the machine into the Laptops register and marks this line
            # with the same employee, so the two registers stay in agreement.
            try:
                summary = self.store.issue_challan(record["id"], dialog.chosen(),
                                                   note=dialog.note(),
                                                   actor=self.username, role=self.role,
                                                   start_date=dialog.on_date())
            except (Invalid, Denied) as exc:
                warn(self, str(exc))
                return
            self.refresh_assets("challan")
            self.refresh_assets("laptop")
            self.refresh()
            self.status.showMessage(f"{summary}. The machine is booked in the "
                                    "Laptops register.", 7000)
            return
        try:
            summary = self.store.assign_asset(record["id"], dialog.chosen(),
                                              note=dialog.note(), actor=self.username,
                                              role=self.role, start_date=dialog.on_date())
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.refresh_assets(kind)
        self.status.showMessage(summary, 6000)

    def release_asset(self, kind: str):
        if not self.ensure("edit", "Sign in as a super admin to release assets."):
            return
        record = self._selected_asset(kind)
        if not record:
            return
        if not record["current_emp_name"] and not record["current_emp_id"]:
            warn(self, "This asset is not currently assigned to anyone.")
            return
        note, ok = QInputDialog.getMultiLineText(
            self, "Release asset", f"Release {record['identity']} from "
            f"{record['current_emp_name']} ({record['current_emp_id']})?\nReason / note "
            "(optional):")
        if not ok:
            return
        try:
            summary = self.store.release_asset(record["id"], note=note.strip(),
                                               actor=self.username, role=self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.refresh_assets(kind)
        self.status.showMessage(summary, 6000)

    def show_asset_history(self, kind: str):
        record = self._selected_asset(kind)
        if not record:
            return
        history = self.store.asset_history(record)
        dialog = AssetHistoryDialog(self, kind, record, history)
        dialog.exec_()

    def delete_asset(self, kind: str):
        if not self.ensure("delete", "Sign in as a super admin to delete assets."):
            return
        record = self._selected_asset(kind)
        if not record:
            return
        if not confirm_danger(
                self, f"Delete {ASSET_META[kind]['label'].lower()}",
                f"Delete {record['identity']} ({record['name_type'] or 'no model'})?\n\n"
                "The row is removed, but the Activity Log keeps a copy and the assignment "
                "history is preserved."):
            return
        try:
            self.store.delete_asset(record["id"], self.username, self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.refresh_assets(kind)
        self.status.showMessage(f"{ASSET_META[kind]['label']} deleted.", 4000)

    def export_assets(self, kind: str, fmt: str):
        if not self.ensure("export", "Sign in as a super admin to export."):
            return
        rows = self.asset_rows[kind]
        if not rows:
            warn(self, "There is nothing to export.")
            return
        meta = ASSET_META[kind]
        ext = {"Excel": ".xlsx", "PDF": ".pdf"}[fmt]
        suggested = str(Path.home() / "Downloads" / f"{kind}s{ext}")
        path, _ = QFileDialog.getSaveFileName(self, f"Save {fmt}", suggested, f"{fmt} (*{ext})")
        if not path:
            return
        columns = meta["columns"]
        labels = _asset_labels(meta)
        try:
            if fmt == "Excel":
                written = export_excel(rows, path, columns=columns, labels=labels)
            else:
                written = export_pdf(rows, path, columns=columns, labels=labels,
                                     title=f"{meta['tab']} register")
        except PermissionError:
            warn(self, "That file is open in another program. Close it and try again.")
            return
        except Exception as exc:
            warn(self, f"Could not write the file:\n{exc}")
            return
        what = f"{len(rows)} {meta['tab'].lower()} to {fmt}"
        self.store.log(self.username, "export", meta["entity"], "", f"{what}: {written}")
        self.status.showMessage(f"Exported {what}.", 6000)
        QMessageBox.information(self, "Export finished", f"Saved:\n{written}")

    def record_asset(self, kind: str):
        if not self.ensure("export", "Sign in as a super admin to print records."):
            return
        record = self._selected_asset(kind)
        if not record:
            return
        meta = ASSET_META[kind]
        labels = _asset_labels(meta)
        fields = [(labels[c], record[c]) for c in meta["columns"] if str(record[c]).strip()]
        history = [{"emp": f"{h['emp_name'] or ''} ({h['emp_id']})".strip(),
                    "from": self._date_label(h["assigned_on"]),
                    "until": ("" if not h["released_on"]
                              else self._date_label(h["released_on"])),
                    "note": h["note"]}
                   for h in self.store.asset_history(record)]
        document_no = f"ITR/{meta['tag']}/{record['identity'] or record['id']}"
        title = f"{meta['label'].upper()} RECORD"
        subtitle = f"Status: {record['status'] or 'not recorded'}  |  {meta['tab']} register"
        suggested = str(Path.home() / "Downloads" /
                        f"{record['identity'] or record['name_type'] or kind}"
                        f" - {meta['label']} Record.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Save the record document",
                                              suggested, "PDF (*.pdf)")
        if not path:
            return
        try:
            export_record_pdf(title, fields, company=self.store.company(),
                              history=history or None, document_no=document_no,
                              prepared_by=self.username, subtitle=subtitle, path=path)
        except Exception as exc:
            warn(self, f"Could not write the file:\n{exc}")
            return
        self.store.log(self.username, "print", meta["entity"], record["identity"],
                       f"record document: {path}")
        self._after_record(path, record["identity"])

    def _after_record(self, path: str, identity: str):
        self.status.showMessage(f"Record document saved: {path}", 6000)
        answer = QMessageBox.question(
            self, "Record document ready",
            f"The record for {identity} has been saved to:\n{path}\n\n"
            "Open it now to view or print?",
            QMessageBox.Open | QMessageBox.No, QMessageBox.Open)
        if answer == QMessageBox.Open:
            import os
            os.startfile(path)

    # -- import ----------------------------------------------------------

    def import_excel(self):
        if not self.ensure("import", "Sign in as a super admin to import."):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the Excel file to import",
            str(Path.home() / "Downloads"), "Excel files (*.xlsx *.xlsm)")
        if not path:
            return
        try:
            rows, ignored, problems = read_excel(path)
        except PermissionError:
            warn(self, "That file is open in Excel. Close it and try again.")
            return
        except Exception as exc:
            warn(self, f"Could not read that file:\n{exc}")
            return

        if not rows:
            detail = "\n".join(problems) or "No row in the sheet had an Employee ID."
            warn(self, "Nothing to import.\n\n" + detail)
            return

        known = {r["emp_id"] for r in self.store.employees()}
        incoming = {r["emp_id"] for r in rows}
        new_count = len(incoming - known)
        update_count = len(incoming & known)

        dialog = ImportPreview(self, path, rows, new_count, update_count, ignored, problems)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            result = self.store.import_rows(rows, self.username, self.role,
                                            update_existing=dialog.update_existing())
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return

        self.refresh()
        summary = (f"Added: {result['added']}\n"
                   f"Updated: {result['updated']}\n"
                   f"Skipped: {result['skipped']}")
        if result["problems"]:
            summary += "\n\n" + "\n".join(result["problems"][:15])
            if len(result["problems"]) > 15:
                summary += f"\n... and {len(result['problems']) - 15} more"
        QMessageBox.information(self, "Import finished", summary)
        self.status.showMessage(
            f"Imported {result['added']} new and {result['updated']} updated employees.", 8000)

    # -- exports ---------------------------------------------------------

    def _export(self, kind: str, extension: str, writer):
        if not self.ensure("export", "Sign in as a super admin to export."):
            return
        if not self.rows:
            warn(self, "There is nothing to export.")
            return
        suggested = str(Path.home() / "Downloads" / f"employees{extension}")
        path, _ = QFileDialog.getSaveFileName(self, f"Save {kind}", suggested,
                                              f"{kind} (*{extension})")
        if not path:
            return
        try:
            written = writer(self.rows, path)
        except PermissionError:
            warn(self, "That file is open in another program. Close it and try again.")
            return
        except Exception as exc:
            warn(self, f"Could not write the file:\n{exc}")
            return
        what = f"{len(self.rows)} record(s) to {kind}"
        self.store.log(self.username, "export", "employee", "", f"{what}: {written}")
        self.status.showMessage(f"Exported {what}.", 6000)
        QMessageBox.information(self, "Export finished", f"Saved:\n{written}")

    def export_excel(self):
        self._export("Excel", ".xlsx", lambda rows, path: export_excel(rows, path))

    def export_pdf(self):
        filtered = self.search.text().strip()
        subtitle = f"Filtered by '{filtered}'" if filtered else "All employees"
        self._export("PDF", ".pdf",
                     lambda rows, path: export_pdf(rows, path, subtitle=subtitle))

    def _date_label(self, iso: str) -> str:
        return local_time(iso + "T00:00:00+00:00").split("  ")[0] if iso else "present"

    def record_employee(self):
        if not self.ensure("export", "Sign in as a super admin to print records."):
            return
        record = self.selected()
        if not record:
            return
        fields = [(LABELS[c], record[c]) for c in COLUMNS if str(record[c]).strip()]
        subtitle = "  |  ".join(x for x in
                                [record["designation"], record["department"]] if x) or record["status"]
        heading = record["status"] if record["status"] else ""
        title = "EMPLOYEE RECORD"
        document_no = f"ITR/EMP/{record['emp_id'] or record['id']}"
        suggested = str(Path.home() / "Downloads" /
                        f"{record['emp_name'] or record['emp_id']} - Employee Record.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Save the record document",
                                              suggested, "PDF (*.pdf)")
        if not path:
            return
        try:
            export_record_pdf(title, fields, company=self.store.company(),
                              document_no=document_no, prepared_by=self.username,
                              subtitle=subtitle, path=path)
        except Exception as exc:
            warn(self, f"Could not write the file:\n{exc}")
            return
        self.store.log(self.username, "print", "employee",
                       record["emp_id"], f"record document: {path}")
        self._after_record(path, heading)

    # -- activity log ----------------------------------------------------

    def _logs_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)
        self.log_count = QLabel("0 entries")
        self.log_count.setObjectName("count")
        page_title(box, "Activity Log", "Every add, edit, delete, export, assignment and "
                   "sign-in. Nothing here is ever changed.", self.log_count)
        self.log_search = search_box("Search the log - who, what, which employee/asset")
        self.log_search.textChanged.connect(self.load_logs)
        box.addWidget(self.log_search)
        self.log_table = make_table(multi=False)
        box.addWidget(self.log_table, 1)
        return page

    def load_logs(self):
        if not Store.may(self.role, "logs"):
            return
        entries = self.store.logs(self.role, self.log_search.text())
        headers = ["When", "Who", "Action", "Record", "Details"]
        self.log_table.clear()
        self.log_table.setColumnCount(len(headers))
        self.log_table.setHorizontalHeaderLabels(headers)
        self.log_table.setRowCount(len(entries))
        for r, entry in enumerate(entries):
            values = [local_time(entry["at"]), entry["actor"], entry["action"],
                      f"{entry['entity']} {entry['entity_id']}".strip(), entry["detail"]]
            for c, value in enumerate(values):
                self.log_table.setItem(r, c, QTableWidgetItem(value))
        self.log_table.resizeColumnsToContents()
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_count.setText(f"{len(entries)} entries")

    # -- users -----------------------------------------------------------

    def _users_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)
        page_title(box, "Users", "Accounts that can sign in to IT Records")

        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, slot, name in [("Add User", self.add_user, None),
                                 ("Reset Password", self.reset_password, "ghost"),
                                 ("Delete User", self.delete_user, "danger")]:
            self._toolbar_button(bar, text, slot, name)
        bar.addStretch()
        box.addLayout(bar)

        self.user_table = make_table(multi=False)
        box.addWidget(self.user_table, 1)

        legend = QLabel("   ".join(f"•  {d}" for d in ROLES.values()))
        legend.setObjectName("subtitle")
        legend.setWordWrap(True)
        box.addWidget(legend)
        return page

    def load_users(self):
        if not Store.may(self.role, "users"):
            return
        self.user_rows = self.store.users(self.role)
        headers = ["Username", "Role", "Created", "Last Sign-in"]
        self.user_table.clear()
        self.user_table.setColumnCount(len(headers))
        self.user_table.setHorizontalHeaderLabels(headers)
        self.user_table.setRowCount(len(self.user_rows))
        for r, user in enumerate(self.user_rows):
            values = [user["username"], user["role"],
                      local_time(user["created"]), local_time(user["last_login"]) or "never"]
            for c, value in enumerate(values):
                self.user_table.setItem(r, c, QTableWidgetItem(value))
        self.user_table.resizeColumnsToContents()
        self.user_table.horizontalHeader().setStretchLastSection(True)

    def selected_user(self) -> dict | None:
        rows = self.user_table.selectionModel().selectedRows() if self.user_table.selectionModel() else []
        if not rows:
            warn(self, "Select a user row first.")
            return None
        return self.user_rows[rows[0].row()]

    def add_user(self):
        dialog = NewUserDialog(self)
        while dialog.exec_() == QDialog.Accepted:
            try:
                self.store.create_user(dialog.username.text(), dialog.password.text(),
                                       dialog.role.currentData(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                continue
            self.load_users()
            self.status.showMessage("User created.", 4000)
            return

    def reset_password(self):
        user = self.selected_user()
        if not user:
            return
        dialog = PasswordDialog(self, f"New password for {user['username']}")
        while dialog.exec_() == QDialog.Accepted:
            try:
                self.store.set_password(user["username"], dialog.box.text(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                continue
            self.status.showMessage(f"Password changed for {user['username']}.", 5000)
            return

    def delete_user(self):
        user = self.selected_user()
        if not user:
            return
        if not confirm_danger(self, "Delete user",
                              f"Delete the account {user['username']}? They will no longer "
                              "be able to sign in."):
            return
        try:
            self.store.delete_user(user["username"], self.username, self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.load_users()
        self.status.showMessage("User deleted.", 4000)

    # -- dashboard ---------------------------------------------------------

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)
        page_title(box, "Dashboard", "An overview of the registers and data quality")
        self.dashboard_scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        box.addWidget(self.dashboard_scroll, 1)
        holder = QWidget()
        self.dashboard_layout = QVBoxLayout(holder)       # replaced on every load
        self.dashboard_scroll.setWidget(holder)
        return page

    @staticmethod
    def _tile(value, label: str, note: str = "") -> QWidget:
        tile = QWidget()
        tile.setObjectName("tile")
        tile.setAttribute(Qt.WA_StyledBackground, True)
        col = QVBoxLayout(tile)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(0)
        number = QLabel(str(value))
        number.setObjectName("tileValue")
        name = QLabel(label)
        name.setObjectName("tileLabel")
        col.addWidget(number)
        col.addWidget(name)
        if note:
            extra = QLabel(note)
            extra.setObjectName("subtitle")
            col.addWidget(extra)
        return tile

    @staticmethod
    def _stat_box(title: str, lines: list[str]) -> QWidget:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        if not lines:
            layout.addWidget(QLabel("Nothing to show."))
        for line in lines:
            layout.addWidget(QLabel(line))
        return group

    def load_dashboard(self):
        # A fresh holder each time: the old one (charts, grids and all) goes with
        # it, so nothing from the previous load is left drawn underneath.
        holder = QWidget()
        holder.setObjectName("page")
        self.dashboard_layout = QVBoxLayout(holder)
        self.dashboard_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard_layout.setSpacing(12)

        stats = self.store.stats()

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        tiles.addWidget(self._tile(stats["total"], "Employees"))
        for a in stats["assets_by_kind"]:
            tiles.addWidget(self._tile(a["total"], a["label"], f"{a['issued']} issued"))
        self.dashboard_layout.addLayout(tiles)

        grid = QGridLayout()
        grid.setSpacing(12)
        try:
            import matplotlib
            matplotlib.use("Agg")  # non-interactive backend
            import matplotlib.pyplot as plt
            from io import BytesIO
            from PyQt5.QtGui import QPixmap

            def make_bar_chart(data: list, title: str) -> QLabel | None:
                if not data:
                    return None
                labels, values = zip(*data)
                fig, ax = plt.subplots(figsize=(5, 2.8))
                fig.patch.set_facecolor(PALETTE["bg"])
                ax.set_facecolor(PALETTE["bg"])
                bars = ax.barh(labels, values, color=PALETTE["brand"])
                ax.bar_label(bars, padding=3, fontsize=8, color=PALETTE["text"])
                ax.set_title(title, fontsize=10, fontweight="bold", color=PALETTE["text"],
                             loc="left")
                ax.tick_params(labelsize=8, colors=PALETTE["muted"])
                ax.invert_yaxis()                        # largest first, top down
                for side in ("top", "right"):
                    ax.spines[side].set_visible(False)
                for side in ("left", "bottom"):
                    ax.spines[side].set_color(PALETTE["border"])
                plt.tight_layout()
                ratio = self.devicePixelRatioF()           # sharp on a scaled display
                buf = BytesIO()
                fig.savefig(buf, format="png", dpi=100 * ratio)
                plt.close(fig)
                pixmap = QPixmap()
                pixmap.loadFromData(buf.getvalue())
                pixmap.setDevicePixelRatio(ratio)
                lbl = QLabel()
                lbl.setPixmap(pixmap)
                lbl.setMinimumSize(pixmap.size() / ratio)
                lbl.setAlignment(Qt.AlignCenter)
                return lbl

            charts = [(stats["by_department"], "Employees by department"),
                      (stats["by_region"], "Employees by region"),
                      (stats["by_status"], "Employees by status"),
                      ([(a["label"], a["total"]) for a in stats["assets_by_kind"]],
                       "Assets by type")]
            placed = 0
            for data, title in charts:
                chart = make_bar_chart(data, title)
                if chart:
                    grid.addWidget(chart, placed // 2, placed % 2)
                    placed += 1
        except ImportError:
            # Text summaries when matplotlib is not installed
            grid.addWidget(self._stat_box(
                "By status", [f"{name}: {n}" for name, n in stats["by_status"]]), 0, 0)
            grid.addWidget(self._stat_box(
                "By region", [f"{name}: {n}" for name, n in stats["by_region"]]), 0, 1)
            grid.addWidget(self._stat_box(
                "Top departments", [f"{name}: {n}" for name, n in stats["by_department"]]), 1, 0)

        grid.addWidget(self._stat_box("Asset registers", [
            f"{a['label']}: {a['total']} on file, {a['issued']} currently issued"
            for a in stats["assets_by_kind"]
        ]), 2, 0)
        grid.addWidget(self._stat_box("Records missing contact info", [
            f"No email address: {stats['missing_email']}",
            f"No contact number: {stats['missing_contact']}",
        ]), 2, 1)
        self.dashboard_layout.addLayout(grid)

        # --- Data Integrity Cross-Check ---
        integrity_title = QLabel("<b>Data integrity - serial number cross-check</b>")
        integrity_title.setStyleSheet("margin-top: 8px; font-size: 11pt;")
        self.dashboard_layout.addWidget(integrity_title)

        issues = self.store.cross_check_serials()
        total_issues = sum(len(v) for v in issues.values())
        if total_issues == 0:
            ok_label = QLabel("No mismatches found. All serial numbers are consistent.")
            ok_label.setObjectName("ok")
            self.dashboard_layout.addWidget(ok_label)
        else:
            warn_label = QLabel(
                f"Found {total_issues} mismatch(es) between employee records and asset registers:")
            warn_label.setObjectName("error")
            self.dashboard_layout.addWidget(warn_label)
            integrity_grid = QGridLayout()
            labels = {
                "laptop": "Laptop serial mismatches",
                "mobile": "Mobile serial mismatches",
                "printer": "Printer serial mismatches",
                "unassigned_laptop": "Laptops with missing assignment",
            }
            placed = 0
            for key, items in issues.items():
                if items:
                    shown = items[:20] + ([f"... and {len(items) - 20} more"]
                                          if len(items) > 20 else [])
                    integrity_grid.addWidget(self._stat_box(labels.get(key, key), shown),
                                             placed // 2, placed % 2)
                    placed += 1
            self.dashboard_layout.addLayout(integrity_grid)
        self.dashboard_layout.addStretch()
        self.dashboard_scroll.setWidget(holder)      # attach once it is complete

    # -- my account ------------------------------------------------------

    def _account_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 18, 24, 12)
        box.setSpacing(10)
        if self.role == "viewer":
            page_title(box, "My Account", "Not signed in")
            box.addWidget(QLabel(
                "The register is open read-only. Sign in to add or edit employees and "
                "assets, manage accounts and export."))
            info = QLabel(f"Database file:  {self.store.path}")
            info.setObjectName("subtitle")
            info.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(info)
            sign = QPushButton("Sign in")
            sign.setMaximumWidth(200)
            sign.clicked.connect(self.sign_in)
            box.addWidget(sign)
        else:
            page_title(box, "My Account", f"Signed in as {self.username} - {ROLES[self.role]}")
            info = QLabel(f"Database file:  {self.store.path}")
            info.setObjectName("subtitle")
            info.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(info)

            change = QPushButton("Change my password")
            change.setObjectName("ghost")
            change.setMaximumWidth(220)
            change.clicked.connect(self.change_own_password)
            box.addWidget(change)

            co = self.store.company()
            group = QGroupBox("Organisation detail - printed on every record document")
            group.setMaximumWidth(620)
            form = QFormLayout(group)
            self.company_inputs: dict[str, QLineEdit] = {}
            for key, label in (("name", "Company name"), ("address", "Address"),
                               ("city", "City"), ("phone", "Phone"),
                               ("email", "Email")):
                edit = QLineEdit(co.get(key, ""))
                if key == "name":
                    edit.setPlaceholderText("e.g. ABC Corporation (Pvt) Ltd")
                self.company_inputs[key] = edit
                form.addRow(label, edit)
            if Store.may(self.role, "users"):
                save = QPushButton("Save organisation detail")
                save.setMaximumWidth(240)
                save.clicked.connect(self.save_company)
                form.addRow("", save)
                note = QLabel("Saved to the shared database - every PC printing a record "
                              "uses the same letterhead and seal.")
            else:
                note = QLabel("Only the super admin can change the organisation detail.")
                for edit in self.company_inputs.values():
                    edit.setEnabled(False)
            note.setObjectName("subtitle")
            note.setWordWrap(True)
            box.addWidget(group)
            box.addWidget(note)

            if Store.may(self.role, "users"):
                mail = QGroupBox("Email")
                mail.setMaximumWidth(620)
                row = QHBoxLayout(mail)
                row.addWidget(QLabel(f"Emails are sent from  <b>{email_config()['smtp_email']}</b>"))
                row.addStretch()
                edit_mail = QPushButton("Email Settings")
                edit_mail.setObjectName("ghost")
                edit_mail.clicked.connect(self.email_settings)
                row.addWidget(edit_mail)
                box.addWidget(mail)
        box.addStretch()
        return page

    def save_company(self):
        try:
            saved = self.store.save_company({k: w.text() for k, w in self.company_inputs.items()},
                                            self.username, self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.status.showMessage(f"Organisation detail saved ({saved['name']}).", 5000)

    def change_own_password(self):
        dialog = PasswordDialog(self, "Change my password")
        while dialog.exec_() == QDialog.Accepted:
            try:
                self.store.set_password(self.username, dialog.box.text(), self.username, self.role)
            except (Invalid, Denied) as exc:
                warn(dialog, str(exc))
                continue
            self.status.showMessage("Your password has been changed.", 5000)
            return


# ------------------------------------------------------------------ start

_WINDOW = None
_LISTENERS: list = []          # held for the life of the process (GC would close the socket)


class SingleInstance(Exception):
    pass


def _app_icon() -> str:
    """Window / taskbar icon - bundled beside the exe when frozen, else in the
    source folder. Falls back to Qt's default if the .ico is missing."""
    candidates = [Path(getattr(sys, "_MEIPASS", "")), Path(__file__).parent]
    for base in candidates:
        icon = base / "app.ico"
        if icon.is_file():
            return str(icon)
    return ""


def _single_instance(path):
    """One window per database. Two copies of the app editing the same file at
    the same time is the surest way to lose a record, so the second one stops
    and points at the first. A loopback listener keyed off the database path is
    used because Windows file locks do not reliably exclude a second process;
    if the app crashes the OS frees the port and the next start works."""
    import hashlib
    import socket
    port = 45000 + int(hashlib.sha1(str(path).encode("utf-8")).hexdigest(), 16) % 800
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        raise SingleInstance(path.name)
    sock.listen(1)
    _LISTENERS.append(sock)


def run(store: Store):
    global _WINDOW
    if _WINDOW is not None:
        try:
            _WINDOW.close()
        except Exception:
            pass
    _WINDOW = MainWindow(store, "", "viewer")
    _WINDOW.show()


def main() -> int:
    app = QApplication(sys.argv)

    # Set up a global exception handler so crashes are logged to file
    def _handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _handle_exception

    _log.info("Application starting")
    apply_theme(QSettings("ITRecords", "IT Records").value("theme", "light"))
    fade = FadeIn(app)
    app.installEventFilter(fade)

    app.setFont(QFont("Segoe UI", 10))
    icon = _app_icon()
    if icon:
        app.setWindowIcon(QIcon(icon))

    try:
        store = Store()
        _single_instance(store.path)
    except SingleInstance as exc:
        box = QMessageBox(QMessageBox.Warning, "IT Records",
                          f"IT Records is already open.\n\n{exc}")
        QTimer.singleShot(1600, box.close)   # never leave a ghost copy running
        box.exec_()
        return 0
    except Exception as exc:
        QMessageBox.critical(None, "IT Records", f"Cannot open the database:\n{exc}")
        return 1

    first = store.bootstrap()
    store.backup()
    if first:
        user, password = first
        QMessageBox.information(
            None, "First run",
            f"An account has been created.\n\n"
            f"Username:  {user}\nPassword:  {password}\n\n"
            "This is the fixed super admin login for now. Change it from "
            "My Account once real users are on the system.")

    run(store)
    rc = app.exec_()
    _log.info("Application exiting (code %d)", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())