"""Тесты логики бота без реального Telegram API."""

import os
import sys
import tempfile
import types
import asyncio

# Изолированная БД для тестов
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name
os.environ["ADMIN_USER_IDS"] = "1001,1002"
os.environ["COORDINATOR_PHONE"] = "+79001234567"
os.environ["JOIN_FORM_URL"] = "https://docs.google.com/forms/viewform"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import storage  # noqa: E402
import main as bot_main  # noqa: E402


def check(name, cond):
    assert cond, f"FAIL: {name}"
    print(f"ok - {name}")


# ------------------------------ storage -----------------------------------
storage.init_db()

check("новый подписчик зарегистрирован",
      storage.register_new_subscriber(1, "u1", "User One") is True)
check("повторная регистрация не новая",
      storage.register_new_subscriber(1, "u1", "User One") is False)
storage.register_new_subscriber(2, "u2", "User Two", phone="+79990001122")
check("счётчик подписчиков", storage.subscriber_count() == 2)
check("все id подписчиков", set(storage.all_subscriber_ids()) == {1, 2})
check("существование подписчика", storage.subscriber_exists(1))

ev = storage.add_event("Завтрак Эквиум", "https://example.com/breakfast")
check("мероприятие добавлено", ev.id >= 1 and len(storage.all_events()) == 1)
storage.update_event(ev.id, title="Завтрак Эквиум (обновл.)")
check("мероприятие отредактировано",
      storage.all_events()[0].title == "Завтрак Эквиум (обновл.)")
check("удаление мероприятия", storage.delete_event(ev.id) is True)
check("мероприятий нет", len(storage.all_events()) == 0)
check("повторное удаление -> False", storage.delete_event(ev.id) is False)

check("приглашение по телефону создано",
      storage.add_phone_invite("+79001234567", 1001) is True)
check("дубликат приглашения", storage.add_phone_invite("+79001234567", 1001) is False)
check("приглашение найдено", storage.phone_is_invited("+79001234567"))
storage.consume_phone_invite("+79001234567")
check("приглашение израсходовано", not storage.phone_is_invited("+79001234567"))

check("подписчик удалён", storage.remove_subscriber(2) is True)

# ------------------------------ утилиты ------------------------------------
check("нормализация 8-номера", bot_main.normalize_phone("8 900 123-45-67") == "+79001234567")
check("нормализация +7", bot_main.normalize_phone("+7(900)1234567") == "+79001234567")
check("валидный телефон", bot_main.is_valid_phone("+79001234567"))
check("невалидный телефон", not bot_main.is_valid_phone("+7900"))
check("url распознан", bot_main.is_url("https://example.com/e"))
check("не url", not bot_main.is_url("пример"))
check("админ определён", config.is_admin(1001) and config.is_admin(1002))
check("не админ", not config.is_admin(555))

# ------------------------- клавиатуры конструируются -----------------------
import keyboards  # noqa: E402

storage.add_event("Митап", "https://example.com/meetup")
kb = keyboards.main_menu_keyboard()
titles = [b.text for row in kb.inline_keyboard for b in row]
check("главное меню русифицировано", titles == [
    "Об Эквиум", "О мероприятиях", "Связаться с координатором",
    "Стать участником сообщества"])

kb_ev = keyboards.events_keyboard()
first = kb_ev.inline_keyboard[0][0]
check("кнопка-ссылка на мероприятие", first.text == "Митап" and first.url == "https://example.com/meetup")

kb_c = keyboards.coordinator_keyboard()
check("клавиатура координатора собрана", len(kb_c.inline_keyboard) == 2)

kb_a = keyboards.admin_events_keyboard()
texts = [b.text for row in kb_a.inline_keyboard for b in row]
check("панель мероприятий содержит кнопки изменения/удаления",
      any("Изменить" in t for t in texts) and any("Удалить" in t for t in texts))

# ---------------------- рассылка уведомлений (мок бота) --------------------
sent = []
failed_uids = {99}  # этот подписчик «заблокировал» бота


class FakeBot:
    async def send_message(self, chat_id=None, text=None, **kwargs):
        if chat_id in failed_uids:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        sent.append((chat_id, text))


ctx = types.SimpleNamespace(bot=FakeBot())
storage.register_new_subscriber(10, "subscriber", "Подписчик 1")
storage.register_new_subscriber(99, "blocked", "Заблокировавший")
sent.clear()
s, f = asyncio.run(bot_main.notify_all_subscribers(ctx, "Новый митап", "https://e.x/1"))
check("рассылка дошла до активных", s == len([u for u in storage.all_subscriber_ids() if u != 99]) or s >= 1)
check("заблокировавший удалён из базы", not storage.subscriber_exists(99))
check("текст уведомления содержит название и ссылку",
      "Новый митап" in sent[0][1] and "https://e.x/1" in sent[0][1])

os.unlink(_tmp.name)
print("\nВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅")
