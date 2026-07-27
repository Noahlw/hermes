---
name: 41 hybrid close
overview: "Execute MEM-8 hybrid close for GitHub #41: finalize locked memory research docs, uninstall neo4j/Mem0/Qdrant on the Hermes VM with verify gates, keep Honcho healthy, then comment and close the ticket. Portable-restore cron and new Postgres DBs are explicitly out of scope."
todos:
  - id: task1-docs
    content: Persist plan file + finalize MEM docs + commit/push
    status: in_progress
  - id: task2-neo4j
    content: "VM: stop neo4j, stamp data, disable Drive backup cron"
    status: pending
  - id: task3-mem0-qdrant
    content: "VM: stop Qdrant, stamp mem0.json, clean hermes wrapper, restart gateway"
    status: pending
  - id: task4-verify-close
    content: "Live ALL_PASS verify, record in docs, close #41, file follow-up issues"
    status: pending
isProject: false
---

# Issue #41 Hybrid Close Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close GitHub [#41](https://github.com/Noahlw/hermes/issues/41) under **MEM-8**: land MEM-1…8 locks in-repo, remove neo4j + Mem0 + standalone Qdrant on the live VM, verify Honcho remains the working-memory provider, then comment and close the issue.

**Architecture:** Research docs are the source of truth for locks. VM work mirrors the AgentMemory disable pattern (`*.disabled.<UTC>` stamps, no interactive `sudo`). Honcho compose and `memory.provider: honcho` stay up. Two new Postgres DBs and Drive portable-restore cron are **not** built here.

**Tech Stack:** Git/`gh`, SSH to `ubuntu@100.79.87.93` (`~/.ssh/hermes-vm-leaked`), Docker on VM, Hermes `config.yaml` / `cron/jobs.json`, Markdown research docs.

## Global Constraints

- MiniMax-only and Discord-only policies from #39 remain untouched.
- Do not stop or reconfigure Honcho (`/home/ubuntu/honcho-self-hosted`).
- Do not delete Drive Neo4j history until container/data are disabled; retire the cron job that creates new Neo4j dumps.
- Secrets: never print `.env` values; report key names only.
- Destructive git (force-push, hard reset, branch delete) requires explicit user approval — not needed for this plan.
- Branch: work on `research/memory-system-evaluation`; commit docs there; push to `github` remote.
- Plan artifact copy: also save this plan to [`docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md`](docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md) on execute (directory may need creating).

## File Structure & Changes

| Path | Responsibility |
|---|---|
| [`docs/research/memory-system-evaluation.md`](docs/research/memory-system-evaluation.md) | MEM locks, VM baseline, executive finding; mark ticket closable after verify |
| [`CONTEXT.md`](CONTEXT.md) | Glossary terms already updated in grill; ensure consistent with MEM-5/6/7/8 |
| [`docs/use-case-specification.md`](docs/use-case-specification.md) | §6.5 memory table + §11 debt: mark neo4j/Mem0/Qdrant uninstall + #41 closed |
| [`docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md`](docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md) | Durable copy of this plan |
| VM `/home/ubuntu/.hermes/cron/jobs.json` | Disable/remove `Backup Neo4j to Google Drive` (`id: f83f0a829862`) |
| VM `/home/ubuntu/.hermes/mem0.json` | Rename to `mem0.json.disabled.<TS>` |
| VM Docker `neo4j`, `qdrant_mem0` | Stop + rename/move data dirs; do not remove geo-auditor/Honcho/Open WebUI |
| VM `/usr/local/bin/hermes` | Strip or no-op `MEM0_DEFAULT_APP_ID` exports (wrapper currently sets them) |
| GitHub #41 | Closing comment + `gh issue close` |

## What Already Exists

- Grill locks MEM-1…8 already drafted in [`docs/research/memory-system-evaluation.md`](docs/research/memory-system-evaluation.md) and [`CONTEXT.md`](CONTEXT.md) (uncommitted local edits on branch).
- AgentMemory uninstall pattern on VM (`*.disabled.20260727T024441Z`) — reuse for neo4j/Mem0/Qdrant.
- Live facts: `memory.provider: honcho`; containers `neo4j` (bind `~/.hermes/neo4j/data`), `qdrant_mem0` (bind `~/mem0-local/qdrant_data`); cron job `backup_neo4j.sh` every 1440m; `/usr/local/bin/hermes` exports `MEM0_DEFAULT_APP_ID`.
- Existing scripts on VM: `~/.hermes/scripts/backup_neo4j.sh` (retire from cron only; may leave file stamped).

## Not In Scope

