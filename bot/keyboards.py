"""Русифицированное главное меню и клавиатуры бота."""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import config
import storage


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню подписчика (кнопки-команды)."""
    rows = [
        [InlineKeyboardButton(config.MENU_TITLES["about"], callback_data="menu:about")],
        [InlineKeyboardButton(config.MENU_TITLES["events"], callback_data="menu:events")],
        [InlineKeyboardButton(
            config.MENU_TITLES["coordinator"], callback_data="menu:coordinator"
        )],
        [InlineKeyboardButton(config.MENU_TITLES["join"], callback_data="menu:join")],
    ]
    return InlineKeyboardMarkup(rows)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ В главное меню", callback_data="menu:main")]]
    )


def events_keyboard() -> InlineKeyboardMarkup:
    """Меню «О мероприятиях»: отдельная кнопка-ссылка на каждое мероприятие."""
    rows: list[list[InlineKeyboardButton]] = []
    for ev in storage.all_events():
        rows.append([InlineKeyboardButton(ev.title, url=ev.url)])
    if not rows:
        rows.append([InlineKeyboardButton("Сейчас мероприятий нет", callback_data="noop")])
    rows.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def coordinator_keyboard() -> InlineKeyboardMarkup:
    """Меню «Связаться с координатором»: кнопка «Написать сообщение» + возврат в меню.

    Номер телефона показывается в тексте сообщения; кнопка ведёт на личный чат
    координатора (если задан COORDINATOR_USERNAME), иначе копирует номер телефона.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if config.COORDINATOR_USERNAME:
        rows.append([InlineKeyboardButton(
            "📩 Написать сообщение",
            url=f"https://t.me/{config.COORDINATOR_USERNAME}",
        )])
    else:
        rows.append([InlineKeyboardButton(
            "📋 Скопировать номер телефона", copy_text=config.COORDINATOR_PHONE
        )])
    rows.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def share_contact_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопкой шаринга контакта (для самоподписки по телефону)."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить мой контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_request=True,
    )


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню администратора."""
    rows = [
        [InlineKeyboardButton("🗂 Меню «О мероприятиях»", callback_data="admin:events")],
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data="admin:add_event")],
        [InlineKeyboardButton("➕ Добавить участника по телефону",
                              callback_data="admin:add_phone")],
        [InlineKeyboardButton("👥 Список участников", callback_data="admin:subscribers")],
        [InlineKeyboardButton("ℹ️ Обычное меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_events_keyboard() -> InlineKeyboardMarkup:
    """Управление меню «О мероприятиях»: кнопки-ссылки + удаление/редактирование."""
    rows: list[list[InlineKeyboardButton]] = []
    events = storage.all_events()
    for ev in events:
        rows.append([InlineKeyboardButton(ev.title, url=ev.url)])
        rows.append([
            InlineKeyboardButton(f"✏️ Изменить #{ev.id}", callback_data=f"admin:edit:{ev.id}"),
            InlineKeyboardButton(f"🗑 Удалить #{ev.id}", callback_data=f"admin:del:{ev.id}"),
        ])
    if not events:
        rows.append([InlineKeyboardButton("Мероприятий пока нет", callback_data="noop")])
    rows.append([InlineKeyboardButton("➕ Добавить мероприятие", callback_data="admin:add_event")])
    rows.append([InlineKeyboardButton("⬅️ В меню администратора", callback_data="admin:main")])
    return InlineKeyboardMarkup(rows)


def confirm_delete_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin:del_yes:{event_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="admin:events")],
    ])
