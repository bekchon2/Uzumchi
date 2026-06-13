"""
handlers/analytics.py — Haftalik, oylik hisobot, qaytarmalar, AI maslahatchi.
Grafik yo'q, tugmalar yo'q — faqat matn.
"""
import logging
import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from services.uzum_api import (
    get_fbs_orders_period, get_returns, get_expenses,
    get_products, get_invoices, summarize_orders,
    _days_ago_ms, _now_ms
)
from services.storage_tracker import parse_invoices, get_storage_alerts
from services.gemini_ai import (
    ask_gemini, build_sales_analysis_prompt, build_storage_advice_prompt
)
from locales.i18n import t
from utils.keyboards import (
    main_menu_keyboard, back_keyboard, ai_keyboard, cancel_keyboard
)
from utils.helpers import safe_float, safe_int, short_name, format_price

logger = logging.getLogger(__name__)
router = Router()


class AIStates(StatesGroup):
    waiting_question = State()


async def _get_user_or_warn(message: Message) -> dict | None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key") or not user.get("shop_id"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return None
    return user


def _build_daily_data(orders: list[dict], days: int = 7) -> list[dict]:
    from collections import defaultdict
    daily = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    for o in orders:
        ts = o.get("createdAt") or o.get("orderDate") or o.get("date") or 0
        if ts:
            try:
                dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
                day_str = dt.strftime("%d.%m")
                daily[day_str]["orders"] += 1
                if o.get("status") == "DELIVERED":
                    daily[day_str]["revenue"] += safe_float(
                        o.get("finalPrice") or o.get("price") or o.get("orderPrice") or 0
                    )
            except Exception:
                pass
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


