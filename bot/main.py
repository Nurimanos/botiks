"""Telegram-бот информирования о мероприятиях бизнес-сообщества «Эквиум».

Возможности:
  * Подписчики общаются с ботом только через кнопки русифицированного главного меню:
      - Об Эквиум (ссылка на сайт)
      - О мероприятиях (кнопки-ссылки отдельно на каждое мероприятие)
      - Связаться с координатором (номер телефона + кнопка «Написать сообщение»)
      - Стать участником сообщества (готовая ссылка на Google-форму)
  * Администраторы (предустановленные телеграм-аккаунты из ADMIN_USER_IDS):
      - добавляют / редактируют / удаляют мероприятия в формате «название + ссылка»;
        сразу после добавления нового мероприятия всем подписчикам рассылается уведомление;
      - добавляют участников по номеру телефона (приглашение активируется, когда
        человек напишет боту — он становится подписчиком и получает уведомления);
      - просматривают список участников.
  * Любой пользователь может подписаться самостоятельно по ссылке на бота (/start).

Запуск:
    BOT_TOKEN=... ADMIN_USER_IDS=... python bot/main.py
"""

import logging
import re
from html import escape

from telegram import LinkPreviewOptions, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import keyboards
import storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ------------------------------ Утилиты -----------------------------------

