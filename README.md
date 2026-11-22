# direktor-openai

Мультиагентная система на OpenAI Agents SDK. Исходный репозиторий `mikhaildrobinin-bot/direktor` не изменяется.

## Команда
15 ролей: директор, руководитель проекта и 13 специализированных агентов. Директор делегирует РП, РП вызывает профильных специалистов через `Agent.as_tool`.

## Перенос исходных инструкций
Оригинальные prompt-файлы, правила и подробные справочники перенесены в `agents/source/`. Активные инструкции ролей в `agents/prompts/` используют исходные prompt-файлы. Runtime добавляет соответствующие правила и playbooks в контекст агента. Подробности — `docs/MIGRATION_FROM_DIREKTOR.md`.

## Стек
- OpenAI Agents SDK
- FastAPI
- SQLAlchemy + PostgreSQL (SQLite для локальной разработки)
- Docker Compose
- GitHub Actions

## Локальный запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните OPENAI_API_KEY
uvicorn app.main:app --reload
```

Панель управления (на русском): http://127.0.0.1:8000/\n\nSwagger: http://localhost:8000/docs

## Docker
```bash
cp .env.example .env
# заполните OPENAI_API_KEY
docker compose up --build
```

## Обновление на Mac\nПосле изменений на GitHub остановите сервер сочетанием Ctrl+C и выполните из папки проекта:\n```bash\ngit pull\nbash scripts/run_macos.sh\n```\nОткройте http://127.0.0.1:8000/ — там можно отправлять задачи и читать ответы.\n\n## API
- `GET /health` — состояние конфигурации.
- `GET /agents` — список ролей.
- `GET /tasks` — последние задачи.
- `POST /tasks` — передать задачу директору.

## Навыки
Отдельных `SKILL.md` в исходном репозитории не найдено. `skills/registry.yaml` — предварительные функциональные модули, не подтверждённые оригинальные навыки. См. `skills/README.md`.

## Ограничения MVP
Это не production-ready сервис. Не подключены GitHub write tools, shell, публикации и production deploy. Перед эксплуатацией обязательны аутентификация/RBAC, approval workflow, sandbox исполнения кода, аудит, мониторинг, rate limits, бюджетные лимиты и резервное копирование.

Не добавляйте `.env` и API-ключи в Git. Укажите модель, доступную вашему OpenAI API-проекту, в `OPENAI_MODEL`.
