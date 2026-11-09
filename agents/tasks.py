from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from agents.execution import ExecutionError, RetrievalFailed, TraceEvent, generate
from agents.models import Run
from agents.providers import ProviderError, TransientProviderError, get_provider
from agents.tracing import trace_run_safely

RETRIEVAL_ERROR = "Knowledge retrieval failed: {detail}"
TIMEOUT_ERROR = "The run exceeded the time limit."
RETRIES_EXHAUSTED_ERROR = "The provider kept failing after {attempts} attempts: {detail}"


def retry_delay(retries: int) -> float:
    return settings.RUN_RETRY_BACKOFF_SECONDS * (2**retries)


@shared_task(
    bind=True, name="agents.execute_run", soft_time_limit=int(settings.RUN_TIMEOUT_SECONDS) + 5
)
def execute_run(self, run_id: str) -> str:
    run = Run.objects.select_related("agent_version", "tenant").filter(pk=run_id).first()
    if run is None or run.status in (Run.Status.SUCCEEDED, Run.Status.FAILED):
        return run_id
    if run.status == Run.Status.PENDING:
        run.mark_running()
    events: list[TraceEvent] = []
    try:
        result = generate(
            tenant=run.tenant,
            version=run.agent_version,
            user_input=run.input,
            provider=get_provider(),
            timeout=settings.RUN_TIMEOUT_SECONDS,
            events=events,
        )
    except SoftTimeLimitExceeded:
        run.mark_failed(TIMEOUT_ERROR)
    except TransientProviderError as error:
        attempts = self.request.retries + 1
        if self.request.retries >= settings.RUN_MAX_RETRIES:
            run.mark_failed(RETRIES_EXHAUSTED_ERROR.format(attempts=attempts, detail=error))
        else:
            raise self.retry(
                exc=error,
                countdown=retry_delay(self.request.retries),
                max_retries=settings.RUN_MAX_RETRIES,
            ) from error
    except RetrievalFailed as error:
        run.mark_failed(RETRIEVAL_ERROR.format(detail=error))
    except (ProviderError, ExecutionError) as error:
        run.mark_failed(str(error))
    else:
        run.mark_succeeded(result.as_output())
    trace_run_safely(run, events)
    return run_id
