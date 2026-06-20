"""SQLite-backed retrieval helpers for product knowledge chunks."""

from .chunking import ChunkMeta, chunk_product
from .fusion import HybridRetriever, rrf_fuse

__all__ = ["ChunkMeta", "HybridRetriever", "chunk_product", "rrf_fuse"]
