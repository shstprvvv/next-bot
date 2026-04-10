# Деплой

В проекте теперь есть 2 рабочих режима деплоя:

1. Минимальный: сервер сам пересобирает контейнеры.
2. Средний: GitHub собирает Docker image, а сервер только делает `pull` и перезапуск.

## Подготовка сервера

Убедитесь, что на сервере установлены:
- `git`
- `docker`
- `docker-compose` или `docker compose`
- `curl`

Пример для Ubuntu:

```bash
apt update
apt install -y git docker.io docker-compose curl
```

## Первый запуск

```bash
git clone <repo-url> next-bot
cd next-bot
cp .env.example .env
```

Заполните `.env`, затем выполните:

```bash
docker-compose up -d --build
```

## Минимальный flow

После `git push` локальных изменений:

```bash
ssh root@your-server
cd ~/next-bot
make deploy
```

Что делает `make deploy`:
- выполняет `git pull --ff-only`
- пересобирает контейнеры через Docker Compose, если `APP_IMAGE` не задан
- ждет успешный ответ от `http://localhost:8080/health`
- показывает статус контейнеров

Если healthcheck не прошел, скрипт выводит последние логи `api`.

## Средний flow

### Что уже настроено в проекте

- GitHub Actions после успешных тестов и линта собирает Docker image
- образ публикуется в `ghcr.io/<github-user>/next-bot-app`
- если на сервере задан `APP_IMAGE`, `make deploy` переключается с локальной сборки на `docker pull`

### Что сделать один раз

1. Войти в GHCR на сервере:

```bash
docker login ghcr.io
```

2. Добавить в серверный `.env`:

```env
APP_IMAGE=ghcr.io/<your-github-user>/next-bot-app:latest
```

После этого обычный деплой не меняется:

```bash
cd ~/next-bot
make deploy
```

В этом режиме `make deploy`:
- делает `git pull --ff-only`
- скачивает свежий image через `docker-compose pull api bot`
- запускает контейнеры без сборки на проде
- проверяет `/health`

## Полезные команды

```bash
make status
make health
make logs
make logs-api
make logs-bot
make build
make restart
```

## Ручной fallback

Если нужен старый ручной сценарий:

```bash
git pull --ff-only
docker-compose up -d --build
curl http://localhost:8080/health
```
