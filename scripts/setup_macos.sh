#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Python 3.12 не найден."
  if command -v brew >/dev/null 2>&1; then
    echo "Устанавливаю Python 3.12 через Homebrew..."
    brew install python@3.12
  else
    echo "Сначала установите Homebrew с https://brew.sh, затем запустите этот скрипт снова."
    exit 1
  fi
fi

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ""
  echo "Создан .env из шаблона."
  echo "Откройте его командой: open -e .env"
  echo "Добавьте OPENAI_API_KEY. Не публикуйте этот файл."
else
  echo ".env уже существует — оставляю без изменений."
fi

chmod 600 .env

echo ""
echo "Установка зависимостей завершена."
echo "Следующий шаг:"
echo "  open -e .env"
echo "После добавления API key запустите:"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload"
