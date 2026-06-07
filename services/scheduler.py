"""
APScheduler — avtomatik vazifalar jadvali.
Toshkent vaqti: UTC+5
"""
import asyncio
import logging
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from database import get_all_users, log_notification, was_notified_today
from services.uzum_api import (
    get_fbs_orders, get_invoices, get_returns,
    get_products, summarize_orders, _days_ago_ms, _now_ms
)
from services.storage_tracker import parse_invoices, get_storage_alerts

logger = logging.getLogger(__name__)

TASHKENT = pytz.timezone("Asia/Tashkent")

# Delivered buyurtmalarni xotiraga saqlash (restart da tozalanadi)
_seen_delivered: dict[int, set] = {}  # user_id → set of order_ids


def start_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TASHKENT)

    # 08:00 Toshkent — Ertalabki hisobot
    scheduler.add_job(
        run_morning_reports,
        CronTrigger(hour=8, minute=0, timezone=TASHKENT),
        args=[bot],
        id="morning_reports",
        replace_existing=True,
    )

    # Har 4 soat — Ombor ogohlantirishlari
    scheduler.add_job(
        run_storage_alerts,
        IntervalTrigger(hours=4),
        args=[bot],
        id="storage_alerts",
        replace_existing=True,
    )

    # Har 10 daqiqa — Delivered tekshiruv
    scheduler.add_job(
        run_delivered_check,
        IntervalTrigger(minutes=10),
        args=[bot],
        id="delivered_check",
        replace_existing=True,
    )

    # 09:00 va 18:00 — Reyting tekshiruv
    scheduler.add_job(
        run_rating_check,
        CronTrigger(hour=9, minute=0, timezone=TASHKENT),
        args=[bot],
        id="rating_check_morning",
        replace_existing=True,
    )
    scheduler.add_job(
        run_rating_check,
        CronTrigger(hour=18, minute=0, timezone=TASHKENT),
        args=[bot],
        id="rating_check_evening",
        replace_existing=True,
    )

    # 09:30 — Tovar tugash prognozi
    scheduler.add_job(
        run_forecast_check,
        CronTrigger(hour=9, minute=30, timezone=TASHKENT),
        args=[bot],
        id="forecast_check",
        replace_existing=True,
    )

    # Har 30 daqiqa — Yangi qaytarmalar
    scheduler.add_job(
        run_returns_check,
        IntervalTrigger(minutes=30),
        args=[bot],
        id="returns_check",
        replace_existing=True,
    )

    return scheduler


# ─── Ertalabki hisobot ────────────────────────────────────────────────────────

async def run_morning_reports(bot):
    users = await get_all_users()
    for user in users:
        try:
            notif_key = "morning_report"
            if await was_notified_today(user["user_id"], notif_key):
                continue

            api_key = user["api_key"]
            shop_id = user["shop_id"]
            lang = user.get("lang", "ru")

            orders = await get_fbs_orders(api_key, date_from=_days_ago_ms(1))
            stats = summarize_orders(orders)

            invoices = await get_invoices(api_key, shop_id)
            storage_items = parse_invoices(invoices)
            alerts = get_storage_alerts(storage_items)

            if lang == "uz":
                text = (
                    f"🌅 <b>Ertalabki hisobot</b>\n\n"
                    f"📦 Kecha buyurtmalar: <b>{stats['total']}</b>\n"
                    f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                    f"❌ Bekor qilindi: <b>{stats['cancelled']}</b>\n"
                    f"💰 Tushum: <b>{stats['revenue']:,.0f} so'm</b>\n\n"
                    f"🏭 Ombor holati:\n"
                    f"  💸 Pullik saqlash: {len(alerts['paid'])} ta\n"
                    f"  🚨 Xavfli: {len(alerts['alert'])} ta\n"
                    f"  ⚠️ Ogohlantirish: {len(alerts['warn'])} ta\n"
                    f"  ✅ Yaxshi: {len(alerts['ok'])} ta"
                )
            else:
                text = (
                    f"🌅 <b>Утренний отчёт</b>\n\n"
                    f"📦 Заказов вчера: <b>{stats['total']}</b>\n"
                    f"✅ Доставлено: <b>{stats['delivered']}</b>\n"
                    f"❌ Отменено: <b>{stats['cancelled']}</b>\n"
                    f"💰 Выручка: <b>{stats['revenue']:,.0f} сум</b>\n\n"
                    f"🏭 Состояние склада:\n"
                    f"  💸 Платное хранение: {len(alerts['paid'])} шт.\n"
                    f"  🚨 Критично: {len(alerts['alert'])} шт.\n"
                    f"  ⚠️ Предупреждение: {len(alerts['warn'])} шт.\n"
                    f"  ✅ Норма: {len(alerts['ok'])} шт."
                )

            await bot.send_message(user["user_id"], text, parse_mode="HTML")
            await log_notification(user["user_id"], notif_key)
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Morning report error for user {user['user_id']}: {e}")


# ─── Ombor ogohlantirishlari ──────────────────────────────────────────────────

async def run_storage_alerts(bot):
    users = await get_all_users()
    for user in users:
        try:
            api_key = user["api_key"]
            shop_id = user["shop_id"]
            lang = user.get("lang", "ru")

            invoices = await get_invoices(api_key, shop_id)
            storage_items = parse_invoices(invoices)
            alerts = get_storage_alerts(storage_items)

            critical = alerts["paid"] + alerts["alert"]
            if not critical:
                continue

            lines = []
            for item in critical:
                icon = "💸" if item.days_stored >= 60 else "🚨"
                notif_key = f"storage_{icon}_{item.invoice_id}"
                if await was_notified_today(user["user_id"], notif_key):
                    continue
                if lang == "uz":
                    lines.append(
                        f"{icon} Nakładnoy #{item.invoice_number}: "
                        f"{item.days_stored} kun saqlangan, {item.total_accepted} dona"
                    )
                else:
                    lines.append(
                        f"{icon} Накладная #{item.invoice_number}: "
                        f"хранится {item.days_stored} дн., {item.total_accepted} шт."
                    )
                await log_notification(user["user_id"], notif_key)

            if lines:
                header = "🚨 <b>Ombor ogohlantirishi!</b>\n\n" if lang == "uz" else "🚨 <b>Внимание: склад!</b>\n\n"
                await bot.send_message(
                    user["user_id"],
                    header + "\n".join(lines),
                    parse_mode="HTML"
                )
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Storage alert error for user {user['user_id']}: {e}")


