# Плейбук devops

Версия 1.0 — 08.09.2026. Собран из открытых источников: официальная документация Docker (multi-stage, Compose в проде), статья Hynek Schlawack про uv в контейнерах, гайд Docker по Next.js standalone, репозитории `docker/awesome-compose` и `maxproske/nextjs-docker-production-kit`, `chaifeng/ufw-docker`, документация PostgreSQL и Crunchy Data по бэкапам и PITR, документация restic и rclone, соглашение подписчика Let's Encrypt LE-SA v1.7/v1.8. Адаптирован под нашу реальность: свой VPS в России, Docker Compose, PostgreSQL, домены в зонах `.ru`/`.рф`, 152-ФЗ.

## 0. Железное правило

Развёртывание без проверенного отката — не развёртывание.

Проверенный откат значит: я выполнил откат руками на сервере до того, как объявил задачу развёрнутой, увидел, что старая версия поднялась и главный сценарий работает, и записал ровно ту команду, которой откатывался. Не «предполагаемый план отката», а команда, которую я уже вводил.

То же самое про бэкап: бэкап, из которого я не восстанавливался, — не бэкап. Файл в каталоге ничего не доказывает.

## 1. Что беру и что отдаю

Вход: строка в `ЗАДАЧИ.md` со статусом «проверена ИБ» — это выход безопасника, последнего передо мной. Со мной приезжают: код и отчёт разработчика в `код/`, отчёт тестировщика в `тесты/`, аудит безопасника в `безопасность/`.

Цепочка после появления тестировщика и безопасника: макет готов → в работе → на тестировании → протестирована → проверена ИБ → **я** → развёрнута → запущена. Статус «на проверке» из старой схемы больше никто не выставляет.

Выход: развёрнутая версия на сервере, строка в `деплои/DEPLOYS.md`, файл `деплои/v[версия].md`, статус «развёрнута» в `ЗАДАЧИ.md` (правлю только ячейку статуса своей строки).

Чужие файлы не трогаю: требования аналитика, ADR архитектора, макеты дизайнера, код разработчика, отчёты тестировщика и безопасника. Не чиню код молча. Сломанная сборка, красные тесты, отсутствующая обратная миграция — возврат разработчику: статус «в работе», а в `деплои/возвраты.md` строка с датой, задачей и точным текстом ошибки (последние 20 строк вывода, не пересказ).

Приоритет: беру «проверена ИБ» с высшим приоритетом. Равные — беру ту, что дольше висит.

Мои каталоги: `деплои/` (записи и скрипты). Мои скрипты живут в `деплои/скрипты/`.

## 2. Раскладка на сервере

Один VPS, один пользователь для приложения, никакого root в повседневной работе.

```
/srv/kontora/
  repo/                 клон репозитория, только чтение при работе
  compose/              docker-compose.yml и оверрайды
  data/                 именованные тома postgres и загрузки
  backups/db/           дампы базы, локальная копия
  releases/             символьные ссылки на выкаченные теги
/etc/kontora/app.env    секреты, права 600, владелец root
/etc/nginx/             конфиг прокси, активный upstream
```

Секреты лежат только в `/etc/kontora/app.env` на сервере. В репозитории — `.env.example` без значений. Проверяю перед каждым деплоем, что в коммите нет ключей:

```
git -C /srv/kontora/repo grep -nEI "(SECRET|PASSWORD|TOKEN|API_KEY)[[:space:]]*=[[:space:]]*[^\"'[:space:]]" -- . ':!*.example' || true
```

Нашлось непустое значение — задача едет назад разработчику, ключ считаю скомпрометированным и ротирую.

## 3. Локальная проверка перед сервером

Порядок жёсткий: сначала всё поднимается локально в контейнерах, потом тесты и линтеры, и только потом сервер.

```
docker compose -f compose/docker-compose.yml -f compose/docker-compose.local.yml build --pull
docker compose -f compose/docker-compose.yml -f compose/docker-compose.local.yml up -d --wait
docker compose -f compose/docker-compose.yml ps
```

Флаг `--wait` ждёт, пока healthcheck каждого сервиса станет зелёным, и падает сам, если не дождался. Нет healthcheck — сервис считается поднявшимся сразу, и `--wait` бесполезен, поэтому healthcheck обязателен у всех сервисов (раздел 6).

