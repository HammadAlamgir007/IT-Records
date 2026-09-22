IT Records - installation

The app reads the real data by itself, so both ways below work:

Fastest:  double-click  IT Records.exe
          - on a PC with no IT Records data yet, it automatically picks up the
            bundle it came with (YOUR-DATA\employees.db) and shows the real
            registers (employees, laptops, challan, ...).

or step-by-step:
1. Extract everything from this zip to any folder on the PC
   (e.g. C:\IT Records). Keep the files together.
2. Double-click  "Setup my data.cmd"  - it places the sent data on this PC and
   opens  IT Records.exe. Run it again any time you want to restore the data.

If the app ever looks empty on an existing PC (e.g. it was opened before this
copy arrived):
   - run  "Setup my data.cmd"  once, or
   - close the app, delete the folder  %USERPROFILE%\ITRecords , and open
     IT Records.exe again.

Sign-in
The app opens read-only - anyone can look at everything. The admin buttons
(Add, Edit, Delete, Import, Export, Print Record, Assign) ask for a sign-in:

    superadmin   /   admin

That login is fixed in the program and is re-applied every time the app opens,
so it cannot be lost. Changing it from the My Account tab will not stick - to
change it for good it has to be changed in the source and the exe rebuilt.
Ordinary accounts created under the Users tab are unaffected.
