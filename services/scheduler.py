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
from database import get_sku_snapshots, save_sku_snapshots
from services.uzum_api import (
    get_fbs_orders, get_invoices, get_returns,
    get_products, summarize_orders, _days_ago_ms, _now_ms,
    is_product_active, _get_sku_variant_name, calc_total_qty,
)
from services.storage_tracker import parse_invoices, get_storage_alerts
from locales.i18n import t
from utils.helpers import format_date, short_name, safe_float, safe_int

logger = logging.getLogger(__name__)

TASHKENT = pytz.timezone("Asia/Tashkent")

# Delivered buyurtmalarni xotiraga saqlash (restart da tozalanadi)
_seen_delivered: dict[int, set] = {}  # user_id → set of order_ids


def start_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TASHKENT)

    # 09:00 Toshkent — Kunlik mahsulot hisoboti (digest)
    scheduler.add_job(
        run_product_report,
        CronTrigger(hour=9, minute=0, timezone=TASHKENT),
        args=[bot],
        id="product_report_morning",
        replace_existing=True,
    )

    # Har 5 daqiqa — Sotuv tekshiruvi (per-SKU quantity-decrease detection)
    scheduler.add_job(
        run_sale_check,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="sale_check",
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

            text = (
                t("sched_morning_title", lang)
                + "\n\n"
                + t(
                    "sched_morning_body", lang,
                    total=stats["total"], delivered=stats["delivered"],
                    cancelled=stats["cancelled"], revenue=stats["revenue"],
                )
                + "\n\n"
                + t(
                    "sched_morning_storage", lang,
                    paid=len(alerts["paid"]), alert=len(alerts["alert"]),
                    warn=len(alerts["warn"]), ok=len(alerts["ok"]),
                )
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
                lines.append(
                    t(
                        "sched_storage_line", lang,
                        icon=icon, invoice_number=item.invoice_number,
                        days=item.days_stored, qty=item.total_accepted,
                    )
                )
                await log_notification(user["user_id"], notif_key)

            if lines:
                header = t("sched_storage_header", lang) + "\n\n"
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
            delivered_map = {
                str(o.get("id", "")): o
                for o in orders
                if o.get("status") == "DELIVERED"
            }
            delivered_ids = set(delivered_map.keys())

            if uid not in _seen_delivered:
                # Birinchi tekshirish — mavjudlarni saqla, xabar yuborme
                _seen_delivered[uid] = delivered_ids
                continue

            new_delivered = delivered_ids - _seen_delivered[uid]
            _seen_delivered[uid] = delivered_ids

            if new_delivered:
                count = len(new_delivered)
                text = t("sched_delivered", lang, count=count)

                # Yetkazilgan buyurtma sanasini format_date orqali ko'rsatish.
                # date_issued 0/None bo'lsa — o'tkazib yuboriladi (NameError yo'q).
                detail_lines = []
                for oid in list(new_delivered)[:10]:
                    o = delivered_map.get(oid, {})
                    ts = safe_int(
                        o.get("dateIssued") or o.get("date")
                        or o.get("completedDate") or 0
                    )
                    if not ts:
                        continue
                    name = short_name(
                        o.get("productTitle") or o.get("skuTitle")
                        or o.get("title") or "—", 35
                    )
                    detail_lines.append(
                        t(
                            "sched_delivered_detail", lang,
                            name=name,
                            sku=o.get("skuTitle") or "—",
                            price=safe_float(o.get("sellPrice") or o.get("finalPrice")
                                             or o.get("price") or 0),
                            commission=safe_float(o.get("commission")),
                            profit=safe_float(o.get("sellerProfit")),
                            date=format_date(ts),
                        )
                    )

                if detail_lines:
                    text += "\n\n" + "\n\n".join(detail_lines)

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
                    text = t(
                        "sched_rating", lang,
                        shop_name=shop.get("name", "—"), rating=rating,
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
                        warnings.append(
                            t("sched_forecast_line", lang,
                              icon=icon, name=name, days=days_left)
                        )

            if warnings:
                header = t("sched_forecast_header", lang) + "\n\n"
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
                text = t("sched_returns", lang, count=count)
                await bot.send_message(uid, text, parse_mode="HTML")

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Returns check error for user {user['user_id']}: {e}")



# ─── Kunlik mahsulot hisoboti (09:00) ─────────────────────────────────────────

# Hisobotga kiritiladigan eng shoshilinch (out + low) elementlar soni chegarasi.
PRODUCT_REPORT_MAX_ITEMS = 10
LOW_STOCK_THRESHOLD = 5


async def run_product_report(bot):
    """09:00 da har bir foydalanuvchiga aktiv katalog digestini yuborish.

    Kuniga bir marta (was_notified_today guard). Har bir foydalanuvchi try/except
    ichida — bittasi xato bersa qolganlari to'xtamaydi; sendlar asyncio.sleep bilan
    sekinlashtiriladi (Telegram rate-limit).
    """
    users = await get_all_users()
    for user in users:
        try:
            uid = user["user_id"]
            notif_key = "product_report"
            if await was_notified_today(uid, notif_key):
                continue

            api_key = user["api_key"]
            shop_id = user["shop_id"]
            lang = user.get("lang", "ru")

            products = await get_products(api_key, shop_id)
            active = [p for p in products if is_product_active(p)]

            total_active = len(active)
            total_stock = sum(calc_total_qty(p) for p in active)

            low_items = []   # qty <= 5 va > 0
            out_items = []   # qty == 0
            for p in active:
                qty = calc_total_qty(p)
                name = short_name(p.get("title") or p.get("name") or "—", 35)
                if qty == 0:
                    out_items.append((name, qty))
                elif qty <= LOW_STOCK_THRESHOLD:
                    low_items.append((name, qty))

            low_count = len(low_items)
            out_count = len(out_items)

            text = (
                t("product_report_title", lang)
                + "\n\n"
                + t(
                    "product_report_body", lang,
                    total_active=total_active, total_stock=total_stock,
                    low_count=low_count, out_count=out_count,
                )
            )

            # Eng shoshilinch elementlar: avval tugaganlar, keyin kam qolganlar.
            urgent = (out_items + low_items)[:PRODUCT_REPORT_MAX_ITEMS]
            if urgent:
                lines = [
                    t("product_report_item", lang, name=name, qty=qty)
                    for name, qty in urgent
                ]
                text += "\n\n" + "\n".join(lines)

            await bot.send_message(uid, text, parse_mode="HTML")
            await log_notification(uid, notif_key)
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Product report error for user {user['user_id']}: {e}")


# ─── Sotuv tekshiruvi (per-SKU quantity-decrease detection) ───────────────────

def _sku_id_of(sku: dict):
    """Return str sku id from skuId (preferred) else id; None if neither present."""
    sid = sku.get("skuId") or sku.get("id")
    return str(sid) if sid is not None else None


def build_current_map(active_products: list) -> dict:
    """Build {sku_id (str): quantityActive (int)} over active products' SKUs.

    SKUs with neither ``skuId`` nor ``id`` are skipped entirely.
    """
    current: dict[str, int] = {}
    for p in active_products:
        for sku in p.get("skuList", []) or []:
            sid = _sku_id_of(sku)
            if sid is None:
                continue
            current[sid] = int(sku.get("quantityActive") or 0)
    return current


def detect_sales(prev: dict, current: dict) -> list:
    """Return [(sku_id, sold, remaining)] for SKUs whose qty strictly DECREASED.

    A sale event is produced iff the sku is present in BOTH ``prev`` and ``current``
    and ``prev[sku] > current[sku]``. New SKUs (absent from ``prev``) and
    unchanged/increased quantities produce no event. ``sold`` is the positive delta
    (prev - current); ``remaining`` is the current quantity.
    """
    sales = []
    for sid, cur_qty in current.items():
        if sid in prev:
            delta = prev[sid] - cur_qty
            if delta > 0:
                sales.append((sid, delta, cur_qty))
    return sales


async def run_sale_check(bot):
    """Har 5 daqiqada: SKU qoldiq pasayishi orqali sotuvni aniqlash va push yuborish.

    Birinchi pass (snapshot bo'sh) — faqat baseline saqlanadi, push yo'q. Keyingi
    passlarda strict decrease aniqlanadi. Har bir pass oxirida current map saqlanadi.
    Har bir foydalanuvchi try/except ichida + asyncio.sleep bilan paced.
    """
    users = await get_all_users()
    for user in users:
        try:
            uid = user["user_id"]
            api_key = user["api_key"]
            shop_id = user["shop_id"]
            lang = user.get("lang", "ru")

            products = await get_products(api_key, shop_id)
            active = [p for p in products if is_product_active(p)]

            current = build_current_map(active)

            # sku_id -> (product_title, sku_dict) index — variant nomini render uchun.
            sku_index: dict[str, tuple] = {}
            for p in active:
                title = p.get("title") or p.get("name") or "—"
                for sku in p.get("skuList", []) or []:
                    sid = _sku_id_of(sku)
                    if sid is None:
                        continue
                    sku_index[sid] = (title, sku)

            prev = await get_sku_snapshots(uid, shop_id)

            if not prev:
                # Birinchi pass — baseline o'rnatiladi, push yo'q.
                await save_sku_snapshots(uid, shop_id, current)
                await asyncio.sleep(0.3)
                continue

            sales = detect_sales(prev, current)
            for sid, sold, remaining in sales:
                title, sku = sku_index.get(sid, ("—", {}))
                variant = _get_sku_variant_name(sku, lang) if sku else "—"
                text = (
                    t("sale_push_title", lang)
                    + "\n\n"
                    + t(
                        "sale_push_item", lang,
                        product=title, variant=variant,
                        sold=sold, remaining=remaining,
                    )
                )
                await bot.send_message(uid, text, parse_mode="HTML")
                await asyncio.sleep(0.3)

            # Har doim current snapshotni saqlaymiz.
            await save_sku_snapshots(uid, shop_id, current)
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Sale check error for user {user['user_id']}: {e}")
