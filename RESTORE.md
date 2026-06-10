# Backup & Restore Runbook (Joffiels / QuoteForge)

## What is backed up, automatically

A Windows scheduled task — **"QuoteForge Daily Backup"** — runs every night at
**02:00** and executes `python -m quoteforge.admin backup-all`, which:

1. **Database snapshot** → `…/QuoteForge-Output/db_backups/quoteforge_<timestamp>.db`
2. **Auto-commits** any tracked code changes locally
3. **Local git bundle** (full history) → `backups/joffiels_full_backup.bundle`
4. **Pushes** to GitHub (`ajacobusa/members-reader`)
5. **(Optional) off-site** copy to Google Drive (if `BACKUP_TO_DRIVE=1`)

Run it on demand anytime:
```
python -m quoteforge.admin backup-all
```

## How to restore

### Fast path — one command
```
python -m quoteforge.admin restore-all
```
- Restores the **database** from the newest snapshot (reversible — it snapshots the
  current DB first).
- Prints the exact command to restore the **code** from the local bundle.

### Restore the code to a fresh folder (full disaster recovery)
```
python -m quoteforge.admin restore-all --into C:\Joffiels-Restored
```
This clones the complete repo (all history) from the local bundle into a new,
empty folder. Then:
```
cd C:\Joffiels-Restored
pip install -e ".[dev]"
```

### Restore only the database (to a specific snapshot)
```
python -m quoteforge.admin restore "C:\...\db_backups\quoteforge_<timestamp>.db"
```
(omit the path to use the newest snapshot)

### If the whole machine is lost
You have three independent copies — recover from whichever is available:
1. **GitHub** (preferred): `git clone https://github.com/ajacobusa/members-reader.git`
2. **Local bundle** (on a backup drive): `git clone joffiels_full_backup.bundle restored`
3. **Google Drive** (if enabled): download `backup_<date>.bundle`, then
   `git clone backup_<date>.bundle restored`

Then restore the database from the newest `db_*.sqlite3` / snapshot via
`restore-all` (point `OUTPUT_DIR` at where you placed the db_backups).

## Enabling off-site (Google Drive)
1. Create a Google Cloud **service account**, download its JSON key.
2. Create a Drive folder; **share it** with the service-account email.
3. In `.env`:
   ```
   BACKUP_TO_DRIVE=1
   GOOGLE_DRIVE_FOLDER_ID=<the folder id from its URL>
   GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\to\service-account.json
   ```
4. Verify with `python -m quoteforge.admin backup-all` — the "Off-site" line should
   read `uploaded db+bundle`.

## Retention
`BACKUP_RETENTION_DAYS` (default 3) controls how many days of DB snapshots are kept;
the newest is always kept. The git bundle is refreshed in place each run.
