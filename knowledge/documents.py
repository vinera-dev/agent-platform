import hashlib
import os

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from knowledge.models import Document, KnowledgeBase

ALLOWED_EXTENSIONS = (".txt", ".md")
MULTIPART_OVERHEAD_BYTES = 4096


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The uploaded document is too large."
    default_code = "payload_too_large"


def reject_oversized_request(request) -> None:
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > settings.MAX_DOCUMENT_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise PayloadTooLarge(f"Documents are limited to {settings.MAX_DOCUMENT_BYTES} bytes.")


def read_text_upload(upload) -> str:
    if upload.size > settings.MAX_DOCUMENT_BYTES:
        raise PayloadTooLarge(f"Documents are limited to {settings.MAX_DOCUMENT_BYTES} bytes.")
    if not (upload.name or "").lower().endswith(ALLOWED_EXTENSIONS):
        raise ValidationError({"file": "Only .txt and .md files are accepted."})
    raw = upload.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError({"file": "The file must be UTF-8 text."}) from error
    if "\x00" in text or not text.strip():
        raise ValidationError({"file": "The file must contain text."})
    return text


def create_document(knowledge_base: KnowledgeBase, upload, title: str | None) -> Document:
    text = read_text_upload(upload)
    encoded = text.encode("utf-8")
    return Document.objects.create(
        tenant=knowledge_base.tenant,
        knowledge_base=knowledge_base,
        title=title or os.path.basename(upload.name),
        content=text,
        size_bytes=len(encoded),
        content_sha256=hashlib.sha256(encoded).hexdigest(),
    )
