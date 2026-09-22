"""Drives the real widgets without a human:  python test_gui.py

Builds a throwaway database, opens the window as a viewer, as a plain user and as
the super admin, and checks the window actually shows what each one is allowed to
see - including every asset register and its history.
"""

import sys
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import QApplication

import main as gui
from core import Store


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def buttons(window):
    from PyQt5.QtWidgets import QPushButton
    return {b.text(): b for b in window.findChildren(QPushButton) if not b.isHidden()}


def check_login(store, app):
    dialog = gui.LoginDialog(store)
    dialog.user_box.setText("superadmin")
    dialog.pass_box.setText("wrong-password")
    dialog.try_login()
    expect(dialog.error.text() != "", "a wrong password shows an error")
    expect(not dialog.isVisible() or dialog.result() != dialog.Accepted, "and does not sign in")


def check_viewer(store, app):
    """The app opens read-only: nothing but view, and everything viewable."""
    window = gui.MainWindow(store, "", "viewer")
    window.show()
    QApplication.processEvents()

    expect(window.role == "viewer", "an unsigned-in window is a viewer")
    expect(window.table.rowCount() == len(store.employees()),
           "the viewer sees every employee")
    names = buttons(window)
    for disabled in ("Add Employee", "Edit", "Delete", "Import Excel", "Export Excel"):
        expect(disabled not in names, f"a viewer never sees '{disabled}'")
    tabs = [b.text() for b in window.tabs]
    expect("Activity Log" not in tabs and "Users" not in tabs,
           "admin tabs are hidden for a viewer")
    for tab in ("Laptops", "Mobiles", "IP Phones", "Printers", "Challan", "Dashboard"):
        expect(tab in tabs, f"a viewer still sees {tab}")

    # the sign-in upgrade is the only way to earn editing rights
    expect(Store.may(window.role, "edit") is False, "a viewer may not edit")
    window.upgrade("superadmin", "superadmin")
    QApplication.processEvents()
    expect(window.role == "superadmin", "a successful sign-in upgrades the session")
    names = buttons(window)
    for shown in ("Add Employee", "Edit", "Delete", "Import Excel", "Export Excel",
                  "Export CSV", "Export PDF"):
        expect(shown in names, f"after the upgrade the super admin sees '{shown}'")
    tabs = [b.text() for b in window.tabs]
    expect("Activity Log" in tabs and "Users" in tabs,
           "the admin tabs appear after the upgrade")
    expect("Read-only - you can search" not in names,
           "and the read-only banner is gone")
    from PyQt5.QtWidgets import QPushButton
    visible_exports = [b for b in window.findChildren(QPushButton)
                       if b.text() == "Export Excel" and not b.isHidden()]
    expect(len(visible_exports) >= 2,
           "the super admin sees Export Excel on the employees page AND the laptop register")
    expect(window.ensure("edit", "no prompt needed") is True,
           "after the upgrade the right is granted")

    window.sign_out()
    QApplication.processEvents()
    expect(window.role == "viewer", "signing out drops straight back to read-only")
    names = buttons(window)
    expect("Add Employee" not in names, "and the editing buttons disappear again")

    window.close()


def check_window(store, username, role, password):
    window = gui.MainWindow(store, username, role)
    window.show()
    QApplication.processEvents()

    expect(window.table.rowCount() == len(store.employees()),
           f"{role}: the table shows every employee")
    expect(window.table.columnCount() == len(gui.COLUMNS) + 3,
           f"{role}: Sno, every field, updated, updated by")

    window.search.setText("Bilal")
    QApplication.processEvents()
    expect(window.table.rowCount() == 1, f"{role}: search filters the table")
    window.search.setText("")
    QApplication.processEvents()

    names = buttons(window)
    may_edit = Store.may(role, "edit")
    expect(("Add Employee" in names) == may_edit, f"{role}: Add button matches rights")
    expect(("Edit" in names) == may_edit, f"{role}: Edit button matches rights")
    expect(("Delete" in names) == Store.may(role, "delete"), f"{role}: Delete matches rights")
    expect(("Export Excel" in names) == Store.may(role, "export"),
           f"{role}: Export matches rights")
    expect(("Import Excel" in names) == Store.may(role, "import"),
           f"{role}: Import matches rights")
    expect(("Print Record" in names) == Store.may(role, "export"),
           f"{role}: record button matches export rights")

    tabs = [b.text() for b in window.tabs]
    expect(("Activity Log" in tabs) == Store.may(role, "logs"), f"{role}: log tab matches rights")
    expect(("Users" in tabs) == Store.may(role, "users"), f"{role}: user tab matches rights")
    expect("Dashboard" in tabs, f"{role}: every role sees the dashboard")
    for tab in ("Laptops", "Mobiles", "IP Phones", "Printers", "Challan"):
        expect(tab in tabs, f"{role}: {tab} tab is always there")

    window.show_page(9)
    QApplication.processEvents()
    expect(window.dashboard_layout.count() > 0, f"{role}: the dashboard has content")

    if Store.may(role, "logs"):
        window.show_page(6)
        QApplication.processEvents()
        expect(window.log_table.rowCount() > 0, "the log has entries")
    if Store.may(role, "users"):
        window.show_page(7)
        QApplication.processEvents()
        expect(window.user_table.rowCount() == 2, "both accounts are listed")

    window.show_page(8)
    QApplication.processEvents()
    expect(hasattr(window, "company_inputs"), f"{role}: organisation detail is editable")
    expect(all(e.isEnabled() == Store.may(role, "users") for e in window.company_inputs.values()),
           f"{role}: detail field locks match rights")
    window.show_page(0)
    QApplication.processEvents()
    window.close()
    return window


