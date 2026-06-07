"""
handlers/start.py — /start, onboarding, til tanlash, API key kiritish.
Multi-shop support: bir API key — barcha do'konlar.
"""
import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database import (
    get_user, create_user, set_user_lang,
    set_user_api_key, set_user_shop, set_active_shop
)
from services.uzum_api import get_shops, UzumAuthError, UzumAPIError
from locales.i18n import t
from utils.keyboards import (
    lang_keyboard, main_menu_keyboard,
    shops_keyboard, cancel_keyboard
)

logger = logging.getLogger(__name__)
router = Router()


class OnboardingStates(StatesGroup):
    waiting_api_key = State()
    waiting_new_api_key = State()


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)

    if user and user.get("api_key") and user.get("shop_id"):
        # Allaqachon sozlangan — asosiy menyuga
        lang = user.get("lang", "ru")
        shop_name = user.get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        return

    # Yangi foydalanuvchi
    await create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        t("welcome", "ru"),
        reply_markup=lang_keyboard(),
        parse_mode="HTML"
    )


# ─── Til tanlash ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.in_(["lang_ru", "lang_uz"]))
async def select_lang(callback: CallbackQuery, state: FSMContext):
    lang = "ru" if callback.data == "lang_ru" else "uz"
    await set_user_lang(callback.from_user.id, lang)

    await callback.message.edit_text(
        t("lang_selected", lang),
        parse_mode="HTML"
    )
    await asyncio.sleep(0.5)

    # API key so'rash
    await callback.message.answer(
        t("ask_api_key", lang),
        reply_markup=cancel_keyboard(lang),
        parse_mode="HTML"
    )
    await state.set_state(OnboardingStates.waiting_api_key)
    await callback.answer()


# ─── API key kiritish ─────────────────────────────────────────────────────────

@router.message(OnboardingStates.waiting_api_key)
async def process_api_key(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    # Bekor qilish
    cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text and message.text.strip() == cancel_text:
        await state.clear()
        await message.answer(
            t("welcome", lang),
            reply_markup=lang_keyboard(),
            parse_mode="HTML"
        )
        return

    api_key = message.text.strip() if message.text else ""

    # Xabarni o'chirish (xavfsizlik)
    try:
        await message.delete()
    except Exception:
        pass

    if not api_key or len(api_key) < 10:
        await message.answer(t("api_invalid", lang), parse_mode="HTML")
        return

    checking_msg = await message.answer(t("api_checking", lang), parse_mode="HTML")

    try:
        shops = await get_shops(api_key)
        if not shops:
            await checking_msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
            return

        await set_user_api_key(message.from_user.id, api_key)

        # Multi-shop: agar 1 ta bo'lsa avtomatik tanlash
        if len(shops) == 1:
            shop = shops[0]
            shop_id = shop.get("id", 0)
            shop_name = shop.get("name", f"Do'kon {shop_id}")
            await set_user_shop(message.from_user.id, shop_id, shop_name)

            await checking_msg.edit_text(
                t("api_success", lang, shop_name=shop_name),
                parse_mode="HTML"
            )
            await asyncio.sleep(0.5)
            await message.answer(
                t("setup_complete", lang),
                reply_markup=main_menu_keyboard(lang),
                parse_mode="HTML"
            )
            await state.clear()
        else:
            # Bir nechta do'kon — tanlash
            await checking_msg.edit_text(
                t("shop_select_title", lang),
                reply_markup=shops_keyboard(shops, lang),
                parse_mode="HTML"
            )
            await state.update_data(api_key=api_key, shops=shops)
            await state.set_state(None)

    except UzumAuthError:
        await checking_msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
    except UzumAPIError as e:
        await checking_msg.edit_text(
            t("error_api", lang, error=str(e)),
            parse_mode="HTML"
        )


# ─── Do'kon tanlash (multi-shop onboarding) ───────────────────────────────────

@router.callback_query(F.data.startswith("shop_") & ~F.data.startswith("shop_back"))
async def select_shop(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Xato!", show_alert=True)
        return

    shop_id = int(parts[1])
    shop_name = parts[2]

    await set_user_shop(callback.from_user.id, shop_id, shop_name)

    await callback.message.edit_text(
        t("api_success", lang, shop_name=shop_name),
        parse_mode="HTML"
    )
    await asyncio.sleep(0.3)
    await callback.message.answer(
        t("setup_complete", lang),
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "shop_back")
async def shop_back(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await callback.message.edit_text(t("ask_api_key", lang), parse_mode="HTML")
    await state.set_state(OnboardingStates.waiting_api_key)
    await callback.answer()


# ─── Sozlamalar: API key o'zgartirish ────────────────────────────────────────

@router.callback_query(F.data == "settings_change_key")
async def change_api_key(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    await callback.message.answer(
        t("ask_api_key", lang),
        reply_markup=cancel_keyboard(lang),
        parse_mode="HTML"
    )
    await state.set_state(OnboardingStates.waiting_new_api_key)
    await callback.answer()


@router.message(OnboardingStates.waiting_new_api_key)
async def process_new_api_key(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text and message.text.strip() == cancel_text:
        await state.clear()
        await message.answer(
            t("main_menu", lang, shop_name=user.get("shop_name", "—")),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        return

    api_key = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    checking_msg = await message.answer(t("api_checking", lang), parse_mode="HTML")

    try:
        shops = await get_shops(api_key)
        if not shops:
            await checking_msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
            return

        await set_user_api_key(message.from_user.id, api_key)
        shop = shops[0]
        shop_id = shop.get("id", 0)
        shop_name = shop.get("name", f"Do'kon {shop_id}")
        await set_user_shop(message.from_user.id, shop_id, shop_name)

        await checking_msg.edit_text(
            t("api_success", lang, shop_name=shop_name),
            parse_mode="HTML"
        )
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        await state.clear()

    except UzumAuthError:
        await checking_msg.edit_text(t("api_invalid", lang), parse_mode="HTML")
    except UzumAPIError as e:
        await checking_msg.edit_text(
            t("error_api", lang, error=str(e)),
            parse_mode="HTML"
        )


# ─── Sozlamalar: til o'zgartirish ────────────────────────────────────────────

@router.callback_query(F.data == "settings_change_lang")
async def change_language(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌐 Tilni tanlang / Выберите язык:",
        reply_markup=lang_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ─── Sozlamalar: do'kon almashtirish ─────────────────────────────────────────

@router.callback_query(F.data == "settings_switch_shop")
async def switch_shop(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    if not user or not user.get("api_key"):
        await callback.answer(t("no_data", lang), show_alert=True)
        return

    try:
        shops = await get_shops(user["api_key"])
        if len(shops) <= 1:
            await callback.answer(t("shop_single", lang), show_alert=True)
            return

        await callback.message.edit_text(
            t("shop_select_title", lang),
            reply_markup=shops_keyboard(shops, lang),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(str(e)[:100], show_alert=True)
    await callback.answer()
