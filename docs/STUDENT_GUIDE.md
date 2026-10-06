# Інструкція студента — технічний трек

За 8 тижнів ти будуєш **один** проєкт — capstone: невеликий сервіс з AI-фічею або агентом з твого домену.
Кожна домашка — наступний етап цього проєкту. На тижні 8 ти захищаєш його як на AI system design співбесіді.

Цей репозиторій дає три речі:

| Що | Навіщо тобі |
|---|---|
| `tools/` | перевіряєш свій проєкт тими самими інструментами, якими його перевіряємо ми |
| `starter/` | готовий каркас на Python, якщо не хочеш налаштовувати з нуля |
| `demo/` | приклад: як кожен етап зроблено на реальній задачі (On-call Copilot) |

## Тиждень 0 — підготовка (1–2 год)

1. **Встанови:** Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), редактор, AI-асистент для коду
   (Claude Code, Cursor або GitHub Copilot — один на вибір). Docker знадобиться на тижні 6.
2. **Ключ API моделі** (Anthropic або OpenAI). Одразу встанови ліміт витрат у кабінеті провайдера.
   Ключ зберігай лише в `.env`, ніколи в репо.
3. **Обери старт.**
   - **Python:** скопіюй шаблон.
     ```bash
     git clone --depth 1 https://github.com/TraMZzz/career-inbound /tmp/career-inbound
     cp -R /tmp/career-inbound/starter ~/my-capstone && cd ~/my-capstone
     git init && git add -A && git commit -m "Start from Career Inbound starter"
     uv sync && make test
     cp .env.example .env
     make dev
     ```
   - **Інша мова (Java, C#, PHP, TS, Go...):** створи свій проєкт і зроби два ендпоінти:
     `GET /health` → `{"status": "ok", "version": "..."}` і `POST /ask` → `{"answer": "..."}`.
     Поки що `/ask` може повертати заглушку. Повний контракт — у [`tools/README.md`](../tools/README.md).
4. **Створи свій публічний репозиторій на GitHub** і запуш туди проєкт.
5. **Перевір середовище** (сервіс має бути запущений):
   ```bash
   make check STAGE=0          # якщо зі стартера
   # або для будь-якої мови:
   uvx --from "git+https://github.com/TraMZzz/career-inbound@tools-v0.1.0#subdirectory=tools" \
       ci-check --stage 0 --url http://localhost:8000
   ```
   Усі пункти `[x]` — ти готовий до першого уроку.
6. **Ідея capstone:** 3 речення — яка проблема, для кого, як зрозуміти, що працює. Немає ідеї — 10 прикладів
   у брифі capstone на платформі курсу.

## Щотижневий цикл

1. **Урок** на платформі курсу.
2. **Подивись демо уроку:** на GitHub — `tree/lesson-0N/demo`; що змінилось — `compare/lesson-0(N-1)...lesson-0N`.
3. **Зроби етап на своєму проєкті** (таблиця нижче). Переносиш ідеї, а не код: на захисті питатимуть про твої рішення.
4. **Самоперевірка:** `make check STAGE=N` (або `ci-check --stage N --url ...`). `[!]` — виправити, `[ ]` — перевір сам.
5. **Здача:** тег у своєму репо і посилання на нього.
   ```bash
   git tag stage-2 && git push --tags
   ```

## Етапи

| Тиждень | Уроки | Етап | Що має бути в репо | Перевірка |
|---|---|---|---|---|
| 0 | онбординг | Середовище | сервіс запускається, `/health` і `/ask` відповідають | `--stage 0` |
| 1 | 1 | AI-воркфлоу | `AGENTS.md` (або `CLAUDE.md` / rules), `docs/project.md` з метрикою, `docs/ai-log.md`, PR з AI-рев'ю | `--stage 1` |
| 2 | 2 | Верифікація | перша версія `/ask`, `evals/golden.jsonl` (15–30 кейсів, 2+ з тегом `edge`), `evals/results.json`, `docs/failure-modes.md`, тести | `--stage 2` |
| 3 | 3, 4 | Агент | ≥2 інструменти або свій MCP-сервер; `steps` у відповіді `/ask` | `--stage 3` |
| 4 | 5 | Безпека | `docs/threat-model.md`, 3+ кейси з тегом `injection`, підтвердження незворотних дій, секрети лише в env | `--stage 4`, `ci-eval attack` |
| 5 | 6, 7 | Дані й цифри | `sources` у відповідях, 3+ кейси з `sources_include`, `usage`, `evals/perf.json` | `--stage 5`, `ci-eval perf` |
| 6 | 8 | Продакшн | деплой (URL або демо-відео), ADR з цифрами в `docs/adr/`, evals у CI | `--stage 6` |
| 7 | 9 | Кейс | README як історія: проблема, архітектура (діаграма), компроміси, цифри, evals, безпека; code freeze | `--stage 7` |
| 8 | — | Захист | 10 хв демо + 15–20 хв питань як на AI system design співбесіді | чекліст захисту |

Файли `evals/results.json`, `evals/perf.json`, `evals/attack.json` комітяться — це докази твоїх цифр.

## Інструменти — шпаргалка

```bash
T="git+https://github.com/TraMZzz/career-inbound@tools-v0.1.0#subdirectory=tools"
uvx --from "$T" ci-eval run --url http://localhost:8000          # golden set -> evals/results.json
cp evals/results.json evals/baseline.json                         # зберегти «до»
uvx --from "$T" ci-eval compare evals/baseline.json evals/results.json   # «до/після»
uvx --from "$T" ci-eval perf --url http://localhost:8000 --n 20 --exclude-tag edge
uvx --from "$T" ci-eval attack --url http://localhost:8000
uvx --from "$T" ci-check --stage N --url http://localhost:8000
```

Зі стартера те саме коротше: `make eval`, `make baseline`, `make compare`, `make perf`, `make attack`, `make check STAGE=N`.

## Якщо щось не працює

Напиши в чат когорти: що робив, що очікував, що вийшло, і **текстом** вивід команди (не скріншот).

## Робоча задача під NDA

За замовчуванням — відкрита версія робочої задачі: та сама проблема на публічних або синтетичних даних,
без коду й даних компанії. За дотримання NDA відповідаєш ти.
