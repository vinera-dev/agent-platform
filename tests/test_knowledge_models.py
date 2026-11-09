import pytest
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor

from knowledge.embeddings import EMBEDDING_DIMENSIONS
from knowledge.models import Chunk, Document, KnowledgeBase

pytestmark = pytest.mark.django_db


@pytest.fixture
def knowledge_base(tenant):
    return KnowledgeBase.objects.create(tenant=tenant, name="Clinic FAQ")


def make_document(knowledge_base, **extra):
    fields = {
        "tenant": knowledge_base.tenant,
        "knowledge_base": knowledge_base,
        "title": "Hours",
        "content": "Open every day.",
        "size_bytes": 15,
        "content_sha256": "0" * 64,
    }
    return Document.objects.create(**{**fields, **extra})


def test_migration_enables_the_vector_extension():
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() == ("vector",)


def test_migrations_are_fully_applied():
    executor = MigrationExecutor(connection)

    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []


def test_chunk_stores_a_vector_with_the_configured_dimensions(knowledge_base):
    document = make_document(knowledge_base)
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 1.0

    chunk = Chunk.objects.create(
        tenant=knowledge_base.tenant, document=document, position=0, text="Open", embedding=vector
    )
    chunk.refresh_from_db()

    assert len(chunk.embedding) == EMBEDDING_DIMENSIONS
    assert chunk.embedding[0] == 1.0


def test_document_defaults_to_pending(knowledge_base):
    assert make_document(knowledge_base).status == Document.Status.PENDING


def test_knowledge_base_names_are_unique_per_tenant(tenant, make_tenant):
    KnowledgeBase.objects.create(tenant=tenant, name="FAQ")
    KnowledgeBase.objects.create(tenant=make_tenant(slug="other", name="Other"), name="FAQ")

    with pytest.raises(IntegrityError):
        KnowledgeBase.objects.create(tenant=tenant, name="FAQ")


def test_chunk_positions_are_unique_within_a_document(knowledge_base):
    document = make_document(knowledge_base)
    vector = [0.0] * EMBEDDING_DIMENSIONS
    Chunk.objects.create(
        tenant=knowledge_base.tenant, document=document, position=0, text="a", embedding=vector
    )

    with pytest.raises(IntegrityError):
        Chunk.objects.create(
            tenant=knowledge_base.tenant, document=document, position=0, text="b", embedding=vector
        )


def test_deleting_a_knowledge_base_removes_documents_and_chunks(knowledge_base):
    document = make_document(knowledge_base)
    Chunk.objects.create(
        tenant=knowledge_base.tenant,
        document=document,
        position=0,
        text="a",
        embedding=[0.0] * EMBEDDING_DIMENSIONS,
    )

    knowledge_base.delete()

    assert Document.objects.count() == 0
    assert Chunk.objects.count() == 0
