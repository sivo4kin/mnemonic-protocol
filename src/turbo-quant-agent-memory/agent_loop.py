"""
Agent integration loop for the Mnemonic compressed memory system.

Demonstrates a reactive agent that processes multi-turn conversations,
storing and retrieving memories using the compressed index with exact
rerank pipeline. Runnable standalone with MockEmbeddingProvider.

Usage:
    python agent_loop.py
    python agent_loop.py --turns 15
    python agent_loop.py --turns 20 --bits 4
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from pseudocode import (
    MemoryStore,
    MemoryIndexer,
    MemoryRetriever,
    CalibratedScalarQuantizer,
    MockEmbeddingProvider,
    SearchResult,
    estimate_index_bytes,
    quant_diagnostics,
)


# ---------------------------------------------------------------------------
# Conversation scenario data
# ---------------------------------------------------------------------------

@dataclass
class AgentTurn:
    """One turn of the agent loop: a task/input and memories to store."""
    task: str
    memory_type: str = "episodic"
    importance: float = 0.5
    tags: List[str] = field(default_factory=list)


SCENARIO: List[AgentTurn] = [
    # Turn 0: bootstrap context
    AgentTurn(
        task="You are a research assistant. The user is working on a project about compressed vector indexes for agent memory systems. They want to understand tradeoffs between 4-bit and 8-bit quantization.",
        memory_type="semantic",
        importance=0.8,
        tags=["project-context", "quantization"],
    ),
    # Turn 1: first real question
    AgentTurn(
        task="What are the main approaches to compressing embedding vectors for nearest-neighbor search? Focus on scalar quantization vs product quantization.",
        memory_type="episodic",
        importance=0.6,
        tags=["quantization", "research"],
    ),
    # Turn 2: deeper dive
    AgentTurn(
        task="Explain how per-dimension calibration works in scalar quantization. Why is it better than global min-max scaling?",
        memory_type="semantic",
        importance=0.7,
        tags=["quantization", "calibration"],
    ),
    # Turn 3: switch topic — agent architecture
    AgentTurn(
        task="How should an autonomous agent organize its memory? I'm thinking about episodic vs semantic vs procedural memory types.",
        memory_type="semantic",
        importance=0.7,
        tags=["agent", "memory-architecture"],
    ),
    # Turn 4: decision point
    AgentTurn(
        task="Based on our discussion, I've decided to use 8-bit quantization for the initial deployment because recall@10 stays above 0.95 while cutting index size by 4x. We'll revisit 4-bit once we have rotation matrices implemented.",
        memory_type="decision",
        importance=0.9,
        tags=["decision", "quantization", "deployment"],
    ),
    # Turn 5: blockchain topic (cross-domain)
    AgentTurn(
        task="Now let's discuss the blockchain monitoring agent. It needs to track wallet transactions, detect bridge exploits, and alert on anomalous protocol behavior.",
        memory_type="episodic",
        importance=0.6,
        tags=["blockchain", "agent", "monitoring"],
    ),
    # Turn 6: recall earlier decision
    AgentTurn(
        task="What quantization bit-width did we decide on for the initial deployment? I want to make sure we document this.",
        memory_type="episodic",
        importance=0.4,
        tags=["recall", "decision"],
    ),
    # Turn 7: technical detail
    AgentTurn(
        task="The candidate generation step uses the compressed index for approximate scores, then the top candidates get reranked with exact float32 dot products. What's the typical candidate-to-final ratio?",
        memory_type="semantic",
        importance=0.6,
        tags=["retrieval", "reranking"],
    ),
    # Turn 8: new decision
    AgentTurn(
        task="For the blockchain agent's memory, we'll use a separate memory namespace with importance-weighted retrieval. High-importance alerts should always surface when querying recent risk events.",
        memory_type="decision",
        importance=0.85,
        tags=["decision", "blockchain", "memory-architecture"],
    ),
    # Turn 9: recall across topics
    AgentTurn(
        task="Summarize all the architectural decisions we've made so far about the memory system and the blockchain agent.",
        memory_type="episodic",
        importance=0.5,
        tags=["summary", "recall"],
    ),
    # Turn 10: KV cache topic
    AgentTurn(
        task="How does KV cache quantization relate to our embedding compression work? Both reduce memory bandwidth but operate at different levels of the inference stack.",
        memory_type="semantic",
        importance=0.6,
        tags=["kv-cache", "quantization", "inference"],
    ),
    # Turn 11: practical engineering
    AgentTurn(
        task="What's the memory overhead of keeping full-precision embeddings alongside the compressed index? For 100k memories at 384 dimensions, how much RAM do we need?",
        memory_type="episodic",
        importance=0.5,
        tags=["engineering", "memory-overhead"],
    ),
    # Turn 12: cross-reference
    AgentTurn(
        task="Going back to the blockchain monitoring agent — should it use the same compressed memory architecture or does the real-time alerting requirement change things?",
        memory_type="episodic",
        importance=0.6,
        tags=["blockchain", "architecture", "retrieval"],
    ),
    # Turn 13: decision on retrieval
    AgentTurn(
        task="Decision: the blockchain agent will use the same compressed index but with a lower candidate count (20 instead of 50) to keep latency under 10ms for alert correlation.",
        memory_type="decision",
        importance=0.9,
        tags=["decision", "blockchain", "latency"],
    ),
    # Turn 14: final recall
    AgentTurn(
        task="List all decisions we've recorded in this session about quantization settings and the blockchain agent architecture.",
        memory_type="episodic",
        importance=0.4,
        tags=["recall", "summary"],
    ),
    # Turn 15: saturation analysis
    AgentTurn(
        task="How do saturation rates in the quantizer affect retrieval quality? If a dimension is frequently clipped, does that degrade the approximation?",
        memory_type="semantic",
        importance=0.6,
        tags=["quantization", "saturation", "quality"],
    ),
    # Turn 16: rotation discussion
    AgentTurn(
        task="Random rotation matrices like in QJL or RaBitQ spread information across dimensions before quantization. This should reduce saturation and improve recall at 4-bit.",
        memory_type="semantic",
        importance=0.7,
        tags=["quantization", "rotation", "4-bit"],
    ),
    # Turn 17: final decision
    AgentTurn(
        task="Final architecture decision: compressed memory system with 8-bit default, optional 4-bit with rotation for large indexes over 1M memories. Rerank top-50 candidates for standard queries, top-20 for latency-sensitive blockchain alerts.",
        memory_type="decision",
        importance=1.0,
        tags=["decision", "architecture", "final"],
    ),
    # Turn 18: wrap-up retrieval test
    AgentTurn(
        task="What do we know about the tradeoffs between 4-bit and 8-bit quantization from this conversation?",
        memory_type="episodic",
        importance=0.3,
        tags=["recall", "quantization"],
    ),
    # Turn 19: meta-observation
    AgentTurn(
        task="How many memories have we accumulated? Is the retrieval system still performing well with this many entries?",
        memory_type="episodic",
        importance=0.3,
        tags=["meta", "performance"],
    ),
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@dataclass
class TurnStats:
    turn: int
    task_preview: str
    n_retrieved: int
    top_score: float
    top_exact_score: float
    memories_before: int
    memories_after: int
    index_rebuilt: bool
    retrieval_time_ms: float
    exact_time_ms: float
    exact_top_score: float


class MemoryAgent:
    """Reactive agent that uses compressed memory for context retrieval."""

    REBUILD_INTERVAL = 3  # rebuild quantized index every N ingestions

    def __init__(self, bits: int = 8, dim: int = 384):
        self.store = MemoryStore()
        self.embedder = MockEmbeddingProvider(dim=dim)
        self.quantizer = CalibratedScalarQuantizer(bits=bits)
        self.indexer = MemoryIndexer(self.store, self.embedder, self.quantizer)
        self.retriever = MemoryRetriever(self.store, self.embedder, self.quantizer)

        self.turn_counter = 0
        self.memory_counter = 0
        self.ingestions_since_rebuild = 0
        self.turn_stats: List[TurnStats] = []

    def _next_memory_id(self) -> str:
        self.memory_counter += 1
        return f"mem_{self.memory_counter:04d}"

    def _should_rebuild(self) -> bool:
        return self.ingestions_since_rebuild >= self.REBUILD_INTERVAL

    def _rebuild_if_needed(self) -> bool:
        """Scheduled rebuild based on ingestion count."""
        if self._should_rebuild() and len(self.store.memory_ids()) > 0:
            self.indexer.rebuild_quantized_index()
            self.ingestions_since_rebuild = 0
            return True
        return False

    def _has_unindexed_memories(self) -> bool:
        """Check if any memory lacks a quantized record."""
        for mid in self.store.memory_ids():
            if mid not in self.store.quantized:
                return True
        return False

    def _retrieve_context(
        self, query: str, k: int = 5, n_candidates: int = 15
    ) -> Tuple[List[SearchResult], float, List[SearchResult], float]:
        """Retrieve via compressed pipeline and exact search. Returns both results and timings."""
        if not self.store.quantized:
            return [], 0.0, [], 0.0

        # If there are unindexed memories, rebuild now so retrieval covers everything
        if self._has_unindexed_memories():
            self.indexer.rebuild_quantized_index()
            self.ingestions_since_rebuild = 0

        t0 = time.perf_counter()
        compressed_results = self.retriever.retrieve(query, k=k, n_candidates=n_candidates)
        t1 = time.perf_counter()
        exact_results = self.retriever.exact_search(query, k=k)
        t2 = time.perf_counter()

        return (
            compressed_results,
            (t1 - t0) * 1000,
            exact_results,
            (t2 - t1) * 1000,
        )

    def _store_memories(self, turn: AgentTurn, turn_idx: int) -> List[str]:
        """Store one or more memories from this turn. Returns list of stored IDs."""
        stored_ids = []

        # Store the user's input as an episodic memory
        mid = self._next_memory_id()
        self.indexer.ingest_memory(
            memory_id=mid,
            content=turn.task,
            memory_type=turn.memory_type,
            importance_score=turn.importance,
            tags=turn.tags + [f"turn:{turn_idx}"],
        )
        self.ingestions_since_rebuild += 1
        stored_ids.append(mid)

        # For decision-type turns, also store a compact decision summary
        if turn.memory_type == "decision":
            mid2 = self._next_memory_id()
            summary = f"[DECISION t{turn_idx}] {turn.task[:120]}"
            self.indexer.ingest_memory(
                memory_id=mid2,
                content=summary,
                memory_type="decision",
                importance_score=min(1.0, turn.importance + 0.1),
                tags=["decision-index"] + turn.tags + [f"turn:{turn_idx}"],
            )
            self.ingestions_since_rebuild += 1
            stored_ids.append(mid2)

        return stored_ids

    def run_turn(self, turn: AgentTurn) -> TurnStats:
        turn_idx = self.turn_counter
        self.turn_counter += 1
        memories_before = len(self.store.memory_ids())

        # --- Retrieve ---
        compressed_results, retr_ms, exact_results, exact_ms = self._retrieve_context(turn.task)

        top_score = compressed_results[0].exact_score if compressed_results and compressed_results[0].exact_score is not None else 0.0
        exact_top = exact_results[0].exact_score if exact_results and exact_results[0].exact_score is not None else 0.0

        # --- Print turn ---
        print(f"\n{'='*78}")
        print(f"TURN {turn_idx}  [{turn.memory_type.upper()}]  importance={turn.importance:.1f}")
        print(f"{'='*78}")
        task_display = turn.task if len(turn.task) <= 120 else turn.task[:117] + "..."
        print(f"  Task: {task_display}")
        print(f"  Tags: {', '.join(turn.tags)}")

        if compressed_results:
            print(f"\n  Retrieved memories (compressed -> rerank, {retr_ms:.1f}ms):")
            for i, r in enumerate(compressed_results[:5], 1):
                exact_str = f"exact={r.exact_score:.4f}" if r.exact_score is not None else ""
                content_preview = (r.content or "")[:80]
                print(f"    {i}. [{r.memory_id}] approx={r.approx_score:.4f} {exact_str}")
                print(f"       {content_preview}")

            print(f"\n  Exact search comparison ({exact_ms:.1f}ms):")
            for i, r in enumerate(exact_results[:3], 1):
                content_preview = (r.content or "")[:80]
                print(f"    {i}. [{r.memory_id}] score={r.exact_score:.4f}")
                print(f"       {content_preview}")
        else:
            print("\n  No memories indexed yet (first turns).")

        # --- Store ---
        stored_ids = self._store_memories(turn, turn_idx)
        rebuilt = self._rebuild_if_needed()

        memories_after = len(self.store.memory_ids())
        print(f"\n  Stored: {', '.join(stored_ids)}  |  Total memories: {memories_after}  |  Index rebuilt: {rebuilt}")

        stats = TurnStats(
            turn=turn_idx,
            task_preview=turn.task[:60],
            n_retrieved=len(compressed_results),
            top_score=top_score,
            top_exact_score=exact_top,
            memories_before=memories_before,
            memories_after=memories_after,
            index_rebuilt=rebuilt,
            retrieval_time_ms=retr_ms,
            exact_time_ms=exact_ms,
            exact_top_score=exact_top,
        )
        self.turn_stats.append(stats)
        return stats

    def print_summary(self) -> None:
        # Ensure all memories are indexed before computing stats
        if self._has_unindexed_memories():
            self.indexer.rebuild_quantized_index()

        print(f"\n{'#'*78}")
        print(f"  SESSION SUMMARY")
        print(f"{'#'*78}")

        n_turns = len(self.turn_stats)
        total_memories = len(self.store.memory_ids())
        n_decisions = sum(1 for mid in self.store.memory_ids() if self.store.items[mid].memory_type == "decision")
        n_semantic = sum(1 for mid in self.store.memory_ids() if self.store.items[mid].memory_type == "semantic")
        n_episodic = sum(1 for mid in self.store.memory_ids() if self.store.items[mid].memory_type == "episodic")

        print(f"\n  Turns processed:       {n_turns}")
        print(f"  Total memories:        {total_memories}")
        print(f"    episodic:            {n_episodic}")
        print(f"    semantic:            {n_semantic}")
        print(f"    decision:            {n_decisions}")

        # Index stats
        if self.store.quantized:
            float_bytes, compressed_bytes = estimate_index_bytes(self.store)
            ratio = compressed_bytes / max(1, float_bytes)
            sat_min, sat_mean, sat_max = quant_diagnostics(self.store)
            print(f"\n  Index size (float32):  {float_bytes:,} bytes")
            print(f"  Index size (quant):    {compressed_bytes:,} bytes")
            print(f"  Compression ratio:     {ratio:.4f}")
            print(f"  Quantizer bits:        {self.quantizer.bits}")
            print(f"  Avg alpha:             {self.quantizer.average_alpha():.4f}")
            print(f"  Saturation (min/mean/max): {sat_min:.4f} / {sat_mean:.4f} / {sat_max:.4f}")

        # Retrieval stats (skip turns with no retrievals)
        active_stats = [s for s in self.turn_stats if s.n_retrieved > 0]
        if active_stats:
            avg_top = sum(s.top_score for s in active_stats) / len(active_stats)
            avg_exact_top = sum(s.exact_top_score for s in active_stats) / len(active_stats)
            avg_retr_ms = sum(s.retrieval_time_ms for s in active_stats) / len(active_stats)
            avg_exact_ms = sum(s.exact_time_ms for s in active_stats) / len(active_stats)
            max_top = max(s.top_score for s in active_stats)
            min_top = min(s.top_score for s in active_stats)
            rebuilds = sum(1 for s in self.turn_stats if s.index_rebuilt)

            print(f"\n  Retrieval stats ({len(active_stats)} turns with results):")
            print(f"    Avg top reranked score:  {avg_top:.4f}")
            print(f"    Avg top exact score:     {avg_exact_top:.4f}")
            print(f"    Best top score:          {max_top:.4f}")
            print(f"    Worst top score:         {min_top:.4f}")
            print(f"    Avg retrieval time:      {avg_retr_ms:.2f}ms (compressed+rerank)")
            print(f"    Avg exact search time:   {avg_exact_ms:.2f}ms")
            print(f"    Index rebuilds:          {rebuilds}")

        # Per-turn table
        print(f"\n  Per-turn breakdown:")
        print(f"  {'Turn':>4}  {'Type':>9}  {'Mems':>4}  {'TopScore':>8}  {'ExactTop':>8}  {'RetrMs':>7}  {'Rebuilt':>7}  Task")
        print(f"  {'-'*4}  {'-'*9}  {'-'*4}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*30}")
        for s in self.turn_stats:
            print(
                f"  {s.turn:4d}  "
                f"{'rebuild' if s.index_rebuilt else '':>9s}  "
                f"{s.memories_after:4d}  "
                f"{s.top_score:8.4f}  "
                f"{s.exact_top_score:8.4f}  "
                f"{s.retrieval_time_ms:7.2f}  "
                f"{'yes' if s.index_rebuilt else 'no':>7s}  "
                f"{s.task_preview}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent integration loop for Mnemonic compressed memory"
    )
    parser.add_argument(
        "--turns", type=int, default=10,
        help="Number of simulated conversation turns (default: 10, max: %(default)s scenario entries available: 20)",
    )
    parser.add_argument(
        "--bits", type=int, default=8, choices=[4, 8],
        help="Quantization bit-width (default: 8)",
    )
    parser.add_argument(
        "--dim", type=int, default=384,
        help="Embedding dimension (default: 384)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    n_turns = min(args.turns, len(SCENARIO))
    if args.turns > len(SCENARIO):
        print(f"Note: requested {args.turns} turns but scenario has {len(SCENARIO)} entries. Running {n_turns}.")

    print(f"Mnemonic Agent Loop -- {n_turns} turns, {args.bits}-bit quantization, dim={args.dim}")
    print(f"Embedding provider: MockEmbeddingProvider (offline)")
    print(f"Index rebuild interval: every {MemoryAgent.REBUILD_INTERVAL} ingestions")

    agent = MemoryAgent(bits=args.bits, dim=args.dim)

    # Seed the index with a small initial rebuild after first few turns
    # so retrieval is available early
    for i in range(min(n_turns, len(SCENARIO))):
        turn = SCENARIO[i]
        agent.run_turn(turn)

        # Force a rebuild after turn 1 so retrieval works from turn 2 onward
        if i == 1 and not agent.store.quantized:
            agent.indexer.rebuild_quantized_index()
            agent.ingestions_since_rebuild = 0
            print("  [early index build for bootstrapping]")

    agent.print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
