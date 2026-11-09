import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from knowledge.chunking import split_text
from knowledge.embeddings import EMBEDDING_DIMENSIONS, HashingEmbedder, stem
from knowledge.ingestion import ingest_document
from knowledge.models import Chunk, Document, KnowledgeBase
from knowledge.tasks import ingest_document_task

LONG_TEXT = "\n\n".join(
    f"Paragraph {number} talks about topic {number}. It has a second sentence for padding."
    for number in range(20)
)


def test_short_text_is_a_single_chunk():
    assert split_text("Open every day.", 100, 10) == ["Open every day."]


def test_chunks_respect_the_size_and_cover_the_text():
    chunks = split_text(LONG_TEXT, 200, 30)

    assert len(chunks) > 3
    assert all(0 < len(chunk) <= 200 for chunk in chunks)
    assert chunks[0].startswith("Paragraph 0")
    assert chunks[-1].endswith("padding.")
    for number in range(20):
        assert any(f"topic {number}." in chunk for chunk in chunks)


def test_consecutive_chunks_overlap():
    chunks = split_text("word " * 200, 100, 30)

    assert len(chunks) > 2
    assert all(chunks[i][-10:].strip() in chunks[i + 1] for i in range(len(chunks) - 1))


def test_split_is_deterministic():
    assert split_text(LONG_TEXT, 150, 20) == split_text(LONG_TEXT, 150, 20)


def test_split_without_whitespace_still_terminates():
    chunks = split_text("x" * 1000, 100, 20)

    assert len(chunks) >= 10
    assert all(len(chunk) <= 100 for chunk in chunks)


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_invalid_parameters_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        split_text("text", size, overlap)


def test_embedder_is_deterministic_normalized_and_sized():
    embedder = HashingEmbedder()

    first, second = embedder.embed(["Open every day", "Open every day"])
    other = embedder.embed(["vaccination schedule"])[0]

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert sum(value * value for value in first) == pytest.approx(1.0)
    assert sum(a * b for a, b in zip(first, other, strict=True)) < 0.5


def test_embedder_handles_text_without_tokens():
    assert set(HashingEmbedder().embed(["!!!"])[0]) == {0.0}


@pytest.mark.django_db
class TestIngestion:
    @pytest.fixture
    def document(self, tenant, settings):
        settings.CHUNK_SIZE = 200
        settings.CHUNK_OVERLAP = 30
        knowledge_base = KnowledgeBase.objects.create(tenant=tenant, name="FAQ")
        return Document.objects.create(
            tenant=tenant,
            knowledge_base=knowledge_base,
            title="Topics",
            content=LONG_TEXT,
            size_bytes=len(LONG_TEXT),
            content_sha256="0" * 64,
        )

    def test_chunks_are_written_with_embeddings(self, document, tenant):
        count = ingest_document(document)

        document.refresh_from_db()
        chunks = list(Chunk.objects.filter(document=document))
        assert count == len(chunks) > 3
        assert document.status == Document.Status.READY
        assert document.ingested_at is not None
        assert [chunk.position for chunk in chunks] == list(range(count))
        assert all(chunk.tenant_id == tenant.id for chunk in chunks)
        assert all(len(chunk.embedding) == EMBEDDING_DIMENSIONS for chunk in chunks)

    def test_reingesting_replaces_the_chunks(self, document):
        first = ingest_document(document)
        second = ingest_document(document)

        assert first == second
        assert Chunk.objects.filter(document=document).count() == second

    def test_task_marks_the_document_failed_when_embedding_breaks(self, document, monkeypatch):
        class Broken:
            def embed(self, texts):
                raise RuntimeError("embedder down")

        monkeypatch.setattr("knowledge.ingestion.get_embedder", Broken)

        ingest_document_task.apply(args=[str(document.id)], throw=True)

        document.refresh_from_db()
        assert document.status == Document.Status.FAILED
        assert "embedder down" in document.error
        assert Chunk.objects.count() == 0

    def test_task_ignores_unknown_documents(self):
        result = ingest_document_task.apply(args=["00000000-0000-0000-0000-000000000000"])

        assert result.successful()

    def test_upload_triggers_ingestion(
        self, tenant, issued_key, client_for, eager, django_capture_on_commit_callbacks
    ):
        knowledge_base = KnowledgeBase.objects.create(tenant=tenant, name="Other")

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(issued_key.raw_key).post(
                f"/v1/knowledge-bases/{knowledge_base.pk}/documents",
                {"file": SimpleUploadedFile("faq.txt", b"Vaccines are given in spring.")},
                format="multipart",
            )

        document = Document.objects.get(pk=response.json()["id"])
        assert document.status == Document.Status.READY
        assert [chunk.text for chunk in document.chunks.all()] == ["Vaccines are given in spring."]


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("parking", "park"),
        ("vaccines", "vaccine"),
        ("opens", "open"),
        ("needed", "need"),
        ("boxes", "box"),
        ("watches", "watch"),
        ("glass", "glass"),
        ("bus", "bus"),
        ("is", "is"),
    ],
)
def test_stemming_folds_common_inflections(word, expected):
    assert stem(word) == expected
