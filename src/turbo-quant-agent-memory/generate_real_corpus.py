"""
Generate a realistic agent memory corpus for Mnemonic MVP testing.

Creates diverse memory items that resemble what a real autonomous agent
would accumulate: conversations, facts, observations, decisions, code
snippets, research notes.

Usage:
  python3 generate_real_corpus.py --count 1000 --out corpus_1k.jsonl
  python3 generate_real_corpus.py --count 1000 --out corpus_1k.jsonl --queries queries_1k.jsonl
"""

from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path


# --- Memory templates by category ---

EPISODIC = [
    "User asked about {topic} and I explained that {fact}. They seemed satisfied with the answer.",
    "During today's session, we debugged a {lang} issue related to {topic}. The root cause was {cause}.",
    "User requested a summary of {topic}. I provided a concise overview covering {detail1} and {detail2}.",
    "Pair programming session: refactored the {component} module to use {pattern} pattern instead of {old_pattern}.",
    "User shared a link about {topic} and asked me to analyze it. Key takeaway: {fact}.",
    "Had a long conversation about {topic} architecture. Decision: go with {choice} because {reason}.",
    "User was frustrated with {tool} performance. Suggested switching to {alt_tool} which resolved the issue.",
    "Reviewed PR #{pr_num} together. Found {bug_count} issues: {issue1} and {issue2}.",
    "User asked me to write tests for the {component} module. Created {test_count} test cases covering {coverage}.",
    "Morning standup context: user is working on {topic} this sprint, blocked on {blocker}.",
]

SEMANTIC = [
    "The {protocol} protocol uses {mechanism} for consensus, achieving {metric} throughput.",
    "{framework} framework supports {feature1}, {feature2}, and {feature3} out of the box.",
    "Best practice for {topic}: always {practice1} before {practice2} to avoid {pitfall}.",
    "Key difference between {thing1} and {thing2}: {thing1} optimizes for {goal1} while {thing2} prioritizes {goal2}.",
    "{algorithm} has O({complexity}) time complexity and O({space}) space complexity.",
    "In {domain}, the standard approach is to {approach} because {reason}.",
    "{tool} version {version} introduced breaking changes to {api}. Migration guide: {steps}.",
    "The {concept} pattern separates {concern1} from {concern2}, making the system more {quality}.",
    "{lang} error '{error}' typically means {explanation}. Fix: {fix}.",
    "Research finding: {technique} improves {metric} by {amount}% compared to baseline {baseline}.",
]

DECISION = [
    "Decided to use {choice} over {alternative} for {purpose}. Rationale: {reason}.",
    "Architecture decision: {component} will communicate via {mechanism} instead of {old_mechanism}.",
    "Chose {db} as the primary datastore because {reason1} and {reason2}.",
    "Going with {approach} approach for the {feature} feature. Trade-off: {tradeoff}.",
    "Rejected {option} for {purpose} due to {limitation}. Will revisit in Q{quarter}.",
    "Team agreed on {standard} as the coding standard for {lang} files in this project.",
    "Migration plan: move from {old} to {new} in {phases} phases, starting with {first_phase}.",
    "Budget allocated ${amount} for {service} — cheaper than {alternative} at ${alt_amount}/mo.",
    "Security review concluded: {component} needs {fix} before production deployment.",
    "Performance target set: {metric} must stay under {threshold} for the {endpoint} endpoint.",
]

OBSERVATION = [
    "Noticed that {component} memory usage spikes to {amount}MB during {operation}.",
    "API response times for {endpoint} have increased from {old}ms to {new}ms since {event}.",
    "User typically works between {start} and {end} UTC, prefers {style} communication style.",
    "The {service} service has been flaky this week — {count} timeouts in the last {hours} hours.",
    "Build times increased after adding {dep}. Current: {duration} seconds, was {old_duration}.",
    "User prefers {format} format for reports and {other_format} for quick summaries.",
    "The {test_suite} test suite is the slowest at {duration}s. Main bottleneck: {bottleneck}.",
    "Deployment to {env} takes approximately {duration} minutes via {pipeline}.",
    "The {table} table has grown to {size}GB. Might need partitioning soon.",
    "User's {lang} codebase follows {convention} naming convention consistently.",
]

# --- Fill values ---

TOPICS = ["vector quantization", "KV cache compression", "blockchain consensus", "agent memory",
          "embedding models", "transformer attention", "smart contracts", "DeFi protocols",
          "distributed systems", "neural architecture search", "reinforcement learning",
          "zero-knowledge proofs", "homomorphic encryption", "federated learning",
          "graph neural networks", "retrieval augmented generation", "prompt engineering",
          "model distillation", "continual learning", "multi-agent systems"]

FACTS = ["quantization reduces memory by 4-8x with minimal quality loss",
         "attention heads show sparse activation patterns at inference time",
         "Solana processes 65K transactions per second in optimal conditions",
         "cosine similarity is equivalent to dot product on normalized vectors",
         "random rotation makes coordinate distributions nearly independent",
         "scalar quantization is near-optimal for high-dimensional vectors",
         "KV cache grows linearly with sequence length and model depth",
         "embedding dimension affects retrieval quality logarithmically",
         "4-bit quantization achieves 1/256th the distortion of 1-bit",
         "Arweave permanent storage costs approximately $5 per GB"]

LANGS = ["Python", "Rust", "TypeScript", "Go", "Solidity", "C++", "Java", "Kotlin"]
COMPONENTS = ["auth", "indexer", "retriever", "embedder", "quantizer", "serializer",
              "validator", "router", "scheduler", "cache", "monitor", "gateway"]
PATTERNS = ["observer", "strategy", "factory", "singleton", "adapter", "decorator",
            "command", "mediator", "pipeline", "repository"]
TOOLS = ["PostgreSQL", "Redis", "Elasticsearch", "Kafka", "Docker", "Kubernetes",
         "Grafana", "Prometheus", "Terraform", "Ansible", "Webpack", "Vite"]
FRAMEWORKS = ["FastAPI", "Next.js", "Actix-web", "Gin", "Spring Boot", "Django",
              "Express", "Axum", "SvelteKit", "Remix"]
PROTOCOLS = ["Solana", "Ethereum", "Cosmos", "Polkadot", "Avalanche", "Filecoin",
             "Arweave", "Chainlink", "The Graph", "IPFS"]
ALGORITHMS = ["HNSW", "IVF-PQ", "LSH", "KD-tree", "VP-tree", "BFS", "Dijkstra",
              "A*", "MCTS", "PPO", "Adam", "LBFGS"]
ERRORS = ["ConnectionRefused", "TimeoutError", "OutOfMemoryError", "IndexOutOfBounds",
          "NullPointerException", "SegmentationFault", "DeadlockDetected",
          "RateLimitExceeded", "AuthenticationFailed", "SerializationError"]


