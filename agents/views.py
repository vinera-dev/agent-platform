from datetime import date
from uuid import UUID

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.idempotency import read_idempotency_key, request_fingerprint
from agents.models import Agent, AgentVersion, InvalidTransition, Run
from agents.pagination import DefaultPagination
from agents.serializers import (
    AgentSerializer,
    AgentVersionSerializer,
    RunCreateSerializer,
    RunSerializer,
    UsageResponseSerializer,
)
from agents.tasks import execute_run
from agents.usage import filter_period, summarize
from tenants.scoping import TenantScopedViewMixin


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class IdempotencyKeyReused(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "This Idempotency-Key was already used with a different request."
    default_code = "idempotency_key_reused"


class AgentViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class AgentVersionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AgentVersionSerializer

    def get_agent(self):
        return get_object_or_404(
            Agent.objects.for_tenant(self.request.user.tenant), pk=self.kwargs["agent_id"]
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["tenant"] = self.request.user.tenant
        return context

    def get_queryset(self):
        return AgentVersion.objects.filter(agent=self.get_agent())

    def create(self, request, *args, **kwargs):
        self.get_agent()
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        agent = self.get_agent()
        serializer.instance = agent.new_version(**serializer.validated_data)

    def _transition(self, action_name):
        version = self.get_object()
        try:
            getattr(version, action_name)()
        except InvalidTransition as error:
            raise Conflict(str(error)) from error
        return Response(self.get_serializer(version).data)

    @extend_schema(request=None, responses=AgentVersionSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, agent_id=None, pk=None):
        return self._transition("publish")

    @extend_schema(request=None, responses=AgentVersionSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, agent_id=None, pk=None):
        return self._transition("archive")


class AgentRunViewSet(viewsets.GenericViewSet):
    serializer_class = RunCreateSerializer

    @extend_schema(
        request=RunCreateSerializer,
        responses={202: RunSerializer},
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                location=OpenApiParameter.HEADER,
                required=False,
                description="Repeating a request with the same key returns the original run.",
            )
        ],
    )
    def create(self, request, agent_id=None):
        tenant = request.user.tenant
        agent = get_object_or_404(Agent.objects.for_tenant(tenant), pk=agent_id)
        payload = RunCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        key = read_idempotency_key(request)
        fingerprint = request_fingerprint(agent.pk, payload.validated_data["input"])
        if key:
            replay = self._replay(tenant, key, fingerprint)
            if replay is not None:
                return replay
        version = agent.versions.filter(status=AgentVersion.Status.PUBLISHED).first()
        if version is None:
            raise Conflict("The agent has no published version.")
        try:
            with transaction.atomic():
                run = Run.objects.create(
                    tenant=tenant,
                    agent_version=version,
                    input=payload.validated_data["input"],
                    idempotency_key=key or "",
                    request_fingerprint=fingerprint,
                )
        except IntegrityError:
            replay = self._replay(tenant, key, fingerprint) if key else None
            if replay is None:
                raise
            return replay
        transaction.on_commit(lambda: execute_run.delay(str(run.id)))
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    def _replay(self, tenant, key, fingerprint):
        existing = Run.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyKeyReused()
        response = Response(RunSerializer(existing).data, status=status.HTTP_202_ACCEPTED)
        response["Idempotent-Replayed"] = "true"
        return response


class RunViewSet(
    TenantScopedViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = RunSerializer
    pagination_class = DefaultPagination
    queryset = Run.objects.select_related("agent_version")

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        agent_filter = self.request.query_params.get("agent")
        if status_filter:
            if status_filter not in Run.Status.values:
                raise ValidationError(
                    {"status": f"Must be one of: {', '.join(Run.Status.values)}."}
                )
            queryset = queryset.filter(status=status_filter)
        if agent_filter:
            try:
                queryset = queryset.filter(agent_version__agent_id=UUID(agent_filter))
            except ValueError as error:
                raise ValidationError({"agent": "Must be a valid UUID."}) from error
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", enum=Run.Status.values, required=False),
            OpenApiParameter("agent", type=OpenApiTypes.UUID, required=False),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


def parse_date_param(params, name):
    value = params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError({name: "Must be a date in YYYY-MM-DD format."}) from error


class UsageView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("from", type=OpenApiTypes.DATE, required=False),
            OpenApiParameter("to", type=OpenApiTypes.DATE, required=False),
        ],
        responses=UsageResponseSerializer,
    )
    def get(self, request):
        start = parse_date_param(request.query_params, "from")
        end = parse_date_param(request.query_params, "to")
        if start and end and start > end:
            raise ValidationError({"from": "Must not be after the end date."})
        runs = filter_period(Run.objects.for_tenant(request.user.tenant), start, end)
        return Response(
            {
                "period": {
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                },
                **summarize(runs),
            }
        )
