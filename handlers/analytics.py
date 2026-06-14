"""
handlers/analytics.py — AI maslahatchi.
Grafik yo'q, tugmalar inline — faqat matn.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from services.uzum_api import (
    get_fbs_orders_period, get_products, get_invoices, summarize_orders,
)
from services.storage_tracker import parse_invoices
from services.gemini_ai import (
    ask_gemini, build_sales_analysis_prompt, build_storage_advice_prompt,
)
from locales.i18n import t
from utils.keyboards import main_menu_keyboard, ai_keyboard, cancel_keyboard

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
