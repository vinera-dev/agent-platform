from rest_framework import serializers

from knowledge.models import Document, KnowledgeBase


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = ["id", "name", "description", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        tenant = self.context.get("tenant")
        if tenant is not None:
            duplicates = KnowledgeBase.objects.for_tenant(tenant).filter(name=value)
            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError("A knowledge base with this name already exists.")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    knowledge_base_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "knowledge_base_id",
            "title",
            "size_bytes",
            "status",
            "error",
            "created_at",
            "ingested_at",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False)
    title = serializers.CharField(max_length=255, required=False, allow_blank=False)


class SearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=20, default=5)


class SearchHitSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField()
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    position = serializers.IntegerField()
    text = serializers.CharField()
    score = serializers.FloatField()


class SearchResponseSerializer(serializers.Serializer):
    results = SearchHitSerializer(many=True)
