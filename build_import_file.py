"""Faithful per-sheet import of the three source files into the four registers.

Every sheet is read as-is - cells keep their exact text (no re-typing of
numbers, no case changes, no extra cleaning). Only the whitespace around a
value is trimmed, plus stray no-break spaces, which are whitespace, not data.
Where a spreadsheet leaves a required key blank (an Employee ID that reads
'Vendor' or nothing at all) the record still lands under a placeholder id and
the sheet's own cell text is noted in the Remarks field - nothing is dropped
and nothing is silently assumed.

Register mapping (each sheet goes where its own headers point):
  UPDATE.xlsx 'Laptop'            -> the Employees register (it is that sheet)
  UPDATE.xlsx 'Printer  Scanner'  -> the Printers register (assets only -
                                     no owner is known, so Current Owner is
                                     left empty until someone is assigned)
  UPDATE.xlsx 'IP Phone'          -> the IP Phones register, keeping the
                                     headless person-name column the old
                                     loader dropped (it stays on the asset as
                                     its model/type), and 'IP Existing' verbatim
  CHALLAN SHEET.xlsx              -> the Laptops register: every challan row.
                                     Serials matching an employee enrich that
                                     record; the rest arrive as stock laptops
  mobile.xls                      -> the Mobiles register (assets only - the
                                     phones are stock with no owner yet, so
                                     Current Owner stays empty). Its header row
                                     is a copied one that does not line up with
                                     the data, so the layout is taken from the
                                     rows themselves; the detail blob (serial,
                                     RAM/ROM, model) is kept whole

Usage:
  python build_import_file.py --check     # print the plan, touch nothing
  python build_import_file.py --rebuild   # backup, wipe, import, report
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from core import ASSET_COLUMNS, ASSET_META, COLUMNS, Store

HERE = Path(__file__).parent

# latest reads, so --rebuild reuses what --check reported
_BUILD: dict = {}


def _s(value) -> str:
    """A spreadsheet cell as text, verbatim. Whitespace around the value (and
    stray no-break spaces, which are whitespace) is trimmed; nothing else is."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\xa0", " ").strip()


def _xlsx_rows(name: str, sheet: str | None = None):
    from openpyxl import load_workbook
    book = load_workbook(HERE / name, data_only=True, read_only=True)
    try:
        ws = book[sheet] if sheet else book.active
        return list(ws.iter_rows(values_only=True))
    finally:
        book.close()


def _xls_rows():
    import xlrd
    book = xlrd.open_workbook(str(HERE / "mobile.xls"))
    try:
        sheet = book.sheet_by_index(0)
        return [sheet.row_values(i) for i in range(sheet.nrows)]
    finally:
        book.release_resources()


# ----------------------------------------------------------- UPDATE: Laptop

# The app's own employee headings, used by the sheet we already exchange.
LAPTOP_HEADERS = {
    "Emp ID": "emp_id", "Name": "emp_name", "IP Phone": "ip_phone",
    "Department": "department", "User ID": "user_id", "Host Name": "host_name",
    "Email Aik Address": "email", "Contact No": "contact_no",
    "Remarks": "remarks", "Location": "location", "Region": "region",
    "Laptop Serial Number": "laptop_serial", "Name & Type": "laptop_name_type",
}

NUMERIC_ID = re.compile(r"[0-9]+", re.IGNORECASE)


def read_laptop_sheet():
    """Every row verbatim. An Employee ID that is blank or not a plain number
    (the sheet uses 'Vendor' and 'Warmbyte') gets a NOID-<sno> key and the
    sheet's own text is kept in Remarks. Duplicate IDs are kept apart with
    -2, -3 suffixes - a second laptop for the same person is a second row, not
    an overwrite."""
    rows = _xlsx_rows("UPDATE.xlsx", "Laptop")
    mapping = {}
    for i, header in enumerate(rows[0]):
        field = LAPTOP_HEADERS.get(_s(header))
        if field:
            mapping[i] = field

    records, notes = [], []
    used: set[str] = set()
    for raw in rows[1:]:
        if not any(_s(c) for c in raw):
            continue
        emp = {}
        for i, field in mapping.items():
            if i < len(raw):
                emp[field] = _s(raw[i])
        sno = emp.pop("_row", "") or _s(raw[0])
        sheet_id = emp.get("emp_id") or ""
        if sheet_id and not NUMERIC_ID.fullmatch(sheet_id):
            note = (f"Employee ID on the sheet was '{sheet_id}' - not a number, "
                    "imported under a placeholder so nothing is lost")
            emp["emp_id"] = f"NOID-{sno}"
            emp["remarks"] = ((emp.get("remarks", "") + " " + note)).strip()
            notes.append({"sno": sno, "sheet_id": sheet_id})
        else:
            base = sheet_id or f"NOID-{sno}"
            if not sheet_id:
                emp["remarks"] = (emp.get("remarks", "") + " "
                                  "[sheet had no Employee ID]").strip()
                notes.append({"sno": sno, "sheet_id": ""})
            candidate, n = base, 1
            while candidate in used:
                n += 1
                candidate = f"{base}-{n}"
            emp["emp_id"] = candidate
            if candidate != base:
                emp["remarks"] = (emp.get("remarks", "") + " "
                                  f"[ID appears {n}x on the sheet - row kept as "
                                  f"{candidate}]").strip()
                notes.append({"sno": sno, "sheet_id": sheet_id,
                              "kept_as": candidate})
        used.add(emp["emp_id"])
        emp["_row"] = sno
        records.append(emp)
    return records, notes


