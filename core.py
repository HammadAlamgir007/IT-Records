"""IT Records - data layer: SQLite storage, accounts, audit trail and exports.

No GUI code lives here, so it can be tested on its own: python test_core.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import logging.handlers
import os
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- the entity

# (column, label, choices) - choices None means a plain text box.
# Everything except Employee ID is optional, so a record can be started with
# whatever is known today and completed later.
FIELDS = [
    ("sno", "SNO", None),
    ("emp_id", "Employee ID *", None),
    ("join_date", "Date of Joining", None),
    ("emp_name", "Full Name", None),
    ("designation", "Designation", None),
    ("department", "Department", None),
    ("user_id", "User ID", None),
    ("email", "Email Address", None),
    ("contact_no", "Contact No", None),
    ("ip_phone", "IP Phone", None),
    ("host_name", "Host Name", None),
    ("location", "Location", None),
    ("region", "Region", None),
    ("status", "Status", ["Active", "On leave", "Left"]),
    ("laptop_name_type", "Laptop Name & Type", None),
    ("laptop_serial", "Laptop Serial Number", None),
    ("laptop_spec", "Laptop Spec", None),
    ("mobile_name_type", "Mobile Name & Type", None),
    ("mobile_serial", "Mobile Serial Number", None),
    ("imei", "IMEI", None),
    ("sim_number", "SIM Number", None),
    ("vendor", "Vendor Name", None),
    ("delivery_date", "Delivery Date", None),
    ("dc_no", "DC No", None),
    ("po_no", "PO No", None),
    ("remarks", "Remarks", None),
    # Printer fields
    ("printer_location", "Printer Location", None),
    ("printer_model", "Printer Model", None),
    ("printer_serial", "Printer Serial Number", None),
    # IP / Network fields
    ("ip_no", "IP No", None),
    ("ip_dept_location", "IP Dept / Location", None),
    ("mac_no", "Mac No", None),
    ("ip_existing", "IP Existing", ["Yes", "No"]),
]

COLUMNS = [f[0] for f in FIELDS]
LABELS = {f[0]: f[1].removesuffix(" *") for f in FIELDS}
CHOICES = {f[0]: f[2] for f in FIELDS if f[2]}

# How the add/edit form is grouped on screen.
GROUPS = [
    ("Employee", ["sno", "emp_id", "join_date", "emp_name", "designation", "department", "user_id",
                  "email", "contact_no", "ip_phone", "host_name", "location", "region", "status"]),
    ("Laptop", ["laptop_name_type", "laptop_serial", "laptop_spec"]),
    ("Mobile", ["mobile_name_type", "mobile_serial", "imei", "sim_number"]),
    ("Vendor / Challan", ["vendor", "delivery_date", "dc_no", "po_no"]),
    ("Printer", ["printer_location", "printer_model", "printer_serial"]),
    ("IP / Network", ["ip_no", "ip_dept_location", "mac_no", "ip_existing"]),
    ("Notes", ["remarks"]),
]

# Two identities only. Anything not listed here is denied.
ROLES = {
    "user": "user - view and search only",
    "superadmin": "super admin - add, edit, delete, manage users, see logs and export",
}
RIGHTS = {
    "user": {"view"},
    "superadmin": {"view", "edit", "delete", "users", "logs", "export", "import"},
}
# "viewer" is the state before anyone signs in: the register is open read-only,
# exactly like a plain user account, so walking in and looking does not need a
# password. It is never stored in the users table.
RIGHTS["viewer"] = {"view"}

# ---------------------------------------------------------------- assets
#
# Laptops, mobiles, IP phones and printers/scanners are tracked in their own
# registers, completely separate from the employee sheet. One physical item is one
# row, keyed by the number that identifies it (serial, IMEI or MAC). When that is
# not known yet the app issues a tag (LAP-0001, MOB-0001, ...) so the item can
# still be tracked. Something with no serial cannot be followed through time.
#
# Every item carries its own ownership history in the assignments table: who held
# it, from which date to which date, recorded on every assign / transfer / release.
# Assigning an item to an employee also fills in that employee's matching fields
# (e.g. laptop serial) so the two sheets never disagree.

ASSET_META: dict[str, dict] = {
    "laptop": {
        "tab": "Laptops",
        "label": "Laptop",
        "entity": "laptop",
        "tag": "LAP",
        "fields": [
            ("name_type", "Model / Type", None),
            ("serial", "Serial Number", None),
            ("spec", "Specification", None),
            ("status", "Status", ["In use", "Spare", "Repair", "Retired"]),
            ("location", "Location", None),
            ("vendor", "Vendor", None),
            ("delivery_date", "Delivery Date", None),
            ("dc_no", "DC No", None),
            ("po_no", "PO No", None),
            ("notes", "Notes", None),
        ],
        # Asset field -> employee column. Assigning the asset writes these onto
        # the employee row; releasing clears them again (value for value, so a
        # manual entry that never matched is left alone).
        "sync": {"name_type": "laptop_name_type",
                 "serial": "laptop_serial",
                 "spec": "laptop_spec"},
        "columns": ["identity", "name_type", "spec", "status", "current_emp_name",
                    "vendor", "dc_no"],
    },
    "mobile": {
        "tab": "Mobiles",
        "label": "Mobile",
        "entity": "mobile",
        "tag": "MOB",
        "fields": [
            ("name_type", "Model / Type", None),
            ("serial", "Serial Number", None),
            ("imei", "IMEI", None),
            ("sim_number", "SIM Number", None),
            ("status", "Status", ["In use", "Spare", "Repair", "Retired"]),
            ("vendor", "Vendor", None),
            ("delivery_date", "Delivery Date", None),
            ("dc_no", "DC No", None),
            ("po_no", "PO No", None),
            ("notes", "Notes", None),
        ],
        "sync": {"name_type": "mobile_name_type",
                 "serial": "mobile_serial",
                 "imei": "imei",
                 "sim_number": "sim_number"},
        "columns": ["identity", "name_type", "sim_number", "status", "current_emp_name"],
    },
    "ip_phone": {
        "tab": "IP Phones",
        "label": "IP Phone",
        "entity": "IP phone",
        "tag": "IP",
        "fields": [
            ("name_type", "Model / Type", None),
            ("mac_no", "MAC Address", None),
            ("ip_no", "IP No", None),
            ("ip_dept_location", "Dept / Location", None),
            ("ip_existing", "IP Existing", ["Yes", "No"]),
            ("status", "Status", ["In use", "Spare", "Repair", "Retired"]),
            ("notes", "Notes", None),
        ],
        "sync": {"ip_no": "ip_no",
                 "ip_dept_location": "ip_dept_location",
                 "mac_no": "mac_no",
                 "ip_existing": "ip_existing"},
        "columns": ["identity", "name_type", "ip_no", "ip_dept_location", "ip_existing",
                    "status", "current_emp_name"],
    },
    "printer": {
        "tab": "Printers",
        "label": "Printer / Scanner",
        "entity": "printer",
        "tag": "PRN",
        "fields": [
            ("name_type", "Model", None),
            ("serial", "Serial Number", None),
            ("location", "Location", None),
            ("status", "Status", ["In use", "Spare", "Repair", "Retired"]),
            ("notes", "Notes", None),
        ],
        "sync": {"name_type": "printer_model",
                 "serial": "printer_serial",
                 "location": "printer_location"},
        "columns": ["identity", "name_type", "location", "status", "current_emp_name"],
    },
    # Delivery records straight off the CHALLAN sheet - one line per item a
    # vendor delivered. The machine itself lives in the Laptops register; the
    # "Assign" action books the item into Laptops (creating it when new) and
    # marks this line with the employee it was issued to. No field here is ever
    # pushed onto the employee - the Laptops register owns that.
    "challan": {
        "tab": "Challan",
        "label": "Challan",
        "entity": "challan",
        "tag": "CHL",
        "identity_label": "Challan ID",
        "fields": [
            ("delivery_date", "Delivery Date", None),
            ("vendor", "Vendor / Supplier", None),
            ("name_type", "Items Name", None),
            ("spec", "Item Spec", None),
            ("serial", "Items Serial", None),
            ("dc_no", "DC No", None),
            ("po_no", "PO No", None),
            ("status", "Status", ["In use", "Spare", "Repair", "Retired"]),
            ("notes", "Remarks", None),
        ],
        "sync": {},
        "columns": ["identity", "delivery_date", "vendor", "name_type", "spec",
                    "dc_no", "po_no", "status", "current_emp_name"],
    },
}

ASSET_KINDS = tuple(ASSET_META)  # ("laptop", "mobile", "ip_phone", "printer")

# Every column the assets table carries (besides kind and the audit stamps).
ASSET_COLUMNS = ["identity", "name_type", "spec", "serial", "imei", "sim_number",
                 "location", "ip_no", "ip_dept_location", "mac_no", "ip_existing",
                 "status", "vendor", "delivery_date", "dc_no", "po_no", "notes"]

ASSET_LABELS = {
    "identity": "Asset ID",
    "name_type": "Model / Type",
    "spec": "Specification",
    "serial": "Serial Number",
    "imei": "IMEI",
    "sim_number": "SIM Number",
    "location": "Location",
    "ip_no": "IP No",
    "ip_dept_location": "Dept / Location",
    "mac_no": "MAC Address",
    "ip_existing": "IP Existing",
    "status": "Status",
    "vendor": "Vendor",
    "delivery_date": "Delivery Date",
    "dc_no": "DC No",
    "po_no": "PO No",
    "notes": "Notes",
    "current_emp_name": "Current Owner",
}

def _names_conflict(a: str, b: str) -> bool:
    """True only when two names look like different people, not the same person
    typed two ways ('Hina Raza' vs 'Hina R.' share a real word and are not a
    conflict; 'Sohail Ahmed' vs 'Hamza Arif' share nothing and are)."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b or a == b or a in b or b in a:
        return False
    a_words = {w.strip(".") for w in a.split() if len(w.strip(".")) > 1}
    b_words = {w.strip(".") for w in b.split() if len(w.strip(".")) > 1}
    return not (a_words & b_words)


# Fields that identify one physical item. Two employees sharing a real serial
# number is almost always a typo, not two people using the same laptop, so these
# are kept unique (blank is always allowed - most employees are missing a device
# that has not been logged yet).
ASSET_FIELDS = ["laptop_serial", "mobile_serial", "imei", "printer_serial"]
# Which asset register each employee-side serial field belongs to, so an employee
# cannot grab a number that the asset register already shows as issued elsewhere.
FIELD_TO_KIND = {"laptop_serial": "laptop", "mobile_serial": "mobile",
                 "imei": "mobile", "printer_serial": "printer"}

MIN_PASSWORD = 8
_ITERATIONS = 210_000
_MAX_FAILS = 5
_LOCKOUT_SECONDS = 300

# The super admin login is a fixed, known value (change it here whenever this
# is no longer wanted). It is re-applied every time the database is opened, so
# the login never needs to be hunted for and an existing file picks up a change
# to this constant on the next launch.
SUPERADMIN_USER = "superadmin"
SUPERADMIN_PASSWORD = "admin"

