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
make test    # тести, без мережі і без ключа API
make dev     # API на http://localhost:8000, документація на /docs
```

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
