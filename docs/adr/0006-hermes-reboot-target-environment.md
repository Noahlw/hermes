---
status: accepted
---

# Hermes reboot target environment: Oracle Cloud free tier Ampere A1, Ubuntu 24.04 LTS aarch64, provider-agnostic install artifacts

The #80 grilling established the install contract (ADR 0005); this ADR records where the fresh install runs, settled by grilling ticket #78. The old VM is deleted; a new VM was created manually in the Oracle Cloud console.

Constraints already on record: the target is Oracle Cloud free tier (2 CPU / 12 GB RAM). The original D4 premise "cannot serve Ollama" was **corrected by D-C (2026-08-04)**: embedding-class models run locally (nomic-embed-text, 137M params — ~1 s/chunk, 768-dim, ~40 MB RSS); LLM-class serving stays remote (MiniMax-M3, D-D). See the correction section below.

## Decision

1. **Target machine — Oracle Cloud free tier, Ampere A1 (ARM, 2 OCPU / 12 GB RAM).** This is the only free-tier shape that fits the V1 stack (two Postgres instances + pgvector, Honcho, gateway, cron, Tailscale, MCP server); the AMD E2.1.Micro shape (1/8 OCPU / 1 GB) is excluded. Sizing is verified sufficient: the old VM ran the heavier triple-stack memory setup on the same shape; the current stack adds only embedding-class Ollama (~40 MB RSS, D-C).
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

## Correction — local embeddings are runnable (D-C, 2026-08-04)

Decision C of #43 landed on **local Ollama** for embeddings, reversing the
"cannot serve Ollama" constraint above:

- `nomic-embed-text` (137M params, 274 MB) benchmarks on this exact shape:
  ~1 s per ~350-token chunk, 768-dim output, Ollama server RSS ~40 MB,
  5.9 GB RAM free — comfortably inside 12 GB.
- The premise was true only for 7B-class LLM serving, which remains out of
  scope (MiniMax-M3 via API, D-D).
- Ollama binds `127.0.0.1:11434` only; zero public exposure posture
  unchanged (D3). The Honcho embedding columns were migrated to
  `vector(768)` to match, and the `honcho` API/deriver verified live
  (semantic search round-trip, 2026-08-04).