# --------------------------------------------------- UPDATE: Printer  Scanner

def read_printer_sheet():
    """The printers/scanners register, assets only. The sheet names no owner,
    so no employee row is created and the asset stays unassigned."""
    rows = _xlsx_rows("UPDATE.xlsx", "Printer  Scanner")
    mapping = {}
    for i, header in enumerate(rows[0]):
        if _s(header) == "Printer Location":
            mapping[i] = "location"
        elif _s(header) == "Printer Model":
            mapping[i] = "name_type"
        elif _s(header) == "Serial Number":
            mapping[i] = "serial"

    assets = []
    for raw in rows[1:]:
        if not any(_s(c) for c in raw):
            continue
        a = {"kind": "printer"}
        for i, field in mapping.items():
            if i < len(raw):
                a[field] = _s(raw[i])
        if a.get("name_type") or a.get("serial"):
            assets.append(a)
    return assets


# ----------------------------------------------------------- UPDATE: IP Phone

def read_ip_sheet():
    """IP No, Department / Location, Mac No and IP Existing verbatim ('IP
    Existing' holds real LAN addresses in the sheet, so it is kept as-is, not
    forced into Yes/No). The headless column is the desk holder's name - it
    stays on the asset as its model/type, so nothing is dropped the way earlier
    imports dropped it. The holder is not an employee row of their own."""
    rows = _xlsx_rows("UPDATE.xlsx", "IP Phone")
    field_col: dict[str, int] = {}
    person_col = None
    for i, header in enumerate(rows[0]):
        h = _s(header)
        if h == "IP No":
            field_col["ip_no"] = i
        elif h == "Department / Location":
            field_col["ip_dept_location"] = i
        elif h == "Mac No":
            field_col["mac_no"] = i
        elif h == "IP Existing":
            field_col["ip_existing"] = i
        elif not h and person_col is None:
            person_col = i

    assets = []
    for raw in rows[1:]:
        if not any(_s(raw[i]) for i in list(field_col.values()) + [person_col]
                   if i is not None and i < len(raw)):
            continue
        a = {"kind": "ip_phone"}
        for field, i in field_col.items():
            if i is not None and i < len(raw):
                a[field] = _s(raw[i])
        person = _s(raw[person_col]) if person_col is not None else ""
        a["name_type"] = person                     # the desk holder
        assets.append(a)
    return assets


# -------------------------------------------------------------- mobile.xls

# Serial only when the sheet itself labels it: the whole token up to the next
# space (so 'Serial Number 61920/t5s904995 8GB\256' keeps '61920/t5s904995',
# not a truncated half). Everything else (RAM/ROM, model, an EAN) stays in the
# preserved whole-blob text.
_SERIAL_LABEL = re.compile(r"(?:Serial Number|S\\N|S/N)\s+(\S+)", re.IGNORECASE)

# Columns of mobile.xls that hold the real data (the header row is a copied
# one and does not line up): name, item kind, model, location, then in the
# trailing columns the stock date, quantities and the detail blob.
_MOBILE_COLS = {0: "name", 1: "kind", 2: "model", 3: "location",
                6: "stock_date", 8: "qty", 9: "qty2", 12: "units", 13: "blob"}


def read_mobile_sheet():
    """The mobiles register, assets only - handsets in stock, no owners known,
    so no employee rows are created. Serial picked up only when the detail blob
    itself labels one."""
    assets = []
    for raw in _xls_rows()[1:]:
        cells = {}
        for i, label in _MOBILE_COLS.items():
            if i < len(raw) and _s(raw[i]):
                cells[label] = _s(raw[i])
        name = cells.get("name", "")
        if not name:
            continue                                    # trailing blank line
        blob = cells.get("blob", "")
        found = _SERIAL_LABEL.search(blob)
        serial = found.group(1) if found else ""
        kept = " | ".join(f"{k}: {v}" for k, v in cells.items())
        asset = {
            "kind": "mobile",
            "name_type": name,
            "serial": serial,
            "notes": kept,
        }
        if not serial:
            asset["status"] = "Spare"      # no number to track it by -> a tag
        assets.append(asset)
    return assets


