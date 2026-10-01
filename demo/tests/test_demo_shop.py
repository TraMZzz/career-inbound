"""The demo data is the ground truth for every eval, so it gets tested like code."""

import json
import re
from datetime import timedelta

import pytest

from demo_shop.generator import SPECS, build_world, golden_rows
from demo_shop.store import Store, parse_ts

# (where the evidence lives, text) - at WARN level or above, except deploys which live in deploys.jsonl
EVIDENCE = {
    "db_pool_exhausted": ("root", "QueuePool limit"),
    "cache_unavailable": ("cart", "Error 111 connecting to cart-cache:6379"),
    "oom_killed": ("root", "OOMKilled"),
    "bad_deploy": ("root", None),
    "upstream_timeout": ("payments", "psp.example.com"),
    "disk_full": ("orders-db", "No space left on device"),
}
LOOKBACK = timedelta(minutes=15)  # same window the copilot uses


@pytest.fixture(scope="module")
def world():
    return build_world()


def test_generation_is_deterministic(world):
    again = build_world()
    assert json.dumps(world.logs) == json.dumps(again.logs)
    assert json.dumps(world.metrics) == json.dumps(again.metrics)


def test_committed_data_matches_generator(world, tmp_path):
    """data/demo-shop must be regenerated (make data) whenever the generator changes."""
    store = Store()
    assert len(store.logs) == len(world.logs)
    assert store.logs[0]["msg"] == world.logs[0]["msg"]
    assert store.logs[-1]["id"] == world.logs[-1]["id"]


def test_incident_windows_do_not_overlap():
    windows = sorted((s.alert_at - timedelta(minutes=20), s.alert_at + timedelta(minutes=5)) for s in SPECS)
    for (_, end), (start, _) in zip(windows, windows[1:], strict=False):
        assert end < start


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_every_incident_has_findable_evidence(world, spec):
    """The root cause must be visible in the 15 minutes before the alert, or the eval is unfair."""
    where, needle = EVIDENCE[spec.category]
    service = spec.root_service if where == "root" else where
    lo, hi = spec.alert_at - LOOKBACK, spec.alert_at
    if needle is None:
        hits = [d for d in world.deploys if d["service"] == service and lo <= parse_ts(d["ts"]) <= hi]
    else:
        hits = [
            r
            for r in world.logs
            if r["service"] == service
            and r["level"] in ("WARN", "ERROR")
            and needle in r["msg"]
            and lo <= parse_ts(r["ts"]) <= hi
        ]
    assert hits, f"{spec.id}: no evidence ({needle or 'deploy'}) for {service} in the 15 min before the alert"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_alert_metric_breaches_threshold(world, spec):
    inc = next(i for i in world.incidents if i["id"] == spec.id)
    line = inc["alert_text"].splitlines()[1]
    # "error_rate 13.0% > 5% ...", "p95 latency 2130ms > 800ms ...", "4 container restarts ..."
    m = re.search(r"([\d.]+)(?:%|ms)? >", line) or re.match(r"(\d+) ", line)
    value = float(m.group(1))
    threshold = {"HighErrorRate": 5, "HighLatencyP95": 800, "PodCrashLooping": 2, "DiskSpaceLow": 90}
    assert value > threshold[spec.alert_name], line


def test_ground_truth_not_leaked_into_observability_data(world):
    for row in world.logs + world.metrics + world.deploys:
        assert "incident" not in row and "category" not in row


def test_golden_set_shape(world):
    rows = golden_rows(world)
    assert 15 <= len(rows) <= 30
    assert len({r["id"] for r in rows}) == len(rows)
    assert sum("edge" in r["tags"] for r in rows) >= 2


def test_golden_service_names_do_not_collide(world):
    """'сервіс-причина: cart' is a substring of 'сервіс-причина: cart-cache': golden must guard against it."""
    rows = {r["id"]: r for r in golden_rows(world)}
    cart_rows = [r for r in rows.values() if "сервіс-причина: cart" in r["expect"].get("contains", [])]
    assert cart_rows
    for r in cart_rows:
        assert "сервіс-причина: cart-cache" in r["expect"]["not_contains"]
