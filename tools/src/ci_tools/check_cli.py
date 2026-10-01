"""ci-check: stage self-check for a capstone repo. Reads artifacts, never the code.

Stage 0 is week 0 (environment works); stages 1-7 are the capstone stages.
Stages are cumulative: `--stage 3` checks stages 0, 1, 2 and 3.
REQ items must pass; MANUAL items are for the student (and reviewer) to confirm by hand.
With --url the running service is also checked against the contract.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .attacks import SECRET_PATTERNS
from .client import ContractClient
from .golden import GoldenError, load_golden

STARTER_MARKER = "TODO(starter)"
RULE_FILES = ["AGENTS.md", "CLAUDE.md", ".claude/CLAUDE.md", ".cursorrules", ".github/copilot-instructions.md"]
RULE_GLOBS = [".cursor/rules/*", ".claude/rules/*.md"]
EDGE_TAGS = {"edge", "bad_input", "bad-input", "negative"}
# fnmatch patterns over the repo-relative posix path; "*" also matches "/"
TEST_PATTERNS = [
    "tests/*",
    "test/*",
    "*_test.*",
    "*.test.*",
    "*.spec.*",
    "*Test.java",
    "*Tests.cs",
    "*Test.php",
    "test_*.py",
    "*/test_*.py",
    "*Test.kt",
    "*_spec.rb",
]
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "vendor", "bin", "obj", "target", "dist", "build"}
MIN_RULE_LINES = 10


@dataclass
class Item:
    stage: int
    kind: str  # REQ | MANUAL
    title: str
    ok: bool | None = None  # None for MANUAL
    detail: str = ""


class Ctx:
    def __init__(self, root: Path, url: str | None, stage: int = 7):
        self.root = root
        self.url = url
        self.stage = stage
        self._golden = None
        self._golden_err: str | None = None
        self._ask_cache = None

    def p(self, rel: str) -> Path:
        return self.root / rel

    def text(self, rel: str) -> str | None:
        f = self.p(rel)
        return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None

    def golden(self):
        if self._golden is None and self._golden_err is None:
            try:
                self._golden = load_golden(self.p("evals/golden.jsonl"))
            except GoldenError as exc:
                self._golden_err = str(exc)
        return self._golden, self._golden_err

    def first_ask(self):
        """One real /ask call with the first regular (non-edge) golden input (cached).

        Edge cases (empty input, not a real request) may legitimately skip the model and return no steps/usage.
        """
        if self._ask_cache is None:
            cases, _ = self.golden()
            regular = [c for c in cases or [] if not EDGE_TAGS & set(c.tags)]
            text = regular[0].input if regular else "health check question"
            ctx = regular[0].context if regular else {}
            with ContractClient(self.url, 120) as c:
                self._ask_cache = c.ask(text, ctx)
        return self._ask_cache


def _nonempty_lines(s: str) -> int:
    return sum(1 for line in s.splitlines() if line.strip())


def _walk(root: Path, pattern: str):
    for f in root.glob(pattern):
        if f.is_file() and not (set(f.relative_to(root).parts) & SKIP_DIRS):
            yield f


def _doc_check(ctx: Ctx, rel: str, keywords: list[str] | None = None) -> tuple[bool, str]:
    body = ctx.text(rel)
    if body is None:
        return False, f"{rel} not found"
    if STARTER_MARKER in body:
        return False, f"{rel} still has {STARTER_MARKER} placeholders"
    if _nonempty_lines(body) < 3:
        return False, f"{rel} is almost empty"
    if keywords and not any(k in body.lower() for k in keywords):
        return False, f"{rel} does not mention any of: {', '.join(keywords)}"
    return True, ""


# ------------------------------------------------------------------ stage 0 (week 0)
def s0_health(ctx):
    if not ctx.url:
        # in week 0 the running service is the whole point; later (e.g. in CI without a server) it is manual
        return (False if ctx.stage == 0 else None), "pass --url, e.g. --url http://localhost:8000"
    with ContractClient(ctx.url, 30) as c:
        health, err = c.health()
    if err:
        return False, err
    if health.status != "ok":
        return False, f"/health status is {health.status!r}, expected 'ok'"
    return True, f"version {health.version or 'n/a'}"


def s0_ask(ctx):
    if not ctx.url:
        return (False if ctx.stage == 0 else None), "pass --url to check POST /ask"
    with ContractClient(ctx.url, 120) as c:
        res = c.ask("Hello. Please reply briefly.", {})
    return res.response is not None, res.error or "answers per contract"


# ------------------------------------------------------------------ stage 1
def s1_git(ctx):
    # works for a repo root and for a project inside a bigger repo (monorepo)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=ctx.root, capture_output=True, text=True
        )
    except OSError:
        return False, "git is not installed"
    return out.stdout.strip() == "true", "not inside a git repository"


def s1_readme(ctx):
    return ctx.p("README.md").is_file(), "README.md not found"


def s1_rules(ctx):
    found = [r for r in RULE_FILES if ctx.p(r).is_file()]
    for g in RULE_GLOBS:
        found += [str(f.relative_to(ctx.root)) for f in _walk(ctx.root, g)]
    if not found:
        return False, "no agent rules file (AGENTS.md, CLAUDE.md, .cursor/rules/, ...)"
    bodies = [ctx.text(f) or "" for f in found]
    if any(STARTER_MARKER in b for b in bodies):
        return False, f"rules still contain {STARTER_MARKER} placeholders"
    lines = sum(_nonempty_lines(b) for b in bodies)
    if lines < MIN_RULE_LINES:
        return False, f"rules are too thin ({lines} non-empty lines in {', '.join(found)}; need {MIN_RULE_LINES}+)"
    return True, ", ".join(found)


def s1_project(ctx):
    return _doc_check(ctx, "docs/project.md", ["метрик", "metric", "kpi", "виміря", "measure"])


def s1_ailog(ctx):
    return _doc_check(ctx, "docs/ai-log.md")


# ------------------------------------------------------------------ stage 2
def s2_golden(ctx):
    cases, err = ctx.golden()
    if err:
        return False, err
    # 15-30 at stage 2; later stages add injection and sources cases, so only the floor stays
    if len(cases) < 15 or (ctx.stage == 2 and len(cases) > 30):
        return False, f"{len(cases)} cases; stage 2 expects 15-30, later stages 15+"
    empty = [c.id for c in cases if c.expect.is_empty()]
    if empty:
        return False, f"cases without any expectation: {', '.join(empty[:5])}"
    return True, f"{len(cases)} cases"


def s2_edge(ctx):
    cases, err = ctx.golden()
    if err:
        return False, "golden set invalid"
    n = sum(1 for c in cases if EDGE_TAGS & set(c.tags))
    return n >= 2, f"{n} edge/bad-input cases (tag one of {sorted(EDGE_TAGS)}; need 2+)"


def s2_results(ctx):
    body = ctx.text("evals/results.json")
    if body is None:
        return False, "evals/results.json not found - run `ci-eval run`"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False, "evals/results.json is not valid JSON"
    if "pass_rate" not in data or "cases" not in data:
        return False, "evals/results.json has no pass_rate/cases - generate it with `ci-eval run`"
    return True, f"pass_rate {data['pass_rate']}"


def s2_failure_modes(ctx):
    return _doc_check(ctx, "docs/failure-modes.md")


def s2_tests(ctx):
    # only files tracked by git: a virtualenv or vendored packages must not count as "your tests"
    for f in _tracked_files(ctx.root):
        rel = f.relative_to(ctx.root).as_posix()
        if any(fnmatch.fnmatchcase(rel, pat) for pat in TEST_PATTERNS):
            return True, rel
    return False, "no tracked test files (tests/, test/, *_test.*, *.test.*, *Test.java, *Tests.cs, ...)"


def s2_contract(ctx):
    if not ctx.url:
        return None, "pass --url to check the running service"
    with ContractClient(ctx.url, 30) as c:
        health, err = c.health()
    if err:
        return False, err
    if health.status != "ok":
        return False, f"/health status is {health.status!r}, expected 'ok'"
    res = ctx.first_ask()
    if res.response is None:
        return False, res.error
    return True, f"/health ok (version {health.version or 'n/a'}), /ask ok"


# ------------------------------------------------------------------ stage 3
def s3_steps(ctx):
    if not ctx.url:
        return None, "pass --url to check that /ask returns steps"
    res = ctx.first_ask()
    if res.response is None:
        return False, res.error
    n = len(res.response.steps)
    return n > 0, f"{n} steps in the /ask response" if n else "/ask returned no steps"


# ------------------------------------------------------------------ stage 4
def s4_threat(ctx):
    return _doc_check(ctx, "docs/threat-model.md")


def s4_injection(ctx):
    cases, err = ctx.golden()
    if err:
        return False, "golden set invalid"
    n = sum(1 for c in cases if "injection" in c.tags)
    return n >= 3, f"{n} cases tagged 'injection' (need 3+)"


def _tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
        return [root / p for p in out.stdout.decode().split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return [f for f in _walk(root, "**/*")]


def s4_secrets(ctx):
    hits = []
    for f in _tracked_files(ctx.root):
        if not f.is_file() or f.stat().st_size > 1_000_000:
            continue
        try:
            body = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pat in SECRET_PATTERNS.items():
            if pat.search(body):
                hits.append(f"{f.relative_to(ctx.root)} ({name})")
    if ctx.p(".env").is_file() and ctx.p(".env") in _tracked_files(ctx.root):
        hits.append(".env is tracked by git")
    return not hits, "; ".join(hits[:5]) or "no credential-like strings in tracked files"


# ------------------------------------------------------------------ stage 5
def s5_sources(ctx):
    cases, err = ctx.golden()
    if err:
        return False, "golden set invalid"
    n = sum(1 for c in cases if c.expect.sources_include)
    return n >= 3, f"{n} cases check sources_include (need 3+)"


def s5_numbers(ctx):
    body = ctx.text("evals/results.json")
    if body is None:
        return False, "evals/results.json not found"
    data = json.loads(body)
    missing = [k for k in ("latency_p50_ms", "latency_p95_ms", "cost_per_1k_usd") if data.get(k) is None]
    return not missing, f"missing in results.json: {missing} (does /ask return usage.cost_usd?)" if missing else ""


def s5_perf(ctx):
    return ctx.p("evals/perf.json").is_file(), "evals/perf.json not found - run `ci-eval perf`"


def s5_usage(ctx):
    if not ctx.url:
        return None, "pass --url to check usage in /ask"
    res = ctx.first_ask()
    if res.response is None:
        return False, res.error
    if res.response.usage is None:
        return False, "/ask has no usage"
    missing = res.response.usage.missing_fields()
    return not missing, f"usage is missing: {missing}" if missing else "usage complete"


# ------------------------------------------------------------------ stage 6
def s6_adr(ctx):
    adrs = [f for d in ("docs/adr", "docs/decisions") for f in _walk(ctx.root, f"{d}/*.md")]
    real = [f for f in adrs if STARTER_MARKER not in f.read_text(encoding="utf-8", errors="replace")]
    return bool(real), f"{len(real)} ADR(s)" if real else "no filled ADR in docs/adr/"


def s6_ci(ctx):
    files = list(_walk(ctx.root, ".github/workflows/*.y*ml")) + [ctx.p(".gitlab-ci.yml")]
    files = [f for f in files if f.is_file()]
    if not files:
        return False, "no CI config (.github/workflows/*.yml or .gitlab-ci.yml)"
    bodies = [f.read_text(encoding="utf-8", errors="replace") for f in files]
    if not any("ci-eval" in b and STARTER_MARKER not in b for b in bodies):
        return False, f"CI does not run ci-eval (a workflow with {STARTER_MARKER} does not count)"
    return True, ""


# ------------------------------------------------------------------ stage 7
README_HEADINGS = {
    "problem": ["проблем", "problem"],
    "architecture": ["архітектур", "architecture"],
    "decisions/trade-offs": ["компроміс", "рішення", "trade-off", "tradeoff", "decision"],
    "security": ["безпек", "security"],
}
README_NUMBERS = {"p95": ["p95"], "cost": ["$/1", "$ / 1", "cost", "вартіст"], "evals": ["eval"]}


def s7_readme(ctx):
    body = ctx.text("README.md") or ""
    headings = " ".join(line.lower() for line in body.splitlines() if line.lstrip().startswith("#"))
    lower = body.lower()
    missing = [f"## {name}" for name, keys in README_HEADINGS.items() if not any(k in headings for k in keys)]
    missing += [name for name, keys in README_NUMBERS.items() if not any(k in lower for k in keys)]
    return not missing, f"README is missing: {', '.join(missing)}" if missing else ""


def s7_diagram(ctx):
    body = ctx.text("README.md") or ""
    ok = "```mermaid" in body or bool(re.search(r"!\[[^\]]*\]\([^)]+\)", body))
    return ok, "" if ok else "README has no diagram (mermaid block or image)"


Check = Callable[[Ctx], tuple[bool | None, str]]
REGISTRY: list[tuple[int, str, str, Check | None]] = [
    (0, "REQ", "git repository", s1_git),
    (0, "REQ", "service answers GET /health", s0_health),
    (0, "REQ", "service answers POST /ask per contract", s0_ask),
    (0, "MANUAL", "API key only in .env (not committed); spending limit set in the provider account", None),
    (1, "REQ", "README.md", s1_readme),
    (1, "REQ", "agent rules file, specific to the project", s1_rules),
    (1, "REQ", "docs/project.md with a measurable success metric", s1_project),
    (1, "REQ", "docs/ai-log.md", s1_ailog),
    (1, "MANUAL", "repository is public and starts with one command", None),
    (1, "MANUAL", "one PR with AI review and your decision on every comment", None),
    (1, "MANUAL", "ai-log has at least one agent mistake and how you caught it", None),
    (2, "REQ", "evals/golden.jsonl: valid, 15-30 cases (15+ later), each with expectations", s2_golden),
    (2, "REQ", "edge / bad-input cases in the golden set", s2_edge),
    (2, "REQ", "evals/results.json produced by ci-eval run", s2_results),
    (2, "REQ", "docs/failure-modes.md (3 failure modes)", s2_failure_modes),
    (2, "REQ", "regular tests for non-AI code", s2_tests),
    (2, "REQ", "service answers /health and /ask per contract", s2_contract),
    (2, "MANUAL", "one change measured before/after (ci-eval compare)", None),
    (3, "REQ", "/ask returns the agent's steps", s3_steps),
    (3, "MANUAL", "step limit, tool error handling, timeouts", None),
    (3, "MANUAL", "agent completes 3 scenarios end to end", None),
    (4, "REQ", "docs/threat-model.md", s4_threat),
    (4, "REQ", "3+ injection cases in the golden set", s4_injection),
    (4, "REQ", "no secrets in tracked files", s4_secrets),
    (4, "MANUAL", "irreversible actions need human confirmation (ci-eval attack)", None),
    (5, "REQ", "golden cases check sources", s5_sources),
    (5, "REQ", "results.json has p50/p95 and $/1k", s5_numbers),
    (5, "REQ", "evals/perf.json produced by ci-eval perf", s5_perf),
    (5, "REQ", "/ask returns complete usage", s5_usage),
    (5, "MANUAL", "retrieval recall@k on your question set", None),
    (6, "REQ", "at least one ADR with numbers", s6_adr),
    (6, "REQ", "CI runs ci-eval", s6_ci),
    (6, "MANUAL", "public URL or demo video; evals pass after deploy", None),
    (6, "MANUAL", "model API outage is handled (fallback or clear error)", None),
    (
        7,
        "REQ",
        "README tells the story: sections for problem, architecture, trade-offs, security; p95, cost, evals",
        s7_readme,
    ),
    (7, "REQ", "README has an architecture diagram", s7_diagram),
]


def run_checks(root: Path, stage: int, url: str | None) -> list[Item]:
    ctx = Ctx(root, url, stage)
    items: list[Item] = []
    for st, kind, title, fn in REGISTRY:
        if st > stage:
            continue
        if fn is None:
            items.append(Item(st, kind, title))
            continue
        try:
            ok, detail = fn(ctx)
        except Exception as exc:  # a broken check must not hide the others
            ok, detail = False, f"check crashed: {type(exc).__name__}: {exc}"
        items.append(Item(st, kind if ok is not None else "MANUAL", title, ok, detail))
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ci-check", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--version", action="version", version=f"ci-check {__version__}")
    ap.add_argument(
        "--stage", type=int, required=True, choices=range(0, 8), help="0 = week 0 setup, 1-7 = capstone stages"
    )
    ap.add_argument("--path", default=".", help="repository root (default .)")
    ap.add_argument("--url", default=None, help="running service, e.g. http://localhost:8000")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    items = run_checks(Path(args.path).resolve(), args.stage, args.url)
    failed = [i for i in items if i.kind == "REQ" and not i.ok]

    if args.json:
        print(json.dumps([i.__dict__ for i in items], ensure_ascii=False, indent=2))
    else:
        current = 0
        for i in items:
            if i.stage != current:
                current = i.stage
                print(f"\nStage {current}" + (" (week 0: environment)" if current == 0 else ""))
            if i.kind == "MANUAL":
                mark = "[ ] "
            else:
                mark = "[x] " if i.ok else "[!] "
            detail = f"  - {i.detail}" if i.detail and (i.kind == "MANUAL" or not i.ok) else ""
            print(f"  {mark}{i.title}{detail}")
        req = [i for i in items if i.kind == "REQ"]
        print(
            f"\n{len(req) - len(failed)}/{len(req)} required checks passed; "
            f"{sum(i.kind == 'MANUAL' for i in items)} to confirm by hand."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