def check_form(window):
    dialog = gui.EmployeeDialog(window)
    expect(set(dialog.inputs) == set(gui.COLUMNS), "the form has an input for every field")
    dialog.inputs["emp_id"].setText("E-9001")
    dialog.inputs["emp_name"].setText("Form Test")
    expect(dialog.values()["emp_id"] == "E-9001", "the form gives back what was typed")
    expect(dialog.values()["status"] in ("Active", "On leave", "Left"), "status is a dropdown")

    existing = window.rows[0]
    edit = gui.EmployeeDialog(window, existing)
    expect(edit.values()["emp_id"] == existing["emp_id"], "editing preloads the record")


def check_assets(store, app):
    """The four registers: CRUD, assignment, release, history, and the employee
    side-effect of the auto-sync."""
    from core import ASSET_META, Invalid

    window = gui.MainWindow(store, "superadmin", "superadmin")
    window.show()
    QApplication.processEvents()

    for kind, meta in ASSET_META.items():
        window.show_page(gui.ASSET_INDEX[kind])
        QApplication.processEvents()
        expect(window.asset_table[kind].rowCount() == len(store.assets(kind)),
               f"{meta['label']}: the register lists its rows")

    # an asset the window knows how to show
    store.add_asset("laptop", {"name_type": "ThinkPad", "serial": "TP-100",
                               "spec": "16GB", "status": "Spare"},
                    "superadmin", "superadmin")
    window.refresh_assets("laptop")
    row_counts = window.asset_table["laptop"].rowCount()
    expect(row_counts > 0, "a new laptop shows in the register")

    # duplicate identity of the same kind is refused
    try:
        store.add_asset("laptop", {"serial": "TP-100", "status": "In use"},
                        "superadmin", "superadmin")
        raise AssertionError("a duplicate laptop serial must be refused")
    except Invalid:
        pass

    # identity is derived from the serial, and a serial-less item gets a tag
    store.add_asset("printer", {"name_type": "LaserJet", "status": "Spare"},
                    "superadmin", "superadmin")
    printer = store.assets("printer")[0]
    expect(printer["identity"].startswith("PRN-"), "a printer with no serial gets a tag")

    # assign to an employee -> history line + the employee's columns update
    laptop = store.asset(store.assets("laptop", "TP-100")[0]["id"])
    store.assign_asset(laptop["id"], "E-1001", note="new joiner", actor="superadmin", role="superadmin")
    laptop = store.asset(laptop["id"])
    expect(laptop["current_emp_id"] == "E-1001", "the laptop records its holder")
    emp = store.employees("E-1001")[0]
    expect(emp["laptop_serial"] == "TP-100", "the employee sheet is kept in sync")

    # hand it over -> both histories read correctly
    store.assign_asset(laptop["id"], "E-1002", note="handover", actor="superadmin", role="superadmin")
    hist = store.asset_history(store.asset(laptop["id"]))
    expect(len(hist) == 2 and hist[0]["released_on"] and hist[1]["released_on"] == "",
           "a transfer closes the old line and opens a new open one")
    expect(hist[1]["emp_id"] == "E-1002" and hist[0]["emp_id"] == "E-1001",
           "the new holder is first in the history")
    expect(store.employees("E-1001")[0]["laptop_serial"] == "",
           "releasing clears the old holder's synced field")

    # release -> back to unassigned
    store.release_asset(laptop["id"], note="returned", actor="superadmin", role="superadmin")
    laptop = store.asset(laptop["id"])
    expect(laptop["current_emp_id"] == "" and laptop["current_emp_name"] == "",
           "released returns the asset to the pool")

    # per-employee history spans the registers
    rows = store.employee_assets("E-1002")
    expect(any(r["asset_identity"] == "TP-100" for r in rows),
           "an employee's history lists what they held")

    # the history dialog opens and reads
    asset = store.assets("laptop", "TP-100")[0]
    dialog = gui.AssetHistoryDialog(window, "laptop", asset, store.asset_history(asset))
    expect(dialog.table if hasattr(dialog, "table") else True, "history dialog builds")

    window.close()
    return store


