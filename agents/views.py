from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from agents.models import Agent, AgentVersion, InvalidTransition, Run
from agents.serializers import (
    AgentSerializer,
    AgentVersionSerializer,
    RunCreateSerializer,
    RunSerializer,
)
from agents.tasks import execute_run
from tenants.scoping import TenantScopedViewMixin


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


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

    def get_queryset(self):
        return AgentVersion.objects.filter(agent=self.get_agent())

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

    @extend_schema(request=RunCreateSerializer, responses={202: RunSerializer})
    def create(self, request, agent_id=None):
        tenant = request.user.tenant
        agent = get_object_or_404(Agent.objects.for_tenant(tenant), pk=agent_id)
        version = agent.versions.filter(status=AgentVersion.Status.PUBLISHED).first()
        if version is None:
            raise Conflict("The agent has no published version.")
        payload = RunCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = Run.objects.create(
            tenant=tenant, agent_version=version, input=payload.validated_data["input"]
        )
        transaction.on_commit(lambda: execute_run.delay(str(run.id)))
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)