- Provisioning Hermes Postgres or codebase-index Postgres (MEM-3/4 implementation).
- Google Drive portable-restore cron for three Postgres dumps (MEM-6 implementation).
- Personal-advisor news/email features, MCP tools (#42), embeddings (#43), PopIdea (#46).
- Uninstalling Honcho, Ollama, Open WebUI, or geo-auditor.
- Merging `research/memory-system-evaluation` into `master` (optional after close; not required to close #41).

## ASCII Diagrams

```text
Before:  Hermes → Honcho
         + neo4j + qdrant_mem0 + mem0.json + neo4j Drive cron

After:   Hermes → Honcho (verified)
         neo4j/qdrant/mem0 → *.disabled.<TS>
         neo4j Drive cron → disabled/removed
         docs MEM-1..8 locked → #41 CLOSED

Follow-up tickets (not this plan):
         Hermes Postgres + codebase-index Postgres
         Drive backup of those three Postgres DBs (+ Honcho)
```

## Failure Modes & Gaps

- Stopping `qdrant_mem0` may break any forgotten Mem0 client paths; mitigate by confirming `memory.provider` is `honcho` and gateway stays active after restart.
- Neo4j data move while container running can corrupt; always `docker stop` first.
- Cron job disable must not break other jobs (`ollama-keep-alive`, `vm-health-check`, weekly cleanup).
- Honcho `/` returns 404 today — health check must use a known-good endpoint or `docker compose ps` healthy, not HTTP 200 on `/`.
- Uncommitted grill edits must be committed before close comment references them.

## Parallelization / Worktree Strategy

- Single worktree: current checkout `/Users/noah.wong/orca/projects/Hermes` on `research/memory-system-evaluation`.
- Docs commit can happen before or after VM ops; prefer **docs finalize → VM ops → verify → issue close** so the closing comment can cite commit SHA.
- No parallel worktrees.

---

### Task 1: Persist plan + finalize research docs

**Files:**
- Create: `docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md`
- Modify: `docs/research/memory-system-evaluation.md`
- Modify: `CONTEXT.md` (only if glossary drift vs MEM-5/6/7/8)
- Modify: `docs/use-case-specification.md` (§6.5 table + §11 item 11)

**Interfaces:**
- Consumes: MEM-1…8 locks already in research doc
- Produces: Commit on `research/memory-system-evaluation` whose SHA is cited on #41

- [ ] **Step 1: Write plan file**

Copy this approved plan into `docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md` (create `docs/superpowers/plans/` if missing).

- [ ] **Step 2: Mark research doc closable**

In `docs/research/memory-system-evaluation.md`: set ticket status to hybrid-close in progress / ready; ensure locked-decisions table includes MEM-1…8; add a “Close checklist” subsection listing the three live verifies (neo4j gone, Mem0/Qdrant gone, Honcho healthy).

- [ ] **Step 3: Update use-case spec debt**

In `docs/use-case-specification.md` §6.5: change Qdrant/mem0/neo4j fate from “deferred to #41” to “MEM-5/7 uninstall (hybrid close)”; Honcho to “MEM-2 retained”. In §11 item 11: mark memory-stack cleanup as resolved by #41 MEM locks + pending live verify.

- [ ] **Step 4: Commit docs**

```bash
git add docs/superpowers/plans/2026-07-27-memory-41-hybrid-close.md \
  docs/research/memory-system-evaluation.md CONTEXT.md docs/use-case-specification.md
git commit -m "$(cat <<'EOF'
docs(#41): lock MEM-1–8 and prepare hybrid close

EOF
)"
git push github HEAD
```

Expected: push succeeds; note commit SHA.

---

### Task 2: Uninstall neo4j on VM + retire Drive backup cron

**Files (VM):**
- Modify: `/home/ubuntu/.hermes/cron/jobs.json` (disable/remove job `f83f0a829862`)
- Stop/rename: Docker container `neo4j`; data dir `/home/ubuntu/.hermes/neo4j`
- Optional stamp: `/home/ubuntu/.hermes/scripts/backup_neo4j.sh` → `backup_neo4j.sh.disabled.<TS>`

**Interfaces:**
- Consumes: SSH `ubuntu@100.79.87.93` with key `~/.ssh/hermes-vm-leaked`
- Produces: `neo4j` not running; ports `7474`/`7687` closed; cron job not enabled

- [ ] **Step 1: Preflight snapshot**

SSH and record: `docker ps --filter name=neo4j`, `ss -tln | grep -E '7474|7687'`, cron job JSON entry for `f83f0a829862`.

- [ ] **Step 2: Stop and disable neo4j**

```text
TS=$(date -u +%Y%m%dT%H%M%SZ)
docker stop neo4j
docker rename neo4j neo4j.disabled.$TS   # or docker rm only after data moved
mv /home/ubuntu/.hermes/neo4j /home/ubuntu/.hermes/neo4j.disabled.$TS
```

Do not `docker rm` until rename/move succeeded. Prefer stop + rename container + move data bind dir (AgentMemory-style).

- [ ] **Step 3: Disable Neo4j Drive cron**

Edit `jobs.json` so job `f83f0a829862` has `enabled: false` **or** remove that job object entirely. Leave other jobs intact. Stamp `backup_neo4j.sh` with `.disabled.$TS` if present.

- [ ] **Step 4: Verify neo4j removal**

Expected: `docker ps -a --filter name=neo4j` shows only `*.disabled.*` or nothing running; `ss` shows no `7474`/`7687`; jobs.json has no enabled Neo4j backup.

---

### Task 3: Uninstall Mem0 + Qdrant on VM + clean Hermes wrapper

**Files (VM):**
- Stop/rename: Docker `qdrant_mem0`; data `/home/ubuntu/mem0-local/qdrant_data`
- Rename: `/home/ubuntu/.hermes/mem0.json` → `mem0.json.disabled.<TS>`
- Modify: `/usr/local/bin/hermes` — remove `MEM0_DEFAULT_APP_ID` export logic (keep exec-to-venv behavior)
- Confirm: `/home/ubuntu/.hermes/config.yaml` still has `memory.provider: honcho`

**Interfaces:**
- Consumes: Task 2 complete (order flexible vs Task 2)
- Produces: no listeners on `6333`/`6334`; no live `mem0.json`

- [ ] **Step 1: Preflight**

Record `docker ps --filter name=qdrant`, `ss` for 6333/6334, presence of `mem0.json`, and `memory.provider` from config.

- [ ] **Step 2: Stop Qdrant + stamp Mem0 config**

```text
TS=...
docker stop qdrant_mem0
docker rename qdrant_mem0 qdrant_mem0.disabled.$TS
mv /home/ubuntu/mem0-local /home/ubuntu/mem0-local.disabled.$TS   # or only qdrant_data
mv /home/ubuntu/.hermes/mem0.json /home/ubuntu/.hermes/mem0.json.disabled.$TS
```

- [ ] **Step 3: Clean wrapper**

Backup `/usr/local/bin/hermes` to `hermes.bak.$TS`, then rewrite wrapper without MEM0 exports (still exec Hermes venv entrypoint). Requires `sudo -n` if not writable by ubuntu — if sudo fails, move wrapper under `~/.local/bin` only if that is what PATH uses; do not hang on password sudo.

- [ ] **Step 4: Restart gateway + verify**

`systemctl --user restart hermes-gateway.service`  
Expected: active; `ss` shows gateway `8642`; no `6333`/`6334`; `memory.provider` still `honcho`.

---

### Task 4: Live verify MEM-8 checklist + close #41

**Files:**
- Modify: `docs/research/memory-system-evaluation.md` (record verify timestamp/results)
- GitHub: issue #41 comment + close

**Interfaces:**
- Consumes: Task 1 commit SHA; Tasks 2–3 verify output
- Produces: #41 CLOSED with comment linking commit + verify table

- [ ] **Step 1: Run all-pass verify script over SSH**

Must print boolean checks and final `ALL_PASS` only if:

1. neo4j not listening / not running as live container  
2. qdrant_mem0 not listening / not running  
3. `mem0.json` absent (only `*.disabled.*`)  
4. `memory.provider == honcho`  
5. Honcho compose still running (`docker compose -f /home/ubuntu/honcho-self-hosted/docker-compose.yml ps` healthy or equivalent)  
6. `hermes-gateway.service` active  
7. Neo4j backup cron not enabled  

- [ ] **Step 2: Record verify in research doc + commit**

Short “Verified 2026-07-27” block under locked decisions; commit + push.

- [ ] **Step 3: Comment and close #41**

```bash
gh issue comment 41 --repo Noahlw/hermes --body "..."
gh issue close 41 --repo Noahlw/hermes --reason completed
```

Comment must include: MEM-1…8 summary, commit SHAs, live verify table, and explicit follow-ups (Postgres provisioning ticket; portable-restore cron ticket) as non-blocking.

- [ ] **Step 4: File two follow-up GitHub issues (if none exist)**

1. Provision Hermes Postgres + codebase-index Postgres (MEM-3/4)  
2. Portable restore: Drive dumps of Hermes DB + codebase-index DB + Honcho Postgres (MEM-6)  

Label appropriately (`wayfinder:task`); body references #41 and #38.

---

## Self-Review (writing-plans)

1. **Spec coverage:** MEM-8 blockers covered (docs + three uninstalls + Honcho verify + close). MEM-3/4/6 implementation deferred via follow-up issues.  
2. **Clarity:** Exact VM paths, container names, cron id, SSH host/key pattern from prior #39 ops.  
3. **Reversibility:** `*.disabled.<TS>` stamps allow rollback by rename + `docker start`.  
4. **Minimalism:** No new Postgres, no Drive restore scripts, no news/email features in this plan.