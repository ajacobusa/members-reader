# Portable Etsy/Gelato project (self-contained on this drive)

Everything this project needs lives on **this drive** — nothing depends on `C:`.

```
<drive>:\ANOOP PERSONAL HOME\CLAUD\Claud AJ\
├── python\              ← standalone Python 3.14 interpreter (+ stdlib, tkinter)
│   └── Lib\site-packages\   ← ALL project packages (Pillow, anthropic, flask, …)
├── quoteforge\          ← the code
├── src\members_reader\  ← the library package
├── data\                ← OUTPUT_DIR: SQLite DB, assets, proofs, caches
├── .env                 ← secrets + OUTPUT_DIR (the one drive-letter reference)
├── requirements-lock.txt← exact pinned versions (to rebuild the env anywhere)
├── run.bat              ← launcher for admin commands
└── test.bat            ← launcher for the test suite
```

## How to run (use the launchers — they pin this drive's python)
```bat
run.bat deploy-status         :: any admin command
run.bat rebuild-site
test.bat                      :: full test suite
test.bat -q quoteforge_tests\test_admin.py
```
The launchers `cd` to this folder, set `PYTHONNOUSERSITE=1` (so the system's
per-user packages are ignored), and call `python\python.exe`. Result: the project
always uses **this drive's** interpreter + packages, never `C:`.

## What makes it portable
- **Interpreter** — a full copy of CPython; `python.exe` finds its own stdlib
  relative to itself, so it runs no matter the drive letter.
- **Packages** — installed into `python\Lib\site-packages` (on this drive), not the
  C: user-site. `requirements-lock.txt` can recreate the exact set on any machine.
- **Code + data** — both on this drive; `data\` holds the SQLite DB and assets.

## Drive-letter independence (USB-safe)
This drive is a USB stick — its letter can change when another device is plugged
in. The project handles that automatically:
- **`.env`** is found relative to the code (`config.py`'s own path), not a fixed path.
- **`OUTPUT_DIR`** defaults to `<project>\data` (next to the code), so the data dir
  follows the drive to whatever letter it gets — no `.env` edit needed.
- **`run.bat` / `test.bat`** use `%~dp0`, so they target this drive regardless of letter.

So you can move the USB to another machine / port and everything still resolves.

## Daily High-Availability (no single point of failure)
A USB can be lost or unplugged, so the durable copies live elsewhere:
- **GitHub** — code + DB snapshot + a full git bundle (`backup-all`), offsite.
- **C:** — a full local mirror of the project + data (the persistent internal disk).

Install the daily job once (it self-locates the USB by marker, not letter, and runs
from C: so it works even when the USB letter changed or it's unplugged):
```bat
run.bat ha-install            :: schedule it daily at 07:30 (default)
run.bat ha-install --at 22:00 :: pick a time the USB is usually connected
run.bat ha-install --run      :: schedule AND run one sync now
```
It writes `C:\QuoteForge-HA\` (mirror + logs) and logs each run to
`C:\QuoteForge-HA\logs\ha-sync.log`. If the USB isn't connected when it fires, it
logs that and exits cleanly. The order DB is mirrored to C: + (optionally) Google
Drive, but kept OUT of GitHub for privacy.

## Rebuild the environment from scratch (e.g. on a fresh machine)
If you ever need to recreate the packages (or move to a new Python):
```bat
python\python.exe -m pip install -r requirements-lock.txt
python\python.exe -m pip install -e .
```

## Notes
- Requires Windows (this is a Windows CPython build). For macOS/Linux you'd
  recreate the env from `requirements-lock.txt` with that OS's Python.
- The old C: data dir (`%USERPROFILE%\Desktop\QuoteForge-Output`) was copied into
  `data\`; it can be removed once you've confirmed everything works from the drive.
