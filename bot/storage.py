"""Хранилище данных бота на SQLite.

Таблицы:
    subscribers  — подписчики, которым рассылаются уведомления
    events       — мероприятия (название + ссылка)
    phone_invites — приглашения по номеру телефона от администратора
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from config import DB_PATH

_lock = threading.Lock()


@dataclass
class Event:
    id: int
    title: str
    url: str
    created_at: str


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                phone       TEXT,
                added_by    TEXT DEFAULT 'self',      -- self | admin
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                url         TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phone_invites (
                phone       TEXT PRIMARY KEY,
                invited_by  INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------ Подписчики ------------------------------

def subscriber_exists(user_id: int) -> bool:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM subscribers WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row is not None


def register_new_subscriber(user_id: int, username: str | None, full_name: str | None,
                            phone: str | None = None, added_by: str = "self") -> bool:
    """Атомарно добавляет подписчика, возвращает True если это новый подписчик."""
    with _lock, get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM subscribers WHERE user_id = ?", (user_id,)
        ).fetchone()
        if exists:
            conn.execute(
                """UPDATE subscribers SET username=?, full_name=?,
                          phone=COALESCE(?, phone) WHERE user_id=?""",
                (username, full_name, phone, user_id),
            )
            return False
        conn.execute(
            """INSERT INTO subscribers (user_id, username, full_name, phone, added_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, full_name, phone, added_by, _now()),
        )
        return True


def all_subscriber_ids() -> list[int]:
    with _lock, get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM subscribers").fetchall()
    return [r["user_id"] for r in rows]


def subscriber_count() -> int:
    with _lock, get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM subscribers").fetchone()
    return row["c"]


def remove_subscriber(user_id: int) -> bool:
    with _lock, get_conn() as conn:
        cur = conn.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
        deleted = cur.rowcount > 0
    return deleted


# ------------------------------ Мероприятия ------------------------------

def add_event(title: str, url: str) -> Event:
    ts = _now()
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (title, url, created_at) VALUES (?, ?, ?)",
            (title, url, ts),
        )
        last_id = cur.lastrowid
    return Event(id=last_id, title=title, url=url, created_at=ts)


def all_events() -> list[Event]:
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, url, created_at FROM events ORDER BY id"
        ).fetchall()
    return [Event(r["id"], r["title"], r["url"], r["created_at"]) for r in rows]


def delete_event(event_id: int) -> bool:
    with _lock, get_conn() as conn:
        cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        deleted = cur.rowcount > 0
    return deleted


def update_event(event_id: int, title: str | None = None, url: str | None = None) -> bool:
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "UPDATE events SET title=COALESCE(?, title), url=COALESCE(?, url) WHERE id = ?",
            (title, url, event_id),
        )
        updated = cur.rowcount > 0
    return updated


# ---------------------- Приглашения по номеру телефона ----------------------

def add_phone_invite(phone: str, admin_id: int) -> bool:
    """Добавляет номер телефона в список приглашённых. True — если номер новый."""
    with _lock, get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM phone_invites WHERE phone = ?", (phone,)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO phone_invites (phone, invited_by, created_at) VALUES (?, ?, ?)",
            (phone, admin_id, _now()),
        )
        return True


def phone_is_invited(phone: str) -> bool:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM phone_invites WHERE phone = ?", (phone,)
        ).fetchone()
    return row is not None


def consume_phone_invite(phone: str) -> None:
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM phone_invites WHERE phone = ?", (phone,))
