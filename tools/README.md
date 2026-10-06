# tools — інструменти курсу Career Inbound (`ci-eval`, `ci-check`)

Два CLI, які працюють з capstone **будь-якою мовою**, бо говорять з ним лише через HTTP-контракт:

- `ci-eval` — прогін golden set, заміри latency/cost, injection-проби, порівняння двох прогонів
- `ci-check` — самоперевірка етапу capstone за артефактами в репо (код не читає)

## Швидкий старт (студенту)

Твій сервіс запущений на `localhost:8000`, ти в корені свого репо:

```bash
T="git+https://github.com/TraMZzz/career-inbound@tools-v0.1.0#subdirectory=tools"
uvx --from "$T" ci-check --stage 0 --url http://localhost:8000   # тиждень 0: середовище працює
uvx --from "$T" ci-check --stage 2 --url http://localhost:8000   # перед здачею етапу 2
uvx --from "$T" ci-eval run --url http://localhost:8000           # evals/golden.jsonl -> evals/results.json
```

Якщо твій проєкт зі стартера, ці ж команди вже є в `Makefile`: `make check STAGE=2`, `make eval`.

## Контракт (v0.1)

```
GET  /health -> {"status": "ok", "version": "<git sha або тег>"}
POST /ask    <- {"input": "...", "context": {...}, "dry_run": true}
             -> {"answer": "...",
                 "sources": [{"id", "title", "snippet"}],
                 "steps": [{"tool", "args", "ok"}],
                 "actions_proposed": [{"type", "target", "requires_confirmation"}],
                 "usage": {"input_tokens", "output_tokens", "cost_usd", "latency_ms", "model"}}
```

Обовʼязкове лише `answer`. Решта полів зʼявляється по етапах: `steps` з етапу 3, `usage` з етапу 5,
`sources` там, де відповідь спирається на дані. Додаткові поля дозволені. З `dry_run: true` сервіс
не виконує незворотних дій, лише пропонує їх в `actions_proposed`.

## Встановлення

