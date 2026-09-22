# IT Records - Python / PyQt5

Desktop app for the IT register. One employee record holds everything: the person,
their laptop, their mobile, and the vendor challan it came from. On top of that,
**laptops, mobiles, IP phones and printers/scanners each get their own register with
their own history** - who holds what today, and who held it before and when.

## Run it

```
pip install -r requirements.txt
python main.py
```

### The desktop .exe (reliability first)

A ready-to-run build is made with PyInstaller - no Python needed on the target PC:

```
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --noconsole --name "IT Records" `
    --icon app.ico --add-data "app.ico;." `
    --hidden-import=openpyxl --hidden-import=et_xmlfile `
    --exclude-module pandas --exclude-module numpy main.py
```

Copy the whole `dist\IT Records\` folder onto the desktop (the `.exe` needs its
`_internal` folder beside it). The app is built to survive real desktops:

- **Every change is committed to the SQLite database the moment you make it** - add,
  edit, delete, assign, export all write and close the transaction immediately, so a
  power cut or a forced shutdown cannot lose the last action.
- **One window per database.** Starting a second copy pops "already open" and closes
  itself, so two copies can never both edit the file at once - the surest way to lose
  a record. If the app ever crashes, the guard frees itself automatically.
- **Per-user data.** Each Windows account saves to `ITRecords\employees.db` in that
  user's own profile; the first run on a computer creates the super admin account.
  To run a *shared* database instead, set the same `ITRECORDS_DB` environment
  variable (e.g. a mapped drive path) on every PC.
- The database is created and repaired on open; a missing file, a locked file and a
  bad password all give a clear message instead of a crash.

The window opens **read-only** - anyone can look at everything. Clicking an admin
button (Add, Edit, Delete, Import, Export, Asset tools) offers the sign-in dialog;
a successful sign-in unlocks the app for the rest of the session and refreshes every
register immediately.

On the very first run it creates a **superadmin** account. The password is a fixed,
known value for now - it is hardcoded in `core.py` (`SUPERADMIN_PASSWORD`), so every
fresh database ships with the same super admin login. Once the system is live with
real users, change it from **My Account** (or edit the constant and rebuild). Sign
out (header button) to drop back to read-only.

## Who can do what

Three levels, enforced in `core.py` - not in the window - so a hidden button is not
the only thing standing between a viewer and an edit.

| | viewer | user | super admin |
|---|---|---|---|
| View and search every field | yes | yes | yes |
| Add / edit / delete an employee | no | no | yes |
| Asset registers (add / edit / delete / assign / release) | no | no | yes |
| See an asset's history | yes | yes | yes |
| Manage user accounts | no | no | yes |
| See the Activity Log | no | no | yes |
| Export to Excel, CSV and PDF | no | no | yes |
| Import from Excel | no | no | yes |

`viewer` is a session state, not a stored account - it is what the app is when nobody
has signed in. A role that is not one of the two identities gets nothing at all, and an
account carrying one is reset to `user` when the database is opened.

## The employee record

One row per employee, with every field optional except **Employee ID**, so a record
can be started with what is known today and completed later.

- **Employee**: Emp ID, name, designation, department, user ID, email, contact no,
  IP phone, host name, location, region, status
- **Laptop**: name & type, serial number, spec
- **Mobile**: name & type, serial number, IMEI, SIM number
- **Vendor / challan**: vendor, delivery date, DC no, PO no
- **Notes**: remarks

The search box matches a substring of *any* of those fields.

## The asset registers

**Laptops**, **Mobiles**, **IP Phones**, **Printers** and **Challan** are tabs of their
own, next to Employees. Each is a full register: add, edit, delete, and a search box
like the employee sheet. The columns are the ones that matter for that kind of asset.

The **Challan** tab is the vendor delivery book - every line of the supplier challan,
with its delivery date, vendor, item details, serial, DC/PO numbers and status. It is
filled automatically from `CHALLAN SHEET.xlsx` when a rebuild runs (each delivery whose
serial matches an owned laptop is marked issued to that employee; the rest stay
`Spare`).

- An asset is tracked by its **serial number** (or IMEI for mobiles, MAC for IP
  phones). An item typed in without a number is given a tag automatically -
  `LAP-0001`, `MOB-0001`, `IP-0001`, `PRN-0001` - so nothing is too anonymous to hold.
- A serial/IMEI/MAC can never appear twice, and a serial already written on someone
  else's employee record (or already issued to them as an asset) is refused when you
  type it.

### Assignment and history

Every asset has an **Assign** action. Pick the employee (or search by name/ID), add an
optional note, and the item is recorded against them from today. Doing it again to a
different employee is a **handover** - the previous line is closed and a new open one
starts, so the chain of custody reads: *"issued to Hammad on 3 Feb, handed to Shahbaz
on 28 Apr, present"*.

- **Assign / Release** is a super-admin action; the asset's history (the whole chain,
  with notes) is visible to everyone.
- Assigning an asset **keeps the employee sheet in sync** - the matching fields
  (e.g. `Laptop Serial`) are written onto the employee row, and cleared again when the
  item is released or handed over.
- **Delete** removes the asset from its register but the history stays readable; while
  a delete also takes the item back first if someone still holds it.
- The Employees screen has an **Asset History** button per record listing everything
  that person has ever held, across all registers.
- **Assigning a challan line books the machine into the Laptops register** (creating
  the laptop from the delivery when it is not there yet) and marks the challan line
  with the same employee, so the two registers always agree. Releasing that laptop in
  the Laptops register writes the challan line back to `Spare`.

The first time a database made by an older version opens, serials/IMEIs/MACs already
typed into employee records are migrated into these registers, with a history line
dating from when the record was last touched.

## Activity log

Every add, edit, delete, export, sign-in and failed sign-in is recorded with who,
the exact time, and for an edit the old and new value of each changed field. Deleting
an employee keeps a copy of what the record held. Nothing in the app updates or
deletes a log row.

## Import from Excel (super admin)

**Import Excel** on the Employees screen reads an existing sheet. It understands the
headings the department already uses — `Emp ID`, `Name`, `IP Phone`, `Email Aik Address`,
`Laptop Serial Number`, `Name & Type`, `Items Serial`, `Name Vendor`, `Delivery Dates`,
`DC No`, `PO No` and so on — so a file does not have to be rearranged first.

Nothing is written until you have seen a preview showing how many rows are new, how many
already exist, which columns are being ignored, and which rows will be skipped.

- A row with no Employee ID is still imported, with a placeholder ID
  (`UNASSIGNED-<row>`) so nothing typed into the sheet is lost - open the record later
  and give it the real ID. The preview screen tells you how many rows this happened to.
- An Employee ID already on file is updated, and only for the columns the sheet carries,
  so an import can never blank out details it does not include. You can also choose to
  leave existing employees untouched.
- If an Employee ID already on file belongs to a different name than the sheet's row,
  the row is skipped and reported instead of overwriting - an ID collision is almost
  always a mistake in the sheet, not the same person renamed.
- A laptop serial, mobile serial, IMEI or printer serial already on someone else's
  record is refused with the name of who already has it, on Add, Edit and Import alike.
- Dates arrive as dates, not `2026-03-02 00:00:00`; numbers as `2201`, not `2201.0`.
- Importing the same file twice does not create duplicates.

A file produced by **Export Excel** imports straight back, so export first if you want a
template to fill in.

### Direct from the source files (super admin)

The department's own three files can be read straight into the database - no
intermediate workbook needed, every cell preserved exactly as typed:

- `UPDATE.xlsx` - the **Laptop** sheet (140 people, who become the employee
  records, each with their laptop fields), **Printer  Scanner** (8 units) and
  **IP Phone** sheets (33 phones, including the headless person-name column and the
  real `IP Existing` addresses).
- `CHALLAN SHEET.xlsx` - 121 laptops from the vendor, matched to an owned laptop by
  serial number; the ~30 that match nobody are kept as unassigned **Spare** stock so the
  delivery (vendor, dates, DC, PO) is not lost.
- `mobile.xls` - handset stock. Serials are picked up only where the cell itself labels
  one (`Serial Number ...`, `S\N ...`, `S/N ...`); anything else about a handset stays in
  the remarks, verbatim.

Employees are **only** the people on the Laptop sheet - the printers, phones and
handsets are register entries, not employees. None of those sheets name an owner, so
their **Current Owner** column stays empty until an item is assigned from its register
onwards.

Quirks of the originals are kept, not "fixed": trailing spaces are trimmed but case and
every other character stay as typed (so `5CD5254k75` stays lowercase), a row with no
Employee ID is imported under a `NOID-<row>` placeholder with the sheet's text in the
remarks, and a duplicate Employee ID on the sheet becomes `-2`, `-3`, never merged.

```
python build_import_file.py --check   # read-only: report planned counts and any notes
python build_import_file.py --rebuild # wipe registers AND accounts, re-import from the
                                      # three source files (backup taken first)
