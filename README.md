# IT Asset Management & Employee Equipment Tracking (Python/PyQt5)

IT Records is a Python + PyQt5 desktop application for **IT asset management**, **inventory management**, and **employee equipment tracking**.

It provides a searchable employee register plus dedicated hardware registers for **laptop inventory**, **mobile inventory**, **IP phone register**, **printer register**, and **challan/vendor delivery tracking**, backed by a local **SQLite desktop app** database.

## Table of contents

- [Feature summary](#feature-summary)
- [Common use cases](#common-use-cases)
- [Who this is for](#who-this-is-for)
- [Technical stack and platform](#technical-stack-and-platform)
- [Quick start](#quick-start)
- [Roles and access model](#roles-and-access-model)
- [Asset assignment and lifecycle history](#asset-assignment-and-lifecycle-history)
- [Excel import and export](#excel-import-and-export)
- [Windows build (PyInstaller)](#windows-build-pyinstaller)
- [Data location and configuration](#data-location-and-configuration)
- [Security guidance](#security-guidance)
- [Testing](#testing)
- [Contributing](#contributing)

## Feature summary

- Employee register with optional profile, contact, device, and vendor/challan fields.
- Dedicated hardware registers: **Laptops**, **Mobiles**, **IP Phones**, **Printers**, and **Challan**.
- **Asset assignment** and handover flow with per-asset and per-employee **asset lifecycle/history**.
- Import workflows:
  - employee Excel import with preview,
  - source-file rebuild via `build_import_file.py`.
- Exports for employees and asset registers: **Excel and PDF**.
- Send Email to one or many selected employees from a configured sender account.
- Role-based access (`viewer`, `user`, `superadmin`) and activity log.
- Dashboard summaries for inventory and employee record coverage.
- Packaged **Windows** desktop executable support using PyInstaller.

## Common use cases

- Run an internal **IT hardware register** for daily operations.
- Track who currently holds each laptop, mobile, IP phone, or printer.
- Maintain **asset assignment history** for handovers and returns.
- Keep a searchable employee equipment inventory in one desktop app.
- Import existing Excel data and export filtered views for audits/reporting.
- Track challan/vendor delivery records and their issued/spare status.

## Who this is for

- IT support and infrastructure teams managing employee-issued hardware.
- Admin/operations teams maintaining office inventory records.
- Teams that prefer an on-prem/local **SQLite + desktop UI** workflow over a hosted SaaS tool.

## Technical stack and platform

- **Language:** Python
- **GUI framework:** PyQt5
- **Storage:** SQLite (`employees.db`)
- **Spreadsheet I/O:** openpyxl
- **Export formats:** Excel (`.xlsx`), PDF
- **Target environment:** Desktop usage, including Windows executable packaging via PyInstaller

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

The app opens in read-only viewer mode until a privileged user signs in.

## Roles and access model

| Capability | viewer | user | superadmin |
|---|---|---|---|
| View/search employee and asset registers | yes | yes | yes |
| Add/edit/delete employee records | no | no | yes |
| Add/edit/delete/assign/release assets | no | no | yes |
| View asset history | yes | yes | yes |
| Manage users and view activity log | no | no | yes |
| Excel/PDF export, Excel import | no | no | yes |

## Asset assignment and lifecycle history

Each asset register supports assignment to an employee and keeps ownership history over time.

- Re-assignment creates a handover trail (previous assignment is closed, new one opens).
- Release returns an asset to unassigned/spare state.
- Asset history remains viewable.
- Employee records stay synchronized with assigned asset fields (for supported mappings).

## Excel import and export

### Employee import preview

The employee import flow reads spreadsheet headers used by existing records and shows a preview before writing changes.

### Source-file rebuild

```bash
python build_import_file.py --check
python build_import_file.py --rebuild
python build_import_file.py --rebuild --keep-accounts
```

- `--check`: read-only summary.
- `--rebuild`: backup DB, rebuild employee + asset data from source files.
- `--keep-accounts`: preserves existing accounts while rebuilding data.

### Export

The employee register is always listed by **SNO (1, 2, 3 ...)**. The app keeps SNO gap-free: new and imported employees join the end, and deleting one closes the gap.

Superadmins can export employee and asset register views to:

- Excel (`.xlsx`)
- PDF

## Windows build (PyInstaller)

Use the existing build command:

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --noconsole --name "IT Records" `
    --icon app.ico --add-data "app.ico;." `
    --hidden-import=openpyxl --hidden-import=et_xmlfile `
    --exclude-module pandas --exclude-module numpy main.py
```

Distribute the full `dist\IT Records\` directory (including `_internal`).

## Data location and configuration

Default database path:

- `C:\Users\<you>\ITRecords\employees.db`

Optional override:

- Set `ITRECORDS_DB` to use a custom/shared database path.

Backup guidance:

- Close the app before copying `employees.db`.

Email sender:

- The default sender is `kawish.iftikhar@bipl.io` on `smtp.gmail.com:587`.
- The app password is never stored in the source. Put it in `email.json` next to `employees.db` (or next to `IT Records.exe`), or enter it in **More → Email Settings**:

```json
{"smtp_email": "kawish.iftikhar@bipl.io", "smtp_password": "<app password>"}
```

- `email.json` is git-ignored. **Email Settings → Test connection** checks the sign-in without sending anything.

Password recovery command:

```bash
python core.py --reset-password
```

## Security guidance

- This project is intended for internal desktop use. Review authentication and deployment design before production rollout.
- **Change initial credentials immediately** after first setup and enforce your organization’s credential policy.
- Restrict filesystem access to the SQLite database file and backups.
- For vulnerability reporting, see [SECURITY.md](SECURITY.md).

## Testing

Run the existing project checks:

```bash
python test_core.py
python test_gui.py
```

Notes:

- `test_gui.py` exercises real PyQt5 widgets, so it is best run in an environment with GUI support.
- No additional CI workflow is added here to avoid introducing fragile GUI-dependent automation.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and contribution guidance.
