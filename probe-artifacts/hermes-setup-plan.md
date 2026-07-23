# Hermes Setup Plan — AI App Developer Workflow

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Default Profile (Orchestrator)                       │
│  Role: VM maintainer · Deployer · Project planner    │
│  Model: deepseek-v4-flash (this session)              │
│  Gateway: Telegram (running)                          │
│  Honcho peer: hermes (observing ubuntu)               │
│                                                        │
│  Spawns via delegate_task:                             │
│    └── Subagents ──────────────────────────┐           │
│        Model: openrouter/deepseek-v4-flash │           │
│        Fallback 1: github-codex/Codex 5.2 │           │
│        Fallback 2: deepseek/deepseek-v4    │           │
│                                            │           │
│  Cron: VM health · Memory server · Logs    │           │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  Coder Profile (Worker)                                │
│  Role: Code · Test · Feature implementation           │
│  Model: gemini-3.1-pro-preview                        │
│  Backend: Docker (hermes-personal:latest)              │
│  Honcho peer: coder (isolated memory)                  │
│  Workspace: ~/.hermes/profiles/coder/workspace/        │
└──────────────────────────────────────────────────────┘
```

---

## Step 1 — Default Profile: Subagent Model Chain

Subagent fallback chain (3 tiers):

| Tier | Provider | Model | Auth |
|------|----------|-------|------|
| 1 | `openrouter` | `deepseek/deepseek-v4-flash` | OPENROUTER_API_KEY ✓ |
| 2 | `openai-codex` | Codex 5.2 | OAuth (needs login) |
| 3 | `deepseek` | `deepseek-v4-flash` | DEEPSEEK_API_KEY ✓ |

**Config changes:**

```yaml
delegation:
  provider: openrouter
  model: deepseek/deepseek-v4-flash
  max_concurrent_children: 5
  child_timeout_seconds: 900
  max_spawn_depth: 2          # subagents can delegate sub-tasks

fallback_providers: [openrouter, openai-codex, deepseek]
```

The `fallback_providers` cascade: if OpenRouter fails (rate limit / outage), fallback → Codex 5.2 via GitHub Copilot OAuth → DeepSeek API direct.

**Authentication needed:**
- `hermes auth` → OpenAI Codex (for fallback tier 2)
- DEEPSEEK_API_KEY already in .env (for fallback tier 3)

---

## Step 2 — Default Profile: Token Optimization

| Setting | Current | New | Saves |
|---------|---------|-----|-------|
| `compression.threshold` | 70% | 65% | Compress sooner, keep context leaner |
| `compression.target_ratio` | 20% | 15% | More aggressive compression |
| `compression.protect_last_n` | 20 | 15 | Keep less recent fluff |
| `honcho context budget` | uncapped | 4000 tokens | Prevents memory context from ballooning |
| `display.tool_preview_length` | 0 | 0 ✓ | (already minimal — no extra tokens) |
| `display.user_message_preview.first_lines` | 2 | 1 | Less verbose resume |
| `display.user_message_preview.last_lines` | 2 | 1 | |
| `display.resume_max_user_chars` | 300 | 150 | Shorter session resumes |
| `display.resume_max_assistant_chars` | 200 | 100 | |
| `display.resume_exchanges` | 10 | 5 | |
| `display.show_cost` | off | on | Track token spend |
| `agent.max_turns` | 150 | 150 ✓ | Keep (already reasonable) |
| `memory.memory_char_limit` | 5000 | 5000 ✓ | Already bumped |
| `memory.user_char_limit` | 3000 | 3000 ✓ | Already bumped |
| `memory.flush_min_turns` | 3 | 3 ✓ | Already tuned |

**Honcho dialectic tuning:**
```yaml
# honcho.json
"hosts": {
  "hermes": {
    "dialecticCadence": 3,         # was 1 — every 3 turns, not every turn
    "dialecticDepth": 1,           # keep at 1 pass
    "contextCadence": 3,           # refresh base context every 3 turns
    "contextTokens": 4000,         # cap context injection to 4K tokens
  }
}
```

This reduces Honcho LLM calls from "every turn" to "every 3 turns" — same profile quality, 66% fewer tokens spent on internal reasoning.

---

## Step 3 — Default Profile: Config Polish

| Change | Command | Notes |
|--------|---------|-------|
| Config migration | `hermes doctor --fix` | v23 → v24 |
| Enable checkpoints | `hermes config set checkpoints.enabled true` | Safety net before deploys |
| GITHUB_TOKEN | Add to ~/.hermes/.env | Rate limit 60→5000/hr |
| Skills hub init | `hermes skills list` | First call initializes hub |
| Display: show_cost | `hermes config set display.show_cost true` | Track spend |
| Display: show_reasoning | `hermes config set display.show_reasoning true` | ✓ already on |

---

## Step 4 — Default Profile: VM Maintenance Cron

**Cron 1 — Daily VM health report:**
```
Schedule: 0 6 * * *     (every day 06:00 UTC)
Script:   ~/.hermes/scripts/vm_health.sh
          → checks: disk usage (>85% alert), uptime, memory, Hermes gateway status
