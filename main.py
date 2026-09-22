"""IT Records - PyQt5 desktop app.  Run with:  python main.py"""

from __future__ import annotations

import sys
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

_log = logging.getLogger("itrecords.ui")

from PyQt5.QtCore import Qt, QSettings, QTimer, QDate
from PyQt5.QtGui import QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QComboBox, QDateEdit,
                             QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton, QScrollArea,
                             QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
                             QVBoxLayout, QWidget)

import core
from core import (ASSET_LABELS, ASSET_META, CHOICES, COLUMNS, COMPANY_DEFAULTS, FIELDS, GROUPS,
                  LABELS, ROLES, Store, Denied, Invalid, export_csv, export_excel, export_pdf,
                  export_record_pdf, local_time, read_excel)

BRAND = "#006a63"
BRAND_DARK = "#004f49"
YELLOW = "#ffd100"
RED = "#d7282f"

STYLE = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: #14211f; }}
QMainWindow, QDialog, #page {{ background: #f5f7f7; }}
#header {{ background: #ffffff; border-bottom: 3px solid {BRAND}; }}
#brand {{ color: {BRAND}; font-size: 16pt; font-weight: 800; }}
#brandDot {{ color: {YELLOW}; font-size: 16pt; font-weight: 800; }}
#subtitle, #who {{ color: #5f7472; }}
#banner {{ background: #fff8d6; border-left: 4px solid {YELLOW}; padding: 8px; color: #6b5900; }}
QPushButton {{ background: {BRAND}; color: #fff; border: 1px solid {BRAND};
               border-radius: 5px; padding: 6px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {BRAND_DARK}; border-color: {BRAND_DARK}; }}
QPushButton:disabled {{ background: #b9c6c4; border-color: #b9c6c4; }}
QPushButton#ghost {{ background: #fff; color: {BRAND}; }}
QPushButton#ghost:hover {{ background: #e6f1f0; }}
QPushButton#danger {{ background: {RED}; border-color: {RED}; }}
QPushButton#tab {{ background: transparent; color: #5f7472; border: none;
                   border-bottom: 3px solid transparent; border-radius: 0; padding: 8px 9px; }}
