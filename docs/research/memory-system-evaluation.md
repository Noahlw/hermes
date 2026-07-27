# Memory system evaluation for Librarian, Implementor, and Researcher personas

**Wayfinder ticket:** [Memory system evaluation for librarian, implementor, and research agents](https://github.com/Noahlw/hermes/issues/41)<br>
**Parent map:** [Wayfinder Map — Hermes V1 Implementation-Ready Specification](https://github.com/Noahlw/hermes/issues/38)<br>
**Research date:** 2026-07-23 (grill updates 2026-07-27)<br>
**Ticket status:** Hybrid close — docs locked 2026-07-27; live verify required before #41 close.

## Locked decisions (grill, 2026-07-27)

| ID | Decision | Consequence |
|---|---|---|
| **MEM-1** | **Hermes-owned canonical store + retrieval index** | Codebase knowledge, research evidence, and audit/events are Hermes SoT. Qdrant/pgvector are indexes only. Mem0/Honcho/Letta/LangMem may assist working memory, never own code/research truth. Session-start codebase briefs are built from the knowledge layer (#40), not from peer-chat memory. |
| **MEM-2** | **Keep Honcho for working / personal-advisor memory** | Reverted from Mem0 (D). V1 Assistant includes personal-advisor digests (news topics; email connectors may land later). Honcho owns peer/session/user modeling. Mem0/Qdrant working-memory collections are not required for that role — may idle or be cleaned later. Code/research truth still never lives in Honcho. |
| **MEM-3** | **Two-database split** | **Hermes DB** = Hermes operational/canonical data (audit, research evidence, persona scope, session-brief metadata, digest artifacts). **Codebase index DB** = processed repo knowledge layer only (#40). No single combined store. Honcho remains a third runtime for personal working memory, not a third “wiki DB.” |
| **MEM-4** | **Postgres for both DBs** | Hermes DB and codebase index DB are separate Postgres databases (or instances). Codebase index uses pgvector + FTS. Honcho keeps its own Postgres for peer/session memory. Resolves #40 IDX-3 engine deferral for the knowledge layer. |
| **MEM-5** | **Uninstall neo4j now** | Out of V1 stack (same class as AgentMemory). Existing Neo4j→Drive backup cron is retired with it. Durable recovery moves to Postgres DB backups (see MEM-6), not a graph dump. |
| **MEM-6** | **Portable restore: 3 Postgres dumps + secrets path** | Drive backups cover Hermes DB, codebase index DB, and Honcho Postgres. App/config from GitHub clone. Secrets stay on a separate encrypted/offline path. Repo working trees re-fetched from GitHub allowlist — not Drive. |
| **MEM-7** | **Uninstall Mem0 + standalone Qdrant now** | Out of V1. Working memory is Honcho; codebase vectors are Postgres+pgvector. Thin `mem0.json` and `qdrant_mem0` are removal targets before #41 hybrid close. |
| **MEM-8** | **Hybrid close for #41** | Close after research locks land **and** live verify: neo4j + Mem0 + Qdrant removed/disabled; Honcho remains healthy as `memory.provider`. Portable-restore cron and standing up the two new Postgres DBs are non-blocking follow-up tickets. |
| **D-MEM-3** (from #39) | AgentMemory uninstalled | Candidate “retain agentmemory” in the 2026-07-23 draft is obsolete. |

### Close checklist (MEM-8)

- [x] neo4j container not running / disabled stamp; ports 7474/7687 closed
- [x] Qdrant_mem0 container not running / disabled stamp; ports 6333/6334 closed
- [x] mem0.json absent (only *.disabled.*)
- [x] Hermes memory.provider == honcho (unchanged)
- [x] Honcho compose healthy
- [x] hermes-gateway.service active
- [x] Neo4j Drive backup cron not enabled

Verified 2026-07-27 UTC against `477290a`. neo4j/Mem0/Qdrant stamps TS 20260727T043504Z / 20260727T043428Z; Honcho retained as V1 working memory; gateway active on 8642.

### Observed VM baseline (re-verified 2026-07-27)

| Component | State |
|---|---|
| Hermes `memory.provider` | `honcho` (kept for V1 working memory — MEM-2) |
| Qdrant | Up — **MEM-7: uninstall** |
| mem0 | Thin `mem0.json` — **MEM-7: uninstall** |
| Honcho compose | Up (api/deriver/redis/pgvector) |
| neo4j | Up — **MEM-5: uninstall** |
| agentmemory | Removed |
| Ollama | Inference only — not memory |

## Scope and constraints

The handoff describes a self-hosted Hermes deployment on an Oracle VM, Tailscale-only connectivity, MCP as the consumer surface, and a formerly over-composed stack (Qdrant + mem0 + agentmemory + Honcho; agentmemory now gone) ([Hermes V1 planner handoff](../../hermes-v1-handoff.md)). The parent map additionally fixes isolated persona working memory, a shared codebase knowledge layer, explicit persona selection, and controlled delegation ([parent map](https://github.com/Noahlw/hermes/issues/38)).

This evaluation treats “memory” as four different data problems, not as one conversational-history feature:

1. **Persona working memory:** private task state, decisions, constraints, handoffs, and durable operating preferences.
2. **Shared codebase knowledge:** repository content indexed by revision, path, symbol, and line range; readable by all personas.
3. **Research evidence:** source URLs, retrieval dates, excerpts, claims, and confidence; writable by Researcher and readable by other personas.
4. **Audit/events:** append-only tool actions, writes, provenance links, and supersession history.

The key question is therefore not “which product remembers best?” It is “which component should own each data contract, and which component should only provide retrieval or extraction?”

## Executive finding

**MEM-1 locked:** Hermes owns canonical records; retrieval indexes and agent-memory products are not SoT for codebase/research. Keep Qdrant, or benchmark it against pgvector, as a retrieval index; store canonical records and provenance in a relational/document layer controlled by Hermes. Put persona working memory behind a small Hermes-owned adapter with an explicit `(persona_id, task_id, visibility)` scope.

**MEM-2 locked (revised):** Keep Honcho for V1 working / personal-advisor memory (Discord Assistant, prefs, news continuity). Mem0 is not the V1 working-memory SoT. Code/research still never live in Honcho.

**MEM-3 locked:** Two databases — **Hermes DB** (Hermes itself) and **codebase index DB** (processed repos from #40). They are not merged into one store.

**MEM-4 locked:** Both Hermes DB and codebase index DB are Postgres (separate DBs). Codebase index = Postgres + pgvector + FTS. Honcho retains its own Postgres for working memory.

**MEM-5 locked:** Uninstall neo4j for V1. Graph overlay is not required; recovery must not depend on Neo4j dumps.

**MEM-6 locked:** Portable restore = Google Drive dumps of Hermes DB + codebase index DB + Honcho Postgres; GitHub for code/config; secrets offline/encrypted. Repo clones re-fetched from allowlist.

**MEM-7 locked:** Uninstall Mem0 and standalone Qdrant (`qdrant_mem0`) for V1. No dual vector path beside Postgres+pgvector; no Mem0 beside Honcho.

**MEM-8 locked:** Hybrid close — docs + live uninstall verify (neo4j, Mem0, Qdrant); Honcho stays up. Portable-restore cron and new Hermes/codebase Postgres provisioning are follow-up tickets.

The current stack is over-composed for V1 if all four services write overlapping memories. A defensible V1 split is:

```text
Canonical records + audit/provenance (Postgres)
        ├── persona-private working memory (strict scope)
        ├── shared codebase records (read-only to personas)
        └── research evidence records (citation-required)

Qdrant (dense + sparse retrieval index over selected records)
        └── filtered by visibility, persona, task, repository, revision, and source type
```

Mem0 is the strongest candidate in the reviewed set for an optional working-memory extraction layer: its current OSS/API documentation exposes `user_id`, `agent_id`, and `run_id` scopes, metadata filters, history, async operations, reranking, and optional graph memory ([scoped search](https://docs.mem0.ai/core-concepts/memory-operations/search), [REST API](https://docs.mem0.ai/open-source/features/rest-api), [async memory](https://docs.mem0.ai/open-source/features/async-memory), [reranker search](https://docs.mem0.ai/open-source/features/reranker-search), [graph memory](https://docs.mem0.ai/open-source/features/graph-memory)). It still performs LLM-mediated extraction/update behavior and adds provider/storage operations, so it should not silently mutate canonical code facts.

## Comparison

| System | Isolation fit | Provenance fit | Retrieval fit for Hermes | Persistence and operations | Cost / compatibility | Finding |
|---|---|---|---|---|---|---|
| **Qdrant** | Strong logical isolation with payload filters or separate collections; Qdrant recommends payload-based multitenancy for most cases and separate collections when stronger isolation is needed ([collections](https://qdrant.tech/documentation/manage-data/collections/), [filtering](https://qdrant.tech/documentation/search/filtering/)). | Payload accepts arbitrary JSON, so Hermes can store repo, commit, path, line range, URL, and ACL fields; provenance is not automatic ([payload](https://qdrant.tech/documentation/concepts/payload/)). | Strong for code and research: dense+sparse hybrid search, named vectors, prefetch, reranking/multi-stage queries, and indexed filters ([hybrid search](https://qdrant.tech/documentation/search/text-search/hybrid-search/), [hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/)). | Self-hosted single node is straightforward; WAL recovery, on-disk payloads, collection snapshots, and distributed mode exist, but self-hosted replication/shard movement is operator-managed ([storage](https://qdrant.tech/documentation/manage-data/storage/), [snapshots](https://qdrant.tech/documentation/operations/snapshots/), [distributed deployment](https://qdrant.tech/documentation/scaling/distributed_deployment/)). | No separate SaaS fee when self-hosted; still pays VM/storage and embedding/reranking inference. Fits MCP and persona-neutral shared retrieval. | **Keep as the shared retrieval index**, subject to a Hermes benchmark and a canonical metadata/audit layer. |
| **Mem0 OSS / current API** | Explicit `user_id`, `agent_id`, `run_id`, and metadata filters support persona/task/session scopes; official docs warn that searches should be scoped to avoid cross-contamination ([search](https://docs.mem0.ai/core-concepts/memory-operations/search), [add](https://docs.mem0.ai/core-concepts/memory-operations/add)). | Better than a bare vector store: results expose metadata/timestamps, memory history exists, and the evaluation docs describe vector metadata including timestamps, hashes, categories, and `attributed_to`, plus SQL history ([history/evaluation architecture](https://docs.mem0.ai/core-concepts/memory-evaluation), [REST API](https://docs.mem0.ai/open-source/features/rest-api)). The extraction layer can still rewrite or consolidate facts, so Hermes must preserve the original evidence separately. | Better for working-memory facts than raw code indexing: vector search plus filters, optional rerankers, and newer graph/entity retrieval. The official evaluation page reports semantic, BM25, and entity signals, but those evaluations are not evidence for Hermes code-plan queries ([evaluation](https://docs.mem0.ai/core-concepts/memory-evaluation)). | OSS can use Qdrant or Postgres + pgvector; the SDK has local SQLite history, while the self-hosted server uses Postgres + pgvector by default. REST/dashboard/auth/async features add a service and migration surface ([OSS overview](https://docs.mem0.ai/open-source/overview), [configuration](https://docs.mem0.ai/open-source/configuration), [REST API](https://docs.mem0.ai/open-source/features/rest-api)). | Self-hosted avoids platform pricing, but every inferred write may consume LLM/embedding calls; reranking and graph backends add more calls/services. It must be configured to use Hermes’ MiniMax-only model policy; no fallback chain should be introduced. | **Candidate for opt-in persona working memory**, not canonical code/research evidence. Benchmark extraction noise and write cost before enabling by default. |
| **Honcho** | Workspace, peer, and session boundaries are first-class; internal vector collections are keyed by observer/observed peer pairs ([official repository](https://github.com/plastic-labs/honcho), [architecture source](https://github.com/plastic-labs/honcho/blob/main/CLAUDE.md)). This maps well to agent/user interaction traces, but not directly to `persona_id` + repository revision scopes. | Stores messages/events and exposes conclusions, representations, context, and search. The public model is derived peer knowledge, not a source-addressable code record; Hermes would need to attach its own source metadata ([official repository](https://github.com/plastic-labs/honcho)). | Hybrid BM25 + vector search and background reasoning are useful for interaction traces. The peer-representation/dialectic model is a poor default for exact symbol/path/line retrieval ([official repository](https://github.com/plastic-labs/honcho)). | Self-hosting requires the FastAPI server, Postgres with pgvector, migrations, and a separate background deriver; the deriver performs representations, summaries, peer cards, and related work ([self-hosting/architecture](https://github.com/plastic-labs/honcho)). | AGPL-3.0; self-hosted inference still needs configured LLM/embedding providers. It is a substantial second memory service beside Mem0 and Qdrant ([license](https://github.com/plastic-labs/honcho/blob/main/LICENSE)). | **Retain only if Hermes needs peer-centric interaction memory.** Do not use it as the codebase wiki or required V1 memory core without proving its MiniMax-only configuration and operational value. |
| **`agentmemory` PyPI package** | The documented API scopes by a free-form category and metadata; no documented persona/agent/task isolation contract is visible in the package quickstart ([PyPI project](https://pypi.org/project/agentmemory/)). | Returns document, metadata, ID, and optional embeddings, but the documented API does not establish immutable source revisions, citation links, or an audit trail ([PyPI project](https://pypi.org/project/agentmemory/)). | Basic category + text search; no primary documentation found for code-aware hybrid retrieval or controlled reranking. | Defaults to local ChromaDB, with an optional Postgres deployment; the package page is an old release line and should not be conflated with newer repositories using the same name ([PyPI deployment notes](https://pypi.org/project/agentmemory/)). | Low infrastructure cost, but maintenance/version risk is high. | **Retire or isolate if this is the installed package.** First identify the exact distribution and version. |
| **`rohitg00/agentmemory` repository** | Its official README presents a shared local memory server intended for multiple MCP-capable coding agents, but the README is not a substitute for a Hermes-specific ACL contract ([official repository](https://github.com/rohitg00/agentmemory)). | The README advertises confidence/lifecycle/knowledge-graph features; this note did not validate its storage schema or line-level source guarantees. Treat those claims as unverified until the exact pinned release is audited. | Coding-agent orientation and MCP/REST integration are relevant; its published benchmark numbers are vendor claims, not an apples-to-apples Hermes evaluation ([official repository](https://github.com/rohitg00/agentmemory)). | It advertises a local engine with no external DB and a server process, which could reduce service count, but introduces a separate runtime and project-specific operational model ([official repository](https://github.com/rohitg00/agentmemory)). | Potentially low VM cost and good MCP compatibility; exact model, license, backup, and isolation behavior require release-pinned code review. | **Evaluate only if this is the actual current stack.** The name collision with the PyPI package is itself a decision blocker. |
| **Letta** | Strong agent-scoped memory blocks; blocks can be read-only, detached, and shared across agents. This directly models private persona blocks plus explicitly shared blocks ([memory blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks), [attach/detach](https://docs.letta.com/tutorials/attaching-detaching-blocks)). | Blocks and archival passages are persistent records, but code/research citations still need to live in Hermes-owned metadata or external RAG; Letta’s context hierarchy explicitly recommends external RAG/MCP for large corpora ([context hierarchy](https://docs.letta.com/guides/core-concepts/memory/context-hierarchy), [archival API](https://docs.letta.com/api/typescript/resources/agents/subresources/passages)). | Good for agent state and archival recall; external MCP/RAG is the documented fit for millions of documents and codebase knowledge. Always-visible blocks can over-inject shared knowledge if poorly bounded ([context hierarchy](https://docs.letta.com/guides/core-concepts/memory/context-hierarchy)). | Docker persists agent data to a mounted Postgres directory; self-hosted deployments must configure both LLM and embedding models, and a custom Postgres backend requires pgvector ([Docker](https://docs.letta.com/guides/docker), [Postgres](https://docs.letta.com/guides/docker/postgres/)). | More of an agent runtime than a memory library: service, stateful agents, tools, and embedding configuration. MCP stdio is self-hosted-only and custom scripts inside Docker have operational caveats ([MCP stdio](https://docs.letta.com/guides/mcp/stdio)). | **Credible alternative only if Hermes adopts Letta as its agent runtime.** It is overkill as a drop-in memory backend; use external Hermes RAG for code. |
| **LangMem + LangGraph store** | Namespaces can be templated by organization, user, agent, task, or domain; structured schemas can separate persona-private and shared records ([concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/), [dynamic namespaces](https://langchain-ai.github.io/langmem/guides/dynamically_configure_namespaces/)). | Hermes can make provenance fields part of the schema; the store returns raw memory objects. Citation semantics are application-owned, not automatic ([memory tools](https://langchain-ai.github.io/langmem/reference/tools/), [semantic extraction](https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/)). | Semantic/exact search and metadata filtering are available through LangGraph `BaseStore`; it is a useful working-memory primitive, not a code-aware index or source citation system ([memory tools](https://langchain-ai.github.io/langmem/reference/tools/)). | Storage is optional; production guidance points to a persistent `AsyncPostgresStore`, while `InMemoryStore` loses data on restart ([LangMem introduction](https://langchain-ai.github.io/langmem/), [memory tools guide](https://langchain-ai.github.io/langmem/guides/memory_tools/)). | MIT/open-source library, but it adds LangGraph conventions and LLM extraction. It is compatible only if Hermes chooses that runtime/store model; it does not replace Qdrant’s retrieval-specific operations by itself ([official repository](https://github.com/langchain-ai/langmem)). | **Best framework-level alternative for working memory** if Hermes is built on LangGraph. Do not add it solely to obtain a vector database. |
| **Postgres + pgvector** | SQL row ownership and ACLs can directly encode persona/task/visibility scopes; joins make scope enforcement and provenance reviewable. | Strongest canonical-store option: ACID transactions, joins, point-in-time recovery, and application-defined source columns live beside embeddings ([official README](https://github.com/pgvector/pgvector)). | Exact search, HNSW/IVFFlat, sparse vectors, filtering, and Postgres full-text hybrid search are supported. Approximate vector filtering can require iterative scans, higher `ef_search`, partial indexes, or partitioning ([indexing/filtering/hybrid](https://github.com/pgvector/pgvector)). | One Postgres service can replace a separate vector service for a modest corpus; it inherits normal Postgres backup, vacuum, index, and capacity operations. | Lowest service-count option because Honcho and LangMem already use Postgres-compatible stores. It may give up some Qdrant-specific multi-vector/search ergonomics at larger scale. | **Benchmark as the main Qdrant alternative.** It is especially attractive if the VM should run one durable canonical database and retrieval scale is moderate. |

## Persona compatibility

| Persona | Private memory | Shared knowledge | Write authority | Required retrieval result |
|---|---|---|---|---|
| **Librarian** | Query context only; no access to private memories unless explicitly handed off. | Read-only codebase index and approved research evidence. | May ingest/update index records through a controlled ingestion job, not through normal answer generation. | Snippets plus repository, commit, path, symbol, and line-range citations; exact identifier search must coexist with semantic search. |
| **Implementor** | Plan state, task decisions, active worktree/branch, test results, and explicit handoff context. | Read-only codebase index; can read approved research evidence. | May write private task memory and implementation events; may propose source-index updates after a commit. | Evidence sufficient to produce a plan and safely apply it: source locations, dependency edges, revision, and freshness. |
| **Researcher** | Research task state, query decomposition, open questions, and source-review notes. | Read-only codebase knowledge when the research concerns Hermes or a target repository. | May write evidence records only with URL, retrieved date, claim, supporting excerpt, and confidence; cannot overwrite canonical code facts. | Source-linked findings with claim-level provenance and freshness; no unsourced “memory” answer. |

These boundaries imply that one global `user_id` is insufficient. Mem0-style identifiers or LangMem namespaces can implement the dimensions, but Hermes must define the contract itself:

```text
scope = {
  persona_id: "librarian | implementor | researcher | main",
  task_id: "stable task or handoff id",
  visibility: "private | shared",
  repository_id: "optional repository",
  revision: "optional commit SHA"
}
```

## Provenance data contract

Every retrievable record should carry, at minimum:

```text
memory_id, kind, persona_id, task_id, visibility,
content, source_type, source_uri, source_revision,
source_locator, observed_at, created_at, derived_by,
confidence, supersedes, content_hash, acl
```

For code, `source_locator` is a repository-relative path plus symbol and line range; `source_revision` is the commit SHA. For research, it is the canonical URL plus retrieval timestamp and an excerpt hash. Qdrant payload or pgvector columns may hold these fields, but the canonical row/event should remain available independently of the embedding index. This avoids a vector re-embed or deletion becoming the only copy of a citation.

## Retrieval-quality implications

The reviewed systems expose retrieval features, but their official evaluations are mainly conversational-memory benchmarks. Mem0 documents LoCoMo/LongMemEval-style evaluation and Honcho documents LongMemEval/LoCoMo; neither is evidence of recall or citation precision for repository symbols, implementation plans, or first-party research sources ([Mem0 evaluation](https://docs.mem0.ai/core-concepts/memory-evaluation), [Honcho repository](https://github.com/plastic-labs/honcho)). **Inference:** Hermes needs its own workload benchmark before selecting a winner.

The benchmark should contain real or representative queries for all three personas and measure:

- `recall@k`, MRR or nDCG for known answer-bearing chunks;
- exact identifier/path/symbol hit rate versus semantic paraphrase hit rate;
- citation precision and provenance completeness;
- cross-persona contamination rate, with a hard target of zero unauthorized records;
- stale-revision rate and supersession correctness;
- write latency, search p50/p95, reindex time, and snapshot restore time;
- extraction cost per write and total VM/provider cost under a fixed workload.

At minimum, compare: Qdrant + Hermes canonical records; Postgres + pgvector; Mem0 OSS + Qdrant; and LangMem + Postgres. Test Letta only if the agent-runtime decision remains live. Test both `agentmemory` distributions if the VM’s installed package name is not yet pinned.

## Decision candidates for the later map session

1. **Default V1 architecture:** Hermes-owned canonical records and audit events in Postgres; Qdrant as a shared, filtered dense+sparse retrieval index; explicit persona/task/visibility fields at every API boundary.
2. **Working-memory extraction:** start with a minimal Hermes adapter and add Mem0 OSS only behind a feature flag after measuring extraction noise, MiniMax compatibility, history retention, and write cost.
3. **Honcho:** keep only for peer/session interaction memory if that use case survives persona research; otherwise remove it from the required V1 stack to avoid overlapping derived-memory pipelines.
4. **Agentmemory:** resolve the package/repository ambiguity before making any retention decision. The old PyPI package and the newer `rohitg00/agentmemory` repository are materially different candidates.
5. **Qdrant versus pgvector:** run the same code/research benchmark and choose based on citation correctness, filtered recall, backup/restore, and operator burden—not generic vector-database benchmarks.
6. **Letta/LangMem:** treat Letta as an alternate full agent runtime and LangMem as an alternate application-level working-memory primitive; neither is required to implement the shared codebase wiki.

## Primary-source index

- [Hermes V1 planner handoff](../../hermes-v1-handoff.md)
- [Hermes map #38](https://github.com/Noahlw/hermes/issues/38)
- [Honcho source and self-hosting](https://github.com/plastic-labs/honcho)
- [Mem0 OSS overview](https://docs.mem0.ai/open-source/overview)
- [Mem0 evaluation architecture](https://docs.mem0.ai/core-concepts/memory-evaluation)
- [Mem0 search, history, reranking, and graph features](https://docs.mem0.ai/core-concepts/memory-operations/search), [REST API](https://docs.mem0.ai/open-source/features/rest-api), [reranking](https://docs.mem0.ai/open-source/features/reranker-search), [graph memory](https://docs.mem0.ai/open-source/features/graph-memory)
- [`agentmemory` PyPI package](https://pypi.org/project/agentmemory/) and [newer `rohitg00/agentmemory` repository](https://github.com/rohitg00/agentmemory)
- [Qdrant collections, payloads, filtering, hybrid queries, and snapshots](https://qdrant.tech/documentation/manage-data/collections/), [payload](https://qdrant.tech/documentation/concepts/payload/), [filtering](https://qdrant.tech/documentation/search/filtering/), [hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/), [snapshots](https://qdrant.tech/documentation/operations/snapshots/)
- [Letta memory blocks and context hierarchy](https://docs.letta.com/guides/core-concepts/memory/memory-blocks), [context hierarchy](https://docs.letta.com/guides/core-concepts/memory/context-hierarchy), [Docker](https://docs.letta.com/guides/docker), [MCP stdio](https://docs.letta.com/guides/mcp/stdio)
- [LangMem concepts, namespaces, and memory tools](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/), [dynamic namespaces](https://langchain-ai.github.io/langmem/guides/dynamically_configure_namespaces/), [memory tools](https://langchain-ai.github.io/langmem/reference/tools/)
- [pgvector source and README](https://github.com/pgvector/pgvector)
