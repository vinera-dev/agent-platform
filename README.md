# agent-platform

A multi-tenant platform to create, configure and run LLM agents through an API, so product teams can add generative AI features without building their own agent stack.

> **Status:** planned, not started. This README describes the intended scope.

## Purpose

Show how to design and operate a shared agent platform: tenant isolation, versioned contracts, asynchronous execution, retrieval, tool calling, observability and evaluation. All data is fictional.

## Planned scope

- Tenants with API key authentication and per-tenant rate limits
- Agent definitions (prompt, model, tools, knowledge base) with versioned, backward-compatible contracts
- Asynchronous runs through a task queue, with run history and status
- Per-tenant knowledge bases with RAG (embeddings, vector search, ingestion jobs)
- Tool registry with typed input and output contracts
- Observability: traces, latency, token usage and cost per run
- Agent evaluation: labeled datasets, metrics and regression checks in CI

## Planned stack

Python, Django REST Framework, Celery, Redis, PostgreSQL with pgvector, Langfuse, pytest, Docker, GitHub Actions.

## Roadmap

- [ ] 1. Project skeleton, tenants and API key auth
- [ ] 2. Agent definitions and versioned contracts
- [ ] 3. Asynchronous runs and run history
- [ ] 4. Knowledge bases with RAG
- [ ] 5. Tool registry
- [ ] 6. Observability
- [ ] 7. Evaluation suite and CI gates

## License

Released under the [MIT License](LICENSE).