def normalize_phone(raw: str) -> str:
    """Приводит номер телефона к виду +79991234567 (только цифры, с ведущим +)."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


def is_valid_phone(phone: str) -> bool:
    return bool(phone) and 10 <= len(re.sub(r"\D", "", phone)) <= 15


def is_url(url: str) -> bool:
    return bool(re.match(r"^https?://\S+$", (url or "").strip()))


def ensure_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Регистрирует пользователя как подписчика, если он ещё не зарегистрирован.

    Возвращает True, если пользователь новый (нужно отправить приветствие).
    Если телефон пользователя совпадает с приглашением от администратора —
    участник засчитывается как добавленный администратором.
    """
    user = update.effective_user
    if not user:
        return False
    phone = None
    # Телефон из контактного сообщения (если пользователь поделился контактом)
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if getattr(msg, "contact", None) and msg.contact.phone_number:
        phone = normalize_phone(msg.contact.phone_number)
    added_by = "self"
    if phone and storage.phone_is_invited(phone):
        storage.consume_phone_invite(phone)
        added_by = "admin"
    return storage.register_new_subscriber(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        phone=phone,
        added_by=added_by,
    )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет актуальное главное меню (администратору или подписчику)."""
    user = update.effective_user
    text = (
        f"👋 Привет, <b>{escape(user.full_name or '')}</b>!\n\n"
        "Это бот мероприятий бизнес-сообщества <b>Эквиум</b>.\n"
        "Выберите пункт меню:"
    )
    keyboard = (
        keyboards.admin_main_keyboard()
        if config.is_admin(user.id)
        else keyboards.main_menu_keyboard()
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


async def notify_all_subscribers(context: ContextTypes.DEFAULT_TYPE,
                                 title: str, url: str) -> tuple[int, int]:
    """Рассылает уведомление о новом мероприятии всем подписчикам.

    Возвращает (sent, failed). Неактивные (заблокировавших бота) удаляет из базы.
    """
    msg = (
        "🔔 <b>Новое мероприятие!</b>\n\n"
        f"📌 <b>{escape(title)}</b>\n"
        f'🔗 <a href="{escape(url)}">Перейти к мероприятию</a>\n\n'
        f'Все события — в разделе «{escape(config.MENU_TITLES["events"])}» бота.'
    )
    sent, failed = 0, 0
    for uid in storage.all_subscriber_ids():
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=msg,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить уведомление %s: %s", uid, exc)
            failed += 1
            storage.remove_subscriber(uid)
    return sent, failed


# ------------------------------- Команды ----------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — самостоятельная подписка по ссылке и показ главного меню."""
    # Подсказка поделиться контактом — только для приглашённых администратором по номеру
    _pn = getattr(update.effective_user, "phone_number", None)
    invited = bool(_pn) and storage.phone_is_invited(normalize_phone(_pn))
    if update.message and invited:
        await update.message.reply_text(
            "💡 Если вас пригласил администратор по номеру телефона — поделитесь контактом:",
            reply_markup=keyboards.share_contact_keyboard(),
        )
    is_new = ensure_subscriber(update, context)
    if is_new:
        await update.message.reply_text(
            "🎉 Вы подписаны на уведомления о мероприятиях сообщества Эквиум! "
            "Мы напишем вам, как только появится новое событие."
        )
    await send_main_menu(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = [
        "Доступные команды:",
        "/start — главное меню бота",
        "/help — эта справка",
    ]
    if config.is_admin(update.effective_user.id):
        lines += [
            "/events — список мероприятий",
            "/admin — панель администратора",
            "/cancel — отменить текущее действие",
        ]
    await update.message.reply_text("\n".join(lines))


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администраторам.")
        return
    events = storage.all_events()
    if not events:
        await update.message.reply_text("Мероприятий пока нет.")
        return
    lines = ["📅 <b>Мероприятия:</b>"]
    for ev in events:
        lines.append(f'{ev.id}. <a href="{escape(ev.url)}">{escape(ev.title)}</a>')
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав администратора.")
        return
    await update.message.reply_text(
        "🛠 Панель администратора:", reply_markup=keyboards.admin_main_keyboard()
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администраторам.")
        return
    context.chat_data.pop("flow", None)
    context.chat_data.pop("pending_event", None)
    context.chat_data.pop("edit_event_id", None)
    await update.message.reply_text(
        "❌ Действие отменено.", reply_markup=keyboards.admin_main_keyboard()
    )


# --------------------------- Кнопки главного меню --------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ensure_subscriber(update, context)
    data = query.data or ""
    admin = config.is_admin(query.from_user.id)

    if data == "menu:main":
        await query.answer()
        await send_main_menu(update, context)

    elif data == "menu:about":
        await query.answer()
        await query.message.reply_text(
            "🏢 <b>Об Эквиум</b>\n\n"
            f'Подробнее о сообществе — на сайте: <a href="{escape(config.ABOUT_URL)}">'
            f"{escape(config.ABOUT_URL)}</a>",
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=keyboards.back_to_menu_keyboard(),
        )

    elif data == "menu:events":
        await query.answer()
        await query.message.reply_text(
            "📅 <b>О мероприятиях</b>\n\n"
            "Актуальные события сообщества — по кнопкам ниже:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.events_keyboard(),
        )

    elif data == "menu:coordinator":
        await query.answer()
        await query.message.reply_text(
            "🤝 <b>Связаться с координатором</b>\n\n"
            f"📞 Телефон: <code>{escape(config.COORDINATOR_PHONE)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.coordinator_keyboard(),
        )

    elif data == "menu:join":
        await query.answer()
        if config.JOIN_FORM_URL:
            await query.message.reply_text(
                "✅ <b>Стать участником сообщества</b>\n\n"
                'Заполните анкету по ссылке: '
                f'<a href="{escape(config.JOIN_FORM_URL)}">перейти к анкете</a>',
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=keyboards.back_to_menu_keyboard(),
            )
        else:
            await query.message.reply_text(
                "Ссылка на форму пока не настроена. Обратитесь к координатору.",
                reply_markup=keyboards.back_to_menu_keyboard(),
            )

    elif data == "noop":
        await query.answer("Нет действий 🙂")

    elif data.startswith("admin:"):
        if not admin:
            await query.answer("Недостаточно прав.", show_alert=True)
            return
        await handle_admin_callback(update, context)

    else:
        await query.answer()


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "main":
        await query.answer()
        await query.message.reply_text(
            "🛠 Панель администратора:", reply_markup=keyboards.admin_main_keyboard()
        )

    elif action == "events":
        await query.answer()
        await query.message.reply_text(
            "🗂 <b>Управление меню «О мероприятиях»</b>\n\n"
            "Кнопка-ссылка ведёт на мероприятие, ✏️ — изменить, 🗑 — удалить прошедшее.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.admin_events_keyboard(),
        )

    elif action == "add_event":
        await query.answer()
        await start_add_event(update, context)

    elif action == "edit":
        await query.answer()
        await start_edit_event(update, context, int(parts[2]))

    elif action == "del":
        event_id = int(parts[2])
        events = {e.id: e for e in storage.all_events()}
        ev = events.get(event_id)
        if not ev:
            await query.answer("Мероприятие уже удалено.", show_alert=True)
            return
        await query.answer()
        await query.message.reply_text(
            f"Удалить мероприятие «{ev.title}»?",
            reply_markup=keyboards.confirm_delete_keyboard(event_id),
        )

    elif action == "del_yes":
        event_id = int(parts[2])
        if storage.delete_event(event_id):
            await query.answer("Удалено ✅")
        else:
            await query.answer("Мероприятие уже удалено.", show_alert=True)
        await query.message.reply_text(
            "🗂 Управление меню «О мероприятиях»:",
            reply_markup=keyboards.admin_events_keyboard(),
        )

    elif action == "subscribers":
        await query.answer()
        count = storage.subscriber_count()
        await query.message.reply_text(
            f"👥 Подписчиков в базе: <b>{count}</b>.\n"
            "Именно им рассылаются уведомления о новых мероприятиях.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.admin_main_keyboard(),
        )

    elif action == "add_phone":
        await query.answer()
        context.chat_data["flow"] = "add_phone"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "📞 Отправьте номер телефона участника, например: +7 900 123-45-67\n"
                "(для отмены — /cancel)"
            ),
        )


