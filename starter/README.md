# Capstone starter — Career Inbound

Стартовий шаблон capstone на Python (FastAPI). Використовувати не обовʼязково: capstone може бути на будь-якій
мові, головне — два ендпоінти контракту курсу. Тоді інструменти курсу (evals, заміри, тести безпеки,
самоперевірка) працюють з твоїм проєктом так само, як з цим шаблоном.

> Цей README — інструкція до шаблону. До тижня 7 заміни його на README свого проєкту (етап 7).

## Старт

```bash
# 1. Скопіювати шаблон з репозиторію курсу у свою папку
git clone --depth 1 https://github.com/TraMZzz/career-inbound /tmp/career-inbound
cp -R /tmp/career-inbound/starter ~/my-capstone && cd ~/my-capstone
git init && git add -A && git commit -m "Start from Career Inbound starter"
# 2. Створити СВІЙ публічний репозиторій на GitHub і запушити туди

uv sync
make test
cp .env.example .env        # ключ API моделі; .env не комітиться
make dev                    # http://localhost:8000/docs

# 3. В іншому терміналі: перевірка тижня 0
make check STAGE=0          # git, /health і /ask відповідають — середовище готове
```

Потрібні: [uv](https://docs.astral.sh/uv/), Git, для деплою (тиждень 6) — Docker.
`make check` і `make eval` звертаються до запущеного сервісу, тому спершу `make dev`.

## Контракт

```
GET  /health -> {"status": "ok", "version": "..."}
POST /ask    <- {"input": "...", "context": {...}, "dry_run": true}
             -> {"answer": "...", "sources": [...], "steps": [...], "actions_proposed": [...], "usage": {...}}
```

Моделі — в `app/contract.py`. Поля не перейменовуй. `steps` потрібні з етапу 3, `usage` — з етапу 5.
З `dry_run: true` сервіс нічого незворотного не виконує, лише пропонує в `actions_proposed`.

## Інструменти курсу

```bash
make eval            # evals/golden.jsonl -> evals/results.json (pass_rate, p50/p95, $/1000)
make baseline        # зберегти результат як базовий
make compare         # що полагодилось і що зламалось після зміни
make perf            # latency і вартість на 20 запитах -> evals/perf.json
make attack          # 6 injection-проб -> evals/attack.json
make check STAGE=2   # самоперевірка етапу
```

`evals/results.json`, `perf.json`, `attack.json` комітяться: це докази для рев'ю і для захисту.
Формат golden set — у `evals/golden.example.jsonl`; свій набір клади в `evals/golden.jsonl`.

## Етапи і що має бути в репо

| Тиждень | Етап | Файли |
|---|---|---|
| 0 | Середовище | `make check STAGE=0` зелений: сервіс запускається, `/health` і `/ask` відповідають |
| 1 | AI-воркфлоу | `AGENTS.md` (+ `CLAUDE.md` імпортує його), `docs/project.md`, `docs/ai-log.md`, PR з AI-рев'ю |
| 2 | Верифікація | перша версія `/ask`, `evals/golden.jsonl` (15–30 кейсів, 2+ з тегом `edge`), `evals/results.json`, `docs/failure-modes.md`, тести |
| 3 | Агент | ≥2 інструменти або свій MCP-сервер, `steps` у відповіді |
| 4 | Безпека | `docs/threat-model.md`, 3+ кейси з тегом `injection`, секрети лише в env |
| 5 | Дані й цифри | `sources` у відповідях, 3+ кейси з `sources_include`, `usage`, `evals/perf.json` |
| 6 | Продакшн | деплой, `docs/adr/0002-*.md` з цифрами, `evals.yml` у CI увімкнено |
| 7 | Кейс | README як історія: проблема, архітектура (діаграма), компроміси, цифри, evals, безпека |

`TODO(starter)` — ще не заповнено. `ci-check` не зараховує файли з цим маркером, тому CI буде червоним,
доки ти не заповниш етап 1. Так і задумано.

## CI

- `.github/workflows/ci.yml` — лінтер, тести і `ci-check` для поточного етапу. Етап задається змінною
  репозиторію `CAPSTONE_STAGE` (Settings → Secrets and variables → Variables).
- `.github/workflows/evals.yml` — golden set на кожен PR з порогом якості. Вмикається на етапі 6: видали рядок
  з `TODO(starter)` і додай секрет `ANTHROPIC_API_KEY` (або ключ свого провайдера).

## Робоча задача під NDA

За замовчуванням — відкрита версія робочої задачі: та сама проблема на публічних або синтетичних даних,
без коду й даних компанії. За дотримання NDA відповідаєш ти.