# Organisation details for the letterhead printed at the top of each record
# document. Stored in the database so every PC sharing one database prints the
# same header; a super admin edits them from My Account.
COMPANY_FIELDS = ("name", "address", "city", "phone", "email")
COMPANY_DEFAULTS = {k: "" for k in COMPANY_FIELDS}


def default_db_path() -> Path:
    """%ITRECORDS_DB% if set, else ITRecords\\employees.db in the user's profile."""
    env = os.environ.get("ITRECORDS_DB")
    return Path(env) if env else Path.home() / "ITRecords" / "employees.db"


def setup_logging(log_dir: Path) -> logging.Logger:
    """Configure a rotating file logger for the application.
    Log file sits next to the database so it is easy to find.
    Returns the root 'itrecords' logger.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "it_records.log"
    logger = logging.getLogger("itrecords")
    for handler in list(logger.handlers):
        # Already pointed at this file: nothing to do. Pointed somewhere else
        # (a second Store, or a test's temp folder): close it first, or the old
        # file stays locked on Windows and the log goes to the wrong folder.
        if isinstance(handler, logging.FileHandler):
            if Path(handler.baseFilename) == log_path.resolve():
                return logger
            logger.removeHandler(handler)
            handler.close()
        else:
            logger.removeHandler(handler)
    logger.setLevel(logging.DEBUG)
    # Rotating: max 2 MB, keep 5 old files
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    # Also send WARNING+ to stderr so terminal users see critical messages
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(sh)
    logger.info("Logging started. Log file: %s", log_path)
    return logger


_log = logging.getLogger("itrecords")  # module-level shortcut


def _bundled_db() -> Path | None:
    """A YOUR-DATA\\employees.db travelling beside the program (the extracted
    folder, or the folder of the frozen exe)."""
    bases: list[Path] = []
    for attr in ("_MEIPASS", "_MEIPASS2"):
        value = getattr(sys, attr, "")
        if value:
            base = Path(value)
            bases.extend((base, base.parent))
    bases.append(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                 else Path(__file__).resolve().parent.parent)
    for base in bases:
        candidate = base / "YOUR-DATA" / "employees.db"
        if candidate.is_file():
            return candidate
    return None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_time(iso: str) -> str:
    """UTC in the database, local clock on screen."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d %b %Y  %H:%M:%S")
    except ValueError:
        return iso


class Denied(Exception):
    """Raised when the signed-in role may not do this."""


