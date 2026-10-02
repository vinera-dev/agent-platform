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
docker compose up -d --wait
python manage.py migrate
python manage.py runserver
```

`docker compose` starts PostgreSQL (with the pgvector extension) and Redis, bound to `127.0.0.1` only. The host ports are `55432` and `56379` to avoid clashing with other local databases. Use `127.0.0.1` instead of `localhost` in the URLs: on Windows `localhost` can resolve to IPv6 first, and the connection waits for a timeout.

Configuration comes from environment variables, or from a `.env` file at the project root (ignored by git). `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` are required and have no default. Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Secret key (required). The `change-me` placeholder is rejected when `DJANGO_DEBUG` is off |
| `DJANGO_DEBUG` | `1` to enable debug mode (default off) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names |
| `TENANT_RATE_LIMIT` | Requests per tenant, as `count/period` (default `120/min`); counters live in the Django cache |
| `ALLOWED_MODELS` | Comma-separated model names an agent version may use (default `gpt-4o-mini,gpt-4o`) |
| `DATABASE_URL` | Database URL (default: SQLite file in the project root) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Credentials of the PostgreSQL container (the password is required) |
| `POSTGRES_PORT`, `REDIS_PORT` | Host ports published by Docker Compose |
| `REDIS_URL` | Redis URL (used by the task queue in later steps) |

## Tenants and API keys

Create a tenant and its first API key (the key is printed once and only its hash is stored):

```bash
python manage.py create_tenant acme-vet --name "Acme Vet"
```

Authenticate with the `Authorization` header:

```bash
curl -H "Authorization: Api-Key <key>" http://127.0.0.1:8000/v1/whoami
```

Every `/v1` request is scoped to the key's tenant and limited by `TENANT_RATE_LIMIT`.

## Roadmap

- [x] 1. Project skeleton, tenants and API key auth
- [ ] 2. Agent definitions and versioned contracts
- [ ] 3. Asynchronous runs and run history
- [ ] 4. Knowledge bases with RAG
- [ ] 5. Tool registry
- [ ] 6. Observability
- [ ] 7. Evaluation suite and CI gates

## License

Released under the [MIT License](LICENSE).
