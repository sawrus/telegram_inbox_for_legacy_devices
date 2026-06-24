# Развёртывание на Orange Pi Zero 2

## 1. Подготовка Ubuntu ARM

Обновите систему:

```bash
sudo apt update
sudo apt upgrade -y
```

Установите Git и Docker:

```bash
sudo apt install -y git ca-certificates curl gnupg
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Перезайдите по SSH или перезагрузите Orange Pi, чтобы группа `docker` применилась.

## 2. Клонирование проекта

```bash
git clone <repo-url>
cd test_codex
```

## 3. Настройка переменных

```bash
cp .env.example .env
nano .env
```

Укажите реальные `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` из <https://my.telegram.org>.

## 4. Первичная авторизация Telegram

```bash
docker compose run --rm telegram-inbox python scripts/init_telegram_session.py
```

Введите номер телефона, код из Telegram и пароль двухфакторной аутентификации, если он включён.

## 5. Запуск сервиса

```bash
docker compose up -d --build
```

Проверьте статус:

```bash
docker compose ps
docker compose logs -f
```

## 6. Открытие сайта

Узнайте IP Orange Pi:

```bash
hostname -I
```

Откройте на iPad Safari:

```text
http://<orange-pi-ip>:8080
```

## 7. Обновление после git pull

```bash
git pull
docker compose up -d --build
```
