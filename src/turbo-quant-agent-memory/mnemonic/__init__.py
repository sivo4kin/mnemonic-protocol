from .models import MemoryItem, EmbeddingRecord, QuantizedRecord, SearchResult
from .math_utils import dot, l2_norm, normalize, clip
from .cache import EmbeddingCache
from .embedders import BaseEmbeddingProvider, MockEmbeddingProvider, OpenAIEmbeddingProvider, NomicEmbeddingProvider, build_embedder, _has_embed_batch
from .quantizer import CalibratedScalarQuantizer
from .store import MemoryStore
from .indexer import MemoryIndexer
from .retriever import MemoryRetriever
from .persistence import (
    load_jsonl, ingest_memory_jsonl,
    save_to_sqlite, load_from_sqlite,
    snapshot_items, restore_from_snapshot,
)
from .benchmark import (
    build_system, generate_synthetic_corpus, recall_at_k,
    estimate_index_bytes, quant_diagnostics,
    run_benchmark, run_multidomain_benchmark,
    run_persist_test, run_provider_switch_test,
)