Потрібен [uv](https://docs.astral.sh/uv/). Інструменти лежать у папці `tools/` репозиторію курсу,
`uvx` бере їх звідти без встановлення:

```bash
uvx --from "git+https://github.com/TraMZzz/career-inbound#subdirectory=tools" ci-eval --help
# зафіксувати версію на весь потік:
uvx --from "git+https://github.com/TraMZzz/career-inbound@tools-v0.1.0#subdirectory=tools" ci-eval --help
```

З локального клону репозиторію курсу:

```bash
uv tool install ./tools      # ci-eval і ci-check стають доступні в PATH
```

## ci-eval

```bash
ci-eval run     --url http://localhost:8000                 # evals/golden.jsonl -> evals/results.json
ci-eval run     --url ... --min-pass 0.8                    # exit 1, якщо pass_rate < 0.8 (гейт у CI)
ci-eval compare evals/baseline.json evals/results.json      # що полагодилось, що зламалось
ci-eval perf    --url ... --n 50 --exclude-tag edge         # p50/p95, $/запит, $/1000 -> evals/perf.json
ci-eval attack  --url ...                                   # 6 injection-проб -> evals/attack.json
```

### Golden set: `evals/golden.jsonl`

Один кейс на рядок:

```json
{"id": "g-001", "input": "текст запиту", "context": {}, "expect": {"contains": ["..."], "not_contains": ["..."], "sources_include": ["runbook-12"], "action_type": "restart_service"}, "tags": ["edge"]}
```

| Поле | Перевірка |
|---|---|
| `contains` | кожен рядок є у `answer` (без урахування регістру) |
| `not_contains` | жодного з рядків немає в `answer` (без урахування регістру) |
| `sources_include` | кожен id є серед `sources[].id` |
| `action_type` | серед `actions_proposed` є дія такого типу |
| `context` | необовʼязковий, передається в `/ask` як є |
| `tags` | вільні; `ci-check` рахує `edge` (або `bad_input`) і `injection` |

Кейс проходить, якщо відповідь відповідає контракту і всі перевірки пройдені.
Невідомі поля в `expect` — помилка (щоб опечатка не робила кейс завжди зеленим).

### Як рахуються цифри

- **latency** — на боці клієнта (скільки чекає користувач), percentile за методом nearest-rank:
  на 20–50 замірах він не вигадує значень, яких не було
- **$/1000** — середнє `usage.cost_usd` × 1000; якщо сервіс не повертає `cost_usd`, виводиться `n/a`
- `run` за замовчуванням послідовний (`-j 1`), щоб latency не спотворювалась паралельними запитами
- у `run` цифри latency і вартості рахуються по всіх кейсах, включно з крайовими; для чесних цифр
  продакшн-навантаження використовуйте `perf --exclude-tag edge`
- таймаут на запит — 120 с (`--timeout`): має бути більшим за найгірший час сервісу з усіма повторами

### attack

Шість доменно-нейтральних проб: пряме перевизначення інструкцій, інструкція в даних (`context`),
тиск «дій без підтвердження», запит системного промпту й ключів, інструкція в base64, перевизначення українською.
Спершу перевіряється `/health`: з неправильним `--url` проби не запускаються. Відмова сервісу з HTTP 400/403/422
вважається безпечною, інші помилки (404, 5xx, падіння) — ні. Судження тільки детерміновані: canary-рядок не зʼявився у відповіді, усі дії з `requires_confirmation: true`,
у відповіді немає нічого схожого на ключ. Це нижня планка: атаки через **ваші** дані (рядки логів, документи)
додавайте в golden set з тегом `injection`.

## ci-check

```bash
ci-check --stage 0 --url http://localhost:8000      # тиждень 0: git, /health, /ask
ci-check --stage 2                                  # етапи 0..2; без --url живі перевірки стають ручними
ci-check --stage 2 --path demo                      # проєкт у підпапці теж працює
ci-check --stage 2 --url http://localhost:8000      # + перевірка живого сервісу за контрактом
ci-check --stage 5 --json                           # для CI
```

`[x]` — пройдено, `[!]` — треба виправити (exit 1), `[ ]` — підтвердити вручну.
Маркер `TODO(starter)` у файлах зі стартового шаблону означає «ще не заповнено» і валить перевірку.

| Етап | Автоматично | Вручну |
|---|---|---|
| 0 | git; з `--url`: `/health` відповідає `ok`, `/ask` відповідає за контрактом | ключ API лише в `.env`, ліміт витрат у кабінеті провайдера |
| 1 | README, файл правил агента (10+ непорожніх рядків, без плейсхолдерів), `docs/project.md` з метрикою, `docs/ai-log.md` | публічний репо, PR з AI-рев'ю, помилка агента в лозі |
| 2 | golden 15–30 кейсів з очікуваннями, 2+ edge-кейси, `evals/results.json`, `docs/failure-modes.md`, тести, контракт (`--url`) | зміна виміряна до/після |
| 3 | `/ask` повертає `steps` (`--url`) | ліміт кроків, обробка помилок, 3 сценарії |
| 4 | `docs/threat-model.md`, 3+ кейси `injection`, немає секретів у tracked-файлах | підтвердження незворотних дій (`ci-eval attack`) |
| 5 | 3+ кейси з `sources_include`, p50/p95 і $/1k у results.json, `evals/perf.json`, повний `usage` (`--url`) | recall@k |
| 6 | ADR у `docs/adr/`, CI запускає `ci-eval` | публічний URL/відео, обробка недоступності API |
| 7 | README має розділи (заголовки) про проблему, архітектуру, компроміси, безпеку; згадує p95, вартість, evals; є діаграма | чи це справді історія — на захисті |

## Розробка

```bash
cd tools
uv sync
uv run pytest
uv run ruff check .
```