QPushButton#tab:checked {{ color: {BRAND_DARK}; border-bottom: 3px solid {YELLOW}; }}
QLineEdit, QComboBox {{ background: #fff; border: 1px solid #d9e2e1; border-radius: 5px; padding: 6px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {BRAND}; }}
QTableWidget {{ background: #fff; border: 1px solid #d9e2e1; border-radius: 6px;
                gridline-color: #e6eceb; }}
QTableWidget::item:selected {{ background: #e6f1f0; color: #14211f; }}
QHeaderView::section {{ background: {BRAND}; color: #fff; font-weight: 600;
                        padding: 6px; border: none; border-bottom: 3px solid {YELLOW}; }}
QGroupBox {{ border: 1px solid #d9e2e1; border-radius: 6px; margin-top: 14px;
             background: #fff; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px;
                    color: {BRAND_DARK}; font-weight: 700; }}
QLabel#error {{ color: {RED}; }}
QLabel#count {{ background: #e6f1f0; color: {BRAND_DARK}; border-radius: 9px;
                padding: 3px 10px; font-weight: 600; }}
"""


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


# ------------------------------------------------------------ employee form

class EmployeeDialog(QDialog):
    """Add or edit one employee. Every field of the entity is on this one form."""

    def __init__(self, parent, record: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit employee" if record else "Add employee")
        # Use WindowMaximized flag so exec_() opens it maximized on Windows
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setWindowState(Qt.WindowMaximized)
        self.inputs: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        holder = QWidget()
        holder.setObjectName("page")
        body = QVBoxLayout(holder)

        for group_name, keys in GROUPS:
            group = QGroupBox(group_name)
            grid = QGridLayout(group)
            for index, key in enumerate(keys):
                row, column = divmod(index, 2)
                if key == "sno":
                    widget = QLineEdit(str(record.get(key, "")) if record else "")
                    widget.setReadOnly(True)
                    widget.setPlaceholderText("Auto-generated")
                elif key == "join_date":
                    widget = QDateEdit()
                    widget.setCalendarPopup(True)
                    widget.setDisplayFormat("yyyy-MM-dd")
                    if record and record.get(key):
                        try:
                            parts = record[key].split("-")
                            if len(parts) == 3:
                                widget.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                        except Exception:
                            widget.setDate(QDate.currentDate())
                    else:
                        widget.setDate(QDate.currentDate())
                elif key in CHOICES:
                    widget = QComboBox()
                    widget.addItems(CHOICES[key])
                    if record and record.get(key):
                        widget.setCurrentText(record[key])
                else:
                    widget = QLineEdit(str(record.get(key, "")) if record else "")
                self.inputs[key] = widget
                label = QLabel(dict(((f[0], f[1]) for f in FIELDS))[key])
                grid.addWidget(label, row, column * 2)
                grid.addWidget(widget, row, column * 2 + 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            body.addWidget(group)

        note = QLabel("Only Employee ID is required. Anything not known yet can be left blank "
                      "and filled in later. A serial number that an asset is already issued "
                      "under will be refused.")
        note.setObjectName("subtitle")
        body.addWidget(note)
        body.addStretch()
        scroll.setWidget(holder)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict:
        result = {}
        for key, w in self.inputs.items():
            if isinstance(w, QComboBox):
                result[key] = w.currentText()
            elif isinstance(w, QDateEdit):
                result[key] = w.date().toString("yyyy-MM-dd")
            else:
                result[key] = w.text()
        return result

    def accept(self):
        """Validate before closing."""
        emp_id_widget = self.inputs.get("emp_id")
        if emp_id_widget and not emp_id_widget.text().strip():
            emp_id_widget.setStyleSheet("border: 2px solid #d7282f;")
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
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        
        self.settings = QSettings("ITRecords", "Settings")
        
        self.server = QLineEdit(self.settings.value("smtp_server", "smtp.gmail.com"))
        self.port = QLineEdit(self.settings.value("smtp_port", "587"))
        self.email = QLineEdit(self.settings.value("smtp_email", "hammadalamgir778@gmail.com"))
        self.password = QLineEdit(self.settings.value("smtp_password", "qxab wjpx xvje orma"))
        self.password.setEchoMode(QLineEdit.Password)
        
        form.addRow("SMTP Server:", self.server)
        form.addRow("SMTP Port:", self.port)
        form.addRow("Sender Email:", self.email)
        form.addRow("App Password:", self.password)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        self.settings.setValue("smtp_server", self.server.text())
        self.settings.setValue("smtp_port", self.port.text())
        self.settings.setValue("smtp_email", self.email.text())
        self.settings.setValue("smtp_password", self.password.text())
        self.accept()

class ComposeEmailDialog(QDialog):
    def __init__(self, parent, to_email):
        super().__init__(parent)
        self.setWindowTitle(f"Compose Email to {to_email}")
        self.resize(500, 400)
        self.to_email = to_email
        
        box = QVBoxLayout(self)
        
        form = QFormLayout()
        self.subject = QLineEdit()
        form.addRow("Subject:", self.subject)
        box.addLayout(form)
        
        from PyQt5.QtWidgets import QTextEdit as _QTE  # noqa: F401 — use module-level import
        self.body = QTextEdit()
        box.addWidget(self.body)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Send")
        btns.accepted.connect(self.send)
        btns.rejected.connect(self.reject)
        box.addWidget(btns)

    def send(self):
        settings = QSettings("ITRecords", "Settings")
        server = settings.value("smtp_server", "")
        port = settings.value("smtp_port", "")
        email_addr = settings.value("smtp_email", "")
        password = settings.value("smtp_password", "")
        
        if not all([server, port, email_addr, password]):
            QMessageBox.warning(self, "Missing Settings", "Please configure Email Settings first.")
            return

        try:
            msg = EmailMessage()
            msg['Subject'] = self.subject.text()
            msg['From'] = email_addr
            msg['To'] = self.to_email
            msg.set_content(self.body.toPlainText())

            with smtplib.SMTP(server, int(port)) as s:
                s.starttls()
                s.login(email_addr, password)
                s.send_message(msg)
            
            _log.info("Email sent to %s subject='%s'", self.to_email, self.subject.text())
            QMessageBox.information(self, "Success", "Email sent successfully!")
            self.accept()
        except Exception as e:
            _log.error("Email send failed to %s: %s", self.to_email, e)
            QMessageBox.critical(self, "Error", f"Failed to send email:\n{str(e)}")

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
        self.resize(620, 640)
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

        self.setWindowTitle("IT Records")
        self.settings = QSettings("ITRecords", "IT Records")
        geometry = self.settings.value("geometry")
        self.restoreGeometry(geometry) if geometry else self.resize(1380, 780)

        page = QWidget()
        page.setObjectName("page")
        self.setCentralWidget(page)
        outer = QVBoxLayout(page)
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

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def _shortcuts(self):
        keys = [
            ("Ctrl+F", lambda: (self.show_page(0),
                                (self.search if self.stack.currentIndex() == 0
                                 else self.search).setFocus(), self.search.selectAll())),
            ("F5", self.refresh),
            ("Ctrl+N", self.add_employee),
            ("Ctrl+E", self.edit_employee),
            ("Delete", self._delete_current),
            ("Ctrl+Q", self.close),
        ]
        for key, slot in keys:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

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

    def _header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("header")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 0)
        row.addWidget(brand_mark("Register"))

        self.tabs: list[QPushButton] = []
        names = [("Employees", 0), ("Laptops", 1), ("Mobiles", 2), ("IP Phones", 3),
                 ("Printers", 4), ("Challan", 5), ("Activity Log", 6), ("Users", 7),
                 ("My Account", 8), ("Dashboard", 9)]
        for text, index in names:
            if index == 6 and not Store.may(self.role, "logs"):
                continue
            if index == 7 and not Store.may(self.role, "users"):
                continue
            button = QPushButton(text)
            button.setObjectName("tab")
            button.setCheckable(True)
            button.clicked.connect(lambda _, i=index: self.show_page(i))
            row.addWidget(button)
            self.tabs.append(button)

        row.addStretch()
        if self.role == "viewer":
            who = QLabel("Read-only view")
            who.setObjectName("who")
            row.addWidget(who)
            sign = QPushButton("Sign in")
            sign.setObjectName("ghost")
            sign.clicked.connect(self.sign_in)
            row.addWidget(sign)
        else:
            who = QLabel(f"{self.username}  ·  {ROLES[self.role].split(' - ')[0]}")
            who.setObjectName("who")
            row.addWidget(who)
            sign = QPushButton("Sign out")
            sign.setObjectName("ghost")
            sign.clicked.connect(self.sign_out)
            row.addWidget(sign)

        # Theme toggle button — always visible in header
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setToolTip("Toggle Dark / Light mode")
        self._update_theme_btn_icon()
        self.theme_btn.clicked.connect(self.toggle_theme)
        row.addWidget(self.theme_btn)
        return bar

    def _update_theme_btn_icon(self):
        theme = self.settings.value("theme", "light")
        self.theme_btn.setText("Light" if theme == "dark" else "Dark")

    def toggle_theme(self):
        current = self.settings.value("theme", "light")
        new_theme = "light" if current == "dark" else "dark"
        self.settings.setValue("theme", new_theme)
        try:
            import qdarktheme
            if new_theme == "dark":
                QApplication.instance().setStyleSheet(qdarktheme.load_stylesheet("dark"))
            else:
                QApplication.instance().setStyleSheet(STYLE)
        except (ImportError, Exception):
            QApplication.instance().setStyleSheet(STYLE)
        self._update_theme_btn_icon()
        self.status.showMessage(
            f"{'Dark' if new_theme == 'dark' else 'Light'} mode enabled.", 3000)

    def _rebuild_header(self):
        outer = self.centralWidget().layout()
        outer.removeWidget(self.header_widget)
        self.header_widget.deleteLater()
        self.header_widget = self._header()
        outer.insertWidget(0, self.header_widget)

    def show_page(self, index: int):
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

    # -- employees -------------------------------------------------------

    def _employees_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(16, 12, 16, 12)

        if not Store.may(self.role, "edit"):
            banner = QLabel("Read-only - you can search, view and print, but not change "
                            "records. Sign in as super admin to add or edit.")
            banner.setObjectName("banner")
            box.addWidget(banner)

        bar = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search anything - name, Emp ID, department, "
                                                "serial number, IMEI, vendor, DC no...")
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        self.count = QLabel("0 records")
        self.count.setObjectName("count")
        bar.addWidget(self.count)

        def button(text, slot, name=None, right=None):
            b = QPushButton(text)
            b.clicked.connect(slot)
            if name:
                b.setObjectName(name)
            if right and not Store.may(self.role, right):
                b.hide()
            bar.addWidget(b)
            return b

        button("Add Employee", self.add_employee, right="edit").setShortcut("Ctrl+N")
        button("Edit", self.edit_employee, "ghost", right="edit").setShortcut("Ctrl+E")
        button("Delete", self.delete_employee, "danger", right="delete")
        button("Asset History", self.show_employee_assets, "ghost")
        button("Print Record", self.record_employee, "ghost", right="export")
        button("Import Excel", self.import_excel, "ghost", right="import")
        button("Email Settings", self.email_settings, "ghost", right="superadmin")
        button("Send Email", self.compose_email, "ghost")

        self.export_buttons = [
            button("Export Excel", self.export_excel, "ghost", right="export"),
            button("Export CSV", self.export_csv, "ghost", right="export"),
            button("Export PDF", self.export_pdf, "ghost", right="export"),
        ]
        if Store.may(self.role, "delete"):
            self.btn_select_all = QPushButton("Select All")
            self.btn_select_all.setObjectName("ghost")
            self.btn_select_all.clicked.connect(self.select_all_employees)
            bar.addWidget(self.btn_select_all)

            self.btn_delete_selected = QPushButton("Delete Selected")
            self.btn_delete_selected.setObjectName("danger")
            self.btn_delete_selected.clicked.connect(self.delete_selected_employees)
            bar.addWidget(self.btn_delete_selected)

            self.btn_delete_all = QPushButton("Delete All")
            self.btn_delete_all.setObjectName("danger")
            self.btn_delete_all.clicked.connect(self.delete_all_employees)
            bar.addWidget(self.btn_delete_all)
        box.addLayout(bar)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.edit_employee)
        self.table.setToolTip("Double-click a row to open it. Shift/Ctrl+click to multi-select.")
        box.addWidget(self.table, 1)
        return page

    def refresh(self):
        self.rows = self.store.employees(self.search.text())
        headers = [LABELS[c] for c in COLUMNS] + ["Last Updated", "Updated By"]
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            values = [str(row[c]) for c in COLUMNS] + \
                     [local_time(row["updated"]), row["updated_by"]]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 0:
                    # The table sorts, so the row number on screen is not a
                    # position in self.rows - carry the real one, or Edit,
                    # Delete and Print Record act on the wrong employee.
                    item.setData(Qt.UserRole, r)
                self.table.setItem(r, c, item)

        # Sort by join_date (index 2 in COLUMNS)
        self.table.sortItems(2, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.count.setText(f"{len(self.rows)} record{'' if len(self.rows) == 1 else 's'}")
        for button in self.export_buttons:
            button.setEnabled(bool(self.rows))
            button.setToolTip("" if self.rows else "Nothing to export - the list is empty")

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
        row = self.selected()
        if not row:
            return
        if QMessageBox.question(self, "Delete record",
                                f"Delete the record for {row['emp_name']} ({row['emp_id']})?\n\n"
                                "Any assets they hold will be released immediately.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.store.delete_employee(row["id"], self.username, self.role)
        except (Invalid, Denied) as exc:
            warn(self, str(exc))
            return
        self.refresh()
        self.status.showMessage("Employee deleted.", 4000)

    def email_settings(self):
        dialog = EmailConfigDialog(self)
        dialog.exec_()

    def compose_email(self):
        row = self.selected()
        if not row:
            return
        to_email = row.get("email")
        if not to_email:
            warn(self, "Selected employee does not have an email address.")
            return
        dialog = ComposeEmailDialog(self, to_email)
        dialog.exec_()


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
        answer = QMessageBox.question(
            self, "Delete selected employees",
            f"Permanently delete {len(records)} employee(s)?\n\n{names}\n\n"
            "The Activity Log will keep a copy of every deleted record.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        failed = 0
        for record in records:
            try:
                self.store.delete_employee(record["id"], self.username, self.role)
            except (Invalid, Denied):
                failed += 1
        self.refresh()
        msg = f"Deleted {len(records) - failed} employee(s)."
        if failed:
            msg += f" {failed} could not be deleted."
        self.status.showMessage(msg, 6000)

    def delete_all_employees(self):
        if not self.ensure("delete", "Sign in as a super admin to delete employees."):
            return
        if not self.rows:
            warn(self, "There are no records to delete.")
            return
        total = len(self.rows)
        filtered = self.search.text().strip()
        scope = f"matching '{filtered}'" if filtered else "in the entire database"
        answer = QMessageBox.question(
            self, "Delete ALL employees",
            f"You are about to permanently delete ALL {total} employee record(s) {scope}.\n\n"
            "This cannot be undone, though the Activity Log will keep a copy.\n\n"
            "Are you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        answer2 = QMessageBox.warning(
            self, "Final confirmation",
            f"Delete {total} record(s)? This is your last chance to cancel.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer2 != QMessageBox.Yes:
            return
        failed = 0
        for record in list(self.rows):
            try:
                self.store.delete_employee(record["id"], self.username, self.role)
            except (Invalid, Denied):
                failed += 1
        self.refresh()
        msg = f"Deleted {total - failed} employee(s)."
        if failed:
            msg += f" {failed} could not be deleted."
        self.status.showMessage(msg, 8000)

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
        box.setContentsMargins(16, 12, 16, 12)

        bar = QHBoxLayout()
        search = QLineEdit(placeholderText=f"Search {meta['tab'].lower()} - serial, model, "
                                           "owner, vendor...")
        search.textChanged.connect(lambda _=None, k=kind: self.refresh_assets(k))
        self.asset_search = getattr(self, "asset_search", {})
        self.asset_search[kind] = search
        bar.addWidget(search, 1)
        count = QLabel("0 assets")
        count.setObjectName("count")
        self.asset_count = getattr(self, "asset_count", {})
        self.asset_count[kind] = count
        bar.addWidget(count)

        def button(text, slot, name=None, right=None):
            b = QPushButton(text)
            b.clicked.connect(slot)
            if name:
                b.setObjectName(name)
            if right and not Store.may(self.role, right):
                b.hide()
            bar.addWidget(b)
            return b

        button(f"Add {meta['label']}", lambda _=None, k=kind: self.add_asset(k), right="edit")
        button("Edit", lambda _=None, k=kind: self.edit_asset(k), "ghost", right="edit")
        button("Assign", lambda _=None, k=kind: self.assign_asset(k), "ghost", right="edit")
        button("Release", lambda _=None, k=kind: self.release_asset(k), "ghost", right="edit")
        button("History", lambda _=None, k=kind: self.show_asset_history(k), "ghost")

        button("Print Record", lambda _=None, k=kind: self.record_asset(k), "ghost",
               right="export")
        button("Delete", lambda _=None, k=kind: self.delete_asset(k), "danger", right="delete")
        for fmt in ("Excel", "CSV", "PDF"):
            self.asset_export_buttons[kind].append(
                button(f"Export {fmt}", lambda _=None, k=kind, f=fmt: self.export_assets(k, f),
                       "ghost", right="export"))
        box.addLayout(bar)

        table = QTableWidget()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.doubleClicked.connect(lambda _=None, k=kind: self.edit_asset(k))
        table.setToolTip("Double-click a row to open it. Shift/Ctrl+click to multi-select.")
        self.asset_table = getattr(self, "asset_table", {})
        self.asset_table[kind] = table
        box.addWidget(table, 1)
        return page

    def refresh_assets(self, kind: str):
        table = self.asset_table[kind]
        rows = self.store.assets(kind, self.asset_search[kind].text())
        self.asset_rows[kind] = rows
        meta = ASSET_META[kind]
        labels = _asset_labels(meta)
        headers = ["Sno"] + [labels[c] for c in meta["columns"]] + ["Last Updated", "Updated By"]
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [str(r + 1)] + [row[c] for c in meta["columns"]] + \
                     [local_time(row["updated"]), row["updated_by"]]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.UserRole, r)      # survives a header-click sort
                table.setItem(r, c, item)
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.asset_count[kind].setText(f"{len(rows)} asset{'' if len(rows) == 1 else 's'}")

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
        answer = QMessageBox.question(
            self, f"Delete {ASSET_META[kind]['label'].lower()}",
            f"Delete {record['identity']} ({record['name_type'] or 'no model'})?\n\n"
            "The row is removed, but the Activity Log keeps a copy and the assignment "
            "history is preserved.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
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
        ext = {"Excel": ".xlsx", "CSV": ".csv", "PDF": ".pdf"}[fmt]
        suggested = str(Path.home() / "Downloads" / f"{kind}s{ext}")
        path, _ = QFileDialog.getSaveFileName(self, f"Save {fmt}", suggested, f"{fmt} (*{ext})")
        if not path:
            return
        columns = meta["columns"]
        labels = _asset_labels(meta)
        try:
            if fmt == "Excel":
                written = export_excel(rows, path, columns=columns, labels=labels)
            elif fmt == "CSV":
                written = export_csv(rows, path, columns=columns, labels=labels)
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

    def export_csv(self):
        self._export("CSV", ".csv", lambda rows, path: export_csv(rows, path))

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
        box.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Every add, edit, delete, export, assignment and sign-in. "
                       "Nothing here is ever changed.")
        title.setObjectName("subtitle")
        box.addWidget(title)

        bar = QHBoxLayout()
        self.log_search = QLineEdit(placeholderText="Search the log - who, what, which employee/asset")
        self.log_search.textChanged.connect(self.load_logs)
        bar.addWidget(self.log_search, 1)
        self.log_count = QLabel("0 entries")
        self.log_count.setObjectName("count")
        bar.addWidget(self.log_count)
        box.addLayout(bar)

        self.log_table = QTableWidget()
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.log_table.verticalHeader().setVisible(False)
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
        box.setContentsMargins(16, 12, 16, 12)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Accounts that can sign in to IT Records"))
        bar.addStretch()
        for text, slot, name in [("Add User", self.add_user, None),
                                 ("Reset Password", self.reset_password, "ghost"),
                                 ("Delete User", self.delete_user, "danger")]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            if name:
                button.setObjectName(name)
            bar.addWidget(button)
        box.addLayout(bar)

        self.user_table = QTableWidget()
        self.user_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.verticalHeader().setVisible(False)
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
        if QMessageBox.question(self, "Delete user", f"Delete the account {user['username']}?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
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
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(10)

        title = QLabel("Dashboard - A visual overview of your IT records.")
        title.setObjectName("subtitle")
        box.addWidget(title)

        scroll = QScrollArea(widgetResizable=True, frameShape=QScrollArea.NoFrame)
        holder = QWidget()
        holder.setObjectName("page")
        self.dashboard_layout = QVBoxLayout(holder)
        self.dashboard_layout.addStretch()
        scroll.setWidget(holder)
        box.addWidget(scroll, 1)
        return page

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
        while self.dashboard_layout.count():
            item = self.dashboard_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = self.store.stats()

        headline = QLabel(f"<b>{stats['total']}</b> employee record(s) on file")
        self.dashboard_layout.addWidget(headline)

        grid = QGridLayout()

        # --- matplotlib charts (optional) ---
        try:
            import matplotlib
            matplotlib.use("Agg")  # non-interactive backend
            import matplotlib.pyplot as plt
            from io import BytesIO
            from PyQt5.QtGui import QPixmap

            def make_bar_chart(data: list, title: str) -> QLabel | None:
                if not data:
                    return None
                labels, values = zip(*data) if data else ([], [])
                fig, ax = plt.subplots(figsize=(4, 2.5))
                fig.patch.set_facecolor('#f5f7f7')
                ax.set_facecolor('#f5f7f7')
                bars = ax.barh(labels, values, color='#006a63')
                ax.bar_label(bars, padding=3, fontsize=8)
                ax.set_title(title, fontsize=9, fontweight='bold')
                ax.tick_params(labelsize=7)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                plt.tight_layout()
                buf = BytesIO()
                fig.savefig(buf, format='png', dpi=100)
                plt.close(fig)
                buf.seek(0)
                pixmap = QPixmap()
                pixmap.loadFromData(buf.read())
                lbl = QLabel()
                lbl.setPixmap(pixmap)
                lbl.setAlignment(Qt.AlignCenter)
                return lbl

            dept_chart = make_bar_chart(stats["by_department"], "Employees by Department")
            if dept_chart:
                grid.addWidget(dept_chart, 0, 0)

            region_chart = make_bar_chart(stats["by_region"], "Employees by Region")
            if region_chart:
                grid.addWidget(region_chart, 0, 1)

            status_chart = make_bar_chart(stats["by_status"], "Employees by Status")
            if status_chart:
                grid.addWidget(status_chart, 1, 0)

            asset_data = [(a['label'], a['total']) for a in stats["assets_by_kind"]]
            assets_chart = make_bar_chart(asset_data, "Assets by Type")
            if assets_chart:
                grid.addWidget(assets_chart, 1, 1)

        except ImportError:
            # Fallback to text boxes if matplotlib is not installed
            grid.addWidget(self._stat_box(
                "By status", [f"{name}: {n}" for name, n in stats["by_status"]]), 0, 0)
            grid.addWidget(self._stat_box(
                "By region", [f"{name}: {n}" for name, n in stats["by_region"]]), 0, 1)
            grid.addWidget(self._stat_box(
                "Top departments", [f"{name}: {n}" for name, n in stats["by_department"]]), 1, 0)

        # Always show summary boxes
        grid.addWidget(self._stat_box("Asset registers", [
            f"{a['label']}: {a['total']} on file, {a['issued']} currently issued"
            for a in stats["assets_by_kind"]
        ]), 2, 0)
        grid.addWidget(self._stat_box("Records missing contact info", [
            f"No email address: {stats['missing_email']}",
            f"No contact number: {stats['missing_contact']}",
        ]), 2, 1)
        self.dashboard_layout.insertLayout(1, grid)

        # --- Data Integrity Cross-Check ---
        integrity_title = QLabel("<b>Data Integrity - Serial Number Cross-Check</b>")
        integrity_title.setStyleSheet("margin-top: 12px;")
        self.dashboard_layout.addWidget(integrity_title)

        issues = self.store.cross_check_serials()
        total_issues = sum(len(v) for v in issues.values())

        if total_issues == 0:
            ok_label = QLabel("No mismatches found. All serial numbers are consistent.")
            ok_label.setStyleSheet("color: #006a63; font-weight: bold; padding: 8px;")
            self.dashboard_layout.addWidget(ok_label)
        else:
            warn_label = QLabel(
                f"Found {total_issues} mismatch(es) between employee records and asset registers:")
            warn_label.setStyleSheet("color: #d7282f; font-weight: bold; padding: 4px;")
            self.dashboard_layout.addWidget(warn_label)

            integrity_grid = QGridLayout()
            col = 0
            labels = {
                "laptop": "Laptop Serial Mismatches",
                "mobile": "Mobile Serial Mismatches",
                "printer": "Printer Serial Mismatches",
                "unassigned_laptop": "Laptops with Missing Assignment",
            }
            row_pos = 0
            for key, items in issues.items():
                if items:
                    box = self._stat_box(labels[key], items[:20])
                    integrity_grid.addWidget(box, row_pos // 2, row_pos % 2)
                    row_pos += 1
            self.dashboard_layout.addLayout(integrity_grid)

        self.dashboard_layout.addStretch()

    # -- my account ------------------------------------------------------

    def _account_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(16, 12, 16, 12)
        if self.role == "viewer":
            box.addWidget(QLabel("<b>Not signed in</b>"))
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
            box.addWidget(QLabel(f"<b>Signed in as {self.username}</b>"))
            box.addWidget(QLabel(ROLES[self.role]))
            info = QLabel(f"Database file:  {self.store.path}")
            info.setObjectName("subtitle")
            info.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(info)

            change = QPushButton("Change my password")
            change.setMaximumWidth(220)
            change.clicked.connect(self.change_own_password)
            box.addWidget(change)

            co = self.store.company()
            group = QGroupBox("Organisation detail - printed on every record document")
            group.setMaximumWidth(560)
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
    # Apply saved theme preference on startup
    saved_theme = QSettings("ITRecords", "IT Records").value("theme", "light")
    try:
        import qdarktheme
        if saved_theme == "dark":
            app.setStyleSheet(qdarktheme.load_stylesheet("dark"))
        else:
            app.setStyleSheet(STYLE)
    except (ImportError, Exception):
        app.setStyleSheet(STYLE)

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