"""Copilot v1 (lesson 2): a fixed pipeline with exactly one LLM call.

    alert text -> parse -> logs (WARN+), metrics and deploys of the alerting service, last 15 min
               -> one LLM call -> deterministic checks -> answer

Known limitation, on purpose: it only looks at the service that alerted. When the root cause is in a
dependency (DB, cache, external provider, another service's deploy) the model sees only the symptom.
Lesson 3 replaces this pipeline with an agent that decides what else to look at.
"""

from __future__ import annotations

import time
from datetime import timedelta

from demo_shop.store import Store
from demo_shop.topology import DEPENDS_ON, SERVICES

from .alerts import Alert, parse_alert
from .contract import ActionProposed, AskResponse, Source, Usage
from .llm import Diagnoser, Diagnosis
from .pricing import cost_usd
from .prompts import system_prompt

LOOKBACK = timedelta(minutes=15)
MAX_LOG_LINES = 40
METRIC_KEYS = [
    "rps",
    "p95_ms",
    "error_rate_pct",
    "cpu_pct",
    "mem_pct",
    "restarts",
    "db_pool_in_use",
    "disk_used_pct",
    "up",
]


class Copilot:
    def __init__(self, store: Store, llm: Diagnoser, prompt_version: str | None = None):
        self.store = store
        self.llm = llm
        self.prompt_version, self.system = system_prompt(prompt_version)

    # ------------------------------------------------------------------ public
    def ask(self, text: str) -> AskResponse:
        started = time.perf_counter()
        alert = parse_alert(text)
        if alert is None:
            return self._unknown("Не бачу алерту: потрібен текст з [FIRING], service=... і startsAt=...", started)
        if alert.service not in SERVICES:
            return self._unknown(f"Сервіс {alert.service!r} не належить demo-shop, даних по ньому немає.", started)

        logs = self._logs(alert)
        user = self._user_message(alert, logs)
        result = self.llm.diagnose(self.system, user)

        diagnosis, warnings = self._check(result.diagnosis, {r["id"] for r in logs})
        by_id = {r["id"]: r for r in logs}
        return AskResponse(
            answer=render(diagnosis),
            sources=[
                Source(
                    id=i, title=f"{by_id[i]['service']} {by_id[i]['level']} {by_id[i]['ts']}", snippet=by_id[i]["msg"]
                )
                for i in diagnosis.evidence_log_ids
            ],
            actions_proposed=[
                ActionProposed(type=a.type, target=a.target, requires_confirmation=True) for a in diagnosis.actions
            ],
            usage=Usage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=cost_usd(self.llm.model, result.input_tokens, result.output_tokens),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                model=result.model,
            ),
            warnings=warnings,
        )

    # ------------------------------------------------------------------ steps
    def _logs(self, alert: Alert) -> list[dict]:
        return self.store.search_logs(
            alert.service, alert.starts_at - LOOKBACK, alert.starts_at, min_level="WARN", limit=MAX_LOG_LINES
        )

    def _user_message(self, alert: Alert, logs: list[dict]) -> str:
        metrics = self.store.get_metrics(alert.service, alert.starts_at - LOOKBACK, alert.starts_at)
        keys = [k for k in METRIC_KEYS if metrics and k in metrics[0]]
        metric_lines = [" | ".join(["ts", *keys])]
        metric_lines += [" | ".join([m["ts"][11:16], *(str(m[k]) for k in keys)]) for m in metrics]
        log_lines = [f"[{r['id']}] {r['ts']} {r['level']} {r['source']}: {r['msg']}" for r in logs]
        deploys = self.store.list_deploys(alert.starts_at - LOOKBACK, alert.starts_at, service=alert.service)
        deploy_lines = [
            f"{d['ts']} {d['service']} {d['previous']} -> {d['version']} (commit {d['commit']})" for d in deploys
        ]
        deps = ", ".join(DEPENDS_ON[alert.service]) or "none"
        return (
            f"ALERT:\n{alert.text}\n\n"
            f"SERVICE: {alert.service} ({SERVICES[alert.service]}; depends on: {deps})\n\n"
            f"LOGS of {alert.service}, WARN and above, last 15 min, oldest first:\n"
            + ("\n".join(log_lines) or "(no warnings or errors)")
            + f"\n\nMETRICS of {alert.service}, per minute (UTC), last 15 min:\n"
            + "\n".join(metric_lines)
            + f"\n\nDEPLOYS of {alert.service}, last 15 min:\n"
            + ("\n".join(deploy_lines) or "(none)")
        )

    @staticmethod
    def _check(d: Diagnosis, allowed_ids: set[str]) -> tuple[Diagnosis, list[str]]:
        """Deterministic guardrails on model output. The model is not trusted to cite correctly."""
        warnings = []
        invented = [i for i in d.evidence_log_ids if i not in allowed_ids]
        if invented:
            warnings.append(f"dropped evidence ids not present in the input: {invented}")
        kept = list(dict.fromkeys(i for i in d.evidence_log_ids if i in allowed_ids))
        return d.model_copy(update={"evidence_log_ids": kept}), warnings

    def _unknown(self, reason: str, started: float) -> AskResponse:
        d = Diagnosis(
            summary=reason,
            category="unknown",
            root_service="unknown",
            evidence_log_ids=[],
            next_steps=["Перевірте текст алерту і назву сервісу."],
            actions=[],
        )
        return AskResponse(
            answer=render(d),
            usage=Usage(
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                model="none (no LLM call)",
            ),
        )


def render(d: Diagnosis) -> str:
    """Stable, machine-checkable answer format: evals match 'категорія: X' and 'сервіс-причина: Y'."""
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(d.next_steps, start=1)) or "—"
    lines = [
        f"Діагноз: {d.summary}",
        f"Категорія: {d.category}",
        f"Сервіс-причина: {d.root_service}",
        f"Докази: {', '.join(d.evidence_log_ids) or 'немає'}",
        f"Наступні кроки:\n{steps}",
    ]
    if d.actions:
        lines.append(
            "Пропоновані дії (потрібне підтвердження): "
            + "; ".join(f"{a.type} {a.target} — {a.reason}" for a in d.actions)
        )
    return "\n".join(lines)
