---
status: accepted
---

# Persona policy layer integrates into hermes-agent via pre_gateway_dispatch, one profile per persona

Hermes V1's persona contract gate (`hermes/personas/`, this repo) needs to actually govern the VM's live Discord and MCP traffic. The VM runs `NousResearch/hermes-agent` v0.15.1 as a working gateway (`hermes-gateway.service`, confirmed live 49+ days). We verified against hermes-agent's public source (commit `d71033a`) rather than assuming:

- **Integration seam**: hermes-agent exposes a real, production-wired `pre_gateway_dispatch` plugin hook, invoked in `GatewayRunner._handle_message` (`gateway/run.py`) before auth/pairing and before agent dispatch. Plugins return `{"action": "skip"|"rewrite"|"allow"}`. Verified by locating the actual `invoke_hook("pre_gateway_dispatch", ...)` callsite directly (GitHub's code search missed it on this 10k+ line file; found via full-file fetch + local search).
- **No LLM intent classifier precedes routing**: Discord message dispatch (`_dispatch_discord_message` → `_handle_message`) is deterministic (mention/auth/command checks) before any model call in `agent/conversation_loop.py`. Our regex-based `_infer_action` in `adapters.py` does not compete with an existing LLM router at this stage.
- **Discord bot tokens are not a list**: `PlatformConfig.token` is a scalar per platform. The only path to multiple Discord bot identities is hermes-agent's **profile multiplexing** — each profile is a fully isolated `HERMES_HOME` (own `config.yaml`, `.env`, memory, sessions, skills, cron, logs), and same-token reuse across profiles is explicitly refused (`gateway/run.py`).
- **Profile-scoped `honcho.json` gives each profile its own Honcho `ai_peer` identity** (`plugins/memory/honcho/client.py`: `resolve_active_host()` derives a per-profile host key; `ai_peer=resolved_host`). This means the profile mechanism satisfies persona identity separation for both Discord bot selection and Honcho peer naming in one integration point — though whether the underlying Honcho `workspace_id` (the actual cross-read isolation boundary) also varies per profile is **unverified** and remains an open gap, not a solved requirement.

## Decision

- Our `hermes/personas/contract_gate.py` / `adapters.py` functions are called from a hermes-agent plugin registered on `pre_gateway_dispatch`, not by rewriting hermes-agent's gateway or running a second competing Discord process.
- Five hermes-agent profiles are provisioned: `main_agent`, `assistant`, `tutor` (Discord-enabled via multiplex), `librarian`, `researcher` (MCP-invoked only, no Discord platform enabled). This matches the already-locked "one bot per persona" decision (`CONTEXT.md`: Discord persona bots) and the "five isolated Honcho peers" requirement (`CONTEXT.md`: Persona memory) with a single mechanism.

## Considered options

- Replace hermes-agent's gateway entirely with this repo's runtime (rejected: discards a working, 49-day-live system for no stated benefit)
- Run this repo as a sidecar process with its own Discord connection (rejected: hermes-agent explicitly refuses duplicate-token adapters; two processes would race for the same channel)
- Library import via the `pre_gateway_dispatch` hook, one hermes-agent profile per persona (chosen)

## Consequences

- The pure-Python contract-gate/adapter package still needs to be wrapped as an actual hermes-agent plugin (`PluginContext.register_hook("pre_gateway_dispatch", ...)`) and validated against real `MessageEvent` shapes — unstarted follow-up work, not done.
- hermes-agent's existing infrastructure becomes a real constraint: `discord.py`-based UI components (`ExecApprovalView`, `SlashConfirmView`) are already available for `confirm_delete`-style flows rather than needing new UI work.
- hermes-agent's own cron system (`cron/jobs.json`, `InProcessCronScheduler`) is the VM's existing cron — not a system to build alongside. The `main_agent` profile's `run_ops_digest` action becomes a new job in that profile's cron store.
- Deploying 5 profiles is heavier than "3 Discord tokens in one config" — each profile duplicates config/skills/memory/cron/logs directory structure. This is accepted because it buys genuine isolation the persona roster requires anyway, not because it was the cheapest option.
- **Open gap, explicitly not resolved by this ADR**: whether Honcho's `workspace_id` (not just `ai_peer` identity) is set per-profile is unverified. If it defaults to a shared `"hermes"` workspace across all 5 profiles, cross-persona memory reads may be technically possible even though each persona has a distinct peer name. This must be verified against the actual `honcho.json` config resolution path (or operationally, on the VM) before the "5 isolated Honcho peers" requirement can be marked satisfied.

## Amendment — D-B fork 2 (2026-08-04): this repo's hermes-agent becomes the V1 runtime

On 2026-08-04 the original VM — and with it the running hermes-agent v0.15.1
gateway (live 49+ days at the time of the original ADR) — was deleted. Only
the GitHub repo and the replacement VM remain; hermes-agent's gateway code is
not recoverable. Decision gate D-B (plan
`docs/omp-plans/2026-08-04-hermes-config-honcho.md`, fork 2) supersedes the
"replace vs sidecar vs plugin hook" framing above:


**Superseded context:** the original Decision, Considered options, and
Consequences sections above describe the deleted VM's architecture. They are
retained as historical record; every current-state claim they make (running
gateway, existing cron/UI infrastructure, the plugin-hook choice) describes a
system that no longer exists and is superseded by this amendment.

- **Rebuild decision:** this repo will gain a minimal hermes-agent runtime
  (`hermes_agent/`, implemented as plan Task 5) that
  imports the repo's policy layer (`hermes/personas/` —
  `route_discord_message()`, `route_mcp_tool()`, `pre_gateway_dispatch` hook
  semantics, `ExecApprovalView`-style approval flows) and honors the
  integration model recorded above as its interface contract: deterministic
  dispatch before any model call, one isolated profile per persona (profiles =
  separate `HERMES_HOME`), scalar Discord token per profile, same-token reuse
  refused, per-profile `honcho.json` `ai_peer`.
- The upstream facts verified against `d71033a` remain load-bearing for the
  rebuild even though the upstream code itself no longer runs.
- **This amendment records the decision only.** Implementation is tracked as
  Task 5 of the map #76 plan; no rebuilt runtime code exists in the repo at
  the time of writing.
- **Workspace-isolation gap (resolved):** the open gap above is closed
  operationally by plan Task 4 (2026-08-04): `setup/honcho-workspaces.py`
  provisions per-persona workspace AND peer `hermes_<persona>` (get-or-create
  against self-hosted Honcho v3.0.12, verified live + SQL), matching
  `hermes/profiles/config.py` `generate_honcho_json()`. The five
  workspace-level isolation boundaries now exist server-side.
- ADR 0005 D4 items 2–3 ("hermes-gateway.service up", "3 bots answer
  @-mention") re-target at the rebuilt `hermes-gateway.service` (Task 5
  acceptance).