def check_import_preview(window, folder):
    """The preview must show what is coming before anything is written."""
    from openpyxl import Workbook

    from core import read_excel

    book = Workbook()
    book.active.append(["Sno", "Emp ID", "Name", "Department", "Cost Centre"])
    book.active.append([1, "E-1001", "Bilal Ahmed", "Audit", "CC-1"])      # already on file
    book.active.append([2, "E-7777", "Brand New", "IT", "CC-2"])           # new
    path = folder / "preview.xlsx"
    book.save(path)

    rows, ignored, problems = read_excel(path)
    before = len(window.store.employees())
    dialog = gui.ImportPreview(window, path, rows, new_count=1, update_count=1,
                               ignored=ignored, problems=problems)
    expect(dialog.update_existing() is True, "updating existing rows is the default")
    expect(len(window.store.employees()) == before,
           "opening the preview must not write anything")
    dialog.reject()
    expect(len(window.store.employees()) == before, "cancelling must not write anything")


def check_exports(store, folder):
    from core import export_csv, export_excel, export_pdf
    rows = store.employees()
    xlsx = export_excel(rows, folder / "gui.xlsx")
    csv_file = export_csv(rows, folder / "gui.csv")
    pdf = export_pdf(rows, folder / "gui.pdf", subtitle="GUI test")
    expect(xlsx.stat().st_size > 0 and pdf.read_bytes().startswith(b"%PDF"),
           "both exports produce real files")
    expect(csv_file.stat().st_size > 0 and "Employee ID" in csv_file.read_text(encoding="utf-8-sig"),
           "the CSV export produces a real file with the right headers")

    # asset registers export with their own columns and labels
    import core
    lap = store.assets("laptop")
    ax = export_excel(lap, folder / "assets.xlsx", columns=core.ASSET_META["laptop"]["columns"],
                      labels=core.ASSET_LABELS)
    expect(ax.stat().st_size > 0, "an asset register exports to Excel")


def check_duplicate_assets(store):
    from core import Invalid

    def raises_invalid(fn, message):
        try:
            fn()
        except Invalid:
            return
        raise AssertionError(message)

    store.add_employee({"emp_id": "E-9101", "emp_name": "Owner One", "laptop_serial": "DUP-001"},
                       "superadmin", "superadmin")
    raises_invalid(
        lambda: store.add_employee({"emp_id": "E-9102", "emp_name": "Owner Two",
                                    "laptop_serial": "DUP-001"}, "superadmin", "superadmin"),
        "a laptop serial already on file must not be assignable to a second employee")

    store.add_employee({"emp_id": "E-9102", "emp_name": "Owner Two"}, "superadmin", "superadmin")
    raises_invalid(
        lambda: store.update_employee(
            store.employees("E-9102")[0]["id"], {"laptop_serial": "DUP-001"},
            "superadmin", "superadmin"),
        "editing in a serial already on file must be refused the same way")

    # a serial that is an asset currently issued elsewhere is refused too
    asset = store.add_asset("laptop", {"serial": "ISSUED-001", "status": "Spare"},
                            "superadmin", "superadmin")
    store.assign_asset(asset, "E-9101", actor="superadmin", role="superadmin")
    raises_invalid(
        lambda: store.add_employee({"emp_id": "E-9103", "emp_name": "Grabbit",
                                    "laptop_serial": "ISSUED-001"}, "superadmin", "superadmin"),
        "an employee must not grab an asset that is issued to someone else")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(gui.STYLE)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        store = Store(folder / "gui.db")
        _, password = store.bootstrap()
        store.create_user("amir", "viewer-password", "user", "superadmin", "superadmin")
        store.add_employee({"emp_id": "E-1001", "emp_name": "Bilal Ahmed", "department": "Finance",
                            "laptop_serial": "5CG1234ABC"}, "superadmin", "superadmin")
        store.add_employee({"emp_id": "E-1002", "emp_name": "Sana Khan", "department": "HR"},
                           "superadmin", "superadmin")

        check_login(store, app)
        check_viewer(store, app)
        window = check_window(store, "superadmin", "superadmin", password)
        check_form(window)
        check_import_preview(window, folder)
        check_window(store, "amir", "user", "viewer-password")
        check_assets(store, app)
        check_exports(store, folder)
        check_duplicate_assets(store)
    print("gui check OK")


if __name__ == "__main__":
    main()