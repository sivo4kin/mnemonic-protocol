import sys
from .benchmark import (
    run_demo, run_benchmark, run_persist_test,
    run_multidomain_benchmark, run_provider_switch_test,
)
import argparse
from pathlib import Path
from typing import List


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compressed agent memory MVP prototype")
    sub = parser.add_subparsers(dest="command", required=False)

    demo = sub.add_parser("demo", help="run small interactive demo")
    demo.add_argument("--bits", type=int, default=8, choices=[4, 8])
    demo.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])

    bench = sub.add_parser("benchmark", help="run benchmark")
    bench.add_argument("--bits", type=int, default=8, choices=[4, 8])
    bench.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])
    bench.add_argument("--memories", type=int, default=1000)
    bench.add_argument("--queries", type=int, default=50)
    bench.add_argument("--k", type=int, default=10)
    bench.add_argument("--candidates", type=int, default=50)
    bench.add_argument("--memory-file", type=Path, default=None)
    bench.add_argument("--query-file", type=Path, default=None)
    bench.add_argument("--out", type=Path, default=None)

    persist = sub.add_parser("persist-test", help="prove SQLite save/load round-trip preserves retrieval exactly")
    persist.add_argument("--bits", type=int, default=8, choices=[4, 8])
    persist.add_argument("--memories", type=int, default=500)
    persist.add_argument("--queries", type=int, default=50)
    persist.add_argument("--k", type=int, default=10)
    persist.add_argument("--candidates", type=int, default=50)
    persist.add_argument("--out", type=Path, default=None)

    multi = sub.add_parser("multidomain", help="Experiment 4: recall across code/legal/news/medical domains")
    multi.add_argument("--bits", type=int, default=8, choices=[4, 8])
    multi.add_argument("--embedder", type=str, default="mock", choices=["mock", "openai"])
    multi.add_argument("--n-per-domain", type=int, default=250)
    multi.add_argument("--k", type=int, default=10)
    multi.add_argument("--candidates", type=int, default=50)
    multi.add_argument("--out", type=Path, default=None)

    switch = sub.add_parser("provider-switch", help="prove memory survives a provider/model switch")
    switch.add_argument("--bits", type=int, default=8, choices=[4, 8])
    switch.add_argument("--memories", type=int, default=500)
    switch.add_argument("--queries", type=int, default=50)
    switch.add_argument("--k", type=int, default=10)
    switch.add_argument("--candidates", type=int, default=50)
    switch.add_argument("--out", type=Path, default=None)

    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    cmd = args.command or "demo"

    if cmd == "demo":
        run_demo(bits=args.bits, embedder_name=args.embedder)
        return 0

    if cmd == "benchmark":
        run_benchmark(
            bits=args.bits,
            embedder_name=args.embedder,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            memory_file=args.memory_file,
            query_file=args.query_file,
            out_file=args.out,
        )
        return 0

    if cmd == "persist-test":
        run_persist_test(
            bits=args.bits,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    if cmd == "multidomain":
        run_multidomain_benchmark(
            bits=args.bits,
            embedder_name=args.embedder,
            n_per_domain=args.n_per_domain,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    if cmd == "provider-switch":
        run_provider_switch_test(
            bits=args.bits,
            n_memories=args.memories,
            n_queries=args.queries,
            k=args.k,
            n_candidates=args.candidates,
            out_file=args.out,
        )
        return 0

    print("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