class Invalid(Exception):
    """Raised when the data is not acceptable - shown to the user as-is."""


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db_path()
        self._seed_from_bundle()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure logging is set up for this Store's directory
        setup_logging(self.path.parent)
        _log.info("Store opened: %s", self.path)
        self._fails: dict[str, tuple[int, float]] = {}
        with self._conn() as c:
            c.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {', '.join(f"{col} TEXT NOT NULL DEFAULT ''" for col in COLUMNS)},
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS employees_emp_id ON employees(emp_id);
"""
            )

            # Auto-migrate: add any missing columns to employees table
            cursor = c.execute("PRAGMA table_info(employees)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col in COLUMNS:
                if col not in existing_cols:
                    c.execute(f"ALTER TABLE employees ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

            c.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created TEXT NOT NULL,
                    last_login TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS users_name ON users(username);

                -- Append-only: nothing in this program updates or deletes a row here.
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS audit_at ON audit(at);

                -- The asset registers. One physical item, one row.
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    {', '.join(f"{col} TEXT NOT NULL DEFAULT ''" for col in ASSET_COLUMNS)},
                    current_emp_id TEXT NOT NULL DEFAULT '',
                    current_emp_name TEXT NOT NULL DEFAULT '',
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS assets_kind_identity
                    ON assets(kind, identity);

                -- Ownership history: one row per appointment of an asset to a person.
                -- released_on is '' while the person still holds it. Nothing here is
                -- deleted; a released row is how the past is remembered.
                CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    emp_id TEXT NOT NULL,
                    emp_name TEXT NOT NULL DEFAULT '',
                    assigned_on TEXT NOT NULL,
                    released_on TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT '',
                    at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assignments_asset ON assignments(asset_id);
                CREATE INDEX IF NOT EXISTS assignments_emp ON assignments(emp_id);

                -- Key/value app settings (organisation detail for the letterhead).
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );
                """
            )
        # Migration: add any columns that did not exist in an older database file.
        with self._conn() as c:
            existing_cols = {row[1] for row in c.execute("PRAGMA table_info(employees)")}
            for col in COLUMNS:
                if col not in existing_cols:
                    c.execute(f"ALTER TABLE employees ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

        self._backfill_sno()

        # Serials that already sit on employee records are brought into the asset
        # registers with that employee as the current owner, so the tabs are not
        # empty for data people were already keeping. This runs on every open and
        # only ever adds what is missing - an item already tracked is left alone,
        # so a run interrupted part-way simply finishes on the next open.
        self._seed_assets_from_employees()

        with self._conn() as c:
            # A database written by an older version may hold roles that no longer exist.
            # Drop those accounts to view-only rather than leave them holding rights
            # nobody can see in the list - a super admin can promote them again.
            stale = [r["username"] for r in
                     c.execute("SELECT username FROM users WHERE role NOT IN (?, ?)", tuple(ROLES))]
        for username in stale:
            with self._conn() as c:
                c.execute("UPDATE users SET role='user' WHERE username=?", (username,))
            self.log("system", "role", "user", username, "unknown role reset to user")

    def backup(self):
        import shutil
        import datetime
        if not self.path.exists():
            return
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / f"employees_{today}.db"
        if not backup_path.exists():
            try:
                shutil.copy2(self.path, backup_path)
                _log.info("Daily backup created: %s", backup_path)
            except Exception as exc:
                _log.error("Backup failed: %s", exc)

    def _seed_from_bundle(self) -> None:
        """First run on a fresh computer: the profile has no database yet, but a
        bundled copy (YOUR-DATA\\employees.db, shipped next to the program) has the
        real registers - bring it in so the app is never empty for someone who
        double-clicks the exe without running the setup script. Only seeds when
        nothing exists yet; an existing database is never touched."""
        if self.path.exists():
            return
        bundle = _bundled_db()
        if bundle is None:
            return
        if bundle.resolve() == self.path.resolve():
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(bundle.read_bytes())
        except OSError:
            pass

    @contextmanager
    def _conn(self):
        """Commits on success, rolls back on an error, and always closes.

        Leaving connections for the garbage collector keeps the file locked on
        Windows, which stops anyone copying the database for a backup.
        """
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            with c:
                yield c
        finally:
            c.close()

    # ------------------------------------------------------------ employees

    def employees(self, search: str = "") -> list[dict]:
        """Newest first. A search matches a substring of any field."""
        sql = "SELECT * FROM employees"
        args: list[str] = []
        if search.strip():
            sql += " WHERE " + " OR ".join(f"{c} LIKE ?" for c in COLUMNS)
            args = [f"%{search.strip()}%"] * len(COLUMNS)
        sql += " ORDER BY id DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def employee(self, row_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM employees WHERE id=?", (row_id,)).fetchone()
        return dict(row) if row else None

    def _duplicate_asset(self, data: dict, exclude_id: int | None = None) -> str | None:
        """A message describing the conflict if a serial/IMEI in `data` is already
        on someone else's record, else None. Blank values are never flagged."""
        with self._conn() as c:
            for field in ASSET_FIELDS:
                value = (data.get(field) or "").strip()
                if not value:
                    continue
                sql = f"SELECT emp_id, emp_name FROM employees WHERE {field}=? COLLATE NOCASE"
                args: list = [value]
                if exclude_id is not None:
                    sql += " AND id<>?"
                    args.append(exclude_id)
                row = c.execute(sql, args).fetchone()
                if row:
                    who = row["emp_name"] or row["emp_id"]
                    return f"{LABELS[field]} '{value}' is already on file for {who} ({row['emp_id']})"
                # The number may not be on an employee yet, but it might be the
                # identity of an asset that is currently issued to someone.
                kind_col = {"laptop_serial": "serial", "mobile_serial": "serial",
                            "imei": "imei", "printer_serial": "serial"}[field]
                held = c.execute(
                    "SELECT a.kind, a.identity, a.current_emp_id, a.current_emp_name "
                    "FROM assets a WHERE a.kind=?"
                    f" AND a.{kind_col}=? COLLATE NOCASE AND a.current_emp_id <> ''",
                    (FIELD_TO_KIND[field], value)).fetchone()
                if held and held["current_emp_id"] != (data.get("emp_id") or ""):
                    who = held["current_emp_name"] or held["current_emp_id"]
                    return (f"{LABELS[field]} '{value}' is an asset currently issued to "
                            f"{who} ({held['current_emp_id']}) - release or reassign it first")
        return None

    def _backfill_sno(self) -> None:
        """Give every employee a serial number.

        `sno` was added after the first databases were in use, so an ALTER TABLE
        left every existing row with an empty one - and an imported sheet without
        a Sno column does the same. Rows that already carry a number keep it (it
        is the number the department's own sheet uses); the blanks are filled in
        record order, continuing past the highest number already taken.
        """
        with self._conn() as c:
            blanks = [r["id"] for r in c.execute(
                "SELECT id FROM employees WHERE TRIM(sno)='' ORDER BY id")]
            if not blanks:
                return
            taken = {str(r["sno"]).strip() for r in c.execute(
                "SELECT sno FROM employees WHERE TRIM(sno)<>''")}
            nums = {int(t) for t in taken if t.isdigit()}
            nxt = max(nums, default=0) + 1
            for row_id in blanks:
                c.execute("UPDATE employees SET sno=? WHERE id=?", (str(nxt), row_id))
                nxt += 1
        _log.info("Filled in %d missing serial number(s)", len(blanks))

    def _next_sno(self, c) -> str:
        highest = c.execute("SELECT MAX(CAST(sno AS INTEGER)) FROM employees").fetchone()[0]
        return str((highest or 0) + 1)

    def add_employee(self, data: dict, actor: str, role: str) -> int:
        self._require(role, "edit")
        data = self._clean(data)
        conflict = self._duplicate_asset(data)
        if conflict:
            raise Invalid(conflict)
        stamp = now()
        with self._conn() as c:
            if not data.get("sno"):
                data["sno"] = self._next_sno(c)
            cols = list(data) + ["created", "updated", "created_by", "updated_by"]
            values = list(data.values()) + [stamp, stamp, actor, actor]
            try:
                cur = c.execute(
                    f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise Invalid(f"Employee ID {data['emp_id']} already exists") from exc
            row_id = cur.lastrowid
        self.log(actor, "add", "employee", data["emp_id"], self._describe(data))
        _log.info("Employee added: %s by %s", data["emp_id"], actor)
        return row_id

    def update_employee(self, row_id: int, data: dict, actor: str, role: str) -> None:
        self._require(role, "edit")
        before = self.employee(row_id)
        if not before:
            raise Invalid("That employee record no longer exists")
        data = self._clean(data)
        conflict = self._duplicate_asset(data, exclude_id=row_id)
        if conflict:
            raise Invalid(conflict)
        sets = ", ".join(f"{c}=?" for c in data) + ", updated=?, updated_by=?"
        with self._conn() as c:
            try:
                c.execute(
                    f"UPDATE employees SET {sets} WHERE id=?",
                    list(data.values()) + [now(), actor, row_id],
                )
            except sqlite3.IntegrityError as exc:
                raise Invalid(f"Employee ID {data['emp_id']} already exists") from exc
        changes = [
            f"{LABELS.get(k, k)}: '{before[k]}' -> '{v}'" for k, v in data.items()
            if k in before and before[k] != v
        ]
        changes_str = "; ".join(changes) if changes else "no field changed"
        self.log(actor, "edit", "employee", data["emp_id"], changes_str)
        _log.info("Employee updated: %s by %s -- %s", data["emp_id"], actor, changes_str)

    def delete_employee(self, row_id: int, actor: str, role: str) -> None:
        self._require(role, "delete")
        row = self.employee(row_id)
        if not row:
            raise Invalid("That employee record no longer exists")
        with self._conn() as c:
            c.execute("DELETE FROM employees WHERE id=?", (row_id,))
        # The record is gone; the fact that it existed and who removed it is not.
        self.log(actor, "delete", "employee", row["emp_id"],
                 self._describe({k: row[k] for k in COLUMNS}))
        _log.info("Employee deleted: %s by %s", row["emp_id"], actor)

    # -------------------------------------------------------------- assets

    @staticmethod
    def _kind(kind: str) -> dict:
        meta = ASSET_META.get(kind)
        if not meta:
            raise Invalid(f"Unknown asset kind: {kind}")
        return meta

    @staticmethod
    def _asset_identity(kind: str, data: dict) -> str:
        """The number that tracks one physical item. A mobile is keyed by its IMEI
        when one exists, else its serial; an IP phone by its MAC, else its IP."""
        if kind == "mobile":
            return (data.get("imei") or "").strip() or (data.get("serial") or "").strip()
        if kind == "ip_phone":
            return (data.get("mac_no") or "").strip() or (data.get("ip_no") or "").strip()
        return (data.get("serial") or "").strip()

    def _next_asset_tag(self, kind: str) -> str:
        prefix = ASSET_META[kind]["tag"]
        with self._conn() as c:
            used = {r[0] for r in c.execute("SELECT identity FROM assets")}
        n = 1
        while f"{prefix}-{n:04d}" in used:
            n += 1
        return f"{prefix}-{n:04d}"

    def assets(self, kind: str, search: str = "") -> list[dict]:
        """Newest first. Search reaches every field plus the current owner's name."""
        meta = self._kind(kind)
        cols = list(ASSET_COLUMNS) + ["current_emp_name", "current_emp_id"]
        sql = "SELECT * FROM assets WHERE kind=?"
        args: list = [kind]
        if search.strip():
            sql += " AND (" + " OR ".join(f"{c} LIKE ?" for c in cols) + ")"
            args += [f"%{search.strip()}%"] * len(cols)
        sql += " ORDER BY id DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def asset(self, asset_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return dict(row) if row else None

    def _asset_identity_conflict(self, kind: str, identity: str,
                                 exclude_id: int | None = None) -> str | None:
        """A message if an identity is already in use by another asset of the same
        kind - the same serial on two laptops is a typo, not two laptops."""
        if not identity:
            return None
        with self._conn() as c:
            sql = "SELECT id FROM assets WHERE kind=? AND identity=? COLLATE NOCASE"
            args: list = [kind, identity]
            if exclude_id is not None:
                sql += " AND id<>?"
                args.append(exclude_id)
            row = c.execute(sql, args).fetchone()
        if row:
            label = ("IMEI" if kind == "mobile" else "MAC" if kind == "ip_phone" else "Serial")
            return f"{label} '{identity}' is already on file for another {ASSET_META[kind]['label'].lower()}"
        return None

    def add_asset(self, kind: str, data: dict, actor: str, role: str) -> int:
        self._require(role, "edit")
        self._kind(kind)
        data = self._clean_asset(kind, data)
        if not data["identity"]:
            data["identity"] = self._next_asset_tag(kind)
        conflict = self._asset_identity_conflict(kind, data["identity"])
        if conflict:
            raise Invalid(conflict)
        stamp = now()
        cols = ["kind"] + list(data) + ["current_emp_id", "current_emp_name",
                                        "created", "updated", "created_by", "updated_by"]
        values = [kind] + list(data.values()) + ["", "", stamp, stamp, actor, actor]
        with self._conn() as c:
            try:
                cur = c.execute(
                    f"INSERT INTO assets ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    values)
            except sqlite3.IntegrityError as exc:
                raise Invalid(f"{data['identity']} already exists on file") from exc
        self.log(actor, "add", ASSET_META[kind]["entity"], data["identity"],
                 "; ".join(f"{ASSET_LABELS[k]}: {v}" for k, v in data.items() if v))
        return cur.lastrowid

    def update_asset(self, asset_id: int, data: dict, actor: str, role: str) -> None:
        self._require(role, "edit")
        before = self.asset(asset_id)
        if not before:
            raise Invalid("That asset record no longer exists")
        kind = before["kind"]
        # The caller submits whatever the form knows about; anything it leaves out
        # keeps its current value instead of being blanked out.
        merged = {c: before[c] for c in ASSET_COLUMNS}
        merged.update({k: str(v).strip() for k, v in data.items() if k in ASSET_COLUMNS})
        merged = self._clean_asset(kind, merged)
        merged["identity"] = merged["identity"] or before["identity"]
        if merged["identity"] != before["identity"]:
            conflict = self._asset_identity_conflict(kind, merged["identity"], exclude_id=asset_id)
            if conflict:
                raise Invalid(conflict)
        sets = ", ".join(f"{c}=?" for c in merged) + ", updated=?, updated_by=?"
        with self._conn() as c:
            c.execute(f"UPDATE assets SET {sets} WHERE id=?",
                      list(merged.values()) + [now(), actor, asset_id])
        changes = [
            f"{ASSET_LABELS.get(k, k)}: '{before[k]}' -> '{v}'"
            for k, v in merged.items() if before[k] != v
        ]
        self.log(actor, "edit", ASSET_META[kind]["entity"], merged["identity"],
                 "; ".join(changes) if changes else "no field changed")

    def delete_asset(self, asset_id: int, actor: str, role: str) -> None:
        self._require(role, "delete")
        row = self.asset(asset_id)
        if not row:
            raise Invalid("That asset record no longer exists")
        kind = row["kind"]
        if row["current_emp_id"]:
            # The item is leaving the register while issued - free that employee's
            # matching fields and close its history line so the past still reads.
            self._release_locked(row, note="asset record deleted", actor=actor, role=role)
        with self._conn() as c:
            c.execute("DELETE FROM assignments WHERE asset_id=?", (asset_id,))
            c.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        self.log(actor, "delete", ASSET_META[kind]["entity"], row["identity"],
                 "; ".join(f"{ASSET_LABELS[k]}: {v}" for k, v in row.items()
                           if k in ASSET_COLUMNS and v))

    @staticmethod
    def _clean_asset(kind: str, data: dict) -> dict:
        meta = ASSET_META[kind]
        statuses = next((f[2] for f in meta["fields"] if f[0] == "status"), [])
        out = {c: str(data.get(c) or "").strip() for c in ASSET_COLUMNS}
        out["status"] = out["status"] if out["status"] in statuses else "In use"
        derived = Store._asset_identity(kind, out)
        if derived:
            out["identity"] = derived
        if not out["identity"] and not out["name_type"]:
            raise Invalid(f"Give the {meta['label'].lower()} a model/type or a "
                          f"serial/IMEI/MAC number so it can be tracked")
        return out

    # -- assignment / release -------------------------------------------

    def assign_asset(self, asset_id: int, emp_id: str, note: str = "",
                     actor: str = "", role: str = "", start_date: str = "") -> str:
        """Give an asset to an employee, recording who held it before. Returns a
        short summary ('assigned to E-101' / 'handed over from E-99 to E-101').
        `start_date` dates the new assignment line (default: today)."""
        self._require(role, "edit")
        asset = self.asset(asset_id)
        if not asset:
            raise Invalid("That asset record no longer exists")
        kind = asset["kind"]
        with self._conn() as c:
            emp = c.execute("SELECT emp_id, emp_name FROM employees WHERE emp_id=?",
                            (emp_id,)).fetchone()
        if not emp:
            raise Invalid(f"No employee found with Employee ID '{emp_id}'")
        if asset["current_emp_id"] and asset["current_emp_id"] == emp_id:
            raise Invalid("This asset is already assigned to that employee")
        today = datetime.now().date().isoformat()
        start = (start_date or "").strip() or today

        if asset["current_emp_id"]:
            self._release_locked(asset, note="handed over", actor=actor, role=role)
            summary = f"handed over from {asset['current_emp_name'] or asset['current_emp_id']} to "
        else:
            summary = "assigned to "
        summary += f"{emp['emp_name'] or emp['emp_id']} ({emp['emp_id']})"

        with self._conn() as c:
            c.execute(
                "INSERT INTO assignments (asset_id, emp_id, emp_name, assigned_on, note, actor, at) "
                "VALUES (?,?,?,?,?,?,?)",
                (asset_id, emp["emp_id"], emp["emp_name"], start, note, actor, now()))
            # Someone holds it now, so it is in use - unless it is being tracked
            # as away for repair or retired, which the register should keep saying.
            c.execute("UPDATE assets SET current_emp_id=?, current_emp_name=?, "
                      "status=CASE WHEN status IN ('Repair', 'Retired') THEN status "
                      "ELSE 'In use' END, updated=?, updated_by=? WHERE id=?",
                      (emp["emp_id"], emp["emp_name"], now(), actor, asset_id))
            self._sync_employee(c, asset_id, emp["emp_id"])
        self.log(actor, "assign", ASSET_META[kind]["entity"], asset["identity"], summary)
        return summary

    def release_asset(self, asset_id: int, note: str = "",
                      actor: str = "", role: str = "") -> str:
        """Take an asset back - whoever held it is written off the register and the
        item goes back to available stock."""
        self._require(role, "edit")
        asset = self.asset(asset_id)
        if not asset:
            raise Invalid("That asset record no longer exists")
        if not asset["current_emp_id"]:
            raise Invalid("This asset is not currently assigned to anyone")
        who = asset["current_emp_name"] or asset["current_emp_id"]
        self._release_locked(asset, note=note, actor=actor, role=role)
        self.log(actor, "release", ASSET_META[asset["kind"]]["entity"], asset["identity"],
                 f"released from {who} ({asset['current_emp_id']})")
        return f"released from {who} ({asset['current_emp_id']})"

    def _release_locked(self, asset: dict, note: str, actor: str, role: str) -> None:
        """Inner half of a release: close the open assignment line and clear the
        employee's synced fields. Used by release_asset, assign_asset (for the old
        holder) and delete_asset."""
        kind = asset["kind"]
        today = datetime.now().date().isoformat()
        with self._conn() as c:
            c.execute("UPDATE assignments SET released_on=?, note=CASE WHEN note='' THEN ? ELSE note END "
                      "WHERE asset_id=? AND released_on=''",
                      (today, note, asset["id"]))
            # Nobody holds it any more, so it is back in stock. Repair and Retired
            # are deliberate states and are left alone.
            c.execute("UPDATE assets SET current_emp_id='', current_emp_name='', "
                      "status=CASE WHEN status='In use' THEN 'Spare' ELSE status END, "
                      "updated=?, updated_by=? WHERE id=?",
                      (now(), actor, asset["id"]))
            for asset_col, emp_col in ASSET_META[kind]["sync"].items():
                value = asset.get(asset_col, "")
                c.execute(
                    f"UPDATE employees SET {emp_col}=CASE WHEN {emp_col}=? THEN '' ELSE {emp_col} END, "
                    "updated=?, updated_by=? WHERE emp_id=?",
                    (value, now(), actor, asset["current_emp_id"]))
            # A laptop leaving service writes the matching challan delivery line
            # back to stock too, so the challan register never claims an item no
            # longer in use.
            if kind == "laptop" and (asset.get("serial") or "").strip():
                key = (asset["serial"] or "").strip().rstrip(" ;,.").lower()
                rows = [r["id"] for r in c.execute(
                    "SELECT id FROM assets WHERE kind='challan' AND current_emp_id=? "
                    "AND (LOWER(rtrim(ltrim(serial)))=? OR LOWER(identity)=?)",
                    (asset["current_emp_id"], key, key))]
                if rows:
                    c.execute(
                        "UPDATE assets SET current_emp_id='', current_emp_name='', "
                        "status='Spare', updated=?, updated_by=? "
                        "WHERE id IN ({})".format(",".join("?" * len(rows))),
                        [now(), actor] + rows)
                    c.execute(
                        "UPDATE assignments SET released_on=? "
                        "WHERE asset_id IN ({}) AND released_on=''".format(
                            ",".join("?" * len(rows))),
                        [today] + rows)

    def issue_challan(self, challan_id: int, emp_id: str, note: str = "",
                      actor: str = "", role: str = "", start_date: str = "") -> str:
        """Book a challan delivery out to an employee. The machine is put into the
        Laptops register (created from the delivery line when it is not there yet)
        and this challan line is marked with the same employee, so the two
        registers always agree on who holds a delivered item."""
        self._require(role, "edit")
        challan = self.asset(challan_id)
        if not challan or challan["kind"] != "challan":
            raise Invalid("That challan line no longer exists")
        with self._conn() as c:
            emp = c.execute("SELECT emp_id, emp_name FROM employees WHERE emp_id=?",
                            (emp_id,)).fetchone()
        if not emp:
            raise Invalid(f"No employee found with Employee ID '{emp_id}'")
        if challan["current_emp_id"] == emp_id:
            raise Invalid("This challan line is already assigned to that employee")

        key = (challan.get("serial") or challan.get("identity") or "").strip().rstrip(" ;,.").lower()
        laptop = None
        if key:
            with self._conn() as c:
                row = c.execute(
                    "SELECT * FROM assets WHERE kind='laptop' "
                    "AND (LOWER(rtrim(ltrim(serial)))=? OR LOWER(identity)=?)",
                    (key, key)).fetchone()
                laptop = dict(row) if row else None

        if laptop is None:
            data = {col: challan.get(col, "") for col in ASSET_COLUMNS}
            data["status"] = "In use"
            laptop_id = self.add_asset("laptop", data, actor, role)
            laptop = self.asset(laptop_id)
        if not laptop["current_emp_id"] or laptop["current_emp_id"] != emp_id:
            self.assign_asset(laptop["id"], emp_id,
                              note=note or "issued from a challan line",
                              actor=actor, role=role, start_date=start_date)

        return self.assign_asset(challan_id, emp_id, note=note,
                                 actor=actor, role=role, start_date=start_date)

    def link_challan_from_employees(self, actor: str = "", role: str = "") -> int:
        """After a rebuild, challan deliveries whose serial matches an employee's
        laptop are marked issued to that employee - the machine was delivered and
        is in use, so the challan register should say so instead of listing it as
        spare stock. Runs only for lines that still have no owner."""
        self._require(role, "import")
        with self._conn() as c:
            serials: dict[str, tuple[str, str]] = {}
            for e in c.execute("SELECT emp_id, emp_name, laptop_serial FROM employees"):
                key = (e["laptop_serial"] or "").strip().rstrip(" ;,.").lower()
                if key:
                    serials.setdefault(key, (e["emp_id"], e["emp_name"]))
            rows = [dict(r) for r in c.execute("SELECT * FROM assets WHERE kind='challan'")]
            stamp = now()
            count = 0
            for a in rows:
                if a["current_emp_id"]:
                    continue
                key = (a.get("serial") or "").strip().rstrip(" ;,.").lower()
                owner = serials.get(key)
                if not owner:
                    continue
                emp_id, emp_name = owner
                c.execute(
                    "UPDATE assets SET current_emp_id=?, current_emp_name=?, status='In use', "
                    "updated=?, updated_by=? WHERE id=?",
                    (emp_id, emp_name, stamp, actor, a["id"]))
                assigned_on = (a.get("delivery_date") or "").strip()[:10] or \
                    datetime.now().date().isoformat()
                c.execute(
                    "INSERT INTO assignments (asset_id, emp_id, emp_name, assigned_on, "
                    "note, actor, at) VALUES (?,?,?,?,'challan delivery',?,?)",
                    (a["id"], emp_id, emp_name, assigned_on, actor, stamp))
                count += 1
        if count:
            self.log(actor, "import", "challan", "",
                     f"{count} delivered items marked issued to their employee")
        return count

    def _sync_employee(self, c, asset_id: int, emp_id: str) -> None:
        """Push the asset's identity-describing fields onto the employee who has it."""
        asset = c.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        kind = asset["kind"]
        sets = []
        values: list = []
        for asset_col, emp_col in ASSET_META[kind]["sync"].items():
            if asset[asset_col] != "":
                sets.append(f"{emp_col}=?")
                values.append(asset[asset_col])
        sets.append("updated=?")
        values.append(now())
        c.execute(f"UPDATE employees SET {', '.join(sets)} WHERE emp_id=?",
                  values + [emp_id])

    # -- history ---------------------------------------------------------

    def asset_history(self, asset: dict) -> list[dict]:
        """Every time this item changed hands, oldest first. An unbroken line (no
        released date) is the present owner."""
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM assignments WHERE asset_id=? ORDER BY id", (asset["id"],))]

    def employee_assets(self, emp_id: str) -> list[dict]:
        """Everything ever issued to one person across all four registers."""
        meta_label = {k: v["label"] for k, v in ASSET_META.items()}
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT x.*, a.kind, a.identity AS asset_identity "
                "FROM assignments x JOIN assets a ON a.id=x.asset_id "
                "WHERE x.emp_id=? ORDER BY x.assigned_on DESC, x.id DESC", (emp_id,))]
        for row in rows:
            row["kind_label"] = meta_label.get(row["kind"], row["kind"])
        return rows

    def _seed_assets_from_employees(self) -> None:
        """Bring serials/IMEIs/MACs already typed into employee records into the
        asset registers, with that employee as the current owner. Always runs, but
        only ever adds what is missing - an item whose identity is already in its
        register is left alone, so re-opening can never duplicate anything."""
        with self._conn() as c:
            emps = [dict(r) for r in c.execute("SELECT * FROM employees")]
            used = {kind: {r[0] for r in c.execute(
                "SELECT identity FROM assets WHERE kind=?", (kind,))}
                for kind in ASSET_KINDS}

        pending: list = []                      # (kind, data, emp_id, emp_name, stamp)
        for emp in emps:
            base = {k: emp[k] for k in ("vendor", "delivery_date", "dc_no", "po_no")}
            stamp = (emp["updated"] or emp["created"] or "")[:10] or datetime.now().date().isoformat()
            seeds = []
            if (emp.get("laptop_serial") or "").strip():
                seeds.append(("laptop", {"name_type": emp["laptop_name_type"],
                                         "serial": emp["laptop_serial"],
                                         "spec": emp["laptop_spec"], **base}))
            if (emp.get("mobile_serial") or "").strip() or (emp.get("imei") or "").strip():
                seeds.append(("mobile", {"name_type": emp["mobile_name_type"],
                                         "serial": emp["mobile_serial"],
                                         "imei": emp["imei"],
                                         "sim_number": emp["sim_number"], **base}))
            if (emp.get("printer_serial") or "").strip():
                seeds.append(("printer", {"name_type": emp["printer_model"],
                                          "serial": emp["printer_serial"],
                                          "location": emp["printer_location"]}))
            if (emp.get("ip_no") or "").strip() or (emp.get("mac_no") or "").strip():
                seeds.append(("ip_phone", {"name_type": emp["host_name"],
                                           "ip_no": emp["ip_no"],
                                           "ip_dept_location": emp["ip_dept_location"],
                                           "mac_no": emp["mac_no"],
                                           "ip_existing": emp["ip_existing"]}))
            for kind, data in seeds:
                try:
                    data = self._clean_asset(kind, data)
                except Invalid:
                    continue
                identity = data["identity"]
                if not identity:
                    prefix = ASSET_META[kind]["tag"]
                    n = 1
                    while f"{prefix}-{n:04d}" in used[kind]:
                        n += 1
                    identity = f"{prefix}-{n:04d}"
                if identity in used[kind]:
                    continue
                used[kind].add(identity)
                data["identity"] = identity
                pending.append((kind, data, emp["emp_id"], emp["emp_name"], stamp))

        if not pending:
            return
        # One transaction for every row gathered above.
        with self._conn() as c:
            for kind, data, emp_id, emp_name, stamp in pending:
                cols = ["kind"] + list(data) + ["current_emp_id", "current_emp_name",
                                                "created", "updated", "created_by", "updated_by"]
                values = [kind] + list(data.values()) + [emp_id, emp_name, now(), now(),
                                                         "system", "system"]
                cur = c.execute(
                    f"INSERT INTO assets ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    values)
                c.execute(
                    "INSERT INTO assignments (asset_id, emp_id, emp_name, assigned_on, note, actor, at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (cur.lastrowid, emp_id, emp_name, stamp,
                     "imported from employee record", "system", now()))
        self.log("system", "seed", "asset", "", f"created {len(pending)} asset record(s) "
                                                "from existing employee records")

    def bulk_import(self, rows: list[dict], update_existing: bool = True,
                    actor: str = "", role: str = "") -> dict:
        """
        Batch equivalent of import_rows: every add/update happens inside ONE
        transaction instead of one connection per row, and the duplicate/issued
        checks are answered from in-memory indexes rather than a query each, so
        importing a whole source file is a single fast pass.
        """
        self._require(role, "import")
        serial_fields = ("laptop_serial", "mobile_serial", "imei", "printer_serial")
        kind_col = {"laptop_serial": ("laptop", "serial"), "mobile_serial": ("mobile", "serial"),
                    "imei": ("mobile", "imei"), "printer_serial": ("printer", "serial")}
        result = {"added": 0, "updated": 0, "skipped": 0, "problems": []}

        with self._conn() as c:
            existing = {r["emp_id"]: dict(r) for r in c.execute("SELECT * FROM employees")}
            by_field = {f: {} for f in serial_fields}
            for r in existing.values():
                for f in serial_fields:
                    value = (r.get(f) or "").strip().lower()
                    if value and value not in by_field[f]:
                        by_field[f][value] = (r["emp_id"], r["emp_name"] or "")
            issued = {}
            for kind, col in set(kind_col.values()):
                key = f"{kind}::{col}"
                for a in c.execute("SELECT * FROM assets WHERE kind=? AND current_emp_id<>''", (kind,)):
                    value = (a[col] or "").strip().lower()
                    if value:
                        issued.setdefault(key, {})[value] = (a["current_emp_id"],
                                                             a["current_emp_name"] or "")

        stamp = now()
        audit_rows: list = []
        with self._conn() as c:
            next_sno = self._next_sno(c)
            for row in rows:
                record = {k: str(v).strip() for k, v in row.items() if k in COLUMNS}
                where = f"Row {row.get('_row', '?')}"
                emp_id = record.get("emp_id", "")
                current = existing.get(emp_id)
                if current is None:
                    current = None
                conflict = None
                for f in serial_fields:
                    value = record.get(f) or ""
                    if not value:
                        continue
                    holder = by_field[f].get(value.lower())
                    if holder and not (current and current["emp_id"] == holder[0]):
                        conflict = (f"{LABELS[f]} '{value}' is already on file for "
                                    f"{holder[1] or holder[0]} ({holder[0]})")
                        break
                    keeper = (issued.get(f"{kind_col[f][0]}::{kind_col[f][1]}") or {}).get(value.lower())
                    if keeper and keeper[0] != emp_id:
                        who = keeper[1] or keeper[0]
                        conflict = (f"{LABELS[f]} '{value}' is an asset currently issued to "
                                    f"{who} ({keeper[0]}) - release or reassign it first")
                        break
                if conflict:
                    result["skipped"] += 1
                    result["problems"].append(f"{where}: {conflict}")
                    continue
                try:
                    if current is None:
                        data = self._clean(record)
                        if not data.get("sno"):
                            data["sno"] = next_sno
                            next_sno = str(int(next_sno) + 1)
                        cols = list(data) + ["created", "updated", "created_by", "updated_by"]
                        values = list(data.values()) + [stamp, stamp, actor, actor]
                        try:
                            cur = c.execute(
                                f"INSERT INTO employees ({','.join(cols)}) "
                                f"VALUES ({','.join('?' * len(cols))})", values)
                        except sqlite3.IntegrityError as exc:
                            raise Invalid(f"Employee ID {data['emp_id']} already exists") from exc
                        new = data | {"id": cur.lastrowid}
                        existing[data["emp_id"]] = new
                        for f in serial_fields:                  # a later row must see it
                            value = (data.get(f) or "").strip().lower()
                            if value and value not in by_field[f]:
                                by_field[f][value] = (new["emp_id"], new["emp_name"] or "")
                        audit_rows.append((actor, "add", "employee", data["emp_id"],
                                           self._describe(data)))
                        result["added"] += 1
                    elif update_existing:
                        incoming_name = (record.get("emp_name") or "").strip()
                        existing_name = (current["emp_name"] or "").strip()
                        if incoming_name and existing_name and _names_conflict(incoming_name,
                                                                               existing_name):
                            result["skipped"] += 1
                            result["problems"].append(
                                f"{where}: Employee ID {emp_id} already belongs to "
                                f"'{existing_name}' - this row says '{incoming_name}'. "
                                "Skipped - fix the ID or the name and import again.")
                            continue
                        merged = {k: (record.get(k) or current[k]) for k in COLUMNS}
                        sets = ", ".join(f"{k}=?" for k in merged) + ", updated=?, updated_by=?"
                        c.execute(f"UPDATE employees SET {sets} WHERE id=?",
                                  list(merged.values()) + [stamp, actor, current["id"]])
                        for f in serial_fields:
                            value = (merged.get(f) or "").strip().lower()
                            if value:
                                by_field[f][value] = (current["emp_id"],
                                                      merged["emp_name"] or current["emp_name"] or "")
                        changes = [f"{LABELS[k]}: '{current[k]}' -> '{v}'"
                                   for k, v in merged.items() if current[k] != v]
                        audit_rows.append((actor, "edit", "employee", emp_id,
                                           "; ".join(changes) if changes else "no field changed"))
                        existing[emp_id] = current | merged
                        result["updated"] += 1
                    else:
                        result["skipped"] += 1
                except (Invalid, Denied) as exc:
                    result["skipped"] += 1
                    result["problems"].append(f"{where}: {exc}")

            for entry in audit_rows:
                c.execute(
                    "INSERT INTO audit (at, actor, action, entity, entity_id, detail) "
                    "VALUES (?,?,?,?,?,?)", (stamp, *entry))
        return result

    def reset_registers(self, actor: str = "", role: str = "",
                        accounts: bool = False) -> None:
        """Empty the working tables so they can be rebuilt from source files.

        Registers alone by default; pass accounts=True to also clear the users
        and audit tables (a fresh way in is then created by bootstrap() on the
        next launch, which hands back a new superadmin password once).
        """
        self._require(role, "import")
        with self._conn() as c:
            c.execute("DELETE FROM assignments")
            c.execute("DELETE FROM assets")
            c.execute("DELETE FROM employees")
            if accounts:
                c.execute("DELETE FROM users")
                c.execute("DELETE FROM audit")
        self.log(actor, "reset", "register", "",
                 "employees, assets and assignments cleared"
                 + ("; accounts and audit cleared too" if accounts else ""))

    def upsert_assets(self, rows: list[dict], actor: str = "", role: str = "") -> dict:
        """Batch write of asset-register rows, keyed by identity within its kind.

        A serial/MAC/IMEI already on file updates that row and nothing else is
        touched; a new identity is added. Items with no identifying number are
        issued the next tag (LAP-0001...). Ownership, stamps and creator are
        never overwritten - an incoming value fills a blank or refreshes what
        the source file knows, and an incoming blank leaves the row alone. All
        of it happens in one transaction, like bulk_import does for employees.
        """
        self._require(role, "import")
        result = {"added": 0, "updated": 0, "skipped": 0, "problems": []}
        stamp = now()
        with self._conn() as c:
            existing = {kind: {r["identity"]: dict(r) for r in
                               c.execute("SELECT * FROM assets WHERE kind=?", (kind,))}
                        for kind in ASSET_KINDS}
            audit: list = []
            for n, item in enumerate(rows, start=1):
                where = f"Row {n}"
                kind = item.get("kind")
                if kind not in ASSET_META:
                    result["skipped"] += 1
                    result["problems"].append(f"{where}: unknown asset kind {kind!r}")
                    continue
                try:
                    data = self._clean_asset(
                        kind, {col: str(v).strip() for col, v in item.items()
                               if col in ASSET_COLUMNS and (v is not None and str(v).strip())})
                except Invalid as exc:
                    result["skipped"] += 1
                    result["problems"].append(f"{where}: {exc}")
                    continue
                identity = data["identity"]
                if not identity:
                    prefix = ASSET_META[kind]["tag"]
                    i = 1
                    while f"{prefix}-{i:04d}" in existing[kind]:
                        i += 1
                    identity = f"{prefix}-{i:04d}"
                    data["identity"] = identity
                before = existing[kind].get(identity)
                if before is None:
                    cols = ["kind"] + list(data) + ["current_emp_id", "current_emp_name",
                                                    "created", "updated", "created_by", "updated_by"]
                    values = [kind] + list(data.values()) + ["", "", stamp, stamp, actor, actor]
                    try:
                        cur = c.execute(
                            f"INSERT INTO assets ({','.join(cols)}) "
                            f"VALUES ({','.join('?' * len(cols))})", values)
                    except sqlite3.IntegrityError:
                        result["skipped"] += 1
                        result["problems"].append(f"{where}: {identity} already on file")
                        continue
                    existing[kind][identity] = (data | {"id": cur.lastrowid,
                                                        "current_emp_id": "",
                                                        "current_emp_name": ""})
                    audit.append((actor, "add", ASSET_META[kind]["entity"], identity,
                                  "; ".join(f"{ASSET_LABELS[k]}: {v}" for k, v in data.items() if v)))
                    result["added"] += 1
                else:
                    merged = dict(before)
                    for col in ASSET_COLUMNS:
                        if data.get(col):
                            merged[col] = data[col]
                    sets = ", ".join(f"{col}=?" for col in ASSET_COLUMNS) + \
                        ", updated=?, updated_by=?"
                    c.execute(f"UPDATE assets SET {sets} WHERE id=?",
                              [merged[col] for col in ASSET_COLUMNS] + [stamp, actor, before["id"]])
                    changes = [f"{ASSET_LABELS.get(k, k)}: '{before[k]}' -> '{v}'"
                               for k, v in merged.items() if before[k] != v]
                    audit.append((actor, "edit", ASSET_META[kind]["entity"], identity,
                                  "; ".join(changes) if changes else "no field changed"))
                    result["updated"] += 1

            for entry in audit:
                c.execute(
                    "INSERT INTO audit (at, actor, action, entity, entity_id, detail) "
                    "VALUES (?,?,?,?,?,?)", (stamp, *entry))
        return result

    def import_rows(self, rows: list[dict], actor: str, role: str,
                    update_existing: bool = True) -> dict:
        """Adds every row from a spreadsheet. A row whose Employee ID is already on file
        updates that record when update_existing is set, otherwise it is left alone.

        One bad row does not stop the rest: each is reported instead.
        """
        result = self.bulk_import(rows, update_existing=update_existing, actor=actor, role=role)
        self.log(actor, "import", "employee", "",
                 f"{result['added']} added, {result['updated']} updated, "
                 f"{result['skipped']} skipped")
        return result

    @staticmethod
    def _clean(data: dict) -> dict:
        out = {c: str(data.get(c, "") or "").strip() for c in COLUMNS}
        if not out["emp_id"]:
            raise Invalid("Employee ID is required")
        # Auto-generated placeholders (UNASSIGNED-xxx) are allowed through;
        # a super admin can edit them later to assign a real ID.
        return out

    @staticmethod
    def _describe(data: dict) -> str:
        return "; ".join(f"{LABELS[k]}: {v}" for k, v in data.items() if v)

    # ---------------------------------------------------------- organisation

    def company(self) -> dict:
        """Organisation details for the record documents' letterhead. Missing
        fields fall back to blanks, so a fresh database still prints."""
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", ("company",)).fetchone()
        stored = {}
        if row and row["value"]:
            try:
                stored = json.loads(row["value"])
            except ValueError:
                stored = {}
        return {k: str(stored.get(k, COMPANY_DEFAULTS[k]) or "") for k in COMPANY_FIELDS}

    def save_company(self, data: dict, actor: str = "", role: str = "") -> dict:
        """Persist the letterhead organisation detail (a super-admin action)."""
        self._require(role, "users")
        clean = {k: str(data.get(k, "") or "").strip()[:200] for k in COMPANY_FIELDS}
        if not clean["name"]:
            raise Invalid("Give the organisation a name - it is the letterhead title.")
        with self._conn() as c:
            c.execute(
                "INSERT INTO settings(key, value) VALUES('company', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(clean),))
        self.log(actor, "setting", "company", "",
                 f"organisation detail updated ({clean['name']})")
        return clean

    # ----------------------------------------------------------- accounts

    def has_users(self) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def bootstrap(self) -> tuple[str, str] | None:
        """
        Make sure the database has a way in, and return (user, password) when one was
        just made. Covers the empty database and the database whose only super admin
        was deleted or downgraded - otherwise nobody could ever sign in again.
        """
        with self._conn() as c:
            row = c.execute("SELECT hash FROM users WHERE username=? AND role='superadmin'",
                            (SUPERADMIN_USER,)).fetchone()
        if row is not None:
            # The password is a hardcoded constant, so an account left over from an
            # older build (or one whose password was changed) is put back on it.
            if verify_password(SUPERADMIN_PASSWORD, row["hash"]):
                return None
            with self._conn() as c:
                c.execute("UPDATE users SET hash=? WHERE username=?",
                          (hash_password(SUPERADMIN_PASSWORD), SUPERADMIN_USER))
            self.log("system", "password", "user", SUPERADMIN_USER, "reset to the fixed password")
            return None
        with self._conn() as c:
            has_boss = c.execute(
                "SELECT 1 FROM users WHERE role='superadmin' LIMIT 1").fetchone() is not None
        if has_boss:
            return None
        return self.reset_superadmin(SUPERADMIN_PASSWORD)

    def create_user(self, username: str, password: str, role: str, actor: str, actor_role: str) -> None:
        self._require(actor_role, "users")
        self._insert_user(username, password, role, actor)

    def _insert_user(self, username: str, password: str, role: str, actor: str) -> None:
        username = username.strip().lower()
        if not username:
            raise Invalid("Username is required")
        if role not in ROLES:
            raise Invalid(f"Role must be one of: {', '.join(ROLES)}")
        if len(password) < MIN_PASSWORD:
            raise Invalid(f"Password must be at least {MIN_PASSWORD} characters")
        with self._conn() as c:
            try:
                c.execute(
                    "INSERT INTO users (username, hash, role, created) VALUES (?,?,?,?)",
                    (username, hash_password(password), role, now()),
                )
            except sqlite3.IntegrityError as exc:
                raise Invalid(f"User {username} already exists") from exc
        self.log(actor, "add", "user", username, f"role: {role}")

    def users(self, actor_role: str) -> list[dict]:
        self._require(actor_role, "users")
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT username, role, created, last_login FROM users ORDER BY username")]

    def set_password(self, username: str, password: str, actor: str, actor_role: str) -> None:
        """Anyone may change their own password; only a super admin may change someone else's."""
        username = username.strip().lower()
        if username != actor and "users" not in RIGHTS.get(actor_role, set()):
            raise Denied("Only a super admin can change another user's password")
        if len(password) < MIN_PASSWORD:
            raise Invalid(f"Password must be at least {MIN_PASSWORD} characters")
        with self._conn() as c:
            changed = c.execute("UPDATE users SET hash=? WHERE username=?",
                                (hash_password(password), username)).rowcount
        if not changed:
            raise Invalid(f"No user called {username}")
        self.log(actor, "password", "user", username, "password changed")

    def delete_user(self, username: str, actor: str, actor_role: str) -> None:
        self._require(actor_role, "users")
        username = username.strip().lower()
        if username == actor:
            raise Invalid("You cannot delete the account you are signed in with")
        with self._conn() as c:
            remaining = c.execute(
                "SELECT COUNT(*) FROM users WHERE role='superadmin' AND username<>?", (username,)
            ).fetchone()[0]
            if remaining == 0:
                raise Invalid("This is the last super admin - make another one first")
            if not c.execute("DELETE FROM users WHERE username=?", (username,)).rowcount:
                raise Invalid(f"No user called {username}")
        self.log(actor, "delete", "user", username, "account removed")

    def login(self, username: str, password: str) -> str:
        """Returns the role on success. Raises Invalid otherwise."""
        username = username.strip().lower()
        fails, until = self._fails.get(username, (0, 0.0))
        if fails >= _MAX_FAILS and time.time() < until:
            self.log(username, "login-blocked", "user", username, "locked out")
            _log.warning("Login blocked (lockout): user='%s'", username)
            raise Invalid("Too many failed attempts. Try again in a few minutes.")

        with self._conn() as c:
            row = c.execute("SELECT hash, role FROM users WHERE username=?", (username,)).fetchone()
        # Verify even for an unknown user so both answers take the same time.
        stored = row["hash"] if row else hash_password("no-such-user")
        if not verify_password(password, stored) or row is None:
            count = fails + 1 if time.time() < until else 1
            self._fails[username] = (count, time.time() + _LOCKOUT_SECONDS)
            self.log(username, "login-failed", "user", username, f"attempt {count}")
            _log.warning("Login failed: user='%s' attempt=%d", username, count)
            raise Invalid("Wrong username or password")

        self._fails.pop(username, None)
        with self._conn() as c:
            c.execute("UPDATE users SET last_login=? WHERE username=?", (now(), username))
        self.log(username, "login", "user", username, "signed in")
        _log.info("Login successful: user='%s' role='%s'", username, row["role"])
        return row["role"]

    def reset_superadmin(self, password: str | None = None) -> tuple[str, str]:
        """Recovery from the command line when the super admin password is lost."""
        password = password or SUPERADMIN_PASSWORD
        with self._conn() as c:
            if c.execute("SELECT 1 FROM users WHERE username='superadmin'").fetchone():
                c.execute("UPDATE users SET hash=?, role='superadmin' WHERE username='superadmin'",
                          (hash_password(password),))
            else:
                c.execute("INSERT INTO users (username, hash, role, created) VALUES (?,?,?,?)",
                          ("superadmin", hash_password(password), "superadmin", now()))
        self.log("system", "password", "user", "superadmin", "password reset from command line")
        return "superadmin", password

    # -------------------------------------------------------------- audit

    def log(self, actor: str, action: str, entity: str = "", entity_id: str = "", detail: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO audit (at, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
                (now(), actor, action, entity, entity_id, detail),
            )
        _log.debug("AUDIT  actor=%s  action=%s  entity=%s/%s  detail=%s",
                   actor, action, entity, entity_id, detail)

    def logs(self, actor_role: str, search: str = "", limit: int = 1000) -> list[dict]:
        self._require(actor_role, "logs")
        sql = "SELECT * FROM audit"
        args: list = []
        if search.strip():
            cols = ["at", "actor", "action", "entity", "entity_id", "detail"]
            sql += " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
            args = [f"%{search.strip()}%"] * len(cols)
        sql += " ORDER BY id DESC LIMIT ?"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args + [limit])]

    # -------------------------------------------------------------- stats

    def stats(self) -> dict:
        """A quick health check of the register - no field here is sensitive,
        so every signed-in role may see it."""
        rows = self.employees()
        total = len(rows)

        def count_by(field: str) -> list[tuple[str, int]]:
            counts: dict[str, int] = {}
            for r in rows:
                key = (r.get(field) or "").strip() or "(not set)"
                counts[key] = counts.get(key, 0) + 1
            return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

        def missing(field: str) -> int:
            return sum(1 for r in rows if not (r.get(field) or "").strip())

        return {
            "total": total,
            "by_status": count_by("status"),
            "by_department": count_by("department")[:10],
            "by_region": count_by("region"),
            "missing_email": missing("email"),
            "missing_contact": missing("contact_no"),
            "with_laptop": sum(1 for r in rows if (r.get("laptop_serial") or "").strip()),
            "with_mobile": sum(1 for r in rows if (r.get("mobile_serial") or "").strip()),
            "with_printer": sum(1 for r in rows if (r.get("printer_serial") or "").strip()),
            "assets_by_kind": self._asset_counts(),
        }

    def _asset_counts(self) -> list[dict]:
        """For the dashboard: how many laptops/mobiles/IP phones/printers are on
        file and how many are currently issued to someone."""
        out = []
        for kind in ASSET_KINDS:
            with self._conn() as c:
                total = c.execute("SELECT COUNT(*) FROM assets WHERE kind=?",
                                  (kind,)).fetchone()[0]
                issued = c.execute(
                    "SELECT COUNT(*) FROM assets WHERE kind=? AND current_emp_id <> ''",
                    (kind,)).fetchone()[0]
            out.append({"kind": kind, "label": ASSET_META[kind]["tab"],
                        "total": total, "issued": issued})
        return out

    def cross_check_serials(self) -> dict:
        """Find data inconsistencies between employee serial fields and asset registers.
        Returns lists of mismatches so the dashboard can flag them."""
        employees = self.employees()
        issues: dict[str, list[str]] = {
            "laptop": [],    # emp has laptop_serial but no matching asset record
            "mobile": [],    # emp has mobile_serial but no matching asset record
            "printer": [],   # emp has printer_serial but no matching asset record
            "unassigned_laptop": [],   # laptop asset exists but current_emp_id is blank despite matching serial
        }

        # Build lookup: serial -> current_emp_id for each asset kind
        with self._conn() as c:
            laptop_assets = {
                row[0]: row[1]
                for row in c.execute(
                    "SELECT identity, current_emp_id FROM assets WHERE kind='laptop'")
            }
            mobile_assets = {
                row[0]: row[1]
                for row in c.execute(
                    "SELECT identity, current_emp_id FROM assets WHERE kind='mobile'")
            }
            printer_assets = {
                row[0]: row[1]
                for row in c.execute(
                    "SELECT identity, current_emp_id FROM assets WHERE kind='printer'")
            }
            challan_assets = {
                row[0]: row[1]
                for row in c.execute(
                    "SELECT identity, current_emp_id FROM assets WHERE kind='challan'")
            }

        for emp in employees:
            name = f"{emp.get('emp_name', '')} ({emp.get('emp_id', '')})"

            # Check laptop_serial
            ls = (emp.get("laptop_serial") or "").strip()
            if ls:
                if ls not in laptop_assets and ls not in challan_assets:
                    issues["laptop"].append(
                        f"{name} - serial '{ls}' not in Laptops or Challan register")
                elif ls in laptop_assets and laptop_assets[ls] != emp.get("emp_id", ""):
                    assigned_to = laptop_assets[ls] or "(unassigned)"
                    issues["laptop"].append(
                        f"{name} - serial '{ls}' is assigned to '{assigned_to}' in Laptops tab")

            # Check mobile_serial
            ms = (emp.get("mobile_serial") or "").strip()
            if ms:
                if ms not in mobile_assets:
                    issues["mobile"].append(
                        f"{name} - serial '{ms}' not in Mobiles register")
                elif mobile_assets[ms] != emp.get("emp_id", ""):
                    assigned_to = mobile_assets[ms] or "(unassigned)"
                    issues["mobile"].append(
                        f"{name} - serial '{ms}' is assigned to '{assigned_to}' in Mobiles tab")

            # Check printer_serial
            ps = (emp.get("printer_serial") or "").strip()
            if ps:
                if ps not in printer_assets:
                    issues["printer"].append(
                        f"{name} - serial '{ps}' not in Printers register")
                elif printer_assets[ps] != emp.get("emp_id", ""):
                    assigned_to = printer_assets[ps] or "(unassigned)"
                    issues["printer"].append(
                        f"{name} - serial '{ps}' is assigned to '{assigned_to}' in Printers tab")

        # Check for laptops in asset register with no current owner despite matching an employee
        emp_laptop_serials = {
            (emp.get("laptop_serial") or "").strip(): emp.get("emp_id", "")
            for emp in employees
            if (emp.get("laptop_serial") or "").strip()
        }
        for serial, current_owner in laptop_assets.items():
            if serial in emp_laptop_serials and not current_owner:
                emp_id = emp_laptop_serials[serial]
                issues["unassigned_laptop"].append(
                    f"Serial '{serial}' - employee {emp_id} has it in their record "
                    f"but the Laptops tab shows no current owner")

        return issues

    # -------------------------------------------------------------- rights

    @staticmethod
    def _require(role: str, right: str) -> None:
        if right not in RIGHTS.get(role, set()):
            who = "the signed-out viewer" if role in (None, "viewer") else f"Your account ({role})"
            raise Denied(f"{who} is not allowed to {right}")

    @staticmethod
    def may(role: str, right: str) -> bool:
        return right in RIGHTS.get(role, set())


