from celery import shared_task


@shared_task(name="agents.execute_run")
def execute_run(run_id: str) -> str:
    return run_id
