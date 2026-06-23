"""SQLite-backed retrieval helpers for product knowledge chunks."""

from .chunking import ChunkMeta, canonical_chunk_type, chunk_product
from .fusion import HybridRetriever, rrf_fuse
from .types import ChunkSearchResult, ProductRetrievalResult

__all__ = [
    "ChunkMeta",
    "ChunkSearchResult",
    "HybridRetriever",
    "ProductRetrievalResult",
    "canonical_chunk_type",
    "chunk_product",
    "rrf_fuse",
]
