"""Deterministic generator of demo-shop incidents: logs, metrics, deploys, alerts and ground truth.

Each incident gets its own 25-minute window (20 min before the alert, 5 min after). The fault starts
7 minutes before the alert fires (alerts need 5 minutes of breach). Outside the fault the services
produce normal traffic logs, occasional harmless warnings and, for some incidents, an unrelated deploy
as a distractor.

Log messages imitate the real wording of the libraries they name (SQLAlchemy, redis-py, httpx,
psycopg, PostgreSQL, Kubernetes) so the data reads like production, but every value is synthetic.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .topology import APP_SERVICES

SEED = 20261005
WINDOW_BEFORE = timedelta(minutes=20)
WINDOW_AFTER = timedelta(minutes=5)
FAULT_LEAD = timedelta(minutes=7)

BASELINE = {
    "gateway": {"rps": 180, "p95_ms": 140, "error_rate_pct": 0.3},
    "checkout": {"rps": 22, "p95_ms": 310, "error_rate_pct": 0.4},
    "cart": {"rps": 95, "p95_ms": 60, "error_rate_pct": 0.2},
    "payments": {"rps": 20, "p95_ms": 420, "error_rate_pct": 0.5},
    "inventory": {"rps": 60, "p95_ms": 45, "error_rate_pct": 0.2},
}
ENDPOINTS = {
    "gateway": ["GET /api/products", "GET /api/cart", "POST /api/checkout"],
    "checkout": ["POST /v1/orders"],
    "cart": ["GET /v1/carts/{id}", "PUT /v1/carts/{id}/items"],
    "payments": ["POST /v1/charges"],
    "inventory": ["POST /v1/reservations", "GET /v1/stock/{id}"],
}
HARMLESS_WARNINGS = [
    "slow request GET /api/products took 1204ms",
    "retrying request to inventory (attempt 1/3) after connection reset by peer",
    "deprecated header X-Client-Version received from client 4.2.0",
    "feature flag 'new-recs' evaluation failed, using default value",
    "request body larger than 256KiB, streaming to disk",
]
POD_SUFFIX = {
    "gateway": "5f7d9c6b8-q2mzx",
    "checkout": "6c8b7d9f4-h7k2p",
    "cart": "7b9f8c5d6-w4n8t",
    "payments": "8d6c5b7f9-r3j6v",
    "inventory": "7d9c8b6f5-x2k4p",
}


@dataclass
class IncidentSpec:
    id: str
    category: str
    root_service: str
    alert_service: str
    alert_name: str
    alert_at: datetime
    distractor_deploy: str | None = None  # service with an unrelated deploy in the window
    tags: list[str] = field(default_factory=list)


def _t(day: int, hh: int, mm: int) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=UTC)


SPECS: list[IncidentSpec] = [
    IncidentSpec("inc-001", "db_pool_exhausted", "payments", "checkout", "HighErrorRate", _t(5, 14, 3)),
    IncidentSpec("inc-002", "cache_unavailable", "cart-cache", "cart", "HighLatencyP95", _t(5, 19, 41)),
    IncidentSpec("inc-003", "bad_deploy", "checkout", "checkout", "HighErrorRate", _t(6, 11, 17)),
    IncidentSpec("inc-004", "oom_killed", "inventory", "inventory", "PodCrashLooping", _t(6, 23, 52)),
    IncidentSpec("inc-005", "upstream_timeout", "psp", "payments", "HighLatencyP95", _t(7, 9, 26)),
    IncidentSpec("inc-006", "disk_full", "orders-db", "payments", "HighErrorRate", _t(7, 16, 8)),
    IncidentSpec("inc-007", "db_pool_exhausted", "inventory", "inventory", "HighLatencyP95", _t(8, 12, 44)),
    IncidentSpec(
        "inc-008",
        "cache_unavailable",
        "cart-cache",
        "gateway",
        "HighLatencyP95",
        _t(8, 20, 15),
        distractor_deploy="inventory",
    ),
    IncidentSpec("inc-009", "bad_deploy", "cart", "gateway", "HighErrorRate", _t(9, 10, 2)),
    IncidentSpec("inc-010", "oom_killed", "cart", "cart", "PodCrashLooping", _t(9, 3, 37)),
    IncidentSpec("inc-011", "upstream_timeout", "psp", "checkout", "HighErrorRate", _t(12, 13, 55)),
    IncidentSpec("inc-012", "disk_full", "orders-db", "orders-db", "DiskSpaceLow", _t(12, 22, 30)),
    IncidentSpec(
        "inc-013",
        "db_pool_exhausted",
        "payments",
        "payments",
        "HighLatencyP95",
        _t(13, 15, 12),
        distractor_deploy="checkout",
    ),
    IncidentSpec("inc-014", "bad_deploy", "gateway", "gateway", "HighErrorRate", _t(14, 17, 48)),
    IncidentSpec("inc-015", "oom_killed", "payments", "checkout", "HighErrorRate", _t(15, 8, 21)),
    IncidentSpec(
        "inc-016", "disk_full", "orders-db", "inventory", "HighErrorRate", _t(15, 18, 33), distractor_deploy="cart"
    ),
    IncidentSpec(
        "inc-017",
        "cache_unavailable",
        "cart-cache",
        "cart",
        "HighErrorRate",
        _t(16, 11, 6),
        distractor_deploy="cart",
        tags=["hard"],
    ),
]

EXPECTED_ACTION = {"bad_deploy": "rollback_deploy"}


# ----------------------------------------------------------------------------- output records
@dataclass
class World:
    logs: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    deploys: list[dict] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Builder:
    def __init__(self, spec: IncidentSpec, rng: random.Random, world: World):
        self.s = spec
        self.rng = rng
        self.w = world
        self.start = spec.alert_at - WINDOW_BEFORE
        self.end = spec.alert_at + WINDOW_AFTER
        self.fault = spec.alert_at - FAULT_LEAD
        self.minutes = int((self.end - self.start).total_seconds() // 60)
        self._logs: list[tuple[datetime, str, str, str, str]] = []

    # --- helpers
    def log(self, ts: datetime, service: str, level: str, msg: str, source: str = "app") -> None:
        self._logs.append((ts, service, level, source, msg))

    def during_fault(self, per_minute: int, service: str, level: str, msgs: list[str], source: str = "app"):
        minute = self.fault
        while minute < self.end:
            for _ in range(per_minute):
                ts = minute + timedelta(seconds=self.rng.randint(0, 59))
                self.log(ts, service, level, self.rng.choice(msgs), source)
            minute += timedelta(minutes=1)

    def trace(self) -> str:
        return f"{self.rng.getrandbits(64):016x}"

    # --- background traffic
    def background(self) -> None:
        for m in range(self.minutes):
            minute = self.start + timedelta(minutes=m)
            for svc in APP_SERVICES:
                ep = self.rng.choice(ENDPOINTS[svc]).replace("{id}", str(self.rng.randint(1000, 9999)))
                ms = max(5, int(self.rng.gauss(BASELINE[svc]["p95_ms"] * 0.4, BASELINE[svc]["p95_ms"] * 0.1)))
                self.log(minute + timedelta(seconds=self.rng.randint(0, 59)), svc, "INFO", f"{ep} 200 {ms}ms")
                if self.rng.random() < 0.04:
                    self.log(
                        minute + timedelta(seconds=self.rng.randint(0, 59)),
                        svc,
                        "WARN",
                        self.rng.choice(HARMLESS_WARNINGS),
                    )

    def distractor(self) -> None:
        svc = self.s.distractor_deploy
        if not svc:
            return
        ts = self.start + timedelta(minutes=self.rng.randint(3, 9), seconds=self.rng.randint(0, 59))
        minor = self.rng.randint(1, 9)
        self._deploy(ts, svc, f"1.{minor}.4", f"1.{minor}.3")

    def _deploy(self, ts: datetime, svc: str, version: str, previous: str) -> None:
        commit = f"{self.rng.getrandbits(28):07x}"
        self.w.deploys.append(
            {
                "ts": _iso(ts),
                "service": svc,
                "version": version,
                "previous": previous,
                "commit": commit,
                "author": "ci-bot",
            }
        )
        self.log(ts, svc, "INFO", f"deployed {svc} {version} (was {previous}), commit {commit}", "deploy")

    # --- metrics: effects[service] = function(minutes_since_fault) -> dict of overrides
    def metrics(self, effects: dict) -> None:
        for m in range(self.minutes):
            minute = self.start + timedelta(minutes=m)
            since = (minute - self.fault).total_seconds() / 60
            for svc in APP_SERVICES:
                b = BASELINE[svc]
                row = {
                    "ts": _iso(minute),
                    "service": svc,
                    "rps": round(b["rps"] * self.rng.uniform(0.9, 1.1), 1),
                    "p95_ms": round(b["p95_ms"] * self.rng.uniform(0.9, 1.15)),
                    "error_rate_pct": round(b["error_rate_pct"] * self.rng.uniform(0.5, 1.5), 2),
                    "cpu_pct": round(self.rng.uniform(25, 45), 1),
                    "mem_pct": round(self.rng.uniform(48, 62), 1),
                    "restarts": 0,
                }
                if svc in ("payments", "inventory"):
                    row["db_pool_in_use"] = self.rng.randint(3, 9)
                    row["db_pool_max"] = 30
                if since >= 0 and svc in effects:
                    row.update(effects[svc](since))
                self.w.metrics.append(row)
            db = {
                "ts": _iso(minute),
                "service": "orders-db",
                "disk_used_pct": round(71 + m * 0.01, 2),
                "connections": self.rng.randint(18, 30),
            }
            cache = {"ts": _iso(minute), "service": "cart-cache", "up": 1, "mem_used_mb": self.rng.randint(410, 430)}
            if since >= 0 and "orders-db" in effects:
                db.update(effects["orders-db"](since))
            if since >= 0 and "cart-cache" in effects:
                cache.update(effects["cart-cache"](since))
            self.w.metrics.extend([db, cache])

    def flush_logs(self) -> None:
        self._logs.sort(key=lambda r: r[0])
        for ts, svc, level, source, msg in self._logs:
            self.w.logs.append(
                {"ts": _iso(ts), "service": svc, "level": level, "source": source, "msg": msg, "trace_id": self.trace()}
            )


# ----------------------------------------------------------------------------- scenarios
def _callers_of(service: str) -> list[str]:
    return {
        "payments": ["checkout"],
        "inventory": ["checkout"],
        "cart": ["gateway", "checkout"],
        "checkout": ["gateway"],
        "gateway": [],
    }.get(service, [])


def _upstream_errors(b: _Builder, service: str, status: int, extra: str = "") -> None:
    for caller in _callers_of(service):
        b.during_fault(2, caller, "ERROR", [f"upstream {service} returned {status}{extra}"])
        if caller == "checkout":
            for grand in _callers_of("checkout"):
                b.during_fault(1, grand, "ERROR", ["upstream checkout returned 502"])


def _err(pct: float):
    """Error rate of a caller: ramps up to `pct` over ~2 minutes after the fault starts."""
    rng = random.Random(int(pct * 100))

    def effect(since: float) -> dict:
        return {"error_rate_pct": round(min(pct, pct * (since + 1) / 3) * rng.uniform(0.85, 1.15), 2)}

    return effect


def db_pool_exhausted(b: _Builder) -> dict:
    svc = b.s.root_service
    b.during_fault(
        3,
        svc,
        "ERROR",
        [
            "sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached, "
            "connection timed out, timeout 30.00",
        ],
    )
    b.during_fault(1, svc, "WARN", [f"{ENDPOINTS[svc][0]} took 30012ms, waited 30000ms for a DB connection"])
    _upstream_errors(b, svc, 503, " after 30004ms")
    effects = {svc: lambda since: {"db_pool_in_use": 30, "p95_ms": 30000, "error_rate_pct": round(18 + since, 1)}}
    for caller in _callers_of(svc):
        effects[caller] = _err(12.5)
    effects["gateway"] = _err(6.2)
    return effects


def cache_unavailable(b: _Builder) -> dict:
    b.during_fault(
        3,
        "cart",
        "WARN",
        [
            "redis.exceptions.ConnectionError: Error 111 connecting to cart-cache:6379. Connection refused.",
        ],
    )
    b.during_fault(2, "cart", "INFO", ["cart-cache unavailable, serving cart without cache (slow path)"])
    b.log(
        b.fault - timedelta(seconds=20),
        "cart-cache",
        "WARN",
        "# WARNING Memory overcommit must be enabled! Without it, a background save or replication may fail "
        "under low memory condition.",
        "redis",
    )
    effects = {
        "cart": lambda since: {"p95_ms": 1850 + int(since * 40), "error_rate_pct": round(4.5 + since * 0.4, 2)},
        "gateway": lambda since: {"p95_ms": 1420 + int(since * 30), "error_rate_pct": 1.1},
        "cart-cache": lambda since: {"up": 0, "mem_used_mb": 0},
    }
    return effects


def oom_killed(b: _Builder) -> dict:
    svc = b.s.root_service
    pod = f"{svc}-{POD_SUFFIX[svc]}"
    minute = b.fault
    n = 0
    while minute < b.end:
        n += 1
        b.log(
            minute + timedelta(seconds=b.rng.randint(0, 20)),
            svc,
            "WARN",
            f"pod/{pod} container {svc} last state: Terminated, Reason: OOMKilled, Exit Code: 137 (memory limit 512Mi)",
            "k8s",
        )
        b.log(
            minute + timedelta(seconds=b.rng.randint(25, 59)),
            svc,
            "WARN",
            f"Warning BackOff pod/{pod}: Back-off restarting failed container {svc} in pod {pod}_default",
            "k8s",
        )
        minute += timedelta(minutes=2)
    b.during_fault(1, svc, "INFO", ["loaded 184233 catalog entries into in-memory cache"])
    for caller in _callers_of(svc):
        b.during_fault(2, caller, "ERROR", [f"upstream {svc} connection refused ({svc}:8080)"])
    effects = {
        svc: lambda since: {
            "mem_pct": 99.1 if int(since) % 2 == 0 else 71.4,
            "restarts": int(since // 2) + 1,
            "error_rate_pct": 35.0,
        }
    }
    for caller in _callers_of(svc):
        effects[caller] = _err(9.5)
    return effects


BAD_DEPLOY_ERRORS = {
    "checkout": "KeyError: 'currency' in checkout/pricing.py:88 build_order_total",
    "cart": "TypeError: unsupported operand type(s) for +: 'NoneType' and 'int' in cart/totals.py:41",
    "gateway": "KeyError: 'X-Request-Id' in gateway/middleware.py:57 propagate_request_id",
}


def bad_deploy(b: _Builder) -> dict:
    svc = b.s.root_service
    b._deploy(b.fault - timedelta(seconds=40), svc, "2.14.0", "2.13.2")
    b.during_fault(
        4,
        svc,
        "ERROR",
        [f"unhandled exception on {ENDPOINTS[svc][-1].replace('{id}', '4711')}: {BAD_DEPLOY_ERRORS[svc]}"],
    )
    _upstream_errors(b, svc, 500)
    effects = {svc: lambda since: {"error_rate_pct": round(24 + since * 0.5, 1)}}
    for caller in _callers_of(svc):
        effects[caller] = _err(11.0)
    return effects


def upstream_timeout(b: _Builder) -> dict:
    b.during_fault(2, "payments", "ERROR", ["httpx.ReadTimeout: The read operation timed out"])
    b.during_fault(
        2, "payments", "ERROR", ["PSP charge failed: POST https://psp.example.com/v1/charges timed out after 10.0s"]
    )
    b.during_fault(2, "payments", "WARN", ["retrying PSP charge (attempt 2/3)", "retrying PSP charge (attempt 3/3)"])
    _upstream_errors(b, "payments", 504, " after 30011ms")
    return {
        "payments": lambda since: {"p95_ms": 30150 + int(since * 90), "error_rate_pct": round(14 + since, 1)},
        "checkout": _err(10.5),
        "gateway": _err(5.8),
    }


def disk_full(b: _Builder) -> dict:
    relfile = f"base/16384/{b.rng.randint(24000, 26000)}"
    b.during_fault(
        3,
        "orders-db",
        "ERROR",
        [f'ERROR:  could not extend file "{relfile}": No space left on device HINT:  Check free disk space.'],
        "postgres",
    )
    for svc in ("payments", "inventory"):
        b.during_fault(
            2, svc, "ERROR", [f'psycopg.errors.DiskFull: could not extend file "{relfile}": No space left on device']
        )
        _upstream_errors(b, svc, 500)
    return {
        "orders-db": lambda since: {"disk_used_pct": 100.0 if since >= 1 else 97.8},
        "payments": _err(16.0),
        "inventory": _err(13.0),
        "checkout": _err(9.0),
    }


SCENARIOS = {
    "db_pool_exhausted": db_pool_exhausted,
    "cache_unavailable": cache_unavailable,
    "oom_killed": oom_killed,
    "bad_deploy": bad_deploy,
    "upstream_timeout": upstream_timeout,
    "disk_full": disk_full,
}


# ----------------------------------------------------------------------------- alerts
def _alert_text(spec: IncidentSpec, metrics_at_alert: dict) -> str:
    m = metrics_at_alert
    if spec.alert_name == "HighErrorRate":
        detail = f"error_rate {m['error_rate_pct']}% > 5% for 5m"
    elif spec.alert_name == "HighLatencyP95":
        detail = f"p95 latency {m['p95_ms']}ms > 800ms for 5m"
    elif spec.alert_name == "PodCrashLooping":
        detail = f"{m['restarts']} container restarts in the last 15m"
    elif spec.alert_name == "DiskSpaceLow":
        detail = f"disk used {m['disk_used_pct']}% > 90%"
    else:
        raise ValueError(spec.alert_name)
    return (
        f"[FIRING:1] {spec.alert_name} service={spec.alert_service} severity=page\n"
        f"{detail}\nstartsAt={_iso(spec.alert_at)}"
    )


def build_world(seed: int = SEED) -> World:
    rng = random.Random(seed)
    world = World()
    for spec in SPECS:
        b = _Builder(spec, rng, world)
        b.background()
        b.distractor()
        effects = SCENARIOS[spec.category](b)
        b.metrics(effects)
        b.flush_logs()
        at = _iso(spec.alert_at)
        m = next(r for r in world.metrics if r["ts"] == at and r["service"] == spec.alert_service)
        world.incidents.append(
            {
                "id": spec.id,
                "category": spec.category,
                "root_service": spec.root_service,
                "alert_service": spec.alert_service,
                "alert_name": spec.alert_name,
                "starts_at": at,
                "alert_text": _alert_text(spec, m),
                "expected_action": EXPECTED_ACTION.get(spec.category),
                "distractor_deploy": spec.distractor_deploy,
                "tags": spec.tags,
            }
        )
    world.logs.sort(key=lambda r: r["ts"])  # stable: keeps per-incident order within a second
    world.metrics.sort(key=lambda r: (r["ts"], r["service"]))
    world.deploys.sort(key=lambda r: r["ts"])
    for i, row in enumerate(world.logs, start=1):
        row["id"] = f"L{i:05d}"
    return world


def write_all(root: Path, seed: int = SEED) -> World:
    world = build_world(seed)
    data = root / "data" / "demo-shop"
    data.mkdir(parents=True, exist_ok=True)
    for name, rows in (
        ("logs", world.logs),
        ("metrics", world.metrics),
        ("deploys", world.deploys),
        ("incidents", world.incidents),
    ):
        (data / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    return world


def spec_dict(spec: IncidentSpec) -> dict:
    d = asdict(spec)
    d["alert_at"] = _iso(spec.alert_at)
    return d
