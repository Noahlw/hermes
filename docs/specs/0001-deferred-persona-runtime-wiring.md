# Hermes V1 persona runtime wiring (deferred elements of #62)

## Problem Statement

The persona contract gate (this repo's `hermes/personas/`, 62/62 tests, READY on both code-review axes) is now in place, but the three runtime surfaces that the gate exists to govern are still missing. On the VM there is no Discord identity bound to the Assistant, Tutor, or Main Agent personas; Main Agent's `run_ops_digest` action has no actual destination; and while the hermes-agent profile mechanism gives each persona a distinct Honcho `ai_peer` identity, whether that also gives them isolated Honcho `workspace_id` (the actual cross-read boundary) is unverified. Until these are wired, the gate is policy on paper — not policy at runtime.

## Solution

Per ADR 0004, the contract gate integrates as a hermes-agent `pre_gateway_dispatch` plugin, with five hermes-agent profiles (`main_agent`, `assistant`, `tutor` for Discord; `librarian`, `researcher` for MCP-only). This spec covers the three deferred implementation tickets that the gate alone does not unblock.

## User Stories

1. As the operator, I want the VM's Discord home channel to receive the @Assistant bot, so that task management works against the persona contract.
2. As the operator, I want the @Tutor bot, so that deep-dive tutoring routes through the Tutor contract.
3. As the operator, I want the @Main Agent bot, so that ops/escalation is reachable from Discord.
4. As the operator, I want the three bots to coexist on the home channel, so that no per-persona channel management is needed.
5. As the operator, I want @-mention to be the only routing signal, so that ambient channel chatter does not trigger any persona.
6. As a Discord user with a `manage_tasks` delete request, I want the bot to send a native button confirmation (Yes/No), so that task deletion is intentional and obvious.
7. As a Discord user, I want the button click to invoke the contract gate with `confirm_delete=True` automatically, so that I do not need to type a confirmation phrase.
8. As the operator, I want a daily ops digest in the Hermes database, so that historical digests are queryable and not lost.
9. As the operator, I want the same digest proactively posted to the Discord home channel, so that I see it without asking.
10. As the operator, I want the digest to fire daily at `0 7 * * *`, staggered one hour after the existing `vm-health-check` job (`0 6 * * *`), so that the digest can incorporate the morning's health check.
11. As the operator, I want every registered cron job (not just health checks) represented in the digest as a one-line status entry, so that the existing `≤ 200 token` / "one-line per check" budget in §10 is honored.
12. As the operator, I want the digest to be implemented in the `main_agent` hermes-agent profile, so that the cron entry lives in that profile's `cron/jobs.json` and is ticked by hermes-agent's existing in-process scheduler.
13. As the operator, I want the digest's destination table (`digests` on the Hermes database) to follow the existing migration pattern (`db/hermes/migrations/0001_init.sql` family), so that schema management stays consistent.
14. As the operator, I want each persona's Honcho memory to be isolated from the others, so that Assistant/Tutor/Main Agent super-set cannot read each other's working diaries.
15. As the operator, I want this isolation to be backed by distinct `workspace_id` (not just distinct `ai_peer` name), so that cross-read isolation is enforced at the Honcho backend, not only by convention.

## Implementation Decisions

### Ticket 1 — Discord bot wiring (3 bots via multiplex profiles)

- Three new hermes-agent profiles under `~/.hermes/profiles/`: `main_agent`, `assistant`, `tutor`. Each has its own `HERMES_HOME`, `config.yaml`, `.env`, `DISCORD_BOT_TOKEN`, `cron/`, `memory/`, `sessions/`, `skills/`, `logs/`.
- `gateway.multiplex_profiles: true` enabled in the default profile's config so the gateway serves all three.
- `profile_routing.yaml` (or equivalent route table) maps all three profiles to the same `DISCORD_HOME_CHANNEL` — they share one Discord channel; bot identity (the @-mention target) is what selects the persona.
- Same-token reuse across profiles is explicitly forbidden by hermes-agent; each profile's `DISCORD_BOT_TOKEN` must be a real, distinct bot token.
- A new hermes-agent plugin (in this repo, registered via `PluginContext.register_hook("pre_gateway_dispatch", ...)`) imports this repo's `hermes/personas/adapters.py` and calls `route_discord_message` on every inbound event.
- For `manage_tasks` delete requests (action refused with `confirm_required=True`): the plugin sends a native `discord.ui.View` confirmation (reusing the `ExecApprovalView` pattern) via `gateway.adapters[Platform.DISCORD].send(...)` and returns `{"action": "skip"}` to the gateway.
- A separate Discord interaction handler (not `pre_gateway_dispatch` — Discord interactions are not `MessageEvent`s) catches the button click and re-invokes the contract gate with `confirm_delete=True` set, then runs the deletion if the gate returns ALLOW.

### Ticket 2 — Native `confirm_delete` button flow

- A delete request that reaches the Assistant or Main Agent policy path without confirmation sends a native Discord `discord.ui.View` prompt with explicit Yes/No actions, reusing hermes-agent's existing `ExecApprovalView` pattern.
- The pre-dispatch plugin sends the prompt through the active Discord adapter and returns `{"action": "skip"}` so normal agent dispatch cannot perform the deletion concurrently.
- A separate Discord interaction handler authorizes the original requester/context, re-invokes the shared gate with `confirm_delete=True`, and calls the existing task deletion operation only after an ALLOW result. No/expired/duplicate/unauthorized interactions are safe no-ops.
- Tutor, Librarian, and Researcher requests cannot reach task deletion even when a confirmation button is clicked.

### Ticket 3 — Cron / digest (`run_ops_digest`)

- New `digests` table on the Hermes database (the `hermes` logical DB on the dedicated `hermes-pg` instance), following the existing migration convention in `db/hermes/migrations/0001_init.sql`. Schema: `id`, `created_at`, `window_start`, `window_end`, `summary_markdown`, `per_job_status` (jsonb).
- New cron job entry in the `main_agent` profile's `cron/jobs.json` at `0 7 * * *`, one hour after `vm-health-check` at `0 6 * * *`.
- Every registered cron job contributes one concise status line; total output stays within the existing `≤ 200 token` / “one-line status per check” budget. The job writes the digest row and posts identical rendered content to the Main Agent Discord adapter.
- First deployment will surface `weekly-workspace-cleanup`'s pre-existing 401 auth failure (a known VM fact per `docs/use-case-specification.md` §6.7) — that surfacing is correct behavior, not a regression; the failure itself is a separate ops ticket.

### Ticket 4 — Honcho isolation (5 personas, workspace-level)

- Five hermes-agent profiles total: `main_agent`, `assistant`, `tutor`, `librarian`, `researcher` (the last two are MCP-invoked and do not enable Discord).
- Each profile's `honcho.json` (`$HERMES_HOME/honcho.json`) carries a distinct `host` block. hermes-agent's `resolve_active_host()` already derives `hermes_<profile>` from the profile name; this must also flow into `HonchoClientConfig.workspace_id` so each profile's Honcho reads hit a distinct backend workspace, not just a distinct peer name.
- Verification on the VM must prove that `honcho.context(session_id, peer=...)` calls from one profile cannot retrieve messages stored under a different profile's session, while same-profile cross-session memory still works. The hermes-agent test seam `tests/gateway/test_multiplex_credential_isolation.py` is prior art.

## Ticket dependencies

- Ticket 1 has no blocker.
- Tickets 2, 3, and 4 each depend on Ticket 1 and are independent of one another.

## Testing Decisions


- **Test seams** (verified file paths):
  - `tests/gateway/test_pre_gateway_dispatch.py` (Ticket 1) — already used by hermes-agent to test the hook contract; this repo's plugin will be tested in the same shape.
  - `tests/gateway/test_discord_bot_auth_bypass.py` (Ticket 1) and `tests/gateway/test_discord_clarify_buttons.py` (Ticket 2) — confirmed; hermes-agent's prior art for bot auth and button interactions, which our `confirm_delete` view mirrors.
  - `tests/cron/test_cron_profile_isolation.py`, `tests/cron/test_jobs.py` (Ticket 3) — confirmed; hermes-agent's own cron profile-seam tests, mirrored for the new `ops-digest` job.
  - `db/hermes/migrations/0001_init.sql` is the existing migration convention; `digests` table follows that pattern with a new `0002_digests.sql` (or similar) sibling.
  - `tests/gateway/test_64674_multiplex_primary_token_scope.py`, `tests/gateway/test_multiplex_credential_isolation.py` (Ticket 4) — confirmed; hermes-agent's own profile/token isolation tests, mirrored for the Honcho `workspace_id` boundary.
- **Good tests**: external-behavior tests for each new artifact — does the new cron job fire and write to both destinations, does the button click invoke the gate with `confirm_delete=True`, do two profiles' Honcho reads actually return disjoint content.
- **Bad tests to avoid**: snapshotting Discord markdown output, mocking the LLM to make a decision the gate must make, asserting on `cron/jobs.json` literal formatting rather than the scheduler's view of it.
- **No new tests against this repo's existing gate** — that surface already has 62/62 passing tests. The new tests live in the hermes-agent plugin package or the new VM-side packages (digest table migrations, profile provisioning); this repo contributes the plugin registration code, not its own test fixtures.

## Out of Scope

- Developing the persona personas themselves (Tutor defaults, Assistant persona narrative, etc.) — those are upstream prompt concerns, not this ticket.
- Auto-deriving the cron digest content from MiniMax-M3 — the digest is a deterministic formatter over already-written cron output files; no model call.
- Adding new cron jobs beyond what already exists — the digest consolidates what's there.
- Telegram, Slack, WhatsApp, ACP — Discord only for V1.
- Per-persona private tooling (each profile is a copy of the standard toolset; if a profile needs tool restrictions, that is a separate, explicit persona-action decision).
- A new Honcho backend — we use the existing Honcho Postgres instance already on the VM; the change is configuration only, not infrastructure.

## Further Notes

- **Hard-to-reverse integration choices** (already locked in ADR 0004): the `pre_gateway_dispatch` seam and the 5-profile model. These are not up for re-decision in the tickets.
- **Open dependency**: whether hermes-agent's `workspace_id` derivation is fixed in the local checkout (this repo does not vendor hermes-agent; the change must go upstream or be applied to the live VM checkout). If upstream is the path, that is a separate filing.
- **Operational dependency**: three real Discord bot tokens must be created in the Discord developer portal and the operator must be on hand to authorize them on the home guild/channel. Schedule the deploy against the operator's availability.
- **VM fact check before each ticket starts**: confirm the `0 6 * * *` `vm-health-check` schedule has not drifted, confirm the four `cron/jobs.json` entries are still the only ones, confirm `weekly-workspace-cleanup` is still 401-failing (so we know the digest will surface it as expected).
- **Grill record** for these decisions: `docs/adr/0004-hermes-agent-integration-model.md` (Q1, Q2) and `CONTEXT.md` "Ops digest (deferred — design captured, not implemented)" + "confirm_delete UX (deferred — design captured, not implemented)" + "Contract gate integration" terms (Q3–Q6).