def fill_template(template: str, rng: random.Random) -> str:
    """Fill a template string with random contextual values."""
    replacements = {
        "{topic}": rng.choice(TOPICS),
        "{fact}": rng.choice(FACTS),
        "{lang}": rng.choice(LANGS),
        "{cause}": rng.choice(["missing null check", "race condition", "stale cache",
                               "incorrect type cast", "off-by-one error", "memory leak"]),
        "{detail1}": rng.choice(["architecture", "trade-offs", "implementation", "benchmarks"]),
        "{detail2}": rng.choice(["failure modes", "cost analysis", "alternatives", "migration path"]),
        "{component}": rng.choice(COMPONENTS),
        "{pattern}": rng.choice(PATTERNS),
        "{old_pattern}": rng.choice(PATTERNS),
        "{choice}": rng.choice(TOOLS + FRAMEWORKS),
        "{alternative}": rng.choice(TOOLS + FRAMEWORKS),
        "{alt_tool}": rng.choice(TOOLS),
        "{reason}": rng.choice(["better performance", "simpler API", "active community",
                                "lower latency", "cost savings", "type safety",
                                "better documentation", "proven at scale"]),
        "{tool}": rng.choice(TOOLS),
        "{pr_num}": str(rng.randint(100, 9999)),
        "{bug_count}": str(rng.randint(1, 5)),
        "{issue1}": rng.choice(["missing error handling", "SQL injection risk",
                                "unused import", "hardcoded config"]),
        "{issue2}": rng.choice(["missing tests", "memory leak", "race condition",
                                "improper logging"]),
        "{test_count}": str(rng.randint(5, 30)),
        "{coverage}": rng.choice(["happy path", "edge cases", "error scenarios",
                                  "concurrency", "integration"]),
        "{blocker}": rng.choice(["API rate limits", "missing credentials",
                                "flaky CI", "dependency conflict", "design review"]),
        "{protocol}": rng.choice(PROTOCOLS),
        "{mechanism}": rng.choice(["proof-of-stake", "proof-of-history", "BFT",
                                   "Tendermint", "Nakamoto", "DAG-based"]),
        "{metric}": rng.choice(["50K TPS", "sub-second finality", "99.99% uptime",
                                "3x throughput", "50% latency reduction"]),
        "{framework}": rng.choice(FRAMEWORKS),
        "{feature1}": rng.choice(["hot reload", "SSR", "middleware", "WebSocket"]),
        "{feature2}": rng.choice(["auth", "caching", "rate limiting", "logging"]),
        "{feature3}": rng.choice(["monitoring", "testing", "deployment", "i18n"]),
        "{practice1}": rng.choice(["validate inputs", "run linter", "write tests", "review deps"]),
        "{practice2}": rng.choice(["deploying", "merging", "releasing", "committing"]),
        "{pitfall}": rng.choice(["data loss", "security breach", "downtime", "corruption"]),
        "{thing1}": rng.choice(TOOLS[:5]),
        "{thing2}": rng.choice(TOOLS[5:]),
        "{goal1}": rng.choice(["read throughput", "consistency", "simplicity"]),
        "{goal2}": rng.choice(["write throughput", "availability", "flexibility"]),
        "{algorithm}": rng.choice(ALGORITHMS),
        "{complexity}": rng.choice(["n log n", "n^2", "log n", "n", "1"]),
        "{space}": rng.choice(["n", "1", "n log n", "n^2"]),
        "{domain}": rng.choice(["information retrieval", "distributed systems",
                                "machine learning", "blockchain", "databases"]),
        "{approach}": rng.choice(["shard", "replicate", "batch", "stream", "cache"]),
        "{version}": f"{rng.randint(1,5)}.{rng.randint(0,9)}.{rng.randint(0,20)}",
        "{api}": rng.choice(["authentication API", "query interface", "config format",
                             "plugin system", "CLI flags"]),
        "{steps}": rng.choice(["update config, run migration, restart",
                               "pin old version, test, then upgrade",
                               "update imports, fix types, run tests"]),
        "{concept}": rng.choice(PATTERNS),
        "{concern1}": rng.choice(["business logic", "data access", "presentation"]),
        "{concern2}": rng.choice(["infrastructure", "transport", "storage"]),
        "{quality}": rng.choice(["maintainable", "testable", "scalable", "extensible"]),
        "{error}": rng.choice(ERRORS),
        "{explanation}": rng.choice(["the connection was refused by the target host",
                                     "the operation exceeded the configured timeout",
                                     "the process ran out of available memory"]),
        "{fix}": rng.choice(["increase timeout", "add retry logic", "check config",
                             "upgrade dependency", "add error handling"]),
        "{technique}": rng.choice(["quantization-aware training", "knowledge distillation",
                                   "pruning", "mixed precision", "gradient checkpointing"]),
        "{amount}": str(rng.randint(5, 50)),
        "{baseline}": rng.choice(["full precision", "naive quantization", "random baseline"]),
        "{old_mechanism}": rng.choice(["REST", "gRPC", "message queue", "shared memory"]),
        "{db}": rng.choice(["PostgreSQL", "SQLite", "DynamoDB", "MongoDB", "CockroachDB"]),
        "{reason1}": rng.choice(["ACID compliance", "horizontal scaling", "JSON support"]),
        "{reason2}": rng.choice(["team familiarity", "cost", "managed service available"]),
        "{feature}": rng.choice(["search", "notifications", "analytics", "export"]),
        "{tradeoff}": rng.choice(["more complexity but better perf",
                                  "slower writes but faster reads",
                                  "higher cost but simpler ops"]),
        "{option}": rng.choice(TOOLS + FRAMEWORKS),
        "{limitation}": rng.choice(["license restrictions", "poor documentation",
                                    "no active maintainers", "missing features"]),
        "{quarter}": str(rng.randint(1, 4)),
        "{standard}": rng.choice(["PEP 8", "Airbnb", "Google", "Standard", "Prettier"]),
        "{old}": rng.choice(["monolith", "v1 API", "legacy auth", "manual deploys"]),
        "{new}": rng.choice(["microservices", "v2 API", "OAuth 2.0", "CI/CD"]),
        "{phases}": str(rng.randint(2, 5)),
        "{first_phase}": rng.choice(["data migration", "read path", "non-critical services"]),
        "{alt_amount}": str(rng.randint(100, 500)),
        "{service}": rng.choice(["monitoring", "CDN", "search", "logging", "CI/CD"]),
        "{operation}": rng.choice(["bulk indexing", "report generation", "cache rebuild"]),
        "{endpoint}": rng.choice(["/api/search", "/api/embed", "/api/ingest",
                                  "/api/auth", "/health", "/api/query"]),
        "{old}ms": f"{rng.randint(50, 200)}ms",
        "{new}ms": f"{rng.randint(200, 800)}ms",
        "{event}": rng.choice(["last deploy", "schema migration", "traffic spike"]),
        "{start}": f"{rng.randint(7, 11)}:00",
        "{end}": f"{rng.randint(18, 23)}:00",
        "{style}": rng.choice(["concise", "detailed", "technical", "casual"]),
        "{count}": str(rng.randint(5, 50)),
        "{hours}": str(rng.randint(12, 72)),
        "{dep}": rng.choice(["heavy test fixtures", "new linter", "type checker"]),
        "{duration}": str(rng.randint(30, 300)),
        "{old_duration}": str(rng.randint(10, 60)),
        "{format}": rng.choice(["markdown", "PDF", "JSON", "HTML"]),
        "{other_format}": rng.choice(["bullet points", "one-liners", "tables"]),
        "{test_suite}": rng.choice(["integration", "e2e", "load", "security"]),
        "{bottleneck}": rng.choice(["database setup", "network calls", "file I/O"]),
        "{env}": rng.choice(["staging", "production", "dev", "canary"]),
        "{pipeline}": rng.choice(["GitHub Actions", "Jenkins", "ArgoCD", "GitLab CI"]),
        "{table}": rng.choice(["events", "transactions", "logs", "embeddings", "users"]),
        "{size}": str(rng.randint(10, 500)),
        "{convention}": rng.choice(["snake_case", "camelCase", "PascalCase", "kebab-case"]),
        "{purpose}": rng.choice(["the search backend", "data pipeline", "auth system"]),
        "{threshold}": f"{rng.randint(50, 500)}ms",
        "{fix}": rng.choice(["input validation", "rate limiting", "encryption at rest"]),
    }
    result = template
    for key, value in replacements.items():
        result = result.replace(key, str(value), 1)
    return result