def _is_in_week(order: dict, week_num: int) -> bool:
    ts = order.get("createdAt") or order.get("orderDate") or order.get("date") or 0
    if not ts:
        return False
    try:
        dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
        days_ago = (datetime.datetime.now() - dt).days
        return week_num * 7 <= days_ago < (week_num + 1) * 7
    except Exception:
        return False


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

        if lang == "uz":
            text = (
                f"📈 <b>Haftalik hisobot</b> (so'nggi 7 kun)\n\n"
                f"📦 Jami buyurtmalar: <b>{stats['total']}</b>\n"
                f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                f"❌ Bekor qilindi: <b>{stats['cancelled']}</b>\n"
                f"💰 Tushum: <b>{stats['revenue']:,.0f} so'm</b>\n\n"
                f"📊 <b>Kunlik:</b>"
            )
            for d in daily_data:
                bar = "█" * min(d["orders"], 15) if d["orders"] > 0 else "░"
                rev = f" ({d['revenue']:,.0f} so'm)" if d["revenue"] > 0 else ""
                text += f"\n{d['date']}: {bar} {d['orders']} ta{rev}"
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
                bar = "█" * min(d["orders"], 15) if d["orders"] > 0 else "░"
                rev = f" ({d['revenue']:,.0f} сум)" if d["revenue"] > 0 else ""
                text += f"\n{d['date']}: {bar} {d['orders']} шт.{rev}"

        # Tugmasiz — faqat matn
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Weekly error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


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

        weekly_data = []
        for week_num in range(4):
            week_orders = [o for o in orders if _is_in_week(o, week_num)]
            w_stats = summarize_orders(week_orders)
            week_label = f"{week_num + 1}-hafta" if lang == "uz" else f"{week_num + 1} неделя"
            weekly_data.append({
                "week": week_label,
                "orders": w_stats["total"],
                "revenue": w_stats["revenue"],
            })

        expenses_data = await get_expenses(user["api_key"], date_from=_days_ago_ms(30))
        total_expenses = 0.0
        if expenses_data:
            total_expenses = safe_float(
                expenses_data.get("totalExpenses") or expenses_data.get("total") or 0
            )

        profit = stats["revenue"] - total_expenses
        profitability = (profit / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

        if lang == "uz":
            text = (
                f"📅 <b>Oylik hisobot</b> (so'nggi 30 kun)\n\n"
                f"📦 Jami buyurtmalar: <b>{stats['total']}</b>\n"
                f"✅ Yetkazildi: <b>{stats['delivered']}</b>\n"
                f"❌ Bekor: <b>{stats['cancelled']}</b>\n"
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
                bar = "█" * min(w["orders"], 10) if w["orders"] > 0 else "░"
                text += f"\n{w['week']}: {bar} {w['orders']} ta | {w['revenue']:,.0f} so'm"
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
                bar = "█" * min(w["orders"], 10) if w["orders"] > 0 else "░"
                text += f"\n{w['week']}: {bar} {w['orders']} шт. | {w['revenue']:,.0f} сум"

        # Tugmasiz — faqat matn
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Monthly error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


# ─── Qaytarmalar ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["↩️ Qaytarmalar", "↩️ Возвраты"]))
async def cmd_returns(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    msg = await message.answer(t("loading", lang), parse_mode="HTML")

    try:
        returns_30 = await get_returns(user["api_key"], date_from=_days_ago_ms(30))
        returns_today = await get_returns(user["api_key"], date_from=_days_ago_ms(1))

        logger.info(f"Returns 30d: {len(returns_30)}, today: {len(returns_today)}")
        logger.info(f"First return sample: {returns_30[0] if returns_30 else 'empty'}")

        if not returns_30:
            if lang == "uz":
                text = "↩️ <b>Qaytarmalar</b>\n\nSo'nggi 30 kunda qaytarma yo'q."
            else:
                text = "↩️ <b>Возвраты</b>\n\nЗа последние 30 дней возвратов нет."
            await msg.edit_text(text, parse_mode="HTML")
            return

        if lang == "uz":
            text = (
                f"↩️ <b>Qaytarmalar</b> (30 kun)\n\n"
                f"📊 Jami: <b>{len(returns_30)}</b> ta\n"
                f"🆕 Bugun: <b>{len(returns_today)}</b> ta\n\n"
            )
        else:
            text = (
                f"↩️ <b>Возвраты</b> (30 дней)\n\n"
                f"📊 Всего: <b>{len(returns_30)}</b> шт.\n"
                f"🆕 Сегодня: <b>{len(returns_today)}</b> шт.\n\n"
            )

        for r in returns_30[:15]:
            # Turli response formatlarini qo'llash
            r_id = r.get("id") or r.get("returnId") or "—"
            reason = (
                r.get("reason") or r.get("returnReason")
                or r.get("cancelReason") or r.get("comment") or "—"
            )
            amount = safe_float(
                r.get("amount") or r.get("price") or r.get("orderPrice")
                or r.get("totalPrice") or 0
            )
            product = short_name(
                r.get("productName") or r.get("title") or r.get("name")
                or r.get("itemName") or "—", 35
            )
            status = r.get("status") or r.get("returnStatus") or ""
            status_str = f" [{status}]" if status else ""

            text += (
                f"↩️ #{r_id}{status_str}: {product}\n"
                f"   💰 {amount:,.0f} | "
                + ("Sabab: " if lang == "uz" else "Причина: ")
                + f"{reason}\n\n"
            )

        await msg.edit_text(text.strip(), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Returns error: {e}")
        await msg.edit_text(
            f"❌ <b>Ошибка возвратов:</b>\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


# ─── AI Maslahatchi ───────────────────────────────────────────────────────────

@router.message(F.text.in_(["🤖 AI Maslahat", "🤖 AI Совет"]))
async def cmd_ai(message: Message):
    user = await _get_user_or_warn(message)
    if not user:
        return
    lang = user.get("lang", "ru")
    await message.answer(t("ai_title", lang), reply_markup=ai_keyboard(lang), parse_mode="HTML")


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
        header = "🤖 <b>AI tahlili:</b>\n\n" if lang == "uz" else "🤖 <b>AI анализ:</b>\n\n"
        await msg.edit_text(header + answer, parse_mode="HTML")
    except Exception as e:
        logger.error(f"AI sales error: {e}")
        await msg.edit_text(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")
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
        header = "🤖 <b>Ombor tavsiyasi:</b>\n\n" if lang == "uz" else "🤖 <b>Совет по складу:</b>\n\n"
        await msg.edit_text(header + answer, parse_mode="HTML")
    except Exception as e:
        logger.error(f"AI storage error: {e}")
        await msg.edit_text(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ai_question")
async def ai_question_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await callback.message.answer(t("ai_ask_question", lang), reply_markup=cancel_keyboard(lang), parse_mode="HTML")
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
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    question = (message.text or "").strip()
    if not question:
        return

    msg = await message.answer(t("ai_thinking", lang), parse_mode="HTML")
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
    await msg.edit_text(f"🤖 <b>AI:</b>\n\n{answer}", parse_mode="HTML", reply_markup=ai_keyboard(lang))
    await state.clear()


@router.callback_query(F.data == "ai_back")
async def ai_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()
