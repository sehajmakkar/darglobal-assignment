"""A small, fully fake runtime for API/service tests: no models, no network, no quota."""

from qdrant_client import QdrantClient

from dgbot.api.dependencies import Runtime
from dgbot.chat.cache import AnswerCache
from dgbot.chat.service import ChatService
from dgbot.domain.models import Chunk, Source
from dgbot.llm.fake import FakeLLMClient
from dgbot.retrieval.fake import FakeDenseEmbedder, FakeSparseEmbedder
from dgbot.retrieval.retriever import HybridRetriever
from dgbot.retrieval.vectorstore import QdrantStore

CHUNKS = [
    (
        "darglobal:project:the-astera",
        "The Astera — DarGlobal project\nInteriors by Aston Martin on Al Marjan Island, RAK.",
    ),
    ("darglobal:project:dg1", "DG1 — DarGlobal project\nResidential tower in Business Bay, Dubai."),
    (
        "wasalt:summary:city:riyadh:rent",
        "Wasalt — properties for rent in Riyadh\nApartments and villas in 171 districts.",
    ),
]


def fake_retriever() -> HybridRetriever:
    chunks = [
        Chunk(
            id=f"{rid}#card-0",
            record_id=rid,
            record_type="project",
            section="card",
            source=Source.WASALT if rid.startswith("wasalt") else Source.DARGLOBAL,
            url=f"https://example.test/{rid.rsplit(':', 1)[-1]}",
            title=rid.rsplit(":", 1)[-1],
            text=text,
        )
        for rid, text in CHUNKS
    ]
    dense, sparse = FakeDenseEmbedder(), FakeSparseEmbedder()
    store = QdrantStore(QdrantClient(":memory:"), "test")
    store.recreate(dense.dim)
    texts = [c.text for c in chunks]
    store.upsert(chunks, dense.embed_documents(texts), sparse.embed_documents(texts))
    return HybridRetriever(dense, sparse, store, top_k=3)


def fake_runtime(llm: FakeLLMClient | None = None) -> Runtime:
    service = ChatService(fake_retriever(), llm or FakeLLMClient(), cache=AnswerCache(), top_k=3)
    return Runtime(
        chat=service, index_info={"embedding_model": "fake-dense", "chunks": len(CHUNKS)}
    )