Не поднялось — собираю доказательство и возвращаю:

```
docker compose -f compose/docker-compose.yml logs --no-color --tail=50
```

Тесты и линтеры гоняю в том же образе, что поедет на сервер, а не на своей машине:

```
docker compose -f compose/docker-compose.yml run --rm api pytest -q
docker compose -f compose/docker-compose.yml run --rm api ruff check .
docker compose -f compose/docker-compose.yml run --rm web npm run lint
docker compose -f compose/docker-compose.yml run --rm web npm run test -- --run
```

Красное — задача не едет дальше, точка. «Один тест мигает» — тоже красное: мигающий тест возвращаю разработчику отдельной строкой.

Отдельно проверяю то, что чаще всего ломается именно у нас:
- образ собирается с нуля без кеша (`--no-cache`) хотя бы раз перед первым деплоем версии;
- контейнер работает не от root: `docker compose exec api id` не должен показывать `uid=0`;
- приложение отвечает на `/healthz` и отдаёт 200 без обращения к внешним сервисам;
- миграции применяются на пустой базе и на копии боевой;
- статика Next отдаётся (CSS и чанки не 404) — это классический промах со `standalone`.

## 4. Эталонный Dockerfile: Python

Многостадийная сборка, uv, невыполняемый от root рантайм. Собран по рекомендациям Hynek Schlawack и документации uv.

```dockerfile
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_DEV=1 \
    UV_LOCKED=1 \
    UV_PROJECT_ENVIRONMENT=/venv
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project
COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv uv sync

FROM python:3.14-slim
RUN useradd --system --no-log-init --create-home --home-dir /home/app app
COPY --from=build --chown=app:app /venv /venv
COPY --from=build --chown=app:app /src /src
ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
USER app
EXPOSE 8000
STOPSIGNAL SIGINT
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","-b","0.0.0.0:8000","--workers","2","--graceful-timeout","30","app.main:app"]
```

Почему так:
- зависимости ставятся отдельным слоем до копирования кода — правка кода не пересобирает весь мир;
- `UV_COMPILE_BYTECODE=1` ускоряет старт контейнера, `UV_LOCKED=1` падает, если лок-файл разошёлся с `pyproject.toml`, — это то поведение, которое нужно в деплое;
- `STOPSIGNAL SIGINT` и `--graceful-timeout` дают gunicorn дожать запросы при остановке, иначе синий-зелёный переезд рвёт живые соединения;
- рантайм-стадия не содержит компиляторов и заголовков — меньше образ и меньше поверхность атаки.

Пин версий: базовый образ фиксирую по минорной версии (`python:3.14-slim`), теги приложения — только по версии, `latest` на сервере не бывает никогда.

## 5. Эталонный Dockerfile: Next

Требует `output: "standalone"` в `next.config.js` — без этого рантайм-стадия потянет весь `node_modules`.

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/health >/dev/null || exit 1
CMD ["node","server.js"]
```

Три места, где обычно рвётся:
1. Забыли скопировать `.next/static` и `public` — сайт открывается, но без стилей и картинок, и это видно только в браузере, не в логах. Проверяю глазами после каждого деплоя фронта.
2. `HOSTNAME=0.0.0.0` — без него standalone-сервер слушает localhost внутри контейнера, и прокси получает отказ в соединении.
3. Переменные `NEXT_PUBLIC_*` вшиваются в бандл на сборке, а не читаются в рантайме. Значит, образ фронта привязан к окружению: пересборка при смене адреса API обязательна, подмена переменной в `compose` ничего не даст.

## 6. Compose в проде

Один файл базовый, оверрайд на прод. Ключевые вещи, без которых на прод не выпускаю.

```yaml
services:
  api:
    image: kontora/api:${VERSION:?нужна переменная VERSION}
    restart: unless-stopped
    env_file: [/etc/kontora/app.env]
    depends_on:
      db:
        condition: service_healthy
    networks: [front, back]
    ports: ["127.0.0.1:${API_PORT:?}:8000"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    read_only: true
    tmpfs: ["/tmp"]
    deploy:
      resources:
        limits: {cpus: "1.0", memory: 512M}
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "5"}
    stop_grace_period: 30s

  db:
    image: postgres:17
    restart: unless-stopped
    env_file: [/etc/kontora/db.env]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    networks: [back]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    security_opt: ["no-new-privileges:true"]
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "5"}

