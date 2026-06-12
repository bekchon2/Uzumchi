"""
handlers/main_menu.py — Asosiy menyu: mahsulotlar, buyurtmalar, ombor, hisobot, sozlamalar.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from services.uzum_api import (
    get_products, get_fbs_orders, get_finance_orders,
    get_invoices, summarize_orders,
    UzumAuthError, UzumAPIError,
    _days_ago_ms, _now_ms
)
from services.storage_tracker import parse_invoices, format_storage_report, get_storage_alerts
from services.competitor_monitor import get_product_prices, format_competitor_report
from locales.i18n import t
from utils.keyboards import (
    main_menu_keyboard, settings_keyboard,
    back_refresh_keyboard, back_keyboard,
    products_nav_keyboard, competitor_keyboard
)
from utils.helpers import (
    stock_icon, safe_float, safe_int, short_name,
    format_price, order_status_icon, chunk_list
)

logger = logging.getLogger(__name__)
router = Router()

PRODUCTS_PER_PAGE = 8


class CompetitorStates(StatesGroup):
    waiting_product_name = State()


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _get_user_or_warn(message: Message) -> dict | None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key") or not user.get("shop_id"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return None
    return user


def _api_error_text(lang: str, status: str = "") -> str:
    """API ruxsat xatosi uchun to'g'ri matn."""
    if lang == "uz":
        return (
            f"❌ <b>Yuklashda xato</b>\n\n"
            f"API so'rovda muammo yuz berdi{(' (' + status + ')') if status else ''}.\n\n"
            f"<b>Nima qilish kerak:</b>\n"
            f"• seller.uzum.uz → Sozlamalar → API kalitlar\n"
            f"• Kalitning barcha huquqlari yoqilganligini tekshiring\n"
            f"• Yangi kalit yaratib /start orqali qayta kiriting"
        )
    return (
        f"❌ <b>Ошибка загрузки</b>\n\n"
        f"Проблема при запросе к API{(' (' + status + ')') if status else ''}.\n\n"
        f"<b>Что делать:</b>\n"
        f"• seller.uzum.uz → Настройки → API ключи\n"
        f"• Убедитесь что у ключа включены все права\n"
        f"• Создайте новый ключ и введите через /start"
    )


# ─── Mahsulotlar ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📦 Mahsulotlarim", "📦 Мои товары"]))
async def cmd_products(message: Message, state: FSMContext):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")
    await _send_products_page(msg, user, lang, page=1, edit=True)


async def _send_products_page(msg, user: dict, lang: str, page: int = 1, edit: bool = False):
    try:
        products = await get_products(user["api_key"], user["shop_id"])
        if not products:
            text = t("no_data", lang)
            if edit:
                await msg.edit_text(text, parse_mode="HTML")
            else:
                await msg.answer(text, parse_mode="HTML")
            return

        total = len(products)
        pages = chunk_list(products, PRODUCTS_PER_PAGE)
        total_pages = len(pages)
        page = max(1, min(page, total_pages))
        page_products = pages[page - 1]

        lines = [t("products_title", lang, count=total)]
        for p in page_products:
            name = short_name(p.get("title") or p.get("name") or "—")
            skus = p.get("skuList", [])
            if skus:
                sku = skus[0]
                qty = safe_int(sku.get("quantityActive"))
                price = safe_float(sku.get("price") or sku.get("purchasePrice"))
                avg = safe_float(sku.get("avgdsales"))
                days = safe_int(sku.get("forecastOutOfStock", 999))
                icon = stock_icon(qty)
                lines.append(t("product_item", lang,
                    icon=icon, name=name, qty=qty,
                    price=price, avg=avg,
                    days=days if days < 9999 else "∞"
                ))
            else:
                lines.append(f"• {name}")

        text = "\n\n".join(lines)
        kb = products_nav_keyboard(page, total_pages, lang)

        if edit:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")

    except UzumAuthError as e:
        logger.error(f"Products auth error: {e}")
        err = _api_error_text(lang, "401/403")
        if edit:
            await msg.edit_text(err, reply_markup=back_keyboard(lang), parse_mode="HTML")
        else:
            await msg.answer(err, reply_markup=back_keyboard(lang), parse_mode="HTML")
    except UzumAPIError as e:
        logger.error(f"Products API error: {e}")
        err = _api_error_text(lang, str(e)[:80])
        if edit:
            await msg.edit_text(err, reply_markup=back_keyboard(lang), parse_mode="HTML")
        else:
            await msg.answer(err, reply_markup=back_keyboard(lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("products_page_"))
async def products_pagination(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    lang = user.get("lang", "ru")
    await _send_products_page(callback.message, user, lang, page=page, edit=True)
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

        text = t("orders_title", lang) + "\n\n" + t("orders_summary", lang, **stats)

        if orders:
            text += "\n\n<b>" + ("So'nggi buyurtmalar:" if lang == "uz" else "Последние заказы:") + "</b>"
            for o in orders[:10]:
                status = o.get("status", "—")
                icon = order_status_icon(status)
                order_id = o.get("id", "—")
                price = safe_float(o.get("finalPrice") or o.get("price"))
                text += f"\n{icon} #{order_id} — {format_price(price, lang)}"

        await msg.edit_text(text, reply_markup=back_refresh_keyboard(lang), parse_mode="HTML")

    except (UzumAuthError, UzumAPIError) as e:
        logger.error(f"Orders error: {e}")
        await msg.edit_text(_api_error_text(lang), reply_markup=back_keyboard(lang), parse_mode="HTML")


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
        await msg.edit_text(report, reply_markup=back_refresh_keyboard(lang), parse_mode="HTML")

    except (UzumAuthError, UzumAPIError) as e:
        logger.error(f"Storage error: {e}")
        await msg.edit_text(_api_error_text(lang), reply_markup=back_keyboard(lang), parse_mode="HTML")


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
        total_qty = 0
        low_stock = []
        out_of_stock = []

        for p in products:
            for sku in p.get("skuList", [])[:1]:
                qty = safe_int(sku.get("quantityActive"))
                total_qty += qty
                name = short_name(p.get("title") or p.get("name") or "—", 30)
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
                f"  Jami tovar turi: {total_products} ta\n"
                f"  Umumiy qoldiq: {total_qty} dona\n\n"
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
                f"  Общий остаток: {total_qty} шт.\n\n"
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

        await msg.edit_text(text, reply_markup=back_refresh_keyboard(lang), parse_mode="HTML")

    except (UzumAuthError, UzumAPIError) as e:
        logger.error(f"Report error: {e}")
        await msg.edit_text(_api_error_text(lang), reply_markup=back_keyboard(lang), parse_mode="HTML")


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
        username=username,
        shop_name=shop_name,
        shop_id=shop_id,
        key_status=key_status,
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
    await callback.message.answer(t("competitor_ask_name", lang), reply_markup=back_keyboard(lang), parse_mode="HTML")
    await state.set_state(CompetitorStates.waiting_product_name)
    await callback.answer()


@router.message(CompetitorStates.waiting_product_name)
async def competitor_search_process(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    if message.text and message.text.strip() == t("btn_back", lang):
        await state.clear()
        await message.answer(
            t("main_menu", lang, shop_name=user.get("shop_name", "—")),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        return

    product_name = message.text.strip() if message.text else ""
    if not product_name:
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
        logger.error(f"Competitor search error: {e}")
        await msg.edit_text(t("error_api", lang, error=str(e)[:100]), parse_mode="HTML")

    await state.clear()


@router.callback_query(F.data == "competitor_list")
async def competitor_list(callback: CallbackQuery):
    from database import get_competitor_tracking
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    tracked = await get_competitor_tracking(callback.from_user.id, user.get("shop_id", 0))

    if not tracked:
        text = (
            "📋 Kuzatilayotgan mahsulotlar yo'q." if lang == "uz"
            else "📋 Нет отслеживаемых товаров."
        )
    else:
        lines = ["📋 <b>" + ("Kuzatilayotganlar:" if lang == "uz" else "Отслеживаемые:") + "</b>"]
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
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
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
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
    )


@router.message(F.text.in_(["🔄 Yangilash", "🔄 Обновить"]))
async def cmd_refresh(message: Message):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await message.answer(t("loading", lang), parse_mode="HTML")
