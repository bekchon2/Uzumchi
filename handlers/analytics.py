"""
handlers/analytics.py — Haftalik, oylik hisobot, qaytarmalar, AI maslahatchi.
"""
import logging
import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from services.uzum_api import (
    get_fbs_orders_period, get_returns, get_expenses,
    get_products, get_invoices, summarize_orders,
    UzumAuthError, UzumAPIError,
    _days_ago_ms, _now_ms
)
from services.storage_tracker import parse_invoices, get_storage_alerts
from services.charts import weekly_sales_chart, monthly_sales_chart
from services.gemini_ai import (
    ask_gemini, build_sales_analysis_prompt,
    build_competitor_advice_prompt, build_storage_advice_prompt
)
from locales.i18n import t
from utils.keyboards import (
    main_menu_keyboard, back_keyboard,
    back_refresh_keyboard, ai_keyboard, cancel_keyboard
)
from utils.helpers import safe_float, safe_int, short_name, format_price

logger = logging.getLogger(__name__)
router = Router()


class AIStates(StatesGroup):
    waiting_question = State()


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _get_user_or_warn(message: Message) -> dict | None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key") or not user.get("shop_id"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return None
    return user


def _build_daily_data(orders: list[dict], days: int = 7) -> list[dict]:
    """Kunlik statistika shakllantirish."""
    from collections import defaultdict
    daily: dict[str, dict] = defaultdict(lambda: {"orders": 0, "revenue": 0.0})

    for o in orders:
        ts = o.get("createdAt") or o.get("orderDate") or 0
        if ts:
            try:
                dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
                day_str = dt.strftime("%d.%m")
                daily[day_str]["orders"] += 1
                if o.get("status") == "DELIVERED":
                    daily[day_str]["revenue"] += safe_float(o.get("finalPrice") or o.get("price"))
            except Exception:
                pass

    # So'nggi N kun uchun to'ldirish
    result = []
    for i in range(days - 1, -1, -1):
        dt = datetime.datetime.now() - datetime.timedelta(days=i)
        day_str = dt.strftime("%d.%m")
        result.append({
            "date": day_str,
            "orders": daily[day_str]["orders"],
            "revenue": daily[day_str]["revenue"],
        })
    return result


# ─── Haftalik hisobot ─────────────────────────────────────────────────────────

