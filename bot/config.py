"""Конфигурация бота. Все значения берутся из переменных окружения (.env).

Пример .env:

    BOT_TOKEN=123456:ABC-DEF...
    ADMIN_USER_IDS=11111111,22222222        # предустановленные телеграм-аккаунты администраторов
    COORDINATOR_PHONE=+79001234567
    COORDINATOR_USERNAME=coordinator_nick   # опционально, для кнопки "Написать сообщение"
    ABOUT_URL=https://equium.ru
    JOIN_FORM_URL=https://docs.google.com/forms/d/e/1FAIpQL.../viewform
"""

import os


def _parse_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return ids


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Предустановленные администраторы (телеграм user id)
ADMIN_USER_IDS: set[int] = _parse_ids(os.environ.get("ADMIN_USER_IDS", ""))

# Настройки меню
ABOUT_URL = os.environ.get("ABOUT_URL", "https://equium.ru")
COORDINATOR_PHONE = os.environ.get("COORDINATOR_PHONE", "+79000000000")
COORDINATOR_USERNAME = os.environ.get("COORDINATOR_USERNAME", "")  # может быть пустым
JOIN_FORM_URL = os.environ.get("JOIN_FORM_URL", "")

# Путь к файлу базы данных SQLite
DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")
)

# Русифицированные названия пунктов главного меню
MENU_TITLES = {
    "about": "Об Эквиум",
    "events": "О мероприятиях",
    "coordinator": "Связаться с координатором",
    "join": "Стать участником сообщества",
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS
