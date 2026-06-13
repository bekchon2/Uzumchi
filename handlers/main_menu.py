"""
handlers/main_menu.py — Asosiy menyu.
Tugmalar: faqat mahsulotlar sahifasida Inline pagination bor, qolganlarida tugma yo'q.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from services.uzum_api import (
    get_products, get_fbs_orders, get_invoices,
    summarize_orders, calc_total_qty, format_product_skus,
    UzumAuthError, UzumAPIError,
    _days_ago_ms, _now_ms
)
from services.storage_tracker import parse_invoices, format_storage_report, get_storage_alerts
from services.competitor_monitor import get_product_prices, format_competitor_report
from locales.i18n import t
from utils.keyboards import (
    main_menu_keyboard, settings_keyboard,
    back_keyboard, products_nav_keyboard, competitor_keyboard
)
from utils.helpers import (
    safe_float, safe_int, short_name,
    format_price, order_status_icon, chunk_list
)

logger = logging.getLogger(__name__)
router = Router()

PRODUCTS_PER_PAGE = 5  # SKU ko'rsatish uchun kamroq sahifada


class CompetitorStates(StatesGroup):
    waiting_product_name = State()


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_user_or_warn(message: Message) -> dict | None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key") or not user.get("shop_id"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return None
    return user


async def _edit_or_answer(msg, message: Message, text: str, kb=None, parse_mode="HTML"):
    """edit_text yoki answer — xato bo'lmaydi."""
    try:
        if kb:
            await msg.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
        else:
            await msg.edit_text(text, parse_mode=parse_mode)
    except Exception:
        if kb:
            await message.answer(text, reply_markup=kb, parse_mode=parse_mode)
        else:
            await message.answer(text, parse_mode=parse_mode)


# ─── Mahsulotlar ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📦 Mahsulotlarim", "📦 Мои товары"]))
async def cmd_products(message: Message, state: FSMContext):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")
    await _show_products_page(message, msg, user, lang, page=1)


async def _show_products_page(message: Message, msg, user: dict, lang: str, page: int = 1):
    try:
        products = await get_products(user["api_key"], user["shop_id"])
        if not products:
            await _edit_or_answer(msg, message, t("no_data", lang))
            return

        total_products = len(products)

        # Jami qoldiqni barcha SKU lar bo'yicha hisoblash
        total_qty = sum(calc_total_qty(p) for p in products)

        pages = chunk_list(products, PRODUCTS_PER_PAGE)
        total_pages = len(pages)
        page = max(1, min(page, total_pages))
        page_products = pages[page - 1]

        header = (
            f"📦 <b>Mahsulotlarim</b> ({total_products} xil | jami {total_qty} dona):"
            if lang == "uz" else
            f"📦 <b>Мои товары</b> ({total_products} видов | всего {total_qty} шт.):"
        )

        lines = [header]
        for p in page_products:
            lines.append("")
            lines.append(format_product_skus(p, lang))

        text = "\n".join(lines)
        kb = products_nav_keyboard(page, total_pages, lang)
        await _edit_or_answer(msg, message, text, kb=kb)

    except Exception as e:
        logger.error(f"Products error: {e}")
        await _edit_or_answer(msg, message,
            f"❌ <b>Xato:</b> <code>{str(e)[:200]}</code>" if lang == "uz"
            else f"❌ <b>Ошибка:</b> <code>{str(e)[:200]}</code>"
        )


@router.callback_query(F.data.startswith("products_page_"))
async def products_pagination(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    lang = user.get("lang", "ru")
    await _show_products_page(callback.message, callback.message, user, lang, page=page)
    await callback.answer()


@router.callback_query(F.data == "products_noop")
async def products_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "products_back")
async def products_back(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
    )
    await callback.answer()


