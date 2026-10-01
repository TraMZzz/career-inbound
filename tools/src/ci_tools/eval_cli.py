"""ci-eval: run the golden set, measure latency/cost, probe prompt injection, compare two runs.

Works with any language: it only talks to the service over the HTTP contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx2

from . import __version__
from .attacks import PROBES, judge
from .client import AskResult, ContractClient
from .evaluate import CaseResult, check_case
from .golden import GoldenError, load_golden
from .stats import mean, percentile, rnd

OK, FAIL = "PASS", "FAIL"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cost_per_1k(costs: list[float]) -> float | None:
    avg = mean(costs)
    return None if avg is None else round(avg * 1000, 4)


# ---------------------------------------------------------------- run
def summarize(results: list[CaseResult], url: str, golden: str) -> dict:
    latencies = [r.latency_ms for r in results if r.error is None]
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        for tag in r.tags:
            by_tag[tag].append(r.passed)
    passed = sum(r.passed for r in results)
    return {
        "tool": f"ci-eval {__version__}",
        "run_at": _now(),
        "url": url,
        "golden": golden,
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "errors": sum(r.error is not None for r in results),
        "latency_p50_ms": rnd(percentile(latencies, 50), 1),
        "latency_p95_ms": rnd(percentile(latencies, 95), 1),
        "cost_per_1k_usd": _cost_per_1k(costs),
        "by_tag": {t: {"passed": sum(v), "total": len(v)} for t, v in sorted(by_tag.items())},
        "cases": [r.to_json() for r in results],
    }


def cmd_run(args: argparse.Namespace, transport: httpx2.BaseTransport | None = None) -> int:
    try:
        cases = load_golden(Path(args.golden))
    except GoldenError as exc:
        print(f"golden set error: {exc}", file=sys.stderr)
        return 2

    with ContractClient(args.url, args.timeout, transport) as client:

        def one(case):
            return check_case(case, client.ask(case.input, case.context))

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results = list(pool.map(one, cases))

    summary = summarize(results, args.url, args.golden)
    _write_json(Path(args.out), summary)

    for r in results:
        mark = OK if r.passed else FAIL
        print(f"{mark}  {r.id:<14} {r.latency_ms:>8.0f} ms  {','.join(r.tags)}")
        for c in r.checks:
            if not c.ok:
                print(f"      - {c.name}: {c.detail}")
    p50, p95, c1k = summary["latency_p50_ms"], summary["latency_p95_ms"], summary["cost_per_1k_usd"]
    print(
        f"\npass_rate {summary['pass_rate']:.2f} ({summary['passed']}/{summary['total']})"
        f" | p50 {p50} ms | p95 {p95} ms | $/1k {c1k if c1k is not None else 'n/a (no usage.cost_usd)'}"
    )
    print(f"results -> {args.out}")
    if args.min_pass is not None and summary["pass_rate"] < args.min_pass:
        print(f"quality gate failed: pass_rate {summary['pass_rate']:.2f} < {args.min_pass}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- perf
def cmd_perf(args: argparse.Namespace, transport: httpx2.BaseTransport | None = None) -> int:
    try:
        cases = load_golden(Path(args.golden))
    except GoldenError as exc:
        print(f"golden set error: {exc}", file=sys.stderr)
        return 2
    excluded = set(args.exclude_tag or [])
    inputs = [(c.input, c.context) for c in cases if not excluded & set(c.tags)]
    if not inputs:
        print("no cases left after --exclude-tag", file=sys.stderr)
        return 2
    plan = [inputs[i % len(inputs)] for i in range(args.n)]

    with ContractClient(args.url, args.timeout, transport) as client:

        def one(item):
            return client.ask(item[0], item[1])

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results: list[AskResult] = list(pool.map(one, plan))

    ok = [r for r in results if r.response is not None]
    lat = [r.latency_ms for r in ok]
    usages = [r.response.usage for r in ok if r.response.usage is not None]
    costs = [u.cost_usd for u in usages if u.cost_usd is not None]
    tin = [u.input_tokens for u in usages if u.input_tokens is not None]
    tout = [u.output_tokens for u in usages if u.output_tokens is not None]
    models = sorted({u.model for u in usages if u.model})
    report = {
        "tool": f"ci-eval {__version__}",
        "run_at": _now(),
        "url": args.url,
        "requests": len(results),
        "errors": len(results) - len(ok),
        "concurrency": args.concurrency,
        "excluded_tags": sorted(excluded),
        "latency_p50_ms": rnd(percentile(lat, 50), 1),
        "latency_p95_ms": rnd(percentile(lat, 95), 1),
        "latency_mean_ms": rnd(mean(lat), 1),
        "cost_per_request_usd": rnd(mean(costs), 6),
        "cost_per_1k_usd": _cost_per_1k(costs),
        "input_tokens_mean": rnd(mean(tin), 1),
        "output_tokens_mean": rnd(mean(tout), 1),
        "models": models,
    }
    _write_json(Path(args.out), report)

    print("| metric | value |\n|---|---|")
    for key in (
        "requests",
        "errors",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_mean_ms",
        "cost_per_request_usd",
        "cost_per_1k_usd",
        "input_tokens_mean",
        "output_tokens_mean",
    ):
        val = report[key]
        print(f"| {key} | {val if val is not None else 'n/a'} |")
    print(f"| models | {', '.join(models) or 'n/a'} |")
    if not costs:
        print("\nnote: no usage.cost_usd in responses - cost cannot be measured (required from stage 5).")
    print(f"perf -> {args.out}")
    return 0 if ok else 1


# ---------------------------------------------------------------- attack
def cmd_attack(args: argparse.Namespace, transport: httpx2.BaseTransport | None = None) -> int:
    rows = []
    with ContractClient(args.url, args.timeout, transport) as client:
        _, err = client.health()
        if err:
            # otherwise a wrong --url (404 everywhere) would look like "every probe was refused"
            print(f"service is not reachable per contract: {err}", file=sys.stderr)
            return 2
        # a service that rejects every request (e.g. wrong field names -> 422) must not "hold" every probe
        control = client.ask("Hello. Please reply briefly.", {})
        if control.response is None:
            print(f"/ask does not answer a harmless request per contract: {control.error}", file=sys.stderr)
            return 2
        for probe in PROBES:
            checks = judge(probe, client.ask(probe.input, probe.context))
            rows.append((probe, checks))
    failed = 0
    report_cases = []
    for probe, checks in rows:
        passed = all(c.ok for c in checks)
        failed += not passed
        print(f"{OK if passed else FAIL}  {probe.id:<24} {probe.title}")
        for c in checks:
            if not c.ok:
                print(f"      - {c.name}: {c.detail}")
        report_cases.append(
            {"id": probe.id, "title": probe.title, "pass": passed, "checks": [c.__dict__ for c in checks]}
        )
    _write_json(
        Path(args.out),
        {
            "tool": f"ci-eval {__version__}",
            "run_at": _now(),
            "url": args.url,
            "total": len(rows),
            "failed": failed,
            "cases": report_cases,
        },
    )
    print(f"\n{len(rows) - failed}/{len(rows)} probes held. A probe that got through is a failing test.")
    print(f"attack -> {args.out}")
    return 1 if failed else 0


# ---------------------------------------------------------------- compare
def cmd_compare(args: argparse.Namespace) -> int:
    try:
        a = json.loads(Path(args.before).read_text(encoding="utf-8"))
        b = json.loads(Path(args.after).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read results: {exc}", file=sys.stderr)
        return 2
    before = {c["id"]: c["pass"] for c in a.get("cases", [])}
    after = {c["id"]: c["pass"] for c in b.get("cases", [])}
    fixed = sorted(i for i in after if after[i] and before.get(i) is False)
    broken = sorted(i for i in after if not after[i] and before.get(i) is True)
    print(f"pass_rate  {a.get('pass_rate')} -> {b.get('pass_rate')}")
    for key in ("latency_p50_ms", "latency_p95_ms", "cost_per_1k_usd"):
        print(f"{key:<16} {a.get(key)} -> {b.get(key)}")
    print(f"fixed  ({len(fixed)}): {', '.join(fixed) or '-'}")
    print(f"broken ({len(broken)}): {', '.join(broken) or '-'}")
    only = sorted(set(before) ^ set(after))
    if only:
        print(f"cases present in only one run: {', '.join(only)}")
    return 0


# ---------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ci-eval", description=__doc__)
    p.add_argument("--version", action="version", version=f"ci-eval {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser, default_out: str) -> None:
        sp.add_argument("--url", default="http://localhost:8000", help="service base URL")
        sp.add_argument("--timeout", type=float, default=120.0, help="per-request timeout, seconds (default 120)")
        sp.add_argument("--concurrency", "-j", type=int, default=1, help="parallel requests (default 1)")
        sp.add_argument("--out", default=default_out, help=f"output file (default {default_out})")

    run = sub.add_parser("run", help="run the golden set -> results.json")
    common(run, "evals/results.json")
    run.add_argument("--golden", default="evals/golden.jsonl")
    run.add_argument("--min-pass", type=float, default=None, help="exit 1 if pass_rate is below (CI gate)")

    perf = sub.add_parser("perf", help="latency p50/p95 and cost over N requests -> perf.json")
    common(perf, "evals/perf.json")
    perf.add_argument("--golden", default="evals/golden.jsonl")
    perf.add_argument("--n", type=int, default=50)
    perf.add_argument("--exclude-tag", action="append", help="skip golden cases with this tag (repeatable)")

    atk = sub.add_parser("attack", help="built-in prompt-injection probes -> attack.json")
    common(atk, "evals/attack.json")

    cmp_ = sub.add_parser("compare", help="what changed between two results.json files")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"run": cmd_run, "perf": cmd_perf, "attack": cmd_attack, "compare": cmd_compare}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
