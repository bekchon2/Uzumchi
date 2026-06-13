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
    get_products, get_fbs_orders, get_sales_stats_from_products,
    summarize_orders, calc_total_qty, format_product_skus,
    _days_ago_ms, _now_ms
)
from services.competitor_monitor import (
    get_product_info_by_url,
    check_saved_urls,
    format_single_product_report,
)
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


# ─── Raqib narx monitoring ────────────────────────────────────────────────────

class CompetitorStates(StatesGroup):
    waiting_product_name = State()
    waiting_url = State()
    waiting_url_name = State()


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

        # Agar buyurtmalar API ruxsat bermasa — mahsulot statistikasidan foydalanish
        if stats["total"] == 0:
            product_stats = await get_sales_stats_from_products(user["api_key"], user["shop_id"])
            if product_stats.get("total_sold", 0) > 0:
                if lang == "uz":
                    text = (
                        f"🛒 <b>Buyurtmalar statistikasi</b>\n"
                        f"<i>(API ruxsati yo'q — tovar ma'lumotlaridan)</i>\n\n"
                        f"📦 Jami sotilgan (umumiy): <b>{product_stats['total_sold']}</b> dona\n"
                        f"↩️ Qaytarilgan: <b>{product_stats['total_returned']}</b> dona\n"
                        f"💰 Taxminiy tushum: <b>{product_stats['total_revenue']:,.0f} so'm</b>\n\n"
                        f"⚠️ <i>Aniq buyurtmalar uchun seller.uzum.uz da API kalitga "
                        f"«Buyurtmalar» ruxsatini bering</i>"
                    )
                else:
                    text = (
                        f"🛒 <b>Статистика продаж</b>\n"
                        f"<i>(нет доступа к API заказов — из данных товаров)</i>\n\n"
                        f"📦 Всего продано (суммарно): <b>{product_stats['total_sold']}</b> шт.\n"
                        f"↩️ Возвращено: <b>{product_stats['total_returned']}</b> шт.\n"
                        f"💰 Ориентировочная выручка: <b>{product_stats['total_revenue']:,.0f} сум</b>\n\n"
                        f"⚠️ <i>Для точных данных по заказам выдайте ключу API "
                        f"разрешение «Заказы» в seller.uzum.uz</i>"
                    )
                await msg.edit_text(text, parse_mode="HTML")
                return

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
        elif stats["total"] == 0:
            text += "\n\n" + ("📭 Bugun buyurtma yo'q" if lang == "uz" else "📭 Заказов сегодня нет")

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
        # FBS sotuvchi uchun ombor = mahsulot qoldiqlari asosida
        products = await get_products(user["api_key"], user["shop_id"])

        if not products:
            await msg.edit_text(t("no_data", lang), parse_mode="HTML")
            return

        from utils.helpers import stock_icon, safe_float, safe_int, short_name

        total_products = len(products)
        total_qty = sum(calc_total_qty(p) for p in products)

        low_list = []   # ≤5
        out_list = []   # 0
        ok_list = []    # >15
        warn_list = []  # 6-15

        for p in products:
            name = short_name(p.get("title") or p.get("name") or "—", 35)
            qty = calc_total_qty(p)
            avg = 0.0
            forecast = 9999
            for sku in p.get("skuList", [])[:1]:
                avg = safe_float(sku.get("avgdsales", 0))
                forecast = safe_int(sku.get("forecastOutOfStock", 9999))

            item = {"name": name, "qty": qty, "avg": avg, "forecast": forecast}
            if qty == 0:
                out_list.append(item)
            elif qty <= 5:
                low_list.append(item)
            elif qty <= 15:
                warn_list.append(item)
            else:
                ok_list.append(item)

        if lang == "uz":
            text = (
                f"🏭 <b>Ombor holati (FBS)</b>\n\n"
                f"📊 Jami tovar turi: {total_products} ta\n"
                f"📦 Umumiy qoldiq: {total_qty} dona\n\n"
            )
            if out_list:
                text += f"🚫 <b>Tugagan ({len(out_list)} ta):</b>\n"
                for i in out_list[:10]:
                    text += f"  • {i['name']}\n"
                text += "\n"
            if low_list:
                text += f"⚠️ <b>Kam qolgan — ≤5 dona ({len(low_list)} ta):</b>\n"
                for i in low_list[:10]:
                    d = f" | ⏳ {i['forecast']} kun" if i['forecast'] < 9999 else ""
                    text += f"  • {i['name']}: {i['qty']} dona{d}\n"
                text += "\n"
            if warn_list:
                text += f"🟡 <b>Diqqat — 6-15 dona ({len(warn_list)} ta):</b>\n"
                for i in warn_list[:10]:
                    text += f"  • {i['name']}: {i['qty']} dona\n"
                text += "\n"
            if ok_list:
                text += f"✅ <b>Yaxshi zaxira — >15 dona ({len(ok_list)} ta)</b>"
        else:
            text = (
                f"🏭 <b>Состояние склада (FBS)</b>\n\n"
                f"📊 Всего видов: {total_products}\n"
                f"📦 Общий остаток: {total_qty} шт.\n\n"
            )
            if out_list:
                text += f"🚫 <b>Закончились ({len(out_list)} шт.):</b>\n"
                for i in out_list[:10]:
                    text += f"  • {i['name']}\n"
                text += "\n"
            if low_list:
                text += f"⚠️ <b>Мало — ≤5 шт. ({len(low_list)} шт.):</b>\n"
                for i in low_list[:10]:
                    d = f" | ⏳ {i['forecast']} дн." if i['forecast'] < 9999 else ""
                    text += f"  • {i['name']}: {i['qty']} шт.{d}\n"
                text += "\n"
            if warn_list:
                text += f"🟡 <b>Внимание — 6-15 шт. ({len(warn_list)} шт.):</b>\n"
                for i in warn_list[:10]:
                    text += f"  • {i['name']}: {i['qty']} шт.\n"
                text += "\n"
            if ok_list:
                text += f"✅ <b>Хороший запас — >15 шт. ({len(ok_list)} шт.)</b>"

        await msg.edit_text(text.strip(), parse_mode="HTML")

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
                f"  Jami qoldiq (barcha SKU): {total_qty} dona"
            )
        else:
            text = (
                f"📊 <b>Отчёт за сегодня</b>\n\n"
                f"🛒 <b>Заказы (24 часа):</b>\n"
                f"  Всего: {stats['total']} | ✅ {stats['delivered']} | ❌ {stats['cancelled']}\n"
                f"  💰 Выручка: {stats['revenue']:,.0f} сум\n\n"
                f"📦 <b>Товары:</b>\n"
                f"  Видов товаров: {total_products}\n"
                f"  Общий остаток (все SKU): {total_qty} шт."
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
    if lang == "uz":
        text = (
            "🔗 <b>Uzum tovar sahifasining havolasini yuboring</b>\n\n"
            "Masalan:\n<code>https://uzum.uz/ru/product/suv-shari-123456</code>\n\n"
            "Havola botda saqlanadi va kuzatib boriladi."
        )
    else:
        text = (
            "🔗 <b>Отправьте ссылку на товар в Uzum</b>\n\n"
            "Например:\n<code>https://uzum.uz/ru/product/vodyanoy-shar-123456</code>\n\n"
            "Ссылка сохранится и будет отслеживаться."
        )
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(CompetitorStates.waiting_url)
    await callback.answer()


@router.message(CompetitorStates.waiting_url)
async def competitor_url_received(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    url = (message.text or "").strip()

    # Orqaga
    if url in ["🔙 Назад", "🔙 Orqaga"]:
        await state.clear()
        return

    # URL tekshiruvi
    if "uzum.uz" not in url.lower():
        await message.answer(
            "❌ Bu Uzum URL emas. uzum.uz dan havola yuboring." if lang == "uz"
            else "❌ Это не Uzum URL. Отправьте ссылку с uzum.uz"
        )
        return

    # Darhol tekshira boshlaymiz — nom so'ramaymiz
    msg = await message.answer(
        "⏳ Tovar ma'lumotlari olinmoqda..." if lang == "uz"
        else "⏳ Получаю данные о товаре..."
    )

    from services.competitor_monitor import get_product_info_by_url
    info = await get_product_info_by_url(url)

    if not info:
        await msg.edit_text(
            "⚠️ URL dan ma'lumot olinmadi.\n\n"
            "• Uzum tovar sahifasining to'g'ri URL ekanligini tekshiring\n"
            "• URL bunday ko'rinishda bo'lishi kerak:\n"
            "<code>https://uzum.uz/ru/product/tovar-nomi-123456</code>" if lang == "uz"
            else
            "⚠️ Не удалось получить данные по URL.\n\n"
            "• Проверьте что это правильная ссылка на товар Uzum\n"
            "• Ссылка должна выглядеть так:\n"
            "<code>https://uzum.uz/ru/product/tovar-imya-123456</code>",
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Tovar nomini avtomatik olish
    product_name = info.get("title") or "Tovar"
    # Nomni qisqartirish (30 belgidan oshmasin)
    product_name_short = product_name[:40].strip()

    # DB ga saqlash
    from database import add_product_url
    await add_product_url(
        user_id=message.from_user.id,
        shop_id=user["shop_id"] if user else 0,
        product_name=product_name_short,
        uzum_url=url
    )

    # Mening narximni topish
    products = await get_products(user["api_key"], user["shop_id"])
    my_price = 0.0
    for p in products:
        p_title = (p.get("title") or p.get("name") or "").lower()
        pn_lower = product_name_short.lower()
        # Umumiy so'z bormi
        p_words = set(p_title.split())
        n_words = set(pn_lower.split())
        if p_words & n_words:
            for sku in p.get("skuList", [])[:1]:
                my_price = safe_float(sku.get("price") or sku.get("purchasePrice"))
            break

    from services.competitor_monitor import format_single_product_report
    report = format_single_product_report(product_name_short, my_price, info, lang)
    await msg.edit_text(report, parse_mode="HTML")
    await state.clear()


@router.message(CompetitorStates.waiting_product_name)
async def competitor_search_process(message: Message, state: FSMContext):
    """Eski handler — endi URL kerak."""
    await state.clear()


@router.callback_query(F.data == "competitor_list")
async def competitor_list(callback: CallbackQuery):
    """Saqlangan URL larni tekshirish."""
    from database import get_product_urls
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    msg = await callback.message.answer(
        "⏳ Narxlar tekshirilmoqda..." if lang == "uz"
        else "⏳ Проверяю цены...",
        parse_mode="HTML"
    )

    saved_urls = await get_product_urls(callback.from_user.id, user.get("shop_id", 0))

    if not saved_urls:
        await msg.edit_text(
            "📋 Kuzatilayotgan tovarlar yo'q.\n\n"
            "🔗 <b>Qo'shish uchun:</b> «Narx qidirish» → Uzum sahifa URL sini yuboring." if lang == "uz"
            else
            "📋 Нет отслеживаемых товаров.\n\n"
            "🔗 <b>Чтобы добавить:</b> «Поиск цен» → Отправьте URL страницы товара на Uzum.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Tovarlar ma'lumotlari + narx tekshiruv
    products = await get_products(user["api_key"], user["shop_id"])
    report = await check_saved_urls(user["api_key"], products, saved_urls, lang)
    await msg.edit_text(report, parse_mode="HTML", disable_web_page_preview=True)
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
