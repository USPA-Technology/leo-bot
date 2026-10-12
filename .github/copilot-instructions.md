## Graphify — Codebase Knowledge and Architecture Discovery

Use Graphify as the first step when investigating LEO Bot's architecture, code relationships, data flows, dependencies, or implementation details.

### 1. Discover the Knowledge Graph

Before answering architecture or codebase questions, check whether these files exist:

- `graphify-out/GRAPH_REPORT.md` — architecture overview, major concepts, communities, and important relationships.
- `graphify-out/graph.json` — machine-readable knowledge graph for targeted queries.
- `graphify-out/wiki/index.md` — wiki entry point for deeper documentation, if available.

If `graphify-out/GRAPH_REPORT.md` exists, read it before forming architectural conclusions.

For deep investigations, navigate `graphify-out/wiki/index.md` when available and follow the relevant pages.

### 2. Query Before Exploring Broadly

When the Graphify CLI is available and `graphify-out/graph.json` exists, use targeted graph queries to investigate the relevant components and their relationships.

Examples:

- Trace the chatbot request lifecycle from FastAPI endpoint to response generation.
- Trace RAG retrieval from knowledge ingestion through PostgreSQL/pgvector to prompt construction.
- Trace AI provider selection, embedding configuration, and model invocation.
- Trace nearby-place discovery through PostGIS, RAGAgent, and Dagster enrichment.
- Trace Redis session management, visitor isolation, and rate limiting.
- Trace webhook events from Facebook Messenger or Zalo OA to message processing and outbound replies.

Prefer a focused graph query over loading the entire graph or searching the entire repository without a clear reason.

### 3. Verify Findings Against Source Code

Graphify is a navigation and discovery aid, not the final authority.

After identifying relevant components:

1. Open the actual implementation files.
2. Trace callers, callees, imports, configuration, and database interactions.
3. Inspect the relevant SQL schemas and migrations when database behavior is involved.
4. Check `pyproject.toml`, `requirements.txt`, `.env.example.txt`, and startup scripts when dependencies or runtime behavior are involved.
5. Inspect relevant tests to establish expected behavior and existing regression coverage.

Do not invent modules, APIs, tables, environment variables, or execution paths. Distinguish implemented behavior from inferred relationships and proposed designs.

### 4. Handle Missing or Stale Graphs

- If the graph report does not exist, investigate the repository directly.
- If `graphify-out/wiki/index.md` does not exist, continue using the available report and source code.
- If the graph is missing, stale, or insufficient, build or update it when the Graphify skill is available and appropriate.
- Use `/graphify` in GitHub Copilot Chat to build or update the knowledge graph.
- Prefer incremental updates for ordinary changes; use a full rebuild when structural changes or missing graph coverage justify it.
- Never treat an old graph as proof of the current implementation.

Do not block urgent debugging or straightforward code changes solely because Graphify is unavailable.

### 5. LEO Bot Architecture Boundaries

When investigating or modifying the application, account for these existing architectural areas:

- **API and orchestration:** FastAPI, routers, request validation, and RAGAgent workflows.
- **AI integration:** configurable Google Gemini, OpenAI, and OpenRouter providers.
- **Knowledge retrieval:** document ingestion, chunking, embeddings, PostgreSQL, and pgvector.
- **Geospatial context:** PostGIS, visitor touchpoints, nearby-place search, and place selection.
- **Background processing:** Dagster pipelines for place discovery and enrichment.
- **State and resilience:** Redis-backed visitor state, rate limiting, asynchronous I/O, and error handling.
- **Channels and presentation:** website chat, Facebook Messenger, Zalo OA, and frontend integrations.

Treat this list as an investigation map, not a guarantee that every feature is implemented identically across all code paths. Verify the actual code before changing behavior.

### 6. Implementation and Review Standards

Before proposing a change, identify:

- The current execution path and responsible modules.
- The contracts between API, AI, database, background jobs, and frontend.
- Relevant configuration and backward-compatibility constraints.
- Existing tests and the smallest meaningful regression test.

Prefer minimal, targeted changes that preserve existing interfaces. Avoid introducing dependencies, duplicating existing functionality, or redesigning unrelated components without justification.

When reporting findings, provide source file paths and line references where available. Clearly separate verified facts, reasonable inferences, identified defects, and proposed improvements.