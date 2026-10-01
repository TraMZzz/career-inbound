"""Services of demo-shop and who calls whom."""

from __future__ import annotations

SERVICES: dict[str, str] = {
    "gateway": "public HTTP entry point, routes to checkout and cart",
    "checkout": "places orders; calls cart, payments, inventory",
    "cart": "shopping cart API; caches carts in cart-cache",
    "payments": "charges cards via the external PSP; stores payments in orders-db",
    "inventory": "stock levels and reservations; stores data in orders-db",
    "orders-db": "PostgreSQL shared by payments and inventory",
    "cart-cache": "Redis used by cart",
    "psp": "external payment service provider (psp.example.com), not operated by us",
}

DEPENDS_ON: dict[str, list[str]] = {
    "gateway": ["checkout", "cart"],
    "checkout": ["cart", "payments", "inventory"],
    "cart": ["cart-cache"],
    "payments": ["orders-db", "psp"],
    "inventory": ["orders-db"],
    "orders-db": [],
    "cart-cache": [],
    "psp": [],
}

# Services that emit application logs and per-minute metrics.
APP_SERVICES = ["gateway", "checkout", "cart", "payments", "inventory"]
INFRA_SERVICES = ["orders-db", "cart-cache"]

CATEGORIES: dict[str, str] = {
    "db_pool_exhausted": "application DB connection pool is exhausted; requests wait for a connection and time out",
    "cache_unavailable": "cache (Redis) is unreachable; service falls back to slower paths",
    "oom_killed": "container exceeds its memory limit and is OOM-killed, restart loop",
    "bad_deploy": "a recent deploy introduced an error; rollback fixes it",
    "upstream_timeout": "an external dependency is slow or times out; not fixable by restarting our services",
    "disk_full": "database volume is out of space; writes fail",
    "unknown": "not enough data or not an alert about demo-shop",
}

ACTION_TYPES = ["restart_service", "rollback_deploy", "scale_up", "create_ticket", "post_status_update"]


def topology_text() -> str:
    lines = [
        f"- {name}: {desc}; depends on: {', '.join(DEPENDS_ON[name]) or 'nothing'}" for name, desc in SERVICES.items()
    ]
    return "\n".join(lines)
