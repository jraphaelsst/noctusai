"""Vector/KB seam — Protocol + Fake + SupabaseReal + factory.

A noc seed GAP shaped for promotion: once the seed gains a KB seam this package
becomes a thin re-export of ``noctusai_lib.integrations.vectors``.
"""
from app.integrations.vectors.factory import VectorStoreNotConfigured, make_vector_store
from app.integrations.vectors.fake import FakeVectorStore
from app.integrations.vectors.local import LocalVectorStore
from app.integrations.vectors.protocol import VectorStore
from app.integrations.vectors.supabase_adapter import SupabaseVectorStore
from app.integrations.vectors.types import KBChunk, KBHit

__all__ = [
    "VectorStore",
    "KBChunk",
    "KBHit",
    "FakeVectorStore",
    "LocalVectorStore",
    "SupabaseVectorStore",
    "make_vector_store",
    "VectorStoreNotConfigured",
]