def generate_corpus(n: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    categories = [
        ("episodic", EPISODIC),
        ("semantic", SEMANTIC),
        ("decision", DECISION),
        ("observation", OBSERVATION),
    ]
    memories = []
    for i in range(n):
        cat_name, templates = rng.choice(categories)
        template = rng.choice(templates)
        content = fill_template(template, rng)
        memories.append({
            "memory_id": f"mem_{i:06d}",
            "content": content,
            "memory_type": cat_name,
            "importance_score": round(rng.random(), 2),
            "tags": rng.sample(["quantization", "blockchain", "agent", "retrieval",
                                "architecture", "debugging", "performance", "security",
                                "deployment", "testing"], k=rng.randint(1, 3)),
        })
    return memories


def generate_queries_from_corpus(memories: list[dict], n: int, seed: int = 99) -> list[dict]:
    """Generate queries that have known relevant memories (for recall measurement)."""
    rng = random.Random(seed)
    queries = []
    for i in range(n):
        # Pick a memory and derive a query from its content
        anchor = rng.choice(memories)
        words = anchor["content"].split()
        # Take a substring as a natural query
        start = rng.randint(0, max(0, len(words) - 6))
        query_words = words[start:start + rng.randint(3, 7)]
        query = " ".join(query_words)

        # Find other memories that share significant words with this one
        anchor_words = set(w.lower().strip(".,!?") for w in anchor["content"].split() if len(w) > 4)
        relevant = [anchor["memory_id"]]
        for m in memories:
            if m["memory_id"] == anchor["memory_id"]:
                continue
            m_words = set(w.lower().strip(".,!?") for w in m["content"].split() if len(w) > 4)
            overlap = len(anchor_words & m_words)
            if overlap >= 3:
                relevant.append(m["memory_id"])
            if len(relevant) >= 10:
                break

        queries.append({
            "query": query,
            "relevant_ids": relevant,
        })
    return queries


def main():
    parser = argparse.ArgumentParser(description="Generate realistic agent memory corpus")
    parser.add_argument("--count", type=int, default=1000, help="Number of memories")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--queries", type=Path, default=None, help="Output queries JSONL path")
    parser.add_argument("--num-queries", type=int, default=100, help="Number of queries")
    args = parser.parse_args()

    memories = generate_corpus(args.count, seed=args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for m in memories:
            f.write(json.dumps(m) + "\n")
    print(f"Wrote {len(memories)} memories to {args.out}")

    if args.queries:
        queries = generate_queries_from_corpus(memories, args.num_queries, seed=args.seed + 1)
        with open(args.queries, "w") as f:
            for q in queries:
                f.write(json.dumps(q) + "\n")
        print(f"Wrote {len(queries)} queries to {args.queries}")


if __name__ == "__main__":
    main()
