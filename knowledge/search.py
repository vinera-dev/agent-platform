from dataclasses import dataclass

from pgvector.django import CosineDistance

from knowledge.embeddings import get_embedder
from knowledge.models import Chunk, KnowledgeBase
from tenants.models import Tenant

MAX_RESULTS = 20


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    document_id: str
    document_title: str
    position: int
    text: str
    score: float


def search_chunks(
    tenant: Tenant, query: str, *, knowledge_base: KnowledgeBase | None = None, limit: int = 5
) -> list[SearchHit]:
    if not query.strip() or limit < 1:
        return []
    vector = get_embedder().embed([query])[0]
    chunks = Chunk.objects.for_tenant(tenant).select_related("document")
    if knowledge_base is not None:
        chunks = chunks.filter(document__knowledge_base=knowledge_base)
    ranked = chunks.annotate(distance=CosineDistance("embedding", vector)).order_by(
        "distance", "id"
    )[: min(limit, MAX_RESULTS)]
    return [
        SearchHit(
            chunk_id=chunk.id,
            document_id=str(chunk.document_id),
            document_title=chunk.document.title,
            position=chunk.position,
            text=chunk.text,
            score=round(1.0 - float(chunk.distance), 6),
        )
        for chunk in ranked
    ]