# ------------------------------------------------------------- CHALLAN sheet

CHALLAN_HEADERS = {
    "Delivery Dates": "delivery_date", "Name Vendor": "vendor",
    "Items Name": "name_type", "Item Spec": "spec", "Items Serial": "serial",
    "DC No": "dc_no", "PO No": "po_no", "Remarks": "notes",
}


def read_challan():
    rows = _xlsx_rows("CHALLAN SHEET.xlsx")
    mapping = {}
    for i, header in enumerate(rows[0]):
        field = CHALLAN_HEADERS.get(_s(header))
        if field:
            mapping[i] = field
    out = []
    for raw in rows[1:]:
        if not any(_s(c) for c in raw):
            continue
        row = {}
        for i, field in mapping.items():
            if i < len(raw):
                row[field] = _s(raw[i])
        if any(row.values()):
            out.append(row)
    return out


# ------------------------------------------------------------- plan builder

def _serial_key(value: str) -> str:
    return (value or "").strip().rstrip(" ;,.").lower()


def _plain_serial(value: str) -> str:
    """A serial as a single token - a trailing comma or semicolon in the source
    cell is a list separator, not part of the number."""
    return (value or "").strip().rstrip(" ;,.")


def records_for_import():
    """Read all three files once and work out the full import plan. Returns
    (clean, review, needs_id, stats); nothing here touches the database.

    Employees are ONLY the Laptop sheet's people. Printers, IP phones and the
    mobile stock are register assets; none of them name an owner, so Current
    Owner is left empty for them (assign them from the register later)."""
    laptop_emps, id_notes = read_laptop_sheet()
    printer_assets = read_printer_sheet()
    ip_assets = read_ip_sheet()
    mob_assets = read_mobile_sheet()
    challan = read_challan()

    by_serial = {}
    for emp in laptop_emps:
        key = _serial_key(emp.get("laptop_serial", ""))
        if key:
            by_serial.setdefault(key, emp)

    stock_assets: list[dict] = []
    stock_review: list[dict] = []
    challan_assets: list[dict] = []
    matched_serials: set[str] = set()
    for row in challan:
        key = _serial_key(row.get("serial", ""))
        owner = by_serial.get(key) if key else None
        # Every challan line is also a delivery record on the Challan register.
        ca = {"kind": "challan",
              "name_type": row.get("name_type", ""),
              "spec": row.get("spec", ""),
              "serial": _plain_serial(row.get("serial", "")),
              "vendor": row.get("vendor", ""),
              "delivery_date": row.get("delivery_date", ""),
              "dc_no": row.get("dc_no", ""),
              "po_no": row.get("po_no", ""),
              "notes": row.get("notes", ""),
              "status": "In use" if owner else "Spare"}
        challan_assets.append(ca)
        if owner:
            matched_serials.add(key)
            # challan is the vendor record for an owned laptop
            for src in ("vendor", "delivery_date", "dc_no", "po_no"):
                if row.get(src):
                    owner[src] = row[src]
            if row.get("spec") and not owner.get("laptop_spec"):
                owner["laptop_spec"] = row["spec"]
            if row.get("name_type") and not owner.get("laptop_name_type"):
                owner["laptop_name_type"] = row["name_type"]
            # reuse the exact employee spelling so the asset identity matches
            a = {"kind": "laptop", "serial": owner["laptop_serial"],
                 "vendor": row.get("vendor", ""),
                 "delivery_date": row.get("delivery_date", ""),
                 "dc_no": row.get("dc_no", ""),
                 "po_no": row.get("po_no", ""),
                 "notes": row.get("notes", "")}
            if not owner.get("laptop_spec"):
                a["spec"] = row.get("spec", "")
            if not owner.get("laptop_name_type"):
                a["name_type"] = row.get("name_type", "")
            stock_assets.append(a)
        else:
            a = {"kind": "laptop",
                 "name_type": row.get("name_type", ""),
                 "spec": row.get("spec", ""),
                 "serial": _plain_serial(row.get("serial", "")),
                 "vendor": row.get("vendor", ""),
                 "delivery_date": row.get("delivery_date", ""),
                 "dc_no": row.get("dc_no", ""),
                 "po_no": row.get("po_no", ""),
                 "notes": row.get("notes", "")}
            a["status"] = "Spare"                       # received, not issued
            stock_assets.append(a)
            stock_review.append(a)

    clean = laptop_emps
    review = stock_review
    needs_id = id_notes

    stats = {
        "clean": len(clean),
        "matched": len(matched_serials),
        "printers": len(printer_assets),
        "ip": len(ip_assets),
        "stock": len(mob_assets),
        "challan_rows": len(challan),
        "challan_stock": len(review),
        "challan": len(challan_assets),
        "mobiles": len(mob_assets),
    }
    _BUILD["clean"] = clean
    _BUILD["stock"] = stock_assets
    _BUILD["challan"] = challan_assets
    _BUILD["mobiles"] = mob_assets
    _BUILD["ip"] = ip_assets
    _BUILD["printers"] = printer_assets
    return clean, review, needs_id, stats


