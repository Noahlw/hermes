# Hermes Postgres migrations (#47)

Two logical databases, both on the same dedicated Hermes Postgres instance.

| DB | Purpose | Default port |
|---|---|---|
| `hermes` | Hermes ops, research evidence, audit, persona/task scope, session briefs, digest artifacts and allowlists | `5433` |
| `codebase_index` | Processed coding repositories: catalog, paths/symbols/chunks, FTS, embeddings, sync cursors (paired with #40 indexer) | `5433` |

Honcho keeps its own Postgres on `:5432` for peer/session memory.

## Apply migrations

```bash
cd /path/to/Hermes
./db/migrate.sh all     # or: hermes   /   codebase_index
```

Requires `psql` on the runner host (`postgresql-client-16`).

The runner records each applied filename in `schema_migrations` on the target
DB and skips already-applied files. It also uses `psql -1` so each file runs in
a single transaction.

## Connection defaults

| Var | Default |
|---|---|
| `HERMES_PGHOST` | `127.0.0.1` |
| `HERMES_PGPORT` | `5433` |
| `HERMES_PGUSER` | `$USER` (`postgres` fallback) |
| `HERMES_PGDB_HERMES` | `hermes` |
| `HERMES_PGDB_CODEBASE_INDEX` | `codebase_index` |

VM runs with `127.0.0.1`-only listen and local trust (`pg_hba` `trust` for
`127.0.0.1/32`) per **PG-3 / PG-4** in
[`docs/research/postgres-provisioning-47.md`](../research/postgres-provisioning-47.md).
Harden rotation is a later concern.

## Schema contents

`db/hermes/migrations/0001_init.sql` — Hermes DB core tables.
`db/codebase_index/migrations/0001_init.sql` — repo catalog, files, symbols,
chunks (with generated `tsvector` and GIN), `chunk_embeddings.vector(768)`,
`sync_cursors`, `schema_meta`.

Embeddings default dimension is `768` to match Ollama `nomic-embed-text`.
Changing the default is a #43 follow-up via a new migration.
