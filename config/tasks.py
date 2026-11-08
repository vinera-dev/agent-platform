from celery import shared_task


@shared_task(name="config.ping")
def ping(value):
    return {"pong": value}
