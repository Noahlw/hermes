---
status: accepted
---

# Hermes reboot target environment: Oracle Cloud free tier Ampere A1, Ubuntu 24.04 LTS aarch64, provider-agnostic install artifacts

The #80 grilling established the install contract (ADR 0005); this ADR records where the fresh install runs, settled by grilling ticket #78. The old VM is deleted; a new VM was created manually in the Oracle Cloud console.

Constraints already on record: the target is Oracle Cloud free tier (2 CPU / 12 GB RAM), which cannot serve Ollama — embeddings must not depend on local model serving (ADR 0005, #80 D4).

## Decision

1. **Target machine — Oracle Cloud free tier, Ampere A1 (ARM, 2 OCPU / 12 GB RAM).** This is the only free-tier shape that fits the V1 stack (two Postgres instances + pgvector, Honcho, gateway, cron, Tailscale, MCP server); the AMD E2.1.Micro shape (1/8 OCPU / 1 GB) is excluded. Sizing is verified sufficient: the old VM ran the heavier triple-stack memory setup on the same shape, and this stack is lighter (no Ollama).
2. **OS baseline — Ubuntu 24.04 LTS (noble), aarch64.** Chosen over Oracle Linux 9: the repo's provision scripts are apt-based and pin `postgresql-16` + `postgresql-16-pgvector`, which exist natively in noble's repos. Oracle Linux 9 would require porting the entire scripted core of the install contract to dnf + PGDG (pgvector is not in OL9 repos).
3. **Posture — provider-agnostic artifacts; manual VM creation.** The install contract stays pure apt/systemd/SSH/Tailscale with no Oracle-specific tooling and no OCI credentials in the repo. VM creation is a documented Oracle-console step (Ampere A1, 2 OCPU / 12 GB, Ubuntu 24.04 aarch64) and has already been performed; INSTALL.md documents it for future rebuilds.

## Considered options

- Oracle Cloud free tier Ampere A1 (ARM) — chosen; matches old setup, zero cost, stack fits
- AMD E2.1.Micro free tier — rejected: 1 GB RAM cannot hold the stack
- Other providers (Hetzner et al.) — rejected: cost for zero benefit
- Local machine — rejected: non-disposable target triggers the ADR 0005 D2 redo-semantics caveat, needs always-on for Discord/cron
- Oracle Linux 9 (aarch64) — rejected as baseline: forces dnf + PGDG port of the apt-based provision scripts
- OCI CLI automation of VM creation — rejected: one-time step, adds a credential class, ties repo to Oracle

## Consequences

- The first INSTALL.md step verifies the OS baseline (Ubuntu 24.04 aarch64) before any scripted phase runs.
- #81 (repo restructure) needs **no script porting** — the apt-based provision scripts run unmodified on the chosen baseline.
- arm64 is a solved constraint: Postgres 16, pgvector, age, rclone all ship arm64 builds; the Python package is arch-agnostic.
- If the created VM is later found to be a different image (e.g. Oracle Linux), the scripted core of ADR 0005 must be ported to dnf + PGDG before prototype #77 executes.