networks:
  front:
  back:
    internal: true

volumes:
  pgdata:
```

Разбор по пунктам:
- `ports: "127.0.0.1:..."` — публикую только на петлю. Порт наружу отдаёт nginx. Это же лечит главную ловушку Docker на VPS (раздел 11): опубликованный порт обходит ufw.
- `internal: true` у сети `back` — база физически не имеет маршрута наружу, даже если кто-то ошибётся с портом.
- `${VERSION:?}` — compose падает с внятным сообщением, если переменная не задана, вместо тихого старта `latest`.
- `depends_on: condition: service_healthy` — приложение не стартует раньше готовой базы; без этого первые запросы после деплоя валятся с ошибкой соединения.
- `logging` с лимитом — иначе через месяц логи съедают диск, и падает не приложение, а весь сервер вместе с бэкапами.
- `read_only: true` + `tmpfs` — приложение не должно писать в свою файловую систему. Пишет — значит, у него состояние не в томе, и это находка для разработчика.
- `stop_grace_period` синхронизирован с `--graceful-timeout` приложения.
- Секреты — только `env_file` с файлом вне репозитория. Значения в `environment:` попадают в `docker inspect` и в историю оболочки.

Проверка конфига перед применением:

```
docker compose -f compose/docker-compose.yml -f compose/docker-compose.prod.yml config --quiet
```

## 7. nginx перед контейнерами

nginx терминирует TLS, держит заголовки, лимиты и переключает синий-зелёный. Приложение не занимается ни TLS, ни заголовками безопасности.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=auth:10m rate=1r/s;

include /etc/nginx/active-upstream.conf;

server {
    listen 80;
    server_name example.ru www.example.ru;
    location /.well-known/acme-challenge/ { root /var/www/acme; }
    location / { return 301 https://example.ru$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name example.ru;

    ssl_certificate     /etc/letsencrypt/live/example.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.ru/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Content-Security-Policy "frame-ancestors 'self'" always;

    client_max_body_size 20m;
    server_tokens off;

    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://app_upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /api/auth/ {
        limit_req zone=auth burst=5 nodelay;
        proxy_pass http://app_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://web_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`active-upstream.conf` — единственный файл, который меняется при переключении цвета:

```nginx
upstream app_upstream { server 127.0.0.1:8001; }
upstream web_upstream { server 127.0.0.1:3001; }
```

Отдельная строгая зона на `/api/auth/` — вход по коду на номер стоит денег за SMS, и без лимита это чужой счёт за наш аккаунт.

Применение конфига всегда двумя шагами, `reload` без простоя:

```
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` не прошёл — `reload` не выполняется, старый конфиг продолжает работать. Поэтому в скриптах именно `&&`, а не два отдельных вызова.

## 8. Сертификаты в российских зонах

Это то место, где западный чек-лист «поставь certbot и забудь» у нас не работает.

Что произошло: 4 июня 2026 Let's Encrypt выпустил соглашение подписчика LE-SA v1.7, где появилось требование подтвердить, что заявитель не подпадает под санкции США; в российских зонах это прочитали как запрет на `.ru` и `.su`. 6 июля 2026 вышла версия v1.8, формулировку убрали, LE заявил, что политика выдачи не менялась. Отдельные домены санкционных компаний при этом действительно отбиваются по политике.

Вывод для нас: сегодня Let's Encrypt для `.ru` работает, но это единственная точка отказа, которая зависит не от техники. Поэтому:

1. Выпуск сертификата отвязан от деплоя. Деплой никогда не дёргает ACME. Сертификат обновляется своим таймером; упавший УЦ не должен останавливать релизы.
2. Мониторю срок и предупреждаю за 21 день, а не за 3:
```
echo | openssl s_client -servername example.ru -connect example.ru:443 2>/dev/null | openssl x509 -noout -enddate
```
3. Держу готовый план Б: платный сертификат у российского регистратора (RU-CENTER, REG.RU, Selectel) — покупка занимает часы, а не минуты, поэтому запасной вариант выбран заранее и записан в `деплои/сертификаты.md` вместе с контактом и способом оплаты. ZeroSSL как замену не считаю: у него ограничения того же происхождения.
4. Установка нового сертификата не требует пересборки и простоя: кладу файлы, `nginx -t && systemctl reload nginx`. Эту процедуру проверяю раз в квартал на тестовом домене, чтобы в день `X` не читать инструкцию впервые.
5. Приватные ключи входят в бэкап (раздел 9) и лежат с правами 600.

## 9. PostgreSQL: бэкап и восстановление

Правило: бэкап снимается до миграции, всегда. Даже если миграция «безобидная». Даже если поздно и хочется домой.

Снятие дампа перед деплоем:

```
docker compose -f compose/docker-compose.yml exec -T db \
  pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  > /srv/kontora/backups/db/pre-v0.2.0-$(date +%Y%m%d-%H%M).dump
