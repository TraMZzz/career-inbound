# Career Inbound — код курсу

Тут увесь код технічного треку курсу: демо, яке будується на уроках, інструменти перевірки і шаблон capstone.

| Папка | Що це | Кому |
|---|---|---|
| [`demo/`](demo/) | **On-call Copilot** — помічник чергового інженера, який росте урок за уроком | автор показує на записі; студент дивиться, як зроблено |
| [`tools/`](tools/) | `ci-eval` і `ci-check` — evals, latency і вартість, injection-проби, самоперевірка етапів | студент запускає на **своєму** capstone, будь-якою мовою |
| [`starter/`](starter/) | шаблон capstone на Python (FastAPI) | студент копіює собі як старт, необовʼязково |

**Студент не здає роботи в цей репозиторій.** Його capstone живе в його власному публічному репо — це артефакт
для співбесід. Звідси він бере інструменти, шаблон і приклад.

## Інструкції

- **Студенту:** [`docs/STUDENT_GUIDE.md`](docs/STUDENT_GUIDE.md) — тиждень 0, що робити кожного тижня, як перевірити і здати етап
- **Автору:** [`docs/AUTHOR_GUIDE.md`](docs/AUTHOR_GUIDE.md) — публікація, видача студентам, запис уроків, нові версії інструментів, рев'ю
- По папках: [`demo/README.md`](demo/README.md), [`tools/README.md`](tools/README.md), [`starter/README.md`](starter/README.md)

## Уроки = git-теги

`git checkout lesson-02` — стан коду після уроку 2. Що додав урок: `git diff lesson-01 lesson-02 -- demo/`.

| Тег | Урок | Що в `demo/` |
|---|---|---|
| `lesson-00` | старт | порожній FastAPI, demo-shop і його синтетичні дані |
| `lesson-01` | 1 · AI-навички | правила для агентів, опис проєкту з метрикою, AI-лог, `/health` |
| `lesson-02` | 2 · Верифікація і evals | copilot v1: один виклик моделі, `POST /ask`, 20 кейсів, промпти v1/v2 |

`tools-v0.1.0` — версія інструментів, на яку посилається шаблон; вона не змінюється протягом потоку.

## Швидкий старт

```bash
# студент: перевірити свій проєкт (сервіс запущений на :8000)
uvx --from "git+https://github.com/<ORG>/career-inbound@tools-v0.1.0#subdirectory=tools" ci-check --stage 0 --url http://localhost:8000

# будь-хто: подивитись демо
git clone https://github.com/<ORG>/career-inbound && cd career-inbound/demo
uv sync && make test
```

Потрібен [uv](https://docs.astral.sh/uv/). CI цього репозиторію (`.github/workflows/test.yml`) запускає лінтер
і тести в усіх трьох папках.