# ------------------------- Диалоги ввода у администратора -------------------

async def start_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data["flow"] = "add_event_title"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "➕ <b>Новое мероприятие</b>\n\n"
            "Шаг 1. Введите название мероприятия.\n"
            "(для отмены — /cancel)"
        ),
        parse_mode=ParseMode.HTML,
    )


async def start_edit_event(update: Update, context: ContextTypes.DEFAULT_TYPE,
                           event_id: int) -> None:
    events = {e.id: e for e in storage.all_events()}
    ev = events.get(event_id)
    if not ev:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Мероприятие не найдено."
        )
        return
    context.chat_data["flow"] = "edit_event"
    context.chat_data["edit_event_id"] = event_id
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"✏️ Изменение мероприятия #{event_id}\n"
            f"Текущее название: <b>{escape(ev.title)}</b>\n"
            f"Текущая ссылка: <code>{escape(ev.url)}</code>\n\n"
            "Отправьте новое значение в формате «название | ссылка»\n"
            "или только название / только ссылку. Для отмены — /cancel",
        ),
        parse_mode=ParseMode.HTML,
    )


async def create_event_and_notify(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  title: str, url: str) -> None:
    """Сохраняет мероприятие и сразу рассылает уведомление всем подписчикам."""
    ev = storage.add_event(title, url)
    sent, failed = await notify_all_subscribers(context, title, url)
    status = (
        f"✅ Мероприятие №{ev.id} «{title}» добавлено в меню «О мероприятиях».\n"
        f"📣 Уведомления отправлены: {sent}"
    )
    if failed:
        status += f", недоступны (удалены из базы): {failed}"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=status,
        reply_markup=keyboards.admin_events_keyboard(),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения: для подписчиков — подсказка про меню,
    для администраторов — шаги диалогов добавления/редактирования."""
    # Пользователь поделился контактом — регистрируем с телефоном
    if update.effective_message and update.effective_message.contact:
        await update.effective_message.reply_text(
            "OK", reply_markup=ReplyKeyboardRemove()
        )
        phone = normalize_phone(update.effective_message.contact.phone_number)
        user = update.effective_user
        added_by = "self"
        if phone and storage.phone_is_invited(phone):
            storage.consume_phone_invite(phone)
            added_by = "admin"
        is_new = storage.register_new_subscriber(
            user_id=user.id, username=user.username, full_name=user.full_name,
            phone=phone, added_by=added_by,
        )
        if is_new:
            await update.message.reply_text(
                "🎉 Вы подписаны на уведомления о мероприятиях сообщества Эквиум!"
            )
        else:
            await update.message.reply_text("Контакт сохранён 👍")
        await send_main_menu(update, context)
        return

    if not config.is_admin(update.effective_user.id):
        # Подписчики сообщения не отправляют — перенаправляем в меню
        ensure_subscriber(update, context)
        await update.message.reply_text(
            "Пожалуйста, пользуйтесь кнопками главного меню 📋",
            reply_markup=keyboards.main_menu_keyboard(),
        )
        return

    flow = context.chat_data.get("flow")
    text = (update.message.text or "").strip()

    if not flow:
        await update.message.reply_text(
            "Чтобы управлять мероприятиями, откройте панель администратора:",
            reply_markup=keyboards.admin_main_keyboard(),
        )
        return

    if flow == "add_phone":
        phone = normalize_phone(text)
        if not is_valid_phone(phone):
            await update.message.reply_text(
                "⚠️ Похоже, это некорректный номер. Попробуйте ещё раз, "
                "например: +7 900 123-45-67\n(для отмены — /cancel)"
            )
            return
        is_new = storage.add_phone_invite(phone, update.effective_user.id)
        context.chat_data.pop("flow", None)
        if is_new:
            await update.message.reply_text(
                f"✅ Номер <code>{escape(phone)}</code> добавлен в участники.\n\n"
                "Как только человек с этим номером начнёт общение с ботом (нажмёт /start), "
                "он автоматически получит приветствие и будет получать уведомления "
                "о мероприятиях.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.admin_main_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"Номер <code>{escape(phone)}</code> уже был добавлен ранее.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.admin_main_keyboard(),
            )
        return

    if flow == "add_event_title":
        if len(text) > 200:
            await update.message.reply_text(
                "⚠️ Название слишком длинное (максимум 200 символов). Попробуйте ещё раз."
            )
            return
        context.chat_data["pending_event"] = {"title": text}
        context.chat_data["flow"] = "add_event_url"
        await update.message.reply_text(
            "Шаг 2. Отправьте ссылку на мероприятие "
            "(начинается с http:// или https://)\n(для отмены — /cancel)"
        )
        return

    if flow == "add_event_url":
        if not is_url(text):
            await update.message.reply_text(
                "⚠️ Ссылка должна начинаться с http:// или https://. Попробуйте ещё раз.\n"
                "(для отмены — /cancel)"
            )
            return
        pending = context.chat_data.pop("pending_event", {})
        context.chat_data.pop("flow", None)
        title = pending.get("title", text)
        await create_event_and_notify(update, context, title, text)
        return

    if flow == "edit_event":
        event_id = context.chat_data.get("edit_event_id")
        if not event_id:
            context.chat_data.pop("flow", None)
            return
        if "|" in text:
            new_title, new_url = (p.strip() for p in text.split("|", 1))
            if new_url and not is_url(new_url):
                await update.message.reply_text(
                    "⚠️ Некорректная ссылка. Попробуйте ещё раз.\n(для отмены — /cancel)"
                )
                return
            storage.update_event(event_id, new_title or None, new_url or None)
        elif is_url(text):
            storage.update_event(event_id, url=text)
        else:
            storage.update_event(event_id, title=text[:200])
        context.chat_data.pop("flow", None)
        context.chat_data.pop("edit_event_id", None)
        await update.message.reply_text(
            "✅ Мероприятие обновлено.",
            reply_markup=keyboards.admin_events_keyboard(),
        )
        return


# ------------------------------ Сборка приложения ---------------------------

def build_application(token: str) -> Application:
    storage.init_db()
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
    application.add_handler(CommandHandler("events", cmd_events))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.CONTACT, on_text))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return application


async def _post_init(application: Application) -> None:
    from telegram import BotCommand

    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Справка"),
        BotCommand("events", "Список мероприятий (админ)"),
        BotCommand("admin", "Панель администратора"),
        BotCommand("cancel", "Отменить текущее действие (админ)"),
    ])
    logger.info("Бот запущен. Предустановленных администраторов: %d",
                len(config.ADMIN_USER_IDS))


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "ERROR: не задан BOT_TOKEN. Скопируйте .env.example в .env и заполните значения."
        )
    if not config.ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS пуст — никто не сможет управлять мероприятиями!")

    app = build_application(config.BOT_TOKEN)
    app.post_init = _post_init
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
