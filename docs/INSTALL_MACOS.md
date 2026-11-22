# Локальная установка на macOS

## 1. Требования
- macOS 13+ рекомендуется.
- Python 3.12.
- Git.
- Доступ к OpenAI API и API key.
- Интернет во время работы (модель вызывается через API).

Docker не требуется для первого запуска: по умолчанию используется локальная SQLite-база.

## 2. Установить инструменты
Если Homebrew уже установлен:
```bash
brew install git python@3.12
```
Если Homebrew не установлен, установите его с официального сайта https://brew.sh, затем выполните команду выше.

Проверить:
```bash
git --version
python3.12 --version
```

## 3. Скачать проект
```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/mikhaildrobinin-bot/direktor-gpt.git
cd direktor-gpt
```

## 4. Создать виртуальное окружение
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
При следующем открытии Terminal перед работой снова активируйте окружение:
`cd ~/Projects/direktor-gpt && source .venv/bin/activate`.

## 5. Настроить OpenAI API
Скопировать шаблон:
```bash
cp .env.example .env
open -e .env
```
Вставить ключ только в локальный файл:
```dotenv
OPENAI_API_KEY=sk-ВАШ_КЛЮЧ
OPENAI_MODEL=gpt-5.4
DATABASE_URL=sqlite:///./direktor.db
MAX_ACTIVE_TASKS=3
APP_ENV=development
```
Сохранить файл. Не отправляйте ключ в чат, не добавляйте его в GitHub и не делайте скриншоты с ключом. В OpenAI Platform проверьте API billing/limits: ChatGPT Plus не включает API-трафик.

## 6. Запустить сервер
В активированном виртуальном окружении, из папки проекта:
```bash
uvicorn app.main:app --reload
``
Оставьте это окно Terminal открытым.

## 7. Проверить
Откройте:
- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/agents
- http://127.0.0.1:8000/docs

На `/health` ожидается `"openai_configured": true`. На `/agents` — 15 ролей. Swagger UI `/docs` — технический интерфейс API; отдельной пользовательской панели в текущем репозитории пока нет.

## 8. Первый тест
В Swagger откройте `POST /tasks`, нажмите Try it out и отправьте:
```json
{
  "instruction": "Директор, попроси РП подготовить короткий план запуска тестового проекта. РП должен привлечь аналитика и вернуть цель, этапы, риски и критерии готовности."
}
```
Запрос выполняет платный вызов OpenAI API. Следите за лимитами и расходами.

## 9. Остановить и запустить снова
Остановить: `Control + C` в окне Terminal.

Повторный запуск:
```bash
cd ~/Projects/direktor-gpt
source .venv/bin/activate
uvicorn app.main:app --reload
```

## Диагностика
- `command not found: python3.12`: выполните `brew install python@3.12`, затем откройте новое окно Terminal.
- `OPENAI_API_KEY не задан`: проверьте, что `.env` лежит в корне проекта и ключ записан без кавычек и пробелов.
- `401/invalid_api_key`: создайте новый API key и замените его в локальном `.env`.
- `429`: проверьте API billing, usage limits и доступную квоту.
- Порт занят: запустите `uvicorn app.main:app --reload --port 8001`, затем откройте `http://127.0.0.1:8001/docs`.

## Ограничения текущей версии
Локальный MVP не предоставляет агентам терминал, запись в GitHub или production-доступ. Полные навыки в виде исполняемых SKILL.md ещё не разработаны. Не используйте публичный репозиторий для секретов.
