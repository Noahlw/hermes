# docs/archive

This directory holds repo-root artifacts that were superseded by the
Hermes reboot map [#76](https://github.com/Noahlw/hermes/issues/76) and
its restructure ticket [#81](https://github.com/Noahlw/hermes/issues/81).

These files pinned paths, commands, and runtime facts to the **deleted**
Oracle VM (`100.79.87.93`, `/home/ubuntu/.hermes/`). Under the reboot
that VM is gone, so the documents cannot be assumed; they are retained
here (via `git mv`) for history only and **must not** be cited as
install-time truth.

## Archived on 2026-08-04 (ticket #81)

| File | Reason for archival |
| --- | --- |
| `hermes-v1-handoff.md` | Pre-reboot handoff memo pinned to the deleted VM; superseded by `CONTEXT.md` reboot terms and `INSTALL.md`. |
| `wayfinder-kickoff-prompt.md` | Initial Wayfinder kickoff prompt for map #76; superseded by the accepted ADRs (`docs/adr/0004`, `0005`, `0006`) and the live install runbook. |

## What to use instead

- **Install path**: top-level `INSTALL.md` + `setup/install.sh`.
- **Env contract**: top-level `.env.example`.
- **Runtime decisions**: `docs/adr/` (in particular `0004-hermes-agent-integration-model.md`, `0005-hermes-reboot-install-contract.md`, `0006-hermes-reboot-target-environment.md`).
- **Domain glossary**: `CONTEXT.md` (reboot terms recorded inline).
- **Fresh-install verdict**: `docs/research/2026-08-04-fresh-install-inventory.md`.

Nothing here is invoked at install time. Anything reading these files
should be updated to cite the reboot docs above.