# ─── Delivered tekshiruv ──────────────────────────────────────────────────────

async def run_delivered_check(bot):
    users = await get_all_users()
    for user in users:
        try:
            uid = user["user_id"]
            api_key = user["api_key"]
            lang = user.get("lang", "ru")

            orders = await get_fbs_orders(api_key, date_from=_days_ago_ms(3))
            delivered_ids = {
                str(o.get("id", ""))
                for o in orders
                if o.get("status") == "DELIVERED"
            }

            if uid not in _seen_delivered:
                # Birinchi tekshirish — mavjudlarni saqla, xabar yuborme
                _seen_delivered[uid] = delivered_ids
                continue

            new_delivered = delivered_ids - _seen_delivered[uid]
            _seen_delivered[uid] = delivered_ids

            if new_delivered:
                count = len(new_delivered)
                if lang == "uz":
                    text = f"✅ <b>{count} ta buyurtma yetkazildi!</b>\nHaridor tovarni qabul qildi."
                else:
                    text = f"✅ <b>{count} заказ(ов) доставлено!</b>\nПокупатель получил товар."
                await bot.send_message(uid, text, parse_mode="HTML")

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Delivered check error for user {user['user_id']}: {e}")


# ─── Reyting tekshiruv ────────────────────────────────────────────────────────

async def run_rating_check(bot):
    users = await get_all_users()
    for user in users:
        try:
            api_key = user["api_key"]
            lang = user.get("lang", "ru")

            from services.uzum_api import get_shops
            shops = await get_shops(api_key)
            for shop in shops:
                rating = shop.get("rating", 5.0) or 5.0
                if float(rating) < 4.5:
                    if lang == "uz":
                        text = (
                            f"⭐ <b>Do'kon reytingi past!</b>\n"
                            f"Do'kon: {shop.get('name', '—')}\n"
                            f"Reyting: <b>{rating}</b> / 5.0\n"
                            f"Iltimos, mijozlar shikoyatlarini ko'rib chiqing."
                        )
                    else:
                        text = (
                            f"⭐ <b>Рейтинг магазина низкий!</b>\n"
                            f"Магазин: {shop.get('name', '—')}\n"
                            f"Рейтинг: <b>{rating}</b> / 5.0\n"
                            f"Пожалуйста, проверьте жалобы покупателей."
                        )
                    await bot.send_message(user["user_id"], text, parse_mode="HTML")

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Rating check error for user {user['user_id']}: {e}")


# ─── Tovar tugash prognozi ────────────────────────────────────────────────────

async def run_forecast_check(bot):
    users = await get_all_users()
    for user in users:
        try:
            api_key = user["api_key"]
            shop_id = user["shop_id"]
            lang = user.get("lang", "ru")

            products = await get_products(api_key, shop_id)
            warnings = []

            for p in products:
                for sku in p.get("skuList", []):
                    days_left = sku.get("forecastOutOfStock", 999)
                    if days_left is None:
                        continue
                    try:
                        days_left = int(days_left)
                    except (ValueError, TypeError):
                        continue

                    if days_left <= 14:
                        icon = "🚨" if days_left <= 3 else ("⚠️" if days_left <= 7 else "📉")
                        name = p.get("title", p.get("name", "—"))[:40]
                        if lang == "uz":
                            warnings.append(f"{icon} {name}: {days_left} kun qoldi")
                        else:
                            warnings.append(f"{icon} {name}: осталось {days_left} дн.")

            if warnings:
                if lang == "uz":
                    header = "📉 <b>Tovar tugash ogohlantirishilari:</b>\n\n"
                else:
                    header = "📉 <b>Предупреждение о заканчивающихся товарах:</b>\n\n"
                await bot.send_message(
                    user["user_id"],
                    header + "\n".join(warnings[:20]),
                    parse_mode="HTML"
                )

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Forecast check error for user {user['user_id']}: {e}")


# ─── Qaytarmalar tekshiruv ────────────────────────────────────────────────────

async def run_returns_check(bot):
    users = await get_all_users()
    for user in users:
        try:
            uid = user["user_id"]
            api_key = user["api_key"]
            lang = user.get("lang", "ru")

            returns = await get_returns(api_key, date_from=_days_ago_ms(1))
            if not returns:
                continue

            new_returns = []
            for r in returns:
                r_id = str(r.get("id", ""))
                notif_key = f"return_{r_id}"
                if not await was_notified_today(uid, notif_key):
                    new_returns.append(r)
                    await log_notification(uid, notif_key)

            if new_returns:
                count = len(new_returns)
                if lang == "uz":
                    text = (
                        f"↩️ <b>{count} ta yangi qaytarma!</b>\n"
                        f"Qaytarmalarni ko'rish uchun /start → Qaytarmalar"
                    )
                else:
                    text = (
                        f"↩️ <b>{count} новых возврата!</b>\n"
                        f"Для просмотра: /start → Возвраты"
                    )
                await bot.send_message(uid, text, parse_mode="HTML")

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Returns check error for user {user['user_id']}: {e}")