# ─── Buyurtmalar ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["🛒 Buyurtmalar", "🛒 Заказы"]))
async def cmd_orders(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        orders = await get_fbs_orders(user["api_key"], date_from=_days_ago_ms(1))
        stats = summarize_orders(orders)

        if lang == "uz":
            text = (
                f"🛒 <b>Buyurtmalar</b> (so'nggi 24 soat)\n\n"
                f"📊 Jami: <b>{stats['total']}</b>\n"
                f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                f"🔄 Jarayonda: <b>{stats['processing']}</b>\n"
                f"🚚 Yo'lda: <b>{stats['shipped']}</b>\n"
                f"❌ Bekor: <b>{stats['cancelled']}</b>\n"
                f"💰 Tushum: <b>{stats['revenue']:,.0f} so'm</b>"
            )
        else:
            text = (
                f"🛒 <b>Заказы</b> (последние 24 часа)\n\n"
                f"📊 Всего: <b>{stats['total']}</b>\n"
                f"✅ Доставлено: <b>{stats['delivered']}</b>\n"
                f"🔄 В обработке: <b>{stats['processing']}</b>\n"
                f"🚚 В пути: <b>{stats['shipped']}</b>\n"
                f"❌ Отменено: <b>{stats['cancelled']}</b>\n"
                f"💰 Выручка: <b>{stats['revenue']:,.0f} сум</b>"
            )

        if orders:
            text += "\n\n<b>" + ("So'nggi buyurtmalar:" if lang == "uz" else "Последние заказы:") + "</b>"
            for o in orders[:15]:
                status = o.get("status", "—")
                icon = order_status_icon(status)
                order_id = o.get("id", "—")
                price = safe_float(o.get("finalPrice") or o.get("price") or o.get("orderPrice") or 0)
                text += f"\n{icon} #{order_id} — {format_price(price, lang)}"

        # Tugmasiz — faqat matn
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Orders error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка заказов:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


# ─── Omborxona ────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["🏭 Ombor", "🏭 Склад"]))
async def cmd_storage(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        invoices = await get_invoices(user["api_key"], user["shop_id"])
        storage_items = parse_invoices(invoices)
        report = format_storage_report(storage_items, lang)
        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Storage error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка склада:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


# ─── Bugungi hisobot ──────────────────────────────────────────────────────────

@router.message(F.text.in_(["📊 Hisobot", "📊 Отчёт"]))
async def cmd_report_today(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        orders = await get_fbs_orders(user["api_key"], date_from=_days_ago_ms(1))
        stats = summarize_orders(orders)
        products = await get_products(user["api_key"], user["shop_id"])
        invoices = await get_invoices(user["api_key"], user["shop_id"])
        storage_items = parse_invoices(invoices)
        alerts = get_storage_alerts(storage_items)

        total_products = len(products)
        # Barcha SKU lar bo'yicha to'g'ri qoldiq
        total_qty = sum(calc_total_qty(p) for p in products)

        low_stock = []
        out_of_stock = []
        for p in products:
            name = short_name(p.get("title") or p.get("name") or "—", 30)
            qty = calc_total_qty(p)
            if qty == 0:
                out_of_stock.append(name)
            elif qty <= 5:
                low_stock.append(f"{name} ({qty})")

        if lang == "uz":
            text = (
                f"📊 <b>Bugungi hisobot</b>\n\n"
                f"🛒 <b>Buyurtmalar (24 soat):</b>\n"
                f"  Jami: {stats['total']} | ✅ {stats['delivered']} | ❌ {stats['cancelled']}\n"
                f"  💰 Tushum: {stats['revenue']:,.0f} so'm\n\n"
                f"📦 <b>Mahsulotlar:</b>\n"
                f"  Tovar turlari: {total_products} ta\n"
                f"  Jami qoldiq (barcha SKU): {total_qty} dona\n\n"
                f"🏭 <b>Ombor:</b>\n"
                f"  💸 Pullik: {len(alerts['paid'])} | "
                f"🚨 Xavfli: {len(alerts['alert'])} | "
                f"⚠️ Ogohlantirish: {len(alerts['warn'])}"
            )
        else:
            text = (
                f"📊 <b>Отчёт за сегодня</b>\n\n"
                f"🛒 <b>Заказы (24 часа):</b>\n"
                f"  Всего: {stats['total']} | ✅ {stats['delivered']} | ❌ {stats['cancelled']}\n"
                f"  💰 Выручка: {stats['revenue']:,.0f} сум\n\n"
                f"📦 <b>Товары:</b>\n"
                f"  Видов товаров: {total_products}\n"
                f"  Общий остаток (все SKU): {total_qty} шт.\n\n"
                f"🏭 <b>Склад:</b>\n"
                f"  💸 Платное: {len(alerts['paid'])} | "
                f"🚨 Критично: {len(alerts['alert'])} | "
                f"⚠️ Внимание: {len(alerts['warn'])}"
            )

        if low_stock:
            text += "\n\n" + t("low_stock_header", lang) + "\n"
            text += "\n".join(f"  ⚠️ {n}" for n in low_stock[:10])
        if out_of_stock:
            text += "\n\n" + t("out_of_stock_header", lang) + "\n"
            text += "\n".join(f"  🚫 {n}" for n in out_of_stock[:10])

        # Tugmasiz — faqat matn
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Report error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка отчёта:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


# ─── Sozlamalar ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
async def cmd_settings(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("⚠️ /start bilan boshlang.")
        return
    lang = user.get("lang", "ru")
    username = message.from_user.username or "—"
    shop_name = user.get("shop_name", "—")
    shop_id = user.get("shop_id", 0)
    key_status = t("key_set", lang) if user.get("api_key") else t("key_not_set", lang)
    text = t("settings_title", lang) + "\n\n" + t(
        "settings_info", lang,
        username=username, shop_name=shop_name,
        shop_id=shop_id, key_status=key_status,
    )
    await message.answer(text, reply_markup=settings_keyboard(lang), parse_mode="HTML")


# ─── Raqib narx monitoring ────────────────────────────────────────────────────

@router.message(F.text.in_(["🔍 Raqib narxlar", "🔍 Цены конкурентов"]))
async def cmd_competitor(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    await message.answer(t("competitor_title", lang), reply_markup=competitor_keyboard(lang), parse_mode="HTML")


@router.callback_query(F.data == "competitor_search")
async def competitor_search_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await callback.message.answer(t("competitor_ask_name", lang), parse_mode="HTML")
    await state.set_state(CompetitorStates.waiting_product_name)
    await callback.answer()


@router.message(CompetitorStates.waiting_product_name)
async def competitor_search_process(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    product_name = message.text.strip() if message.text else ""
    if not product_name or product_name in [t("btn_back", lang), "🔙 Назад", "🔙 Orqaga"]:
        await state.clear()
        await message.answer(
            t("main_menu", lang, shop_name=user.get("shop_name", "—") if user else "—"),
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    msg = await message.answer(t("competitor_searching", lang), parse_mode="HTML")

    try:
        products = await get_products(user["api_key"], user["shop_id"])
        my_price = 0.0
        for p in products:
            if product_name.lower() in (p.get("title") or p.get("name") or "").lower():
                for sku in p.get("skuList", [])[:1]:
                    my_price = safe_float(sku.get("price") or sku.get("purchasePrice"))
                break

        competitors = await get_product_prices(product_name)
        if not competitors:
            await msg.edit_text(t("competitor_not_found", lang), parse_mode="HTML")
        else:
            report = format_competitor_report(product_name, my_price, competitors, lang)
            await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Competitor error: {e}")
        await msg.edit_text(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")

    await state.clear()


@router.callback_query(F.data == "competitor_list")
async def competitor_list(callback: CallbackQuery):
    from database import get_competitor_tracking
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    tracked = await get_competitor_tracking(callback.from_user.id, user.get("shop_id", 0))
    if not tracked:
        text = "📋 Нет отслеживаемых товаров." if lang == "ru" else "📋 Kuzatilayotgan mahsulotlar yo'q."
    else:
        lines = ["📋 <b>Отслеживаемые:</b>"]
        for item in tracked:
            lines.append(f"• {item['product_name']} — {item['my_price']:,.0f}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "competitor_back")
async def competitor_back(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()


# ─── Orqaga / Yangilash ───────────────────────────────────────────────────────

@router.message(F.text.in_(["🔙 Orqaga", "🔙 Назад"]))
async def cmd_back(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )


@router.message(F.text.in_(["🔄 Yangilash", "🔄 Обновить"]))
async def cmd_refresh(message: Message):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )


@router.callback_query(F.data == "go_back")
async def cb_go_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "go_refresh")
async def cb_go_refresh(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()
