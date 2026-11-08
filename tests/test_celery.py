import os

import pytest
from celery.contrib.testing.worker import start_worker

from config import celery_app
from config.tasks import ping


def test_settings_configure_celery_from_redis_url(settings):
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert settings.CELERY_BROKER_URL.startswith("redis://")
    assert celery_app.conf.task_serializer == "json"


def test_test_task_is_registered():
    assert "config.ping" in celery_app.tasks


@pytest.fixture
def eager():
    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = previous


def test_task_runs_eagerly_in_tests(eager):

    result = ping.delay("hello")

    assert result.get() == {"pong": "hello"}


@pytest.mark.skipif(
    not os.environ.get("CELERY_INTEGRATION_REDIS"), reason="CELERY_INTEGRATION_REDIS not set"
)
def test_task_runs_in_a_worker_against_real_redis():
    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    celery_app.conf.broker_url = os.environ["CELERY_INTEGRATION_REDIS"]
    celery_app.conf.result_backend = os.environ["CELERY_INTEGRATION_REDIS"]
    try:
        with start_worker(celery_app, perform_ping_check=False, pool="solo"):
            assert ping.delay("hi").get(timeout=15) == {"pong": "hi"}
    finally:
        celery_app.conf.task_always_eager = previous
