import pytest

from knowledge.ingestion import ingest_document
from knowledge.models import Document, KnowledgeBase
from knowledge.search import search_chunks
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db

HOURS = "The clinic opens at eight in the morning and closes at six in the evening."
VACCINES = "Puppy vaccines are given at eight, twelve and sixteen weeks of age."
PARKING = "Free parking is available behind the building for all visitors."


def add_document(tenant, knowledge_base, title, content):
    document = Document.objects.create(
        tenant=tenant,
        knowledge_base=knowledge_base,
        title=title,
        content=content,
        size_bytes=len(content),
        content_sha256="0" * 64,
    )
    ingest_document(document)
    return document


@pytest.fixture
def other_tenant(make_tenant):
    return make_tenant(slug="other-clinic", name="Other Clinic")


@pytest.fixture
def knowledge_base(tenant):
    base = KnowledgeBase.objects.create(tenant=tenant, name="FAQ")
    add_document(tenant, base, "Hours", HOURS)
    add_document(tenant, base, "Vaccines", VACCINES)
    add_document(tenant, base, "Parking", PARKING)
    return base


@pytest.fixture
def other_base(other_tenant):
    base = KnowledgeBase.objects.create(tenant=other_tenant, name="FAQ")
    add_document(other_tenant, base, "Hours", HOURS)
    add_document(other_tenant, base, "Secret", "Internal salary table for the other clinic.")
    return base


def test_most_relevant_chunk_ranks_first(tenant, knowledge_base):
    hits = search_chunks(tenant, "when are puppy vaccines given", knowledge_base=knowledge_base)

    assert hits[0].document_title == "Vaccines"
    assert hits[0].score > hits[1].score
    assert hits[0].text == VACCINES


def test_limit_caps_the_results(tenant, knowledge_base):
    assert len(search_chunks(tenant, "clinic", knowledge_base=knowledge_base, limit=2)) == 2


def test_blank_query_returns_nothing(tenant, knowledge_base):
    assert search_chunks(tenant, "   ", knowledge_base=knowledge_base) == []


def test_search_never_returns_another_tenants_chunks(
    tenant, other_tenant, knowledge_base, other_base
):
    mine = search_chunks(tenant, "clinic hours", knowledge_base=knowledge_base, limit=20)
    theirs = search_chunks(other_tenant, "clinic hours", knowledge_base=other_base, limit=20)

    assert {hit.document_title for hit in mine} == {"Hours", "Vaccines", "Parking"}
    assert {hit.document_title for hit in theirs} == {"Hours", "Secret"}
    assert not {hit.chunk_id for hit in mine} & {hit.chunk_id for hit in theirs}


def test_tenant_scope_holds_even_without_a_knowledge_base_filter(
    tenant, knowledge_base, other_base
):
    hits = search_chunks(tenant, "internal salary table", limit=20)

    assert "Secret" not in {hit.document_title for hit in hits}
    assert len(hits) == 3


def test_a_foreign_knowledge_base_yields_nothing(tenant, other_base):
    assert search_chunks(tenant, "internal salary table", knowledge_base=other_base) == []


def test_search_endpoint_returns_scored_hits(issued_key, client_for, knowledge_base):
    response = client_for(issued_key.raw_key).post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/search",
        {"query": "where can visitors park", "limit": 1},
        format="json",
    )

    body = response.json()
    assert response.status_code == 200
    assert [hit["document_title"] for hit in body["results"]] == ["Parking"]
    assert set(body["results"][0]) == {
        "chunk_id",
        "document_id",
        "document_title",
        "position",
        "text",
        "score",
    }


def test_search_endpoint_hides_other_tenants_knowledge_bases(
    issued_key, client_for, other_base, other_tenant
):
    client = client_for(issued_key.raw_key)

    response = client.post(
        f"/v1/knowledge-bases/{other_base.pk}/search", {"query": "salary"}, format="json"
    )

    assert response.status_code == 404
    other_client = client_for(ApiKey.issue(other_tenant, "other").raw_key)
    own = other_client.post(
        f"/v1/knowledge-bases/{other_base.pk}/search", {"query": "salary"}, format="json"
    )
    assert own.status_code == 200


@pytest.mark.parametrize(
    "payload", [{}, {"query": ""}, {"query": "x", "limit": 0}, {"query": "x", "limit": 21}]
)
def test_search_endpoint_validates_the_payload(issued_key, client_for, knowledge_base, payload):
    response = client_for(issued_key.raw_key).post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/search", payload, format="json"
    )

    assert response.status_code == 400