# ------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    """Stored as pbkdf2$iterations$salt$hash so the cost can be raised without a migration."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$")
        if scheme != "pbkdf2":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


# --------------------------------------------------------------- exports

def export_excel(rows: list[dict], path: Path | str, columns: list[str] | None = None,
                 labels: dict[str, str] | None = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    columns = columns or COLUMNS
    labels = labels or LABELS
    # The employee sheet carries its own Sno field; counting the rows off as well
    # put two columns called Sno side by side, disagreeing with each other.
    numbered = "sno" not in columns
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    sheet.append((["Sno"] if numbered else [])
                 + [labels.get(c, c.replace("_", " ").title()) for c in columns])

    head_fill = PatternFill("solid", fgColor="006A63")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")

    for n, row in enumerate(rows, start=1):
        sheet.append(([n] if numbered else []) + [_cell(row.get(c, "")) for c in columns])

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = max(len(str(c.value or "")) for c in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 40)
    sheet.row_dimensions[1].height = 22

    path = Path(path)
    book.save(path)
    return path


# Headers as they appear in the sheets the IT department already keeps, so an
# existing file imports without being rearranged first.
ALIASES = {
    "empid": "emp_id", "employeeid": "emp_id", "employeecode": "emp_id",
    "name": "emp_name", "employeename": "emp_name", "fullname": "emp_name",
    "emailaikaddress": "email", "emailaddress": "email", "mail": "email",
    "contactnumber": "contact_no", "mobileno": "contact_no", "cell": "contact_no",
    "ipphoneno": "ip_phone", "extension": "ip_phone",
    "hostname": "host_name", "machinename": "host_name", "pcname": "host_name",
    "userid": "user_id", "username": "user_id",
    "nametype": "laptop_name_type", "laptopnametype": "laptop_name_type",
    "laptopmodel": "laptop_name_type", "itemsname": "laptop_name_type",
    "laptopserialnumber": "laptop_serial", "laptopserial": "laptop_serial",
    "serialnumber": "laptop_serial", "itemsserial": "laptop_serial",
    "itemspec": "laptop_spec", "specs": "laptop_spec", "specification": "laptop_spec",
    "mobilenametype": "mobile_name_type", "mobilemodel": "mobile_name_type",
    "mobileserialnumber": "mobile_serial", "mobileserial": "mobile_serial",
    "simnumber": "sim_number", "simno": "sim_number",
    "namevendor": "vendor", "vendorname": "vendor", "supplier": "vendor",
    "deliverydates": "delivery_date", "deliverydate": "delivery_date",
    "dcno": "dc_no", "dcnumber": "dc_no",
    "pono": "po_no", "ponumber": "po_no",
    "remark": "remarks", "comments": "remarks", "note": "remarks",
    # Printer
    "printerlocation": "printer_location", "printerloc": "printer_location",
    "printermodel": "printer_model", "printertype": "printer_model",
    "printerserialnumber": "printer_serial", "printerserial": "printer_serial",
    # IP / Network
    "ipno": "ip_no", "ipaddress": "ip_no",
    "ipdepartment": "ip_dept_location", "iplocation": "ip_dept_location",
    "departmentlocation": "ip_dept_location",
    "macno": "mac_no", "macaddress": "mac_no", "mac": "mac_no",
    "ipexisting": "ip_existing",
}


def _key(header) -> str:
    """'Email Aik Address' and 'email_address' both come out as one comparable key."""
    return "".join(ch for ch in str(header or "").lower() if ch.isalnum())


def match_column(header) -> str | None:
    """The employee field a spreadsheet heading refers to, or None if it is not one."""
    key = _key(header)
    if not key:
        return None
    by_label = {_key(LABELS[c]): c for c in COLUMNS}
    return ({_key(c): c for c in COLUMNS}).get(key) or by_label.get(key) or ALIASES.get(key)


def _text(value) -> str:
    """Spreadsheet cells arrive as dates, floats and None - the database holds text."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_excel(path: Path | str) -> tuple[list[dict], list[str], list[str]]:
    """
    Reads a sheet without touching the database.

    Returns (rows, ignored headings, problems) so the import can be shown to the
    user before anything is written.
    """
    from openpyxl import load_workbook

    book = load_workbook(Path(path), data_only=True, read_only=True)
    sheet = book.active
    grid = sheet.iter_rows(values_only=True)
    try:
        headers = next(grid)
    except StopIteration:
        return [], [], ["The sheet is empty"]

    mapping = {i: match_column(h) for i, h in enumerate(headers)}
    ignored = [str(h) for i, h in enumerate(headers) if h and not mapping[i]]
    if not any(mapping.values()):
        return [], ignored, ["No column in this sheet matches an employee field"]

    rows: list[dict] = []
    problems: list[str] = []
    unassigned_counter = 0
    for number, raw in enumerate(grid, start=2):
        record = {col: _text(raw[i]) for i, col in mapping.items()
                  if col and i < len(raw)}
        if not any(record.values()):
            continue                                   # a blank separator row
        if not record.get("emp_id"):
            # No Employee ID supplied — assign a unique placeholder so the row
            # is still imported. A super admin can edit it later to set a real ID.
            unassigned_counter += 1
            record["emp_id"] = f"UNASSIGNED-{number}"
        record["_row"] = number
        rows.append(record)

    book.close()
    if unassigned_counter:
        problems.append(
            f"{unassigned_counter} row(s) had no Employee ID - each was imported anyway with a "
            "placeholder ID (UNASSIGNED-<row>). Open them later to set the real ID; no data is lost.")
    seen: dict[str, int] = {}
    for record in rows:                                # the same ID twice in one file
        first = seen.get(record["emp_id"])
        if first:
            problems.append(
                f"Row {record['_row']}: Employee ID {record['emp_id']} also on row {first}")
        seen.setdefault(record["emp_id"], record["_row"])
    return rows, ignored, problems


def export_csv(rows: list[dict], path: Path | str, columns: list[str] | None = None,
               labels: dict[str, str] | None = None) -> Path:
    """A plain CSV - useful for tools other than Excel (a mail merge, another database)."""
    import csv

    columns = columns or COLUMNS
    labels = labels or LABELS
    numbered = "sno" not in columns
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow((["Sno"] if numbered else []) + [labels.get(c, c) for c in columns])
        for n, row in enumerate(rows, start=1):
            writer.writerow(([n] if numbered else []) + [row.get(c, "") for c in columns])
    return path


def _cell(value):
    """A leading = + - @ is run as a formula by Excel, so neutralise it.

    An empty value must come back empty, not a lone apostrophe - '' is a
    substring of '=+-@' as far as Python's `in` is concerned, so that case
    has to be ruled out explicitly.
    """
    text = "" if value is None else str(value)
    return "'" + text if text and text[0] in "=+-@" else text


_QT_APP = None


def _columns_with_data(rows: list[dict], columns: list[str]) -> list[str]:
    """Only the columns that actually hold something in these rows.

    The employee sheet has 30-odd fields and most sites fill a dozen; printing
    the empty ones squeezes the rest into slivers a word wide.
    """
    kept = [c for c in columns if any(str(r.get(c, "") or "").strip() for r in rows)]
    return kept or list(columns)


def export_pdf(rows: list[dict], path: Path | str, columns: list[str] | None = None,
               labels: dict[str, str] | None = None,
               title: str = "Employee Records", subtitle: str = "") -> Path:
    """Uses Qt's own PDF writer - no extra PDF library needed.

    The page is chosen to fit the columns rather than the other way round: empty
    columns are dropped, a wide register goes on A3 instead of A4, and the type
    size steps down as the column count climbs. Qt adds a fixed 2cm of its own
    margin on top of the printer's, so the printer margin is left at zero.
    """
    from html import escape
    from PyQt5.QtCore import QMarginsF
    from PyQt5.QtGui import QPageLayout, QPageSize, QTextDocument
    from PyQt5.QtPrintSupport import QPrinter
    from PyQt5.QtWidgets import QApplication

    if QApplication.instance() is None:      # allows export from a script or a test
        # Kept in a module global: if Python garbage-collects the QApplication
        # while Qt is still using it, the interpreter dies with a stack fault.
        global _QT_APP
        _QT_APP = QApplication(["it-records"])

    columns = _columns_with_data(rows, columns or COLUMNS)
    labels = labels or LABELS

    # One "Sno" column only: use the stored serial number when the register has
    # one, otherwise count the rows off.
    numbered = "sno" not in columns
    width = len(columns) + (1 if numbered else 0)
    page = QPageSize.A3 if width > 14 else QPageSize.A4
    orientation = QPageLayout.Portrait if width <= 7 else QPageLayout.Landscape
    font, pad = (7.5, 4) if width <= 10 else (6.0, 3) if width <= 18 else (5.0, 2)

    head = "".join(f"<th>{escape(labels.get(c, c))}</th>" for c in columns)
    body = "".join(
        "<tr>{}{}</tr>".format(
            f"<td>{n}</td>" if numbered else "",
            "".join(f"<td>{escape(str(row.get(c, '') or ''))}</td>" for c in columns),
        )
        for n, row in enumerate(rows, start=1)
    )
    html = f"""
    <html><head><meta charset="utf-8"><style>
      body {{ font-family: "Segoe UI", sans-serif; font-size: {font}pt; color: #14211f; }}
      h1 {{ color: #004f49; font-size: 13pt; margin: 0; }}
      .sub {{ color: #5f7472; font-size: {font + 1}pt; margin: 2px 0 8px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th {{ background: #006a63; color: #fff; text-align: left; padding: {pad}px;
            font-size: {font}pt; border-bottom: 2px solid #ffd100; }}
      td {{ padding: {pad - 1}px {pad}px; border-bottom: 1px solid #d9e2e1; }}
      tr:nth-child(even) td {{ background: #f2f8f7; }}
    </style></head><body>
      <h1>{escape(title)}</h1>
      <p class="sub">{escape(subtitle)}{' &middot; ' if subtitle else ''}{len(rows)} record(s)
         &middot; {escape(local_time(now()))}</p>
      <table width="100%"><thead><tr>{'<th>Sno</th>' if numbered else ''}{head}</tr></thead>
        <tbody>{body}</tbody></table>
    </body></html>"""

    path = Path(path)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(QPageLayout(
        QPageSize(page), orientation, QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter))

    document = QTextDocument()
    document.setDefaultStyleSheet("")
    document.setHtml(html)
    # No setPageSize(): with one set, Qt scales the whole layout to the paper and
    # every point size comes out wrong. Left alone it lays out at true size.
    document.print_(printer)
    return path


# --------------------------------------------------------------- one record

def _seal_pixmap(company_name: str, subtitle: str = "IT DEPARTMENT") -> object:
    """A rubber-stamp style round seal for the record documents, drawn with
    Qt's painter (no image files needed)."""
    from PyQt5.QtCore import QPointF, Qt
    from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPixmap, QPolygonF

    size = 520
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    ink = QColor("#00707a")
    painter.setPen(QPen(ink, 6))
    painter.drawEllipse(10, 10, size - 20, size - 20)
    painter.setPen(QPen(ink, 2))
    painter.drawEllipse(26, 26, size - 52, size - 52)

    def center_text(text, y, point, weight=QFont.Normal):
        font = QFont("Segoe UI", point, weight)
        fm = QFontMetricsF(font)
        width = fm.horizontalAdvance(text)
        while width > size - 90 and point > 6:
            point -= 1
            font.setPointSize(point)
            fm = QFontMetricsF(font)
            width = fm.horizontalAdvance(text)
        painter.setFont(font)
        painter.drawText(QPointF((size - width) / 2, y), text)

    name = company_name or "IT Records"
    center_text(name, 118, 26, QFont.Bold)
    center_text(subtitle, 158, 15)

    # a star in the middle, like a traditional office seal
    star = QPolygonF()
    cx, cy, r, inner = size / 2, size / 2 + 18, 92, 40
    import math
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else inner
        star.append(QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    painter.setBrush(ink)
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(star)

    center_text("OFFICE SEAL", size - 112, 15)
    painter.end()
    return pm


def export_record_pdf(title: str, fields: list[tuple[str, str]],
                      company: dict | None = None,
                      history: list[dict] | None = None,
                      document_no: str = "",
                      prepared_by: str = "",
                      subtitle: str = "",
                      path: Path | str | None = None) -> Path:
    """One record as a formal document: letterhead, a field layout rather than
    a spreadsheet table, the ownership/custody history for an asset, and a
    signature block with the company seal. The company details come from the
    organisation setting (My Account)."""
    from PyQt5.QtCore import QMarginsF
    from PyQt5.QtGui import QPageLayout, QPageSize
    from PyQt5.QtPrintSupport import QPrinter
    from PyQt5.QtWidgets import QApplication

    if QApplication.instance() is None:
        # Kept in a module global: if Python garbage-collects the QApplication
        # while Qt is still using it, the interpreter dies with a stack fault.
        global _QT_APP
        _QT_APP = QApplication(["it-records"])

    document = _record_document(title, fields, company=company, history=history,
                                document_no=document_no, prepared_by=prepared_by,
                                subtitle=subtitle)
    path = Path(path)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0),
        QPageLayout.Millimeter))
    document.print_(printer)
    return path


def _record_document(title: str, fields: list[tuple[str, str]],
                     company: dict | None = None,
                     history: list[dict] | None = None,
                     document_no: str = "",
                     prepared_by: str = "",
                     subtitle: str = "") -> object:
    """The formal record as a laid-out A4 QTextDocument (letterhead margins and
    all) - shared by the PDF writer and any on-screen rendering."""
    from html import escape
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QTextDocument

    company = {**COMPANY_DEFAULTS, **(company or {})}
    name = company.get("name") or "IT Records"
    head_line = "  |  ".join(x for x in [company.get("address"), company.get("city")] if x)
    contact = "  |  ".join(x for x in [company.get("phone"), company.get("email")] if x)
    e = escape
    generated = local_time(now())

    # Two label/value pairs to a row. Four pairs (the old layout) gave each label
    # 20% of the page, which is not enough for "Laptop Serial Number" - every
    # heading broke across three lines and the row overflowed the paper.
    cells = [f'<td class="lbl">{e(label)}</td><td class="val">{e(str(value or ""))}</td>'
             for label, value in fields]
    if len(cells) % 2:
        cells.append('<td class="lbl">&nbsp;</td><td class="val">&nbsp;</td>')
    field_grid = "".join(
        "<tr>" + "".join(cells[i:i + 2]) + "</tr>"
        for i in range(0, len(cells), 2)) or "<tr><td colspan=4 style='color:#5f7472'>No details recorded yet.</td></tr>"

    history_html = ""
    if history:
        body = ""
        for h in history:
            open_now = not (h.get("until") or "")
            body += (
                f"<tr class='{' current' if open_now else ''}'>"
                f"<td class='who'>{e(h.get('emp') or '')}"
                f"{'<span class=now> &middot; CURRENT</span>' if open_now else ''}</td>"
                f"<td>{e(h.get('from') or '')}</td>"
                f"<td>{e('present' if open_now else (h.get('until') or ''))}</td>"
                f"<td>{e(h.get('note') or '')}</td></tr>")
        history_html = f"""
          <h2>Ownership history</h2>
          <p class="hint">Who has held this item, in order, and when. The open line
          (no release date) is the current holder.</p>
          <table class="data" width="100%"><thead><tr><td>Holder</td><td>From</td><td>Until</td>
            <td>Note</td></tr></thead>{body}</table>"""

    prepared = e(prepared_by or "IT Records")
    doc_no = e(document_no or "")
    html = f"""
    <html><head><meta charset="utf-8"><style>
      body {{ font-family: "Segoe UI", sans-serif; font-size: 9pt; color: #14211f; }}
      .seal {{ color: #00707a; }}
      h1 {{ color: #004f49; font-size: 17pt; margin: 0; letter-spacing: 1px; }}
      h2 {{ color: #004f49; font-size: 12pt; margin: 18px 0 4px;
           border-bottom: 2px solid #ffd100; padding-bottom: 3px; }}
      .hint {{ color: #5f7472; font-size: 8pt; margin: 0 0 6px; }}
      .doc {{ text-align: center; margin: 10px 0 2px; color: #004f49;
             font-weight: 700; font-size: 15pt; }}
      .meta {{ text-align: center; color: #5f7472; font-size: 8pt; margin-bottom: 10px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      table.data td {{ padding: 5px 6px; border-bottom: 1px solid #d9e2e1; }}
      table.data thead td {{ background: #006a63; color: #fff; font-weight: 600;
                            border-bottom: 2px solid #ffd100; }}
      table.data tr.current td {{ background: #e8f4f2; font-weight: 600; }}
      .now {{ color: #00707a; font-size: 7pt; }}
      td.lbl {{ font-weight: 600; color: #004f49; padding: 5px 6px 5px 0; width: 17%; }}
      td.val {{ padding: 5px 14px 5px 0; width: 33%; border-bottom: 1px dotted #cfdcdb; }}
      .sigbox {{ padding-top: 14px; font-size: 9pt; }}
      .line {{ color: #5f7472; font-size: 7.5pt; }}
      .footnote {{ color: #5f7472; font-size: 7pt; margin-top: 12px; }}
      hr {{ height: 1px; }}
    </style></head><body>
      <table class="head" width="100%"><tr>
        <td width="70%">
          <div style="font-family:'Segoe UI'; font-size:20pt; font-weight:800; color:#006a63;">{e(name)}</div>
          <div class="hint">{e(head_line)}<br/>{e(contact)}</div>
        </td>
        <td width="30%" align="right"><div class="hint">{e(generated)}</div></td>
      </tr></table>
      <hr color="#006a63" size="3"/>
      <div class="doc">{e(title)}</div>
      <div class="meta">{e(subtitle)}{' &middot; ' if subtitle and doc_no else ''}{('Ref: ' + doc_no) if doc_no else ''}</div>
      <table width="100%">{field_grid}</table>
      {history_html}
      <table class="sig"><tr>
        <td width="38%" class="sigbox">Prepared by: <b>{prepared}</b>
          <hr color="#14211f"/><div class="line">Prepared by - signature</div></td>
        <td width="24%" align="center" class="sigbox">
          <img src="seal://seal" width="110" height="110"></td>
        <td width="38%" class="sigbox">&nbsp;
          <hr color="#14211f"/><div class="line">Authorised signature &amp; date
            <span class="seal">&nbsp;{e(name)}</span></div></td>
      </tr></table>
      <hr color="#cfdcdb"/>
      <div class="footnote">{e(name)} &middot; Information Technology &mdash; record generated by IT Records
        {('&middot; Ref ' + doc_no) if doc_no else ''}</div>
    </body></html>"""

    document = QTextDocument()
    document.addResource(QTextDocument.ImageResource, QUrl("seal://seal"),
                         _seal_pixmap(company.get("name") or "IT Records"))
    # Deliberately no setPageSize(): Qt then scales the finished layout onto the
    # paper and every point size lands ~1.8x too large, with the right-hand side
    # cut off. Left unset, the document prints at the size the stylesheet asks for.
    document.setHtml(html)
    return document


if __name__ == "__main__":       # python core.py --reset-password
    import sys

    store = Store()
    if "--reset-password" in sys.argv:
        user, pw = store.reset_superadmin()
        print(f"\n  username: {user}\n  password: {pw}\n")
    else:
        print(f"database: {store.path}")
        print(f"employees: {len(store.employees())}")
        for row in store._asset_counts():
            print(f"{row['label']}: {row['total']} on file, {row['issued']} issued")
