import hashlib
import math
import re
from collections.abc import Callable
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

EMBEDDING_DIMENSIONS = 256
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


SUFFIXES = ("ing", "ed", "ches", "shes", "xes", "zes", "s")
KEPT_ENDINGS = ("ss", "us", "is")
MIN_STEM_LENGTH = 3


def strip_suffix(word: str, suffix: str) -> str:
    if suffix == "s":
        return word[:-1]
    if suffix in ("ches", "shes", "xes", "zes"):
        return word[:-2]
    return word[: -len(suffix)]


def stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and not word.endswith(KEPT_ENDINGS):
            stripped = strip_suffix(word, suffix)
            return stripped if len(stripped) >= MIN_STEM_LENGTH else word
    return word


def tokenize(text: str) -> list[str]:
    return [stem(word) for word in TOKEN_PATTERN.findall(text.lower())]


class HashingEmbedder:
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize(text)
        features = tokens + [
            f"{left} {right}" for left, right in zip(tokens, tokens[1:], strict=False)
        ]
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 if " " not in feature else 0.5
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


EMBEDDER_BUILDERS: dict[str, Callable[[], Embedder]] = {"hashing": HashingEmbedder}


def get_embedder() -> Embedder:
    name = settings.EMBEDDER
    try:
        return EMBEDDER_BUILDERS[name]()
    except KeyError as error:
        raise ImproperlyConfigured(f"Unknown embedder: {name}.") from error
