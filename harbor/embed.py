"""Local embeddings (no API key, runs on a free CPU host). bge-small: 384 dimensions."""

from functools import cache

from fastembed import TextEmbedding

MODEL = "BAAI/bge-small-en-v1.5"


@cache
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
