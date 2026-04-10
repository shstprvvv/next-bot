# Деплой

Минимальный deploy flow в проекте теперь такой:

1. Локально запушить изменения в GitHub.
2. На сервере выполнить одну команду: `make deploy`
3. При необходимости смотреть `make logs-api` или `make logs-bot`

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

## Обновление проекта

После `git push` локальных изменений:

```bash
ssh root@your-server
cd ~/next-bot
make deploy
```

Что делает `make deploy`:
- выполняет `git pull --ff-only`
- пересобирает контейнеры через Docker Compose
- ждет успешный ответ от `http://localhost:8080/health`
- показывает статус контейнеров

Если healthcheck не прошел, скрипт выводит последние логи `api`.

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
