from types import SimpleNamespace

import httpx
import openai
import pytest
from django.core.exceptions import ImproperlyConfigured

from agents.providers import (
    AzureOpenAIProvider,
    FakeProvider,
    ProviderError,
    TransientProviderError,
    get_provider,
    user_message,
)

REQUEST = httpx.Request("POST", "https://example.invalid/chat")
CALL = {
    "model": "gpt-4o-mini",
    "system_prompt": "Be helpful.",
    "user_input": {"message": "hi"},
    "parameters": {"temperature": 0.2},
    "timeout": 5.0,
}


def status_error(error_class, status):
    response = httpx.Response(status, request=REQUEST)
    return error_class("failure", response=response, body=None)


class StubClient:
    def __init__(self, response=None, error=None):
        self.requests = []
        self._response = response
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def response(text="hello", choices=True):
    message = SimpleNamespace(content=text)
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)] if choices else [], usage=usage
    )


def test_user_message_prefers_the_message_field():
    assert user_message({"message": "hi", "other": 1}) == "hi"
    assert user_message({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'


def test_fake_provider_records_calls_and_never_touches_the_network():
    provider = FakeProvider(reply="echo")

    completion = provider.complete(**CALL)

    assert completion.text == "echo: hi"
    assert provider.calls == [CALL]


def test_fake_provider_raises_scripted_failures_first():
    provider = FakeProvider(failures=[TransientProviderError("boom")])

    with pytest.raises(TransientProviderError):
        provider.complete(**CALL)
    assert provider.complete(**CALL).text == "fake reply: hi"


def test_azure_provider_sends_the_prompt_and_parameters():
    client = StubClient(response("hello"))

    completion = AzureOpenAIProvider(client).complete(**CALL)

    sent = client.requests[0]
    assert sent["model"] == "gpt-4o-mini"
    assert sent["messages"] == [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "hi"},
    ]
    assert sent["temperature"] == 0.2
    assert sent["timeout"] == 5.0
    assert completion.text == "hello"
    assert completion.usage == {"prompt_tokens": 11, "completion_tokens": 7}


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=REQUEST),
        openai.APIConnectionError(request=REQUEST),
        status_error(openai.RateLimitError, 429),
        status_error(openai.InternalServerError, 503),
    ],
)
def test_azure_provider_marks_retryable_failures_as_transient(error):
    with pytest.raises(TransientProviderError):
        AzureOpenAIProvider(StubClient(error=error)).complete(**CALL)


@pytest.mark.parametrize(
    "error",
    [status_error(openai.BadRequestError, 400), status_error(openai.AuthenticationError, 401)],
)
def test_azure_provider_does_not_retry_client_errors(error):
    with pytest.raises(ProviderError) as raised:
        AzureOpenAIProvider(StubClient(error=error)).complete(**CALL)

    assert not isinstance(raised.value, TransientProviderError)


def test_azure_provider_rejects_empty_responses():
    with pytest.raises(ProviderError):
        AzureOpenAIProvider(StubClient(response(choices=False))).complete(**CALL)


def test_get_provider_builds_the_configured_provider(settings):
    settings.LLM_PROVIDER = "fake"

    assert isinstance(get_provider(), FakeProvider)


def test_get_provider_rejects_unknown_names(settings):
    settings.LLM_PROVIDER = "other"

    with pytest.raises(ImproperlyConfigured):
        get_provider()


def test_azure_provider_needs_credentials(settings):
    settings.LLM_PROVIDER = "azure"
    settings.AZURE_OPENAI_ENDPOINT = ""
    settings.AZURE_OPENAI_API_KEY = ""

    with pytest.raises(ImproperlyConfigured) as raised:
        get_provider()

    assert "AZURE_OPENAI_ENDPOINT" in str(raised.value)


def test_azure_provider_builds_with_credentials(settings):
    settings.LLM_PROVIDER = "azure"
    settings.AZURE_OPENAI_ENDPOINT = "https://example.invalid"
    settings.AZURE_OPENAI_API_KEY = "test-key"

    assert isinstance(get_provider(), AzureOpenAIProvider)
