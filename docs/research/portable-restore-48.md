# Portable restore: Drive dumps (#48)

**Wayfinder ticket:** [#48](https://github.com/Noahlw/hermes/issues/48)  
**Parent:** [#38](https://github.com/Noahlw/hermes/issues/38) · MEM-6 from [#41](https://github.com/Noahlw/hermes/issues/41)  
**Branch:** `task/48-portable-restore`  
**Status:** locks grilled 2026-07-27; spec published on #48 as ready-for-agent

## Locked decisions

| ID | Decision | Consequence |
|---|---|---|
| **MEM-6** (from #41) | Three Postgres dumps + secrets path | Hermes DB, codebase_index DB, Honcho Postgres; app from GitHub; secrets not in plain Drive |
| **R-1** | **Encrypted secrets archive on Google Drive + separate unlock key file** | Secrets tarball is uploaded to Drive **encrypted**. A generated **key file** (not on Drive) unlocks it. On restore, operator points the agent/script at that key file. Plaintext secrets never live on Drive. |
| **R-2** | **`age` encryption with generated identity file** | Unlock key = `age` private identity file (off-Drive). Secrets archive encrypted to the matching public recipient. Restore: `age -d -i <keyfile>`. |
| **R-3** | **Per-DB `pg_dump` custom format** | Each run produces `hermes.dump`, `codebase_index.dump`, `honcho.dump` (custom format). Restore via `pg_restore`. |
| **R-4** | **14 daily + 4 weekly on Drive** | Daily under `pg/daily/`; weekly under `pg/weekly/`. Prune older than policy via rclone. |
| **R-5** | **Same Drive folder, `hermes-pg/` prefix** | Reuse folder ID `17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM` / `gdrive:`. Layout: `hermes-pg/daily/<date>/`, `hermes-pg/weekly/<date>/`, `hermes-pg/secrets/secrets.age`. |
| **R-6** | **Minimal Hermes runtime secrets in archive** | Encrypted payload: `~/.hermes/.env` (or filtered token export) + rclone config if needed. Not SSH keys, not full `~/.hermes/`, not Honcho volumes. |
| **R-7** | **Hermes `cron/jobs.json` script job** | Daily dump via new `backup_postgres_drive.sh`; weekly via `--weekly` or day-of-week in same script. Follows cognee/Neo4j cron pattern. |
| **R-8** | **Hybrid close for #48** | Close after live dump+rclone upload, cron enabled, same-VM restore smoke (`pg_restore` + `age -d`), and a written fresh-VM runbook. Full second-machine drill is non-blocking follow-up. |

## Observed VM baseline (2026-07-27)

| Item | State |
|---|---|
| Hermes Postgres | `127.0.0.1:5433` — DBs `hermes`, `codebase_index` |
| Honcho Postgres | Docker `pgvector/pgvector:pg15` on `127.0.0.1:5432` |
| rclone | Present; remote `gdrive:`; existing folder ID `17yovLP4BK1L_2jJKXbu4H4F-1kiGXzQM` (used by `backup_cognee.sh`) |
| Neo4j Drive cron | Disabled (`f83f0a829862` enabled=false) |
| Existing scripts | `backup_cognee.sh` (active pattern); `backup_neo4j.sh.disabled.*` |
