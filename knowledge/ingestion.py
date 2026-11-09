import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from knowledge.chunking import split_text
from knowledge.embeddings import get_embedder
from knowledge.models import Chunk, Document

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


def ingest_document(document: Document) -> int:
    pieces = split_text(document.content, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    embedder = get_embedder()
    vectors: list[list[float]] = []
    for offset in range(0, len(pieces), EMBED_BATCH_SIZE):
        vectors.extend(embedder.embed(pieces[offset : offset + EMBED_BATCH_SIZE]))
    with transaction.atomic():
        Chunk.objects.filter(document=document).delete()
        Chunk.objects.bulk_create(
            Chunk(
                tenant_id=document.tenant_id,
                document=document,
                position=position,
                text=text,
                embedding=vector,
            )
            for position, (text, vector) in enumerate(zip(pieces, vectors, strict=True))
        )
        document.status = Document.Status.READY
        document.error = ""
        document.ingested_at = timezone.now()
        document.save(update_fields=["status", "error", "ingested_at"])
    return len(pieces)


def mark_failed(document: Document, error: Exception) -> None:
    document.status = Document.Status.FAILED
    document.error = f"Ingestion failed: {error}"
    document.save(update_fields=["status", "error"])
    logger.error("document ingestion failed", extra={"document_id": str(document.id)})
