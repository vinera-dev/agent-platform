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

## Development setup

```bash
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env
python manage.py runserver
```

Configuration comes from environment variables, or from a `.env` file at the project root (ignored by git). `DJANGO_SECRET_KEY` is required and has no default. Generate one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Secret key (required). The `change-me` placeholder is rejected when `DJANGO_DEBUG` is off |
| `DJANGO_DEBUG` | `1` to enable debug mode (default off) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names |
| `DATABASE_URL` | Database URL (default: SQLite file in the project root) |

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
