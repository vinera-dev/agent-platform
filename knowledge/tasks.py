from celery import shared_task

from knowledge.ingestion import ingest_document, mark_failed
from knowledge.models import Document


@shared_task(name="knowledge.ingest_document")
def ingest_document_task(document_id: str) -> str:
    document = Document.objects.filter(pk=document_id).first()
    if document is None:
        return document_id
    try:
        ingest_document(document)
    except Exception as error:
        mark_failed(document, error)
    return document_id
