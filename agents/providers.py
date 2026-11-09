import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ProviderError(Exception):
    pass


class TransientProviderError(ProviderError):
    pass


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_input: dict[str, Any],
        parameters: dict[str, Any],
        timeout: float,
    ) -> Completion: ...


def user_message(user_input: dict[str, Any]) -> str:
    message = user_input.get("message")
    if isinstance(message, str):
        return message
    return json.dumps(user_input, ensure_ascii=False, sort_keys=True)


@dataclass
class FakeProvider:
    reply: str = "fake reply"
    failures: list[Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_input: dict[str, Any],
        parameters: dict[str, Any],
        timeout: float,
    ) -> Completion:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_input": user_input,
                "parameters": parameters,
                "timeout": timeout,
            }
        )
        if self.failures:
            raise self.failures.pop(0)
        return Completion(
            text=f"{self.reply}: {user_message(user_input)}",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )


class AzureOpenAIProvider:
    def __init__(self, client: Any) -> None:
        self._client = client

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_input: dict[str, Any],
        parameters: dict[str, Any],
        timeout: float,
    ) -> Completion:
        import openai

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message(user_input)},
                ],
                timeout=timeout,
                **parameters,
            )
        except (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError) as error:
            raise TransientProviderError(str(error)) from error
        except openai.InternalServerError as error:
            raise TransientProviderError(str(error)) from error
        except openai.OpenAIError as error:
            raise ProviderError(str(error)) from error
        if not response.choices:
            raise ProviderError("The provider returned no choices.")
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
            },
        )


def build_azure_provider() -> AzureOpenAIProvider:
    from openai import AzureOpenAI

    missing = [
        name
        for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY")
        if not getattr(settings, name, "")
    ]
    if missing:
        raise ImproperlyConfigured(
            f"Missing settings for the Azure provider: {', '.join(missing)}."
        )
    client = AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        max_retries=0,
    )
    return AzureOpenAIProvider(client)


PROVIDER_BUILDERS: dict[str, Callable[[], LLMProvider]] = {
    "azure": build_azure_provider,
    "fake": FakeProvider,
}


def get_provider() -> LLMProvider:
    name = settings.LLM_PROVIDER
    try:
        return PROVIDER_BUILDERS[name]()
    except KeyError as error:
        raise ImproperlyConfigured(f"Unknown LLM provider: {name}.") from error
