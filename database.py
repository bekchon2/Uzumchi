import aiosqlite
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "uzum_bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Users jadval — multi-shop uchun shop_ids JSON sifatida saqlanadi
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                lang        TEXT DEFAULT 'ru',
                api_key     TEXT,
                shop_id     INTEGER DEFAULT 0,
                shop_name   TEXT DEFAULT '',
                shop_ids    TEXT DEFAULT '[]',
                active_shop_id INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                notif_type  TEXT,
                sent_at     INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        # Raqib narx kuzatuv jadval
        await db.execute("""
            CREATE TABLE IF NOT EXISTS competitor_tracking (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                shop_id     INTEGER,
                product_name TEXT,
                my_price    REAL,
                added_at    INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        await db.commit()

        # Eski DB ustunlarini qo'shish (migration)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN shop_ids TEXT DEFAULT '[]'")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN active_shop_id INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

    logger.info(f"Database initialized: {DB_PATH}")


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int, username: str | None = None, lang: str = "ru"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, lang)
            VALUES (?, ?, ?)
            """,
            (user_id, username, lang),
        )
        await db.commit()


async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id)
        )
        await db.commit()


async def set_user_api_key(user_id: int, api_key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET api_key = ? WHERE user_id = ?", (api_key, user_id)
        )
        await db.commit()


async def set_user_shop(user_id: int, shop_id: int, shop_name: str):
    import json
    async with aiosqlite.connect(DB_PATH) as db:
        # Asosiy shop ni set qilish
        await db.execute(
            "UPDATE users SET shop_id = ?, shop_name = ?, active_shop_id = ? WHERE user_id = ?",
            (shop_id, shop_name, shop_id, user_id),
        )
        await db.commit()


async def set_active_shop(user_id: int, shop_id: int, shop_name: str):
    """Multi-shop: faol do'konni almashtirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET active_shop_id = ?, shop_id = ?, shop_name = ? WHERE user_id = ?",
            (shop_id, shop_id, shop_name, user_id),
        )
        await db.commit()


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE api_key IS NOT NULL AND shop_id != 0"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ─── Notification log ─────────────────────────────────────────────────────────

async def log_notification(user_id: int, notif_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO notification_log (user_id, notif_type) VALUES (?, ?)",
            (user_id, notif_type),
        )
        await db.commit()


async def was_notified_today(user_id: int, notif_type: str) -> bool:
    """Bugun shu turdagi xabar yuborilganmi?"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT 1 FROM notification_log
            WHERE user_id = ? AND notif_type = ?
              AND sent_at >= strftime('%s', 'now', 'start of day')
            LIMIT 1
            """,
            (user_id, notif_type),
        ) as cursor:
            return await cursor.fetchone() is not None


# ─── Competitor tracking ───────────────────────────────────────────────────────

async def add_competitor_tracking(user_id: int, shop_id: int, product_name: str, my_price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        # Bir xil mahsulot ikki marta qo'shilmasin
        await db.execute(
            "DELETE FROM competitor_tracking WHERE user_id=? AND shop_id=? AND product_name=?",
            (user_id, shop_id, product_name)
        )
        await db.execute(
            "INSERT INTO competitor_tracking (user_id, shop_id, product_name, my_price) VALUES (?,?,?,?)",
            (user_id, shop_id, product_name, my_price)
        )
        await db.commit()


async def get_competitor_tracking(user_id: int, shop_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM competitor_tracking WHERE user_id=? AND shop_id=? ORDER BY added_at DESC",
            (user_id, shop_id)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_competitor_tracking(tracking_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM competitor_tracking WHERE id=? AND user_id=?",
            (tracking_id, user_id)
        )
        await db.commit()