@router.message(F.text.in_(["📈 Haftalik", "📈 Недельный"]))
async def cmd_weekly(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        orders = await get_fbs_orders_period(user["api_key"], days=7)
        stats = summarize_orders(orders)
        daily_data = _build_daily_data(orders, days=7)

        # Matn hisobot
        if lang == "uz":
            text = (
                f"📈 <b>Haftalik hisobot</b> (so'nggi 7 kun)\n\n"
                f"📦 Jami buyurtmalar: <b>{stats['total']}</b>\n"
                f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                f"❌ Bekor qilindi: <b>{stats['cancelled']}</b>\n"
                f"💰 Jami tushum: <b>{stats['revenue']:,.0f} so'm</b>\n\n"
                f"📊 <b>Kunlik ko'rsatkich:</b>"
            )
            for d in daily_data:
                bar = "█" * min(d["orders"], 20) if d["orders"] > 0 else "░"
                text += f"\n{d['date']}: {bar} {d['orders']} ta"
        else:
            text = (
                f"📈 <b>Недельный отчёт</b> (последние 7 дней)\n\n"
                f"📦 Всего заказов: <b>{stats['total']}</b>\n"
                f"✅ Доставлено: <b>{stats['delivered']}</b>\n"
                f"❌ Отменено: <b>{stats['cancelled']}</b>\n"
                f"💰 Выручка: <b>{stats['revenue']:,.0f} сум</b>\n\n"
                f"📊 <b>По дням:</b>"
            )
            for d in daily_data:
                bar = "█" * min(d["orders"], 20) if d["orders"] > 0 else "░"
                text += f"\n{d['date']}: {bar} {d['orders']} шт."

        await msg.edit_text(text, parse_mode="HTML")

        # Grafik
        try:
            chart_buf = weekly_sales_chart(daily_data, lang)
            photo = BufferedInputFile(chart_buf.read(), filename="weekly.png")
            await message.answer_photo(
                photo,
                caption="📈 " + ("Haftalik grafik" if lang == "uz" else "Недельный график"),
                reply_markup=back_refresh_keyboard(lang)
            )
        except Exception as e:
            logger.warning(f"Chart error: {e}")
            await message.answer(
                text,
                reply_markup=back_refresh_keyboard(lang),
                parse_mode="HTML"
            )

    except UzumAuthError:
        await msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
    except UzumAPIError as e:
        await msg.edit_text(t("error_api", lang, error=str(e)), parse_mode="HTML")


# ─── Oylik hisobot ────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📅 Oylik", "📅 Месячный"]))
async def cmd_monthly(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        orders = await get_fbs_orders_period(user["api_key"], days=30)
        stats = summarize_orders(orders)

        # Haftalik bo'linish
        weekly_data = []
        for week_num in range(4):
            week_orders = [
                o for o in orders
                if _is_in_week(o, week_num)
            ]
            w_stats = summarize_orders(week_orders)
            if lang == "uz":
                week_label = f"{week_num + 1}-hafta"
            else:
                week_label = f"{week_num + 1} неделя"
            weekly_data.append({
                "week": week_label,
                "orders": w_stats["total"],
                "revenue": w_stats["revenue"],
            })

        # Xarajatlar
        expenses_data = await get_expenses(user["api_key"], date_from=_days_ago_ms(30))
        total_expenses = 0.0
        if expenses_data:
            total_expenses = safe_float(
                expenses_data.get("totalExpenses") or expenses_data.get("total")
            )

        profit = stats["revenue"] - total_expenses
        profitability = (profit / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

        if lang == "uz":
            text = (
                f"📅 <b>Oylik hisobot</b> (so'nggi 30 kun)\n\n"
                f"📦 Jami buyurtmalar: <b>{stats['total']}</b>\n"
                f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                f"❌ Bekor qilindi: <b>{stats['cancelled']}</b>\n"
                f"💰 Tushum: <b>{stats['revenue']:,.0f} so'm</b>\n"
            )
            if total_expenses > 0:
                text += (
                    f"📉 Xarajatlar: <b>{total_expenses:,.0f} so'm</b>\n"
                    f"💵 Foyda: <b>{profit:,.0f} so'm</b>\n"
                    f"📊 Rentabellik: <b>{profitability:.1f}%</b>\n"
                )
            text += "\n<b>Haftalar bo'yicha:</b>"
            for w in weekly_data:
                text += f"\n📅 {w['week']}: {w['orders']} ta buyurtma, {w['revenue']:,.0f} so'm"
        else:
            text = (
                f"📅 <b>Месячный отчёт</b> (последние 30 дней)\n\n"
                f"📦 Всего заказов: <b>{stats['total']}</b>\n"
                f"✅ Доставлено: <b>{stats['delivered']}</b>\n"
                f"❌ Отменено: <b>{stats['cancelled']}</b>\n"
                f"💰 Выручка: <b>{stats['revenue']:,.0f} сум</b>\n"
            )
            if total_expenses > 0:
                text += (
                    f"📉 Расходы: <b>{total_expenses:,.0f} сум</b>\n"
                    f"💵 Прибыль: <b>{profit:,.0f} сум</b>\n"
                    f"📊 Рентабельность: <b>{profitability:.1f}%</b>\n"
                )
            text += "\n<b>По неделям:</b>"
            for w in weekly_data:
                text += f"\n📅 {w['week']}: {w['orders']} заказов, {w['revenue']:,.0f} сум"

        await msg.edit_text(text, parse_mode="HTML")

        # Grafik
        try:
            chart_buf = monthly_sales_chart(weekly_data, lang)
            photo = BufferedInputFile(chart_buf.read(), filename="monthly.png")
            await message.answer_photo(
                photo,
                caption="📅 " + ("Oylik grafik" if lang == "uz" else "Месячный график"),
                reply_markup=back_refresh_keyboard(lang)
            )
        except Exception as e:
            logger.warning(f"Chart error: {e}")
            await message.answer(text, reply_markup=back_refresh_keyboard(lang), parse_mode="HTML")

    except UzumAuthError:
        await msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
    except UzumAPIError as e:
        await msg.edit_text(t("error_api", lang, error=str(e)), parse_mode="HTML")


def _is_in_week(order: dict, week_num: int) -> bool:
    """Buyurtma qaysi haftaga tegishli (0=eng so'nggi hafta)."""
    ts = order.get("createdAt") or order.get("orderDate") or 0
    if not ts:
        return False
    try:
        dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
        now = datetime.datetime.now()
        days_ago = (now - dt).days
        return week_num * 7 <= days_ago < (week_num + 1) * 7
    except Exception:
        return False


# ─── Qaytarmalar ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["↩️ Qaytarmalar", "↩️ Возвраты"]))
async def cmd_returns(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        returns = await get_returns(user["api_key"], date_from=_days_ago_ms(30))
        today_returns = await get_returns(user["api_key"], date_from=_days_ago_ms(1))

        if not returns:
            await msg.edit_text(
                t("no_data", lang),
                reply_markup=back_keyboard(lang),
                parse_mode="HTML"
            )
            return

        lines = [t("returns_title", lang)]
        lines.append(t("returns_today_new", lang, count=len(today_returns)))
        lines.append("")

        for r in returns[:15]:
            r_id = r.get("id", "—")
            reason = r.get("reason") or r.get("returnReason") or "—"
            amount = safe_float(r.get("amount") or r.get("price") or 0)
            product = short_name(
                r.get("productName") or r.get("title") or "—", 30
            )
            lines.append(
                f"↩️ #{r_id}: {product}\n"
                f"   💰 {amount:,.0f} | "
                + ("Sabab" if lang == "uz" else "Причина") + f": {reason}"
            )

        text = "\n\n".join(lines)
        await msg.edit_text(
            text,
            reply_markup=back_refresh_keyboard(lang),
            parse_mode="HTML"
        )

    except UzumAuthError:
        await msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
    except UzumAPIError as e:
        await msg.edit_text(t("error_api", lang, error=str(e)), parse_mode="HTML")


# ─── AI Maslahatchi ───────────────────────────────────────────────────────────

@router.message(F.text.in_(["🤖 AI Maslahat", "🤖 AI Совет"]))
async def cmd_ai(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    await message.answer(
        t("ai_title", lang),
        reply_markup=ai_keyboard(lang),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ai_sales")
async def ai_sales_analysis(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    msg = await callback.message.answer(t("ai_thinking", lang), parse_mode="HTML")

    try:
        orders = await get_fbs_orders_period(user["api_key"], days=7)
        stats = summarize_orders(orders)
        products = await get_products(user["api_key"], user["shop_id"])

        prompt = build_sales_analysis_prompt(stats, products, lang)
        answer = await ask_gemini(prompt, lang)

        await msg.edit_text(
            f"🤖 <b>AI tahlili:</b>\n\n{answer}" if lang == "uz"
            else f"🤖 <b>AI анализ:</b>\n\n{answer}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"AI sales error: {e}")
        await msg.edit_text(t("error_api", lang, error=str(e)), parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data == "ai_storage")
async def ai_storage_advice(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    msg = await callback.message.answer(t("ai_thinking", lang), parse_mode="HTML")

    try:
        invoices = await get_invoices(user["api_key"], user["shop_id"])
        storage_items = parse_invoices(invoices)

        prompt = build_storage_advice_prompt(storage_items, lang)
        answer = await ask_gemini(prompt, lang)

        await msg.edit_text(
            f"🤖 <b>Ombor tavsiyasi:</b>\n\n{answer}" if lang == "uz"
            else f"🤖 <b>Совет по складу:</b>\n\n{answer}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"AI storage error: {e}")
        await msg.edit_text(t("error_api", lang, error=str(e)), parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data == "ai_question")
async def ai_question_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await callback.message.answer(
        t("ai_ask_question", lang),
        reply_markup=cancel_keyboard(lang),
        parse_mode="HTML"
    )
    await state.set_state(AIStates.waiting_question)
    await callback.answer()


@router.message(AIStates.waiting_question)
async def ai_question_process(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text and message.text.strip() == cancel_text:
        await state.clear()
        shop_name = user.get("shop_name", "—") if user else "—"
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        return

    question = message.text.strip() if message.text else ""
    if not question:
        return

    msg = await message.answer(t("ai_thinking", lang), parse_mode="HTML")

    # Kontekst qo'shish
    shop_name = user.get("shop_name", "JoyKid") if user else "JoyKid"
    if lang == "uz":
        full_prompt = (
            f"Sen Uzum marketplace ({shop_name} do'koni) savdo maslahatchisisisan. "
            f"O'zbek tilida qisqa va amaliy javob ber (maksimum 300 so'z):\n\n{question}"
        )
    else:
        full_prompt = (
            f"Ты эксперт по продажам на Uzum marketplace (магазин {shop_name}). "
            f"Дай краткий и практичный ответ на русском (максимум 300 слов):\n\n{question}"
        )

    answer = await ask_gemini(full_prompt, lang)

    await msg.edit_text(
        f"🤖 <b>AI:</b>\n\n{answer}",
        parse_mode="HTML",
        reply_markup=ai_keyboard(lang)
    )
    await state.clear()


@router.callback_query(F.data == "ai_back")
async def ai_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
    )
    await callback.answer()