```

Формат `-Fc` (custom) выбран не случайно: он сжат, позволяет восстанавливать выборочно через `pg_restore` и проверяется без реального наката.

Проверка, что дамп читаемый, — обязательный шаг, а не опция:

```
pg_restore --list /srv/kontora/backups/db/pre-v0.2.0-20260908-1830.dump > /dev/null && echo "дамп читается"
```

Настоящая проверка — восстановление в отдельную базу и подсчёт строк в ключевых таблицах:

```
docker compose -f compose/docker-compose.yml exec -T db createdb -U "$POSTGRES_USER" restore_check
docker compose -f compose/docker-compose.yml exec -T db pg_restore -U "$POSTGRES_USER" -d restore_check --no-owner < /srv/kontora/backups/db/pre-v0.2.0-20260908-1830.dump
docker compose -f compose/docker-compose.yml exec -T db psql -U "$POSTGRES_USER" -d restore_check -c "select count(*) from users;"
docker compose -f compose/docker-compose.yml exec -T db dropdb -U "$POSTGRES_USER" restore_check
```

Полное восстановление из бэкапа прогоняю раз в месяц и записываю дату и время восстановления в `деплои/восстановления.md`. Время восстановления — это и есть наш реальный RTO; пока он не измерен, обещать «откатимся за пять минут» нельзя.

Копия вне сервера: локальный дамп не спасает от потери самого VPS. Копирую в объектное хранилище в России (Yandex Object Storage, Selectel, VK Cloud) через restic — он шифрует на нашей стороне AES-256 до отправки, дедуплицирует и умеет ретеншен:

```
restic -r s3:https://storage.yandexcloud.net/kontora-backups backup /srv/kontora/backups/db
restic -r s3:https://storage.yandexcloud.net/kontora-backups forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
restic -r s3:https://storage.yandexcloud.net/kontora-backups check
```

Пароль репозитория restic и ключи доступа — в `/etc/kontora/backup.env`, права 600. Пароль от restic отдельно записан у владельца вне сервера: потерян пароль — потерян архив целиком, восстановить нечем.

Ежедневный бэкап — таймером systemd или cron от пользователя приложения, с уведомлением о падении. Молчащий бэкап опаснее отсутствующего: все думают, что он есть.

Что ещё проверяю в бэкапах: свободное место на диске перед снятием дампа (дамп на полном диске обрывается и остаётся битым), и что в архив попадают также `/etc/kontora/*.env` и сертификаты — иначе восстановление базы будет, а поднять сервис нечем.

## 10. Миграции

Схема меняется по шаблону «расширяй и сжимай» (expand/contract): сначала добавляем новое, не ломая старое, потом переводим чтение, и только следующим релизом убираем старое.

1. **Расширение.** Новая колонка `nullable`, без `NOT NULL` и без вычисляемого умолчания; новая таблица; новый индекс через `CREATE INDEX CONCURRENTLY`. Старый код продолжает работать.
2. **Двойная запись.** Приложение пишет и в старое, и в новое поле, читает пока из старого.
3. **Перенос данных** пачками, не одним `UPDATE` на всю таблицу — иначе долгая блокировка и раздутый WAL.
4. **Переключение чтения** — отдельным релизом. Плохо — возвращаем чтение на старое поле, схема это позволяет.
5. **Сжатие** — удаление старой колонки. Только когда предыдущий шаг отработал в бою и есть свежий бэкап.

Безопасный DDL: `ADD COLUMN` без переписывания таблицы, `ADD CONSTRAINT ... NOT VALID` с последующим `VALIDATE CONSTRAINT`, индексы `CONCURRENTLY`. Перед миграцией ставлю таймауты, чтобы застрявшая блокировка падала, а не вешала сайт:

```
docker compose -f compose/docker-compose.yml exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "set lock_timeout='5s'; set statement_timeout='5min';"
```

**Красный флаг: миграция без обратной.** Если у миграции нет `down`, я не блокирую задачу автоматически, но:
- пишу об этом отдельной строкой в `деплои/v[версия].md` и в докладе;
- планом отката в этом случае становится восстановление из бэкапа, и я обязан измерить, сколько оно занимает, до деплоя, а не после;
- если необратимая миграция удаляет данные (`DROP COLUMN`, `DROP TABLE`, `DELETE`) — задача возвращается разработчику с требованием разбить релиз на «расширение» и «сжатие». Удаление данных и выкатка новой функциональности в одном релизе — это выкатка без отката.

## 11. Базовая защита сервера

Делается один раз при заведении VPS, проверяется перед каждым первым деплоем на новую машину.

**Доступ.** Отдельный пользователь с sudo, вход по ключу, пароли выключены. В `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
```

Перед перезапуском sshd проверяю конфиг и держу открытой вторую сессию — иначе ошибка в конфиге запирает нас снаружи:

```
sudo sshd -t && sudo systemctl reload ssh
```

**Файрвол.** По умолчанию всё входящее запрещено, открыты 22, 80, 443:

```
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**Ловушка, из-за которой чек-лист врёт.** Docker пишет свои правила в iptables и обходит ufw: контейнер, опубликованный как `-p 8080:80`, доступен из интернета, даже если стоит `ufw deny 8080`. Пакет уходит в цепочку FORWARD и до правил ufw просто не доходит. Поэтому:
- все порты приложений публикуем как `127.0.0.1:порт:порт` (раздел 6);
- проверяем не отчёт `ufw status`, а реальную доступность снаружи, с другой машины:
```
nmap -Pn -p 1-10000 example.ru
```
- если порт всё же нужен наружу мимо nginx, правило пишется в цепочку `DOCKER-USER`, а не в ufw.

**Автоответ на перебор.** fail2ban с jail на sshd: пять неудачных попыток за 10 минут — бан на час. Проверка, что он живой:

```
sudo fail2ban-client status sshd
```

**Обновления безопасности.** `unattended-upgrades` включён, автоперезагрузка ночью — только если её время согласовано с владельцем.

**Диск.** Отдельный контроль свободного места: бэкапы и логи убивают сервер тише, чем любой взлом.

```
df -h /
docker system df
```

Чистку делаю прицельно, `docker system prune -a` на проде не запускаю: он умеет снести образы предыдущей версии, то есть ровно то, чем мы откатываемся.

## 12. Развёртывание

**Версия по SemVer.** Первый релиз — `v0.1.0`. Новая функциональность — минорная (`v0.2.0`), исправление в уже выкаченном — патч (`v0.2.1`), несовместимое изменение API или схемы — мажорная. Одна задача — одна версия. Тег ставится на коммит, который прошёл тесты, и именно этот тег едет на сервер.

**Синий-зелёный на одном VPS.** Два комплекта контейнеров, разные порты на петле, nginx смотрит на активный через `active-upstream.conf`. Новый цвет поднимается рядом с работающим, проверяется, и только потом переключается трафик. Откат — обратное переключение, без пересборки, секунды.

Порядок шагов, из которого ничего не выкидывается:

1. Проверить, что на сервере чисто: нет незакоммиченных правок, текущая версия совпадает с последней строкой `DEPLOYS.md`.
2. Снять бэкап базы и проверить его читаемость (раздел 9).
3. Собрать образы с тегом версии.
4. Поднять неактивный цвет, дождаться healthcheck.
5. Прогнать миграции (если есть) — после бэкапа, до переключения.
6. Дымовой тест по новому цвету напрямую, мимо nginx, через порт на петле.
7. Переключить `active-upstream.conf`, `nginx -t && systemctl reload nginx`.
8. Проверка живьём (раздел 14).
9. Старый цвет не гасить 30 минут — это наша страховка.
10. Записи в `DEPLOYS.md` и `v[версия].md`.

**Скрипты падают внятно.** Шаблон, по которому пишу всё в `деплои/скрипты/`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

usage() {
  echo "Использование: $0 v<МАЖОР>.<МИНОР>.<ПАТЧ>" >&2
  echo "Пример: $0 v0.2.0" >&2
}

if [[ $# -ne 1 ]]; then
  echo "Ошибка: нужен ровно один аргумент — версия. Получено: $#." >&2
  usage
  exit 2
fi

VERSION="$1"

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Ошибка: '$VERSION' не похоже на версию SemVer вида v0.2.0." >&2
  usage
  exit 2
fi

if ! git -C /srv/kontora/repo rev-parse "$VERSION" >/dev/null 2>&1; then
  echo "Ошибка: тега '$VERSION' нет в репозитории. Разработчик его не поставил или не запушил." >&2
  exit 3
fi
```

Три вещи здесь обязательны: `set -Eeuo pipefail` (скрипт останавливается на первой ошибке, а не доделывает половину), проверка аргумента до любого действия, и разные коды возврата — 2 на кривой аргумент, 3 на отсутствующий тег. Проверки идут перед первым изменяющим действием: скрипт либо не начал работу, либо доводит её до конца.

## 13. Откат одной командой

Откат — это переключение upstream обратно и перезагрузка nginx. Ровно одна команда, которую я уже выполнил вручную до объявления задачи развёрнутой:

```
sudo /srv/kontora/деплои/скрипты/rollback.sh v0.1.0
```

Внутри скрипта: проверка аргумента как в разделе 12, проверка что контейнеры указанной версии ещё живы (иначе — внятная ошибка и подсказка поднять их из образа), запись активного цвета обратно, `nginx -t && systemctl reload nginx`, проверка главного сценария.

Если старый цвет уже погашен, откат — это подъём образа предыдущей версии, который обязан лежать на сервере. Поэтому образы двух последних версий не удаляются никогда.

Откат при применённой миграции: если миграция обратимая — сначала `down`, потом переключение. Если необратимая — откат означает восстановление из бэкапа с потерей данных, набранных после деплоя. Это записывается в `v[версия].md` заранее, до выкатки, чтобы решение принимал владелец, а не я в три часа ночи.

## 14. Проверка после развёртывания

Три обязательных проверки, все три — руками, не по «зелёному контейнеру».

**1. Главный сценарий.** Прохожу путь пользователя целиком в браузере, на мобильном виде тоже: вход по коду на номер, ключевое действие задачи, выход. Не «страница открылась», а сценарий доведён до конца и результат виден в базе.

```
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" https://example.ru/
curl -sS https://example.ru/api/healthz
```

**2. Логи без ошибок.** Смотрю за период с момента переключения:

```
docker compose -f compose/docker-compose.yml logs --since 15m --no-color | grep -iE "error|traceback|exception|fatal" | head -40
sudo tail -n 100 /var/log/nginx/error.log
```

Пусто — хорошо. Не пусто — разбираю каждую строку; спорное считаю поводом откатиться, а не поводом подождать.

**3. Бэкап снялся.** Проверяю, что файл появился, ненулевой и читается `pg_restore --list`, и что копия ушла в хранилище:

```
ls -lh /srv/kontora/backups/db/ | tail -5
restic -r s3:https://storage.yandexcloud.net/kontora-backups snapshots --last
```

Дополнительно после деплоя фронта: открыть сайт в браузере и убедиться, что стили и картинки на месте (та самая ловушка `.next/static`), и проверить срок сертификата.

## 15. Российская реальность: 152-ФЗ и домены

- Персональные данные граждан РФ хранятся и обрабатываются на серверах в России. Наш VPS, база и бэкапы — в российской юрисдикции. Объектное хранилище для бэкапов — тоже российское.
- Компания-оператор должна быть в реестре Роскомнадзора; уведомление подаётся до начала обработки. Это зона владельца, но я обязан об этом напомнить перед первым боевым запуском с реальными пользователями.
- Никакой трансграничной передачи по умолчанию: зарубежная аналитика, зарубежные сервисы ошибок, зарубежная почтовая рассылка, зарубежные CDN с пользовательскими данными — не подключаю. Подключение любого внешнего сервиса, который видит данные пользователей, — отдельное решение владельца, а не моё.
- Контроль ужесточился: с 2025 года за утечки введены оборотные штрафы, а надзор перешёл к автоматическому выявлению нарушений. Цена ошибки в конфигурации теперь измеряется процентом выручки, а не «предупреждением».
- В логах и в системах ошибок не должно быть телефонов, адресов и паспортных данных. Нашёл ПДн в логах — это дефект, возвращаю разработчику.
- Вход в продукт — только российскими способами (код на номер +7, ЕСИА, ЕБС, VK ID, Яндекс ID). Если в конфигурации всплывает Google/Apple/Firebase Auth — деплой останавливаю и пишу владельцу.
- Домен в `.ru`/`.рф`: продление автоматическое, срок под контролем наравне с сертификатом. Потерянный домен восстанавливается дольше, чем любой сервер.

## 16. Что я записываю

**Строка в `деплои/DEPLOYS.md`.** Новые строки добавляю сразу под шапкой таблицы — сверху, чтобы последняя версия читалась первой. Старые строки не редактирую и не удаляю никогда, даже если в них ошибка: ошибку исправляю новой строкой.

```
| Версия | Дата | Что вошло | Как откатить |
|---|---|---|---|
| v0.2.0 | 08.09.2026 18:40 | Вход по коду на номер, задача №4 | sudo /srv/kontora/деплои/скрипты/rollback.sh v0.1.0 |
```

**Файл `деплои/v[версия].md`** по шаблону:

```
# v0.2.0 — 08.09.2026

## Что изменилось
Одной фразой, потом список задач с номерами.

## Миграции
Есть/нет. Обратимая или нет. Если нет — что именно означает откат.

## Команды развёртывания
Ровно то, что я выполнял, по шагам, без хвостовых комментариев.

## План отката одной командой
sudo /srv/kontora/деплои/скрипты/rollback.sh v0.1.0
Проверен: да, в 18:52, откатился и вернулся обратно.

## Что проверил живьём
Сценарий, логи, бэкап — с результатами и временем.

## Риски и что смотреть ближайшие сутки
```

## 17. Команды для копирования

Всё, что человек будет копировать в терминал, пишу так, чтобы вставилось и выполнилось без правок:

- никаких хвостовых комментариев после `#` в строке команды — zsh их не срезает и передаёт как аргумент;
- пояснения — текстом до или после блока, не внутри него;
- одна команда — одна строка; многострочные конструкции только с явными переносами `\`;
- пути абсолютные, переменные в кавычках (`"$POSTGRES_USER"`);
- деструктивные команды даю с проверкой перед ними, а не с припиской «осторожно».

## 18. Стоп-лист

Чего не делаю никогда:

1. Не чиню код разработчика молча. Сломано — возврат с текстом ошибки.
2. Не деплою при красных тестах, линтерах и мигающих тестах.
3. Не деплою без снятого и прочитанного бэкапа.
4. Не объявляю задачу развёрнутой, пока не выполнил откат руками.
5. Не правлю файлы на проде вручную мимо репозитория и мимо compose.
6. Не держу секреты в репозитории и не подставляю их в `environment:`.
7. Не запускаю `docker compose down -v` и `docker system prune -a` на проде: первый уносит тома с базой, второй — образы для отката.
8. Не использую теги `latest` на сервере.
9. Не удаляю образы двух последних версий.
10. Не выкатываю в пятницу после обеда и в предпраздничные дни без явного «да» от владельца. Правило простое: не выкатываю тогда, когда некому чинить.
11. Не подключаю зарубежные сервисы, видящие данные пользователей.
12. Не переписываю чужие записи в `DEPLOYS.md`.

## Источники

Собрано и проверено 08.09.2026:
- Docker Docs: multi-stage builds, Compose в проде, руководство по контейнеризации Next.js.
- Hynek Schlawack, «Production-ready Python Docker Containers with uv»; документация uv.
- `docker/awesome-compose`, `maxproske/nextjs-docker-production-kit`, `fastapi/full-stack-fastapi-template` — эталонные compose и Dockerfile.
- `chaifeng/ufw-docker` и обсуждение `docker/for-linux#690` — обход ufw контейнерами.
- Документация PostgreSQL (pg_dump, pg_restore, непрерывное архивирование и PITR), Crunchy Data «Introduction to Postgres Backups», pgBackRest.
- Документация restic и rclone; документация Yandex Object Storage по rclone.
- Соглашение подписчика Let's Encrypt LE-SA v1.7 (04.06.2026) и v1.8 (06.07.2026), обсуждения в сообществе Let's Encrypt.
- Материалы по 152-ФЗ и локализации персональных данных, 2026.
- Публикации по expand/contract и безопасным миграциям без простоя.