def to_store_records(clean):
    """The 'clean' list is already employee-shaped; hand it to bulk_import."""
    return list(clean)


def all_register_assets():
    """Laptops from the challan, the challan deliveries themselves, plus the
    printers, mobiles and IP phones, ready for the identity-keyed upsert."""
    out = list(_BUILD["stock"]) + list(_BUILD["challan"]) + list(_BUILD["printers"]) \
        + list(_BUILD["mobiles"]) + list(_BUILD["ip"])
    return out


# ------------------------------------------------------------------ rebuild

def rebuild(accounts: bool = True, backup: bool = True) -> tuple[dict, dict, dict]:
    """Wipe the working tables and rebuild every register from the sheets.
    Returns (stats, employees_result, assets_result)."""
    from core import default_db_path
    store = Store(default_db_path())
    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = store.path.with_name(store.path.stem + f".{stamp}.bak")
        shutil.copy2(store.path, backup_path)
        print(f"backup: {backup_path}")
    store.reset_registers(actor="system", role="superadmin", accounts=accounts)

    clean, review, ids, stats = records_for_import()
    emp_result = store.bulk_import(to_store_records(clean), actor="system",
                                   role="superadmin")

    store = Store(default_db_path())          # reopen: seeding builds registers
    asset_result = store.upsert_assets(all_register_assets(), actor="system",
                                       role="superadmin")
    challan_linked = store.link_challan_from_employees(actor="system",
                                                       role="superadmin")
    return stats, emp_result, asset_result, challan_linked


def report(stats, emp_result, asset_result, challan_linked: int, accounts: bool):
    print()
    print("Sources read verbatim:")
    print(f"  Employees sheet  : {stats['clean']} people")
    print(f"  Printers         : {stats['printers']} (assets - owner left empty)")
    print(f"  IP phones        : {stats['ip']} (incl. the headless name column)")
    print(f"  Mobiles          : {stats['stock']} from mobile.xls (assets -"
          " owner left empty)")
    print(f"  Challan          : {stats['challan_rows']} rows, "
          f"{stats['matched']} matched to an owned laptop, "
          f"{stats['challan_stock']} received-but-unassigned kept as stock")
    print()
    print("Employees written:")
    print(f"  added {emp_result['added']}  updated {emp_result['updated']}  "
          f"skipped {emp_result['skipped']}")
    for p in emp_result["problems"]:
        print(f"    ! {p}")
    print()
    print("Asset register enrichment / stock:")
    print(f"  added {asset_result['added']}  updated {asset_result['updated']}  "
          f"skipped {asset_result['skipped']}")
    for p in asset_result["problems"]:
        print(f"    ! {p}")
    print(f"  challan deliveries marked issued to their employee: {challan_linked}")
    store = Store()
    print()
    print("Now on file:")
    for row in store._asset_counts():
        print(f"  {row['label']:12} {row['total']:>3}  ({row['issued']} issued)")
    print(f"  Employees    {len(store.employees())}")
    if accounts:
        print()
        print("Accounts and audit reset as agreed - start the app once and it")
        print("prints the fresh superadmin username and password.")
    print()


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        clean, review, needs_id, stats = records_for_import()
        print(f"employees to import : {stats['clean']}")
        print(f"challan matches     : {stats['matched']} / {stats['challan_rows']}")
        print(f"printer rows        : {stats['printers']}")
        print(f"ip phone rows       : {stats['ip']}")
        print(f"mobile rows         : {stats['stock']}")
        print(f"stock laptops       : {stats['challan_stock']}")
        print(f"challan lines       : {stats['challan']}")
        print(f"id notes            : {len(needs_id)}")
        for n in needs_id:
            print(f"    {n}")
        for p in [x for x in clean if x.get("remarks", "").startswith("[")]:
            print("  remark:", p.get("_row"), p.get("emp_id"), p["remarks"][:70])
    elif "--rebuild" in sys.argv:
        s, e, a, ch = rebuild(accounts=("--keep-accounts" not in sys.argv))
        report(s, e, a, ch, accounts=("--keep-accounts" not in sys.argv))
    else:
        print(__doc__)