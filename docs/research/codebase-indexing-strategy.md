# Codebase indexing strategy for a 20–100 repository wiki

Research findings for Hermes map #38, decision ticket #40. Updated 2026-07-23.

## Decision summary

Use a **hybrid, repository-aware index** as the V1 direction:

1. Keep a local, authoritative working set of tracked repository state on the VM. Use normal clones for small repositories and Git partial clone plus sparse checkout for repositories whose history, blobs, or working tree are too large to keep fully materialized.
2. Build a structure-first index from the local checkout: repository/tree metadata, paths, language, symbols, definitions/references where supported, dependency/configuration files, and commit SHA. Add lexical search for exact identifiers and paths before adding embeddings.
3. Add semantic embeddings selectively for documentation, architecture notes, and code chunks that benefit from conceptual retrieval. Keep the source location, repository, ref, commit SHA, and line range in every indexed record.
4. Subscribe to GitHub `push` webhooks to queue incremental updates using the `before` and `after` SHAs. Reconcile periodically with refs/commit comparison so missed, oversized, deleted-branch, and force-push events cannot leave the index silently stale.
5. Use live GitHub APIs as a fallback and freshness check, not as the only codebase store. When a plan needs exact current content, fetch or materialize the referenced files at a verified commit before proposing edits.

This recommendation is an architectural inference from the capabilities and limits documented below. The 20–100 repository count alone is not enough to size storage or embedding cost; total bytes, file count, history depth, language mix, churn, and embedding granularity must be measured during implementation.

## Scope and evaluation criteria

The target is a private, self-hosted Hermes wiki/agent that supports both:

- **Retrieval:** answer questions across many repositories with citations to repository, ref, commit, file, and line range.
- **Code-plan implementation:** understand structure and dependencies, identify affected files, produce a plan, and later operate on an exact local checkout without confusing stale search results for the current source.

The comparison covers the repository count in the ticket, not a specific aggregate code size. It evaluates freshness, code structure, cross-repository navigation, incremental updates, storage/compute, privacy, failure modes, and suitability for both workflows.

## Evidence from primary sources

### GitHub can provide repository trees, blobs, diffs, search, and code navigation

GitHub's Git Trees API exposes Git tree objects and supports recursive reads, but recursive responses are capped at 100,000 entries or 7 MB and set `truncated` when the limit is exceeded. GitHub directs callers that need more files to fetch subtrees one at a time. This makes the API useful for metadata discovery and targeted retrieval, but not a universal replacement for a local repository mirror. ([Git Trees API](https://docs.github.com/en/rest/git/trees))

The Contents API can list files and retrieve file content, but directory responses are limited to 1,000 files and files over 100 MB are unsupported; GitHub again recommends the Git Trees API for more files. ([Repository Contents API](https://docs.github.com/en/rest/repos/contents))

GitHub Code Search is code-aware and supports Boolean expressions, regular expressions, repository/language/path qualifiers, and symbol queries. A query can combine multiple `repo:` qualifiers, which is useful for cross-repository lookup. However, GitHub states that not all code is indexed, vendored/generated/binary/large files can be excluded, only the default branch is searched, exhaustive search is unsupported, and results are limited to 100. ([About GitHub Code Search](https://docs.github.com/en/search-github/github-code-search/about-github-code-search), [Code Search syntax](https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax))

GitHub's code navigation uses the open-source Tree-sitter ecosystem to extract definitions and references for a supported-language set. It is valuable evidence that a structure-aware index is materially different from text or embedding search, but GitHub's documented navigation is scoped to the repository being navigated; Hermes still needs its own cross-repository identity and dependency model. ([Navigating code on GitHub](https://docs.github.com/en/repositories/working-with-files/using-files/navigating-code-on-github))

GitHub's compare-commits API can compare branches, tags, and SHAs and returns changed-file status, including added, removed, modified, and renamed files. The response is paginated with a maximum of 100 files per page. ([Compare two commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits))

### Git supports reduced local materialization, but missing data has operational consequences

Git's partial-clone documentation says a full clone/fetch normally downloads commits, trees, and blobs for the repository's complete history. Partial clone can omit unwanted objects and demand-fetch them later, reducing initial download and disk usage. The same documentation requires the promisor remote to be available for missing objects and notes that dynamic fetching can be slow, especially when many objects are needed. ([Git partial clone](https://git-scm.com/docs/partial-clone))

`git clone --filter=...` enables partial clone; `--filter=blob:none` omits file contents until needed. `git clone --sparse` initially materializes only top-level files, and sparse-checkout can grow the working tree. ([git-clone](https://git-scm.com/docs/git-clone), [git-sparse-checkout](https://git-scm.com/docs/git-sparse-checkout))

Sparse checkout has behavior that matters for implementation: paths outside the selected cone may not be present, some commands can materialize paths temporarily, and the documentation describes the sparse-index feature as experimental. Therefore the indexer must know whether a file is locally present and must be able to materialize the exact file set before planning or editing. ([git-sparse-checkout](https://git-scm.com/docs/git-sparse-checkout))

Git also provides commit-graph files, appendable split commit graphs, and changed-path Bloom filters. These are useful local accelerators for history/path queries, but they optimize Git metadata; they do not replace a semantic or lexical content index. ([git-commit-graph](https://git-scm.com/docs/git-commit-graph))

### Webhooks support near-real-time updates, but a durable reconciler is still required

The GitHub `push` payload includes the ref, `before` SHA, `after` SHA, force-push status, and the pushed commits. GitHub documents a maximum of 2,048 commits in the payload and directs consumers to the Commits API for additional commits. Push events also are not created when more than 5,000 branches are pushed at once. These constraints make a webhook a good update trigger, not a complete source of truth. ([Push webhook payload](https://docs.github.com/en/webhooks/webhook-events-and-payloads#push))

GitHub requires a webhook handler to return a 2XX response within 10 seconds; otherwise the delivery is considered failed. The handler should acknowledge quickly and enqueue indexing work. GitHub provides `X-Hub-Signature-256` HMAC validation for authenticating deliveries. ([Handling webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/handling-webhook-deliveries), [Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries))

### API access and search limits make unbounded live retrieval fragile

GitHub documents a 60-requests-per-hour unauthenticated REST limit and a general 5,000-requests-per-hour authenticated-user limit; search endpoints are more restrictive, and secondary limits apply to concurrency and endpoint usage. A live-only design must therefore batch, cache, paginate, back off, and degrade gracefully. ([REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api))

### A local index can combine exact and semantic retrieval

SQLite FTS5 provides local full-text search, phrase/prefix/NEAR/Boolean queries, column filters, relevance ranking, snippets, and contentless/external-content table options. This is a good fit for exact identifiers, paths, documentation, and a low-operations VM deployment. ([SQLite FTS5](https://sqlite.org/fts5.html))

Tree-sitter is an incremental parsing library that produces concrete syntax trees and remains useful in the presence of syntax errors. Its query system can match syntax-tree structures and its parser API can update from an old tree. This supports a structure-first index that can reparse changed files and extract symbols without requiring a complete compiler for every language. ([Tree-sitter introduction](https://tree-sitter.github.io/tree-sitter/), [Tree-sitter basic parsing](https://tree-sitter.github.io/tree-sitter/using-parsers/2-basic-parsing.html), [Tree-sitter queries](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/index.html))

Embeddings represent text as floating-point vectors whose distances express relatedness; an embedding service may be billed by input tokens, and the resulting vectors can be saved in a vector database. This supports conceptual retrieval but introduces an indexing pipeline, model-version provenance, and—if the service is hosted—an additional code/data boundary. ([OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings))

For a single database deployment, pgvector can store vectors with other Postgres data and supports exact and approximate nearest-neighbor search. Its documentation explicitly describes the speed/recall tradeoff of approximate indexes, and notes that HNSW uses more memory and has slower build times than IVFFlat. ([pgvector README](https://github.com/pgvector/pgvector/blob/master/README.md))

## Comparison

| Approach | Freshness | Code structure and cross-repository navigation | Incremental updates | Storage/compute and privacy | Main failure modes | Retrieval | Code-plan implementation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Full clone + embed everything | Fresh only after a successful sync; otherwise the index can be stale. | Strongest local basis: Git history, paths, exact blobs, and local parsing. Cross-repo navigation is possible if repository and symbol identities are modeled explicitly. | Re-fetch, diff, reparse changed files, and re-embed changed chunks. Embedding churn can be expensive when chunk boundaries move. | Highest storage: working trees, Git objects/history, metadata, lexical index, vectors, and possibly duplicate content. Local embedding keeps source on the VM; hosted embedding adds a provider boundary. | Clone/sync failures, disk pressure, parser gaps, stale vectors, embedding-model drift, and accidental indexing of secrets or generated artifacts. | Excellent for both lexical and conceptual retrieval if the index is healthy. | Best foundation: exact commit-pinned local state can be inspected and edited. Requires correct checkout/ref handling. |
| Live GitHub retrieval/search | Potentially freshest at request time, but GitHub Code Search is indexed rather than a raw live read and only searches the default branch. ([About GitHub Code Search](https://docs.github.com/en/search-github/github-code-search/about-github-code-search)) | Good for GitHub-supported symbol search and targeted file/tree reads; weak for full dependency graphs, non-indexed files, and large result sets. | No local update job, but every request pays network/API cost and depends on GitHub availability and rate limits. | Lowest local storage and indexing compute. Code stays in GitHub, but every request depends on credentials and transfers selected source to Hermes/LLM. | 401/403, rate limits, search omissions, result caps, network outage, branch ambiguity, API pagination, and partial/inconsistent multi-call snapshots. | Good for targeted exact retrieval and fallback discovery; poor as the sole semantic retrieval layer. | Adequate for small targeted plans after fetching exact files; poor for repository-wide impact analysis or offline work. |
| Local structure/lexical index + live blobs | Metadata and lexical results are near the last successful sync; exact blobs can be revalidated live. | Strong for paths, symbols, references, configs, and dependency edges; cross-repo graph can be retained locally. | Re-index changed paths from GitHub compare/webhooks; fetch only the exact blobs needed. | Moderate storage and compute; much less than embedding every chunk. Strong privacy if the index and cache remain local. | Stale metadata, missing local blobs, API outages during materialization, parser failures, and deleted/force-pushed refs. | Strong exact retrieval; semantic recall is weaker without embeddings. | Strong if the local structure index is pinned to a commit and the materializer can obtain all affected files. |
| **Hybrid local mirror + structure/lexical index + selective embeddings + live fallback (recommended)** | Near-real-time after webhook processing; live verification can close the freshness gap before answer/plan generation. | Strongest balance: local Git/Tree-sitter structure, repository-aware identity, exact paths, lexical search, and semantic search for selected content. | Webhook-triggered incremental updates, with compare/ref reconciliation and periodic full checks. Re-embed only changed or selected chunks. | Moderate-to-high but controllable. Local-only embedding preserves privacy; hosted embedding is opt-in. Index cost is bounded by chunk policy and changed files rather than every request. | Webhook loss/duplication, queue backlogs, stale index, partial clone missing objects, model drift, vector recall loss, and disk exhaustion. | Best overall: lexical + semantic + exact live verification. | Best overall: local exact source, commit-aware plans, and a path to materialize/edit a working tree. |
| On-demand clone/cache with no durable content index | Fresh when materialized; cache entries can be stale unless checked against a ref/commit. | Strong after clone, but discovery before materialization is slow and repeated. Cross-repository navigation requires a separate catalog. | Update or evict per repository; low background work but repeated cold-start work. | Lower idle storage/compute, higher request latency and bandwidth. Privacy is local if cloning and parsing stay on the VM. | Cold-start time, partial clone demand-fetch latency, GitHub outage, cache eviction thrash, and insufficient context for large plans. | Fine for targeted requests; poor for broad wiki-style recall. | Good for a small number of implementation tasks, but less reliable for impact analysis across 20–100 repositories. |
| GitHub Code Search as the primary index | Depends on GitHub's index freshness; not a live branch/ref view. | Useful supported-language definitions/references and cross-repo textual search, but documented omissions and 100-result limit make it incomplete. | No Hermes index updates, but no control over GitHub indexing. | Minimal local storage and compute. Access remains governed by GitHub permissions; source must still cross the network for Hermes responses. | Search omissions, default-branch-only behavior, result caps, account/auth failures, and no exhaustive search. | Good discovery/fallback, not sufficient as the only wiki index. | Not sufficient for reliable code-plan implementation without fetching and validating exact source locally. |

## Recommended V1 design

### 1. Repository catalog and identity

Maintain one catalog row per repository and tracked ref with at least:

- canonical owner/name and repository ID;
- default branch and tracked branches/tags policy;
- visibility and access scope;
- last observed ref SHA, last successfully indexed SHA, and sync state;
- local clone path and whether the clone is full, partial, sparse, or cache-only;
- supported-language/parser coverage;
- index schema/model version and last successful embedding version.

Every searchable record should carry `repository`, `ref`, `commit_sha`, `path`, `start_line`, `end_line`, `content_kind`, and a stable content hash. The SHA is the freshness boundary: search results without a commit identity are not safe inputs to a code plan.

### 2. Three complementary index layers

**Exact source layer.** Git objects and/or a materialized working tree provide byte-accurate content at a commit. This is the source used for final verification and implementation planning.

**Structure and lexical layer.** Use the repository tree, language detection, Tree-sitter symbol extraction, dependency/configuration file parsers, Git history metadata, and SQLite FTS5. Index paths, symbol names, signatures, imports/exports, package/module names, documentation headings, and bounded source chunks. This layer should answer “where is this identifier, endpoint, config, or dependency?” without relying on semantic similarity.

**Semantic layer.** Embed selected documentation, architecture explanations, public symbols/signatures, and source chunks that benefit from conceptual search. Do not make embeddings the source of truth. Store the embedding-model/version and chunk hash so changed content or model upgrades can be reprocessed deterministically. If using a hosted embedding API, make the privacy boundary explicit and configurable; a local model avoids sending source text outside the VM at the cost of local compute and model operations.

The initial V1 should make lexical and structure search useful before adding broad embeddings. This reduces cost, gives better exact-identifier behavior, and provides a reliable fallback when vectors are unavailable.

### 3. Incremental update protocol

1. Receive and HMAC-validate a GitHub `push` webhook.
2. Acknowledge within 10 seconds and enqueue an idempotent job keyed by repository/ref/after-SHA.
3. Record the event and compare the tracked `before` and `after` SHAs. For ordinary pushes, request changed files through the Compare API or use the local Git graph after fetching.
4. For added/modified files, update exact metadata, parse structure, update lexical records, and replace embeddings for affected chunks. For deleted/renamed files, remove old records and preserve rename provenance where available.
5. Mark the repository indexed only after all layers succeed. Keep the previous indexed snapshot available while the new snapshot is building.
6. Periodically reconcile current refs against the catalog. A reconciliation must repair missed deliveries, duplicate deliveries, queue failures, force pushes, branch deletion, payload truncation, and manual index drift.
7. Before a code-plan answer, verify that the cited commit is still reachable for the tracked ref. If not, fetch the current source and re-run the impacted query.

The webhook should trigger work, not contain the whole indexing algorithm. The documented payload limit and delivery timeout make a durable queue, retry policy, dead-letter state, and periodic reconciliation necessary design components.

### 4. Retrieval and plan behavior

Use a staged query path:

1. Resolve repository/ref scope and detect whether the request is exact, structural, conceptual, or mixed.
2. Search paths, identifiers, symbols, configs, and dependency edges with lexical/structure indexes.
3. Use semantic retrieval for concepts and documentation, filtered by repository, language, content kind, and indexed commit.
4. Re-rank and deduplicate by repository/path/symbol; retain provenance for every result.
5. For implementation planning, materialize or fetch the exact files at one verified commit, inspect surrounding code and dependency edges, and only then produce the plan.
6. If the local index is stale or unavailable, fall back to live GitHub retrieval with an explicit “live snapshot” provenance and reduced confidence. If required source cannot be verified, return a blocked plan instead of inventing a change.

## Decision implications and follow-on questions

This research resolves the architecture direction for issue #40 but does not choose every implementation detail. The next map tickets should pin down:

- Which repositories and refs are in V1, and what access scopes are acceptable?
- Full clone versus partial/sparse policy based on measured aggregate size and code-plan workloads.
- Exact parser/language coverage and the cross-repository symbol/dependency identity model.
- Chunk boundaries, metadata schema, embedding model, model-upgrade policy, and whether embeddings must be local-only.
- Local storage choice: SQLite FTS5 plus a vector extension/store, or Postgres plus pgvector.
- Webhook deployment over Tailscale, queue/retry behavior, periodic reconciliation interval, and failure visibility.
- Retention and deletion behavior for removed repositories, revoked access, secrets, generated files, and private branches.
- Evaluation fixtures for retrieval precision, stale-result rejection, cross-repository navigation, and implementation-plan correctness.

## Source notes

All sources above are first-party documentation or source repositories for the mechanism being evaluated. No secondary comparison article was used. Cost and privacy conclusions that go beyond explicit product behavior are labeled as architectural inferences; they should be validated with a representative repository sample before implementation is considered complete.
