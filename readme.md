# Telegram бот-органайзер приема лекарств

Бот напоминает о приеме лекарств по расписанию, а затем через 30 минут уточняет, выпито ли лекарство.
Если пользователь нажимает "Нет", бот повторяет напоминание через 15 минут.

## Функции

- Русскоязычный интерфейс.
- Меню-кнопки:
	- `Добавить лекарство`
	- `Посмотреть лекарства`
	- `Редактировать лекарства` (удаление лекарства)
- Ежедневные напоминания в заданное время.
- Повторный вопрос через 30 минут: "Ты выпил лекарство?"
- Кнопки ответа: `Да` или `Нет (напомнить через 15 минут)`.
- Сохранение данных в SQLite (`data/medications.db`).

## Структура

- `bot/main.py` - запуск и обработчики команд/кнопок.
- `bot/db.py` - работа с SQLite.
- `bot/scheduler.py` - фоновый планировщик напоминаний.
- `bot/keyboards.py` - клавиатуры.
- `bot/states.py` - состояния добавления лекарства.

## Быстрый запуск локально

1. Установите Python 3.12+.
2. Создайте файл `.env` по примеру `.env.example`.
3. Установите зависимости:

```bash
pip install -r requirements.txt
```

4. Запустите бота:

```bash
python -m bot.main
```

## Переменные окружения

- `BOT_TOKEN` - токен Telegram-бота (обязательно).
- `BOT_TIMEZONE` - таймзона для расписания, например `Europe/Moscow`.

## Запуск в Docker (для 24/7 на VM)

1. Создайте `.env`.
2. Запустите:

```bash
docker compose up -d --build
```

3. Проверка логов:

```bash
docker compose logs -f
```

4. Остановка:

```bash
docker compose down
```

Контейнер настроен с `restart: always`, поэтому после перезапуска VM бот поднимется автоматически.

## CI/CD на GitHub Actions (self-hosted)

В проект добавлен workflow: `.github/workflows/ci-cd-self-hosted.yml`.

Что делает пайплайн:

- На каждый push в `main` и при ручном запуске (`workflow_dispatch`) запускает CI.
- Проверяет конфиг `docker compose config`.
- Собирает образ `docker compose build`.
- Выполняет деплой `docker compose up -d --build` на self-hosted runner.

### Какие secrets добавить в GitHub

В репозитории: `Settings -> Secrets and variables -> Actions`:

- `BOT_TOKEN` - токен Telegram-бота.
- `BOT_TIMEZONE` - например `Europe/Moscow`.

### Установка self-hosted runner на VM (Linux)

Пример команд (выполняются на VM под отдельным пользователем, не под root):

```bash
mkdir -p actions-runner && cd actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/canibeaieng/organaizer-pills-bot --token <RUNNER_TOKEN>
sudo ./svc.sh install
sudo ./svc.sh start
```

`RUNNER_TOKEN` берется в GitHub: `Repository -> Settings -> Actions -> Runners -> New self-hosted runner`.
