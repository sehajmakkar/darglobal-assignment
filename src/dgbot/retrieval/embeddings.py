"""Text → vectors. Dense (semantic, multilingual) + sparse (BM25 keywords). Local, no API
quota (D-008). Each model family wants its own query/passage prefixes — getting them wrong
silently hurts retrieval, so they live in one table here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class DenseEmbedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SparseEmbedder(Protocol):
    name: str

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]: ...

    def embed_query(self, text: str) -> SparseVector: ...


# (query prefix, passage prefix) per model family — from each model's card.
_PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5": ("query: ", "passage: "),
    "google/embeddinggemma": ("task: search result | query: ", "title: none | text: "),
    "Qwen/Qwen3-Embedding": (
        "Instruct: Given a real-estate question, retrieve passages that answer it\nQuery: ",
        "",
    ),
}


def prefixes_for(model: str) -> tuple[str, str]:
    return next((p for family, p in _PREFIXES.items() if model.startswith(family)), ("", ""))


# Models fastembed doesn't list but can load from an ONNX file in a public repo.
# EmbeddingGemma int8: same weights and repo as fastembed's built-in fp32 model, quantized
# to 309 MB instead of 1.24 GB — loads ~4x faster after a Cloud Run cold start (D-053).
# Output `sentence_embedding` is the model's own pooled vector, as the built-in uses.
_CUSTOM_DENSE: dict[str, tuple[str, str, int]] = {
    # name: (hf repo, onnx file, dim)
    "google/embeddinggemma-300m-int8": (
        "onnx-community/embeddinggemma-300m-ONNX",
        "onnx/model_quantized.onnx",
        768,
    ),
}


def _register_custom_dense(model: str) -> None:
    """Teach fastembed a model from `_CUSTOM_DENSE` (its registry is process-wide)."""
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if model not in _CUSTOM_DENSE or any(
        m["model"] == model for m in TextEmbedding.list_supported_models()
    ):
        return
    repo, onnx_file, dim = _CUSTOM_DENSE[model]
    TextEmbedding.add_custom_model(
        model=model,
        pooling=PoolingType.DISABLED,
        normalization=True,
        sources=ModelSource(hf=repo),
        dim=dim,
        model_file=onnx_file,
        additional_files=[f"{onnx_file}_data"],
        output_name="sentence_embedding",
    )


class FastEmbedDense:
    """fastembed (ONNX, CPU) dense model. Loaded once; reuse the instance."""

    def __init__(self, model: str, cache_dir: Path | None = None, batch_size: int = 32) -> None:
        from fastembed import TextEmbedding  # heavy import: only when actually used

        self.name = model
        _register_custom_dense(model)
        self._model = TextEmbedding(model, cache_dir=str(cache_dir) if cache_dir else None)
        self._query_prefix, self._passage_prefix = prefixes_for(model)
        self._batch_size = batch_size
        self.dim = len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        inputs = [self._passage_prefix + t for t in texts]
        return [v.tolist() for v in self._model.embed(inputs, batch_size=self._batch_size)]

    def embed_query(self, text: str) -> list[float]:
        vector: list[float] = next(iter(self._model.embed([self._query_prefix + text]))).tolist()
        return vector


class FastEmbedSparse:
    """BM25 via fastembed: term weights for exact names ("Pagani", "DG1", "Mouawad")."""

    def __init__(self, model: str = "Qdrant/bm25", cache_dir: Path | None = None) -> None:
        from fastembed import SparseTextEmbedding

        self.name = model
        self._model = SparseTextEmbedding(model, cache_dir=str(cache_dir) if cache_dir else None)

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        return [
            SparseVector(e.indices.tolist(), e.values.tolist())
            for e in self._model.embed(list(texts))
        ]

    def embed_query(self, text: str) -> SparseVector:
        e = next(iter(self._model.query_embed(text)))
        return SparseVector(e.indices.tolist(), e.values.tolist())