Mode:     no_agent=true  (script output delivered verbatim)
```

**Cron 2 — Weekly deployment workspace cleanup:**
```
Schedule: 0 3 * * 0     (every Sunday 03:00 UTC)
Prompt:   "Check ~/projects/ for stale deployments older than 14 days.
           Report disk usage reclaimed vs current free space."
```

---

## Step 5 — Coder Profile: Full Fix

This profile is on config v17 (very outdated) and has no Honcho, no API keys, no tools beyond `hermes-cli`.

| Change | Details |
|--------|---------|
| Config migration | `hermes --profile coder doctor --fix` → v17→latest |
| Honcho setup | `hermes --profile coder honcho setup` → creates honcho.json with aiPeer=coder, peerName=ubuntu |
| Memory enable | `hermes --profile coder config set memory.provider honcho` |
| User profile | `hermes --profile coder config set memory.user_profile_enabled true` |
| Display: reasoning | `hermes --profile coder config set display.show_reasoning true` |
| Display: streaming | `hermes --profile coder config set display.streaming true` |
| Max turns | `hermes --profile coder config set agent.max_turns 150` |
| Toolsets | Add `terminal, file, web, skills, delegation, session_search` to `toolsets` list |
| API keys | Sync .env from default or set per-profile |
| Honjo peer | `hermes --profile coder honcho peer --user ubuntu` |
| Session strategy | `hermes --profile coder honcho strategy global` |

---

## Step 6 — Multi-Profile Memory Sync

```bash
hermes honcho sync
```

This propagates peer identity (`ubuntu`) across all profiles so Honcho recognizes you regardless of which profile spawns.

---

## Summary of All Changes

### Default profile (orchestrator) — 12 changes

1. delegation provider → openrouter
2. delegation model → deepseek/deepseek-v4-flash
3. delegation.max_concurrent_children → 5
4. delegation.child_timeout_seconds → 900
5. delegation.max_spawn_depth → 2
6. fallback_providers → [openrouter, openai-codex, deepseek]
7. compression.threshold → 65%
8. compression.target_ratio → 15%
9. compression.protect_last_n → 15
10. Honcho dialecticCadence → 3, contextTokens → 4000
11. checkpoints.enabled → true
12. Auth: login OpenAI Codex, add GITHUB_TOKEN

### Coder profile (worker) — 12 changes

1. Config migrate (v17→latest)
2. Honcho init + user peer
3. memory.provider → honcho
4. memory.user_profile_enabled → true
5. display.show_reasoning → true
6. display.streaming → true
7. agent.max_turns → 150
8. toolsets → expanded
9. API keys synced
10. honcho peer → ubuntu
11. honcho strategy → global
12. Honjo sync across profiles

### New cron jobs — 2

1. Daily VM health (06:00 UTC, no-agent script)
2. Weekly workspace cleanup (Sunday 03:00 UTC)

---

Want me to start executing? It'll take about 10 minutes total.
