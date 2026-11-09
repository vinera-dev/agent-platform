import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from knowledge.models import Document, KnowledgeBase
from tenants.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(issued_key, client_for):
    return client_for(issued_key.raw_key)


@pytest.fixture
def other_client(make_tenant, client_for):
    other = make_tenant(slug="other-clinic", name="Other Clinic")
    return client_for(ApiKey.issue(other, "other").raw_key)


@pytest.fixture
def knowledge_base(tenant):
    return KnowledgeBase.objects.create(tenant=tenant, name="Clinic FAQ")


def upload(client, knowledge_base, name="hours.txt", data=b"Open every day.", **extra):
    return client.post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/documents",
        {"file": SimpleUploadedFile(name, data), **extra},
        format="multipart",
    )


def test_creates_a_knowledge_base_for_the_calling_tenant(client, tenant):
    response = client.post("/v1/knowledge-bases", {"name": "FAQ"}, format="json")

    assert response.status_code == 201
    assert KnowledgeBase.objects.get(pk=response.json()["id"]).tenant == tenant


def test_knowledge_base_names_must_be_unique_per_tenant(client, knowledge_base):
    response = client.post("/v1/knowledge-bases", {"name": knowledge_base.name}, format="json")

    assert response.status_code == 400


def test_knowledge_bases_are_invisible_to_other_tenants(other_client, knowledge_base):
    assert other_client.get("/v1/knowledge-bases").json() == []
    assert other_client.get(f"/v1/knowledge-bases/{knowledge_base.pk}").status_code == 404


def test_uploads_a_text_document(client, knowledge_base, tenant):
    response = upload(client, knowledge_base, title="Opening hours")

    body = response.json()
    document = Document.objects.get(pk=body["id"])
    assert response.status_code == 202
    assert body["title"] == "Opening hours"
    assert body["status"] == "pending"
    assert body["size_bytes"] == 15
    assert document.tenant == tenant
    assert document.content == "Open every day."
    assert len(document.content_sha256) == 64


def test_title_defaults_to_the_file_name(client, knowledge_base):
    assert upload(client, knowledge_base).json()["title"] == "hours.txt"


def test_large_file_is_rejected_with_413(client, knowledge_base, settings):
    settings.MAX_DOCUMENT_BYTES = 100

    response = upload(client, knowledge_base, data=b"a" * 101)

    assert response.status_code == 413
    assert Document.objects.count() == 0


def test_file_at_the_limit_is_accepted(client, knowledge_base, settings):
    settings.MAX_DOCUMENT_BYTES = 100

    assert upload(client, knowledge_base, data=b"a" * 100).status_code == 202


def test_declared_content_length_is_rejected_before_parsing(client, knowledge_base, settings):
    settings.MAX_DOCUMENT_BYTES = 100

    response = client.post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/documents",
        data=b"x",
        content_type="multipart/form-data; boundary=x",
        CONTENT_LENGTH="999999",
    )

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("notes.pdf", b"text"),
        ("notes.txt", b"\xff\xfe\x00bad"),
        ("notes.txt", b"   \n  "),
        ("notes.txt", b"has\x00nul"),
    ],
)
def test_invalid_files_are_rejected(client, knowledge_base, name, data):
    response = upload(client, knowledge_base, name=name, data=data)

    assert response.status_code == 400
    assert Document.objects.count() == 0


def test_missing_file_is_rejected(client, knowledge_base):
    response = client.post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/documents", {"title": "x"}, format="multipart"
    )

    assert response.status_code == 400


def test_cannot_upload_to_another_tenants_knowledge_base(other_client, knowledge_base):
    response = upload(other_client, knowledge_base)

    assert response.status_code == 404
    assert Document.objects.count() == 0


def test_documents_are_listed_and_deleted_within_the_tenant(client, other_client, knowledge_base):
    document_id = upload(client, knowledge_base).json()["id"]
    base = f"/v1/knowledge-bases/{knowledge_base.pk}/documents"

    assert [item["id"] for item in client.get(base).json()] == [document_id]
    assert other_client.get(base).status_code == 404
    assert other_client.delete(f"{base}/{document_id}").status_code == 404
    assert client.delete(f"{base}/{document_id}").status_code == 204
    assert Document.objects.count() == 0


def test_requires_authentication(client_for, knowledge_base):
    response = client_for("bad.key").post(
        f"/v1/knowledge-bases/{knowledge_base.pk}/documents", {}, format="multipart"
    )

    assert response.status_code == 401
