"""Deterministic, dependency-free embedders for tests and offline dev (no model downloads).

Hashed bag-of-words: texts sharing words get similar vectors, so retrieval tests behave
like a (crude) real system instead of returning random neighbours.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence

from dgbot.retrieval.embeddings import SparseVector

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in _WORD.findall(text)]


def _bucket(token: str, size: int) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big") % size


class FakeDenseEmbedder:
    name = "fake-dense"

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token, count in Counter(_tokens(text)).items():
            vec[_bucket(token, self.dim)] += count
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeSparseEmbedder:
    name = "fake-sparse"

    def _sparse(self, text: str) -> SparseVector:
        counts = Counter(_bucket(t, 1 << 20) for t in _tokens(text))
        indices = sorted(counts)
        return SparseVector(indices, [float(counts[i]) for i in indices])

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        return [self._sparse(t) for t in texts]

    def embed_query(self, text: str) -> SparseVector:
        return self._sparse(text)
