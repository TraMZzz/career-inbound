# On-call Copilot

Референсний проєкт курсу **Career Inbound**: помічник чергового інженера для вигаданого сервісу **demo-shop**.
Отримує алерт, дивиться логи, метрики й деплої, пропонує діагноз і наступні кроки. Незворотні дії (рестарт,
відкат) лише пропонує, виконує їх людина.

Кожен урок курсу закінчується git-тегом `lesson-NN`: `git checkout lesson-02` показує стан після уроку 2.

## Як користуватися

**Студенту.** Це не шаблон для твого capstone, а приклад того, як ті самі етапи робляться на реальній задачі.
Після уроку N:

- переглянь код уроку на GitHub: `.../tree/lesson-02/demo` або що саме змінилось: `.../compare/lesson-01...lesson-02`;
- або локально: `git checkout lesson-02 && cd demo && uv sync && make test` (без ключа API);
- переноси ідеї на свій домен і стек, а не копіюй код: на захисті питатимуть про твої рішення.

**Автору.** Запис уроку N: `git switch -c rec-NN lesson-<N-1>`, у кадрі робиш крок уроку,
результат має збігтися з тегом `lesson-NN`. Деталі — `docs/AUTHOR_GUIDE.md` у корені репозиторію.

## Запуск

Потрібен [uv](https://docs.astral.sh/uv/).

```bash
uv sync
make test                  # тести, без мережі і без ключа API
cp .env.example .env       # і вписати ANTHROPIC_API_KEY
make dev                   # API на http://localhost:8000, документація на /docs
```

## Evals (з уроку 2)

Інструменти курсу лежать поруч, у `../tools` (шлях змінюється через `CI_TOOLS=...`).
У другому терміналі, поки працює `make dev`:

```bash
make eval       # golden set -> evals/results.json, pass_rate, p50/p95, $/1000
make baseline   # зберегти поточний результат як базовий
PROMPT_VERSION=v1 make dev   # перезапустити API з іншим промптом, потім make eval
make compare    # які кейси полагодились, які зламались
make check      # самоперевірка етапу 2
```

Модель задається `COPILOT_MODEL` (за замовчуванням `claude-sonnet-5-5`), ціни для `cost_usd` —
у `app/pricing.py` з датою перевірки.

## Контракт

`POST /ask {"input": "<текст алерту>", "context": {}, "dry_run": true}` повертає `answer`
у стабільному форматі (`Категорія: ...`, `Сервіс-причина: ...`), `sources` (рядки логів, на які спирається
діагноз), `actions_proposed` (завжди з `requires_confirmation: true`), `usage` (токени, вартість, latency, модель).

## demo-shop

Синтетичний e-commerce бекенд, дані генеруються детерміновано (`make data`):

```
gateway -> checkout -> cart -> cart-cache (Redis)
                    -> payments -> orders-db (PostgreSQL), psp (зовнішній платіжний провайдер)
                    -> inventory -> orders-db
```

| Файл | Що всередині |
|---|---|
| `data/demo-shop/logs.jsonl` | логи сервісів (app, k8s, deploy, postgres, redis) |
| `data/demo-shop/metrics.jsonl` | похвилинні метрики: rps, p95, error rate, CPU, памʼять, рестарти, пул зʼєднань, диск |
| `data/demo-shop/deploys.jsonl` | деплої, зокрема сторонні (відволікаючі) |
| `data/demo-shop/incidents.jsonl` | **ground truth** 17 інцидентів: категорія, сервіс-причина. Copilot його не бачить |
| `evals/golden.jsonl` | golden set: 17 алертів з очікуваннями + 3 крайові кейси |

Шість типів збоїв: вичерпаний пул зʼєднань до БД, недоступний кеш, OOM-рестарти, поганий деплой,
таймаути зовнішнього провайдера, переповнений диск БД. Причина часто не в тому сервісі, на який прийшов алерт.
Тексти помилок імітують реальні формати SQLAlchemy, redis-py, httpx, psycopg, PostgreSQL і Kubernetes,
але всі значення вигадані.

```bash
uv run python -m demo_shop summary   # що за інцидент за кожним алертом
```

## Стан по уроках

| Тег | Що додано |
|---|---|
| `lesson-00` | порожній FastAPI-скелет, demo-shop і його дані |
| `lesson-01` | правила для агентів (`AGENTS.md`, `CLAUDE.md`), опис проєкту з метрикою, AI-лог, `GET /health` |
| `lesson-02` | copilot v1: один виклик моделі зі structured output, `POST /ask`, 20 кейсів golden set, два промпти для порівняння, режими відмови |