python build_import_file.py --rebuild --keep-accounts  # wipe registers only
```

`--rebuild` backs the live database up first (`.bak` beside it), resets the asset
registers (Laptops, Mobiles, IP Phones, Printers, Challan) and employees, then imports
everything as one batch. The default also resets user accounts and the activity log so
the app shows a **fresh superadmin username and password on the next launch** - use
`--keep-accounts` to keep the existing logins.

## Exports (super admin)

- **Excel** (`.xlsx`) and **CSV** - one row per employee, filtered by whatever is in the
  search box.
- **PDF** - landscape table, same filter.

All three export exactly the rows on screen, so search first, then export. Every asset
register has the same three export buttons for its own rows, with its own columns.

### One record as a formal document (Print Record)

Every register has a **Print Record** button (next to History). Select one row - an
employee such as *Hammad*, or a machine such as an HP laptop - and it produces one
**formal A4 PDF** with:

- the company **letterhead** (name, address, city, phone, email - set once under
  **My Account → Organisation detail** and every document prints the same header),
- the row's details laid out as a form, not a spreadsheet,
- for an asset, the full **ownership history**: *who held it, in order, and when* -
  the current holder is highlighted `CURRENT`,
- a signature block ("Prepared by", "Authorised signature") with a drawn **company
  seal**, and a reference number (`ITR/EMP/...`, `ITR/LAP/...`, ...) with the date.

The document is saved where you choose (default `Downloads`) and can be opened straight
away for printing. It is also recorded in the Activity Log as a `print` action. History
itself stays visible to everyone on the **History** button and the employee's
**Asset History**.

## Dashboard

A read-only tab, open to every signed-in account: total records, a breakdown by status,
region and department, how many records have a laptop/mobile/printer serial on file, and
how many are missing an email address or contact number. Nothing here is sensitive, so a
`user` account sees the same numbers a super admin does.

## Where the data lives

`C:\Users\<you>\ITRecords\employees.db` - a single SQLite file.
Set the `ITRECORDS_DB` environment variable to put it somewhere else.

Back it up by closing the app and copying that file.

**Sending a copy to another PC:** drop the live `employees.db` into a `YOUR-DATA`
folder next to the program (exe or unzipped folder). On a computer with no
database yet, the app copies it in on first open, so even an exe double-click is
never empty. An existing database is never overwritten; the bundled copy only
seeds when the profile has nothing. `_bundled_db()` in `core.py` finds the
folder.

## Lost the super admin password

```
python core.py --reset-password
```

This restores the hardcoded `core.py: SUPERADMIN_PASSWORD` on the database the
command points at (or the default per-user database if `ITRECORDS_DB` is unset).

## Checks

```
python test_core.py    # database, roles, asset registers, history, exports
python test_gui.py     # builds the real window for each role and checks what it shows
```
