#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Не найдено виртуальное окружение. Сначала выполните: bash scripts/setup_macos.sh"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Не найден .env. Сначала выполните установку: bash scripts/setup_macos.sh"
  exit 1
fi

if ! grep -Eq '^OPENAI_API_KEY=.+$' .env; then
  echo "В .env не задан OPENAI_API_KEY."
  echo "Откройте файл: open -e .env"
  exit 1
fi

source .venv/bin/activate
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
