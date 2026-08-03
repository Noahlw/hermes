# Wayfinder Kickoff Prompt

> Copy-paste this into the session that will chart the Hermes V1 wayfinder map.

## Your job

Pick up the handoff at `hermes-v1-handoff.md` and run the wayfinder skill to create the map + tickets.

## Destination

A **Hermes Agent** on the user's Oracle VM (129.150.37.112) that serves three roles:
1. **Knowledge layer** — MCP tools for coding agents to query a 20–100 repo codebase wiki ("how does X work in repo Y?")
2. **Code plan implementor** — Hermes generates and executes implementation plans against codebases
3. **Research agent** — Background research, fact-gathering, structured findings
4. **Other use cases TBD** — The use-case research ticket must grill the user to discover additional ways Hermes fits into their life

These are all exposed via **MCP tools** over **Tailscale**. **MiniMax-M3 only.**

## Non-negotiables

- MiniMax-M3 only, no fallback chain
- Self-hosted on the VM at /home/ubuntu/.hermes/
- Tailscale for all cross-PC traffic. Zero public exposure.
- MCP tool surface — coding agents call Hermes as an MCP server
- General-purpose codebase wiki from GitHub repos

## Tickets from the handoff (order matters)

1. **Use-case research & grilling** — Map what the user will use Hermes for. List query patterns, define code-plan-implementor and research-agent workflows. **Grill the user** for additional use cases they haven't mentioned. Feeds everything below.

2–5 (parallel after ticket 1):
2. **Codebase indexing strategy** — Compare clone+embed vs. live RAG for 20–100 GitHub repos
3. **Memory system evaluation** — Compare Honcho (running) vs. newer alternatives for librarian + implementor + research use cases
4. **MCP tool surface design** — What tools does Hermes expose? Retrieve + plan-generation + research + whatever else use-case ticket discovers
5. **Embedding model research** — User handles with a prompt. Research prompt only

6. **Persona grill** — After use-case research reveals what Hermes does, grill what personas map to each use case

## Deferred (ticket but not sequenced)

- Monitoring / health checks
- SSH key rotation (leaked key still on VM)

## What's on the VM already

- Hermes Agent v0.15.1 via Docker Compose
- Triple-stack memory running (Qdrant + mem0 + agentmemory + Honcho)
- Tailscale up (VM: 100.79.87.93, Mac: 100.104.102.94)
- User-authored 5-step setup plan at /home/ubuntu/.hermes/hermes-setup-plan.md

## Wayfinder process

1. Read `hermes-v1-handoff.md`
2. Run `/grilling` and `/domain-modeling` to settle the destination
3. Map the frontier — breadth-first across the whole space
4. Create the map issue (label: wayfinder:map) as child of map #27 (or fresh map #39 — decide with user)
5. Create the 6 tickets as children of the map, wire blocking edges
6. Fire research subagents for any research tickets
7. Stop. Charting is one session's work. Hand-resolve nothing.

## Reference

- Handoff: `Hermes/hermes-v1-handoff.md`
- Old map (closed): #27
- Old chart (all superseded): #28–#36
