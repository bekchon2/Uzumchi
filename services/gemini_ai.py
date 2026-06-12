"""
Gemini AI maslahatchi servisi.
Google Gemini API orqali savdo tahlili va tavsiyalar beradi.
"""
import asyncio
import logging
import ssl
import aiohttp
import os
import json

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# Windows SSL muammosini hal qilish
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


async def ask_gemini(prompt: str, lang: str = "ru") -> str:
    """
    Gemini API ga so'rov yuborish.
    Returns: javob matni yoki xato xabari.
    """
    if not GEMINI_API_KEY:
        if lang == "uz":
            return "⚠️ Gemini API kaliti sozlanmagan. GEMINI_API_KEY ni .env ga qo'shing."
        return "⚠️ Ключ Gemini API не настроен. Добавьте GEMINI_API_KEY в .env."

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        }
    }

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
            async with session.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                    return "⚠️ Bo'sh javob olindi." if lang == "uz" else "⚠️ Получен пустой ответ."
                elif resp.status == 429:
                    if lang == "uz":
                        return "⚠️ Gemini API cheklovi. Bir ozdan keyin urinib ko'ring."
                    return "⚠️ Лимит Gemini API. Попробуйте чуть позже."
                else:
                    text = await resp.text()
                    logger.error(f"Gemini API error {resp.status}: {text[:200]}")
                    if lang == "uz":
                        return f"⚠️ Gemini xatosi: {resp.status}"
                    return f"⚠️ Ошибка Gemini: {resp.status}"
    except asyncio.TimeoutError:
        if lang == "uz":
            return "⚠️ Gemini javob bermadi (timeout). Qayta urinib ko'ring."
        return "⚠️ Gemini не ответил (timeout). Попробуйте снова."
    except Exception as e:
        logger.error(f"Gemini request error: {e}")
        if lang == "uz":
            return f"⚠️ Xato: {e}"
        return f"⚠️ Ошибка: {e}"


def build_sales_analysis_prompt(stats: dict, products: list[dict], lang: str = "ru") -> str:
    """Savdo statistikasi asosida Gemini uchun prompt tuzish."""
    total_orders = stats.get("total", 0)
    delivered = stats.get("delivered", 0)
    cancelled = stats.get("cancelled", 0)
    revenue = stats.get("revenue", 0)
    cancel_rate = (cancelled / total_orders * 100) if total_orders > 0 else 0

    # Top mahsulotlar
    top_products = []
    for p in products[:5]:
        for sku in p.get("skuList", [])[:1]:
            qty_active = sku.get("quantityActive", 0)
            avg_sales = sku.get("avgdsales", 0) or 0
            top_products.append(f"- {p.get('title', '?')[:30]}: qoldiq={qty_active}, kunlik={avg_sales:.1f}")

    products_info = "\n".join(top_products) if top_products else "Ma'lumot yo'q"

    if lang == "uz":
        return f"""Sen Uzum marketplace savdo maslahatchisisisan. Quyidagi statistika asosida qisqa, amaliy tavsiya ber (maksimum 300 so'z, o'zbek tilida):

SAVDO MA'LUMOTLARI:
- Jami buyurtmalar: {total_orders}
- Yetkazildi: {delivered}
- Bekor qilindi: {cancelled} ({cancel_rate:.1f}%)
- Tushum: {revenue:,.0f} so'm

TOP MAHSULOTLAR (qoldiq va kunlik sotuv):
{products_info}

Quyidagilarga e'tibor ber:
1. Bekor qilish foizi haqida (yuqori bo'lsa sabab va yechim)
2. Qoldiq kam bo'lgan mahsulotlar uchun tavsiya
3. Tushum oshirish bo'yicha 2-3 ta amaliy maslahat
4. Umumiy holat baholash (yaxshi/o'rta/yomon)"""
    else:
        return f"""Ты эксперт по продажам на маркетплейсе Uzum. На основе данных дай краткий, практичный совет (максимум 300 слов, на русском):

ДАННЫЕ О ПРОДАЖАХ:
- Всего заказов: {total_orders}
- Доставлено: {delivered}
- Отменено: {cancelled} ({cancel_rate:.1f}%)
- Выручка: {revenue:,.0f} сум

ТОП ТОВАРЫ (остаток и дневные продажи):
{products_info}

Обрати внимание на:
1. Процент отмен (если высокий — причины и решение)
2. Рекомендации по товарам с низким остатком
3. 2-3 практических совета по увеличению выручки
4. Общая оценка ситуации (хорошо/средне/плохо)"""


def build_competitor_advice_prompt(
    product_name: str,
    my_price: float,
    avg_competitor_price: float,
    min_competitor_price: float,
    lang: str = "ru"
) -> str:
    """Raqib narx tahlili uchun Gemini prompt."""
    diff_pct = ((my_price - avg_competitor_price) / avg_competitor_price * 100) if avg_competitor_price > 0 else 0

    if lang == "uz":
        return f"""Sen Uzum marketplace narx strategiyasi bo'yicha maslahatchisan. Qisqa tavsiya ber (100-150 so'z, o'zbek tilida):

MAHSULOT: {product_name}
MENING NARXIM: {my_price:,.0f} so'm
RAQIBLAR O'RTACHA NARXI: {avg_competitor_price:,.0f} so'm
RAQIBLAR MINIMAL NARXI: {min_competitor_price:,.0f} so'm
FARQ: {diff_pct:+.1f}%

Narxni o'zgartirish kerakmi? Qaysi yo'nalishda? Nima uchun?"""
    else:
        return f"""Ты эксперт по ценообразованию на Uzum. Дай краткий совет (100-150 слов, на русском):

ТОВАР: {product_name}
МОЯ ЦЕНА: {my_price:,.0f} сум
СРЕДНЯЯ ЦЕНА КОНКУРЕНТОВ: {avg_competitor_price:,.0f} сум
МИН. ЦЕНА КОНКУРЕНТОВ: {min_competitor_price:,.0f} сум
РАЗНИЦА: {diff_pct:+.1f}%

Нужно ли менять цену? В какую сторону? Почему?"""


def build_storage_advice_prompt(storage_items: list, lang: str = "ru") -> str:
    """Ombor holati uchun Gemini prompt."""
    critical = [s for s in storage_items if s.days_stored >= 53]
    if not critical:
        if lang == "uz":
            return "Ombor holati yaxshi. Hech qanday muammo yo'q."
        return "Состояние склада хорошее. Проблем нет."

    items_info = "\n".join(
        f"- Nakładnoy #{s.invoice_number}: {s.days_stored} kun, {s.total_accepted} dona"
        for s in critical[:5]
    )

    if lang == "uz":
        return f"""Uzum ombor menejeri sifatida maslahat ber (100 so'z, o'zbek tilida):

MUDDATI YAQINLASHGAN TOVARLAR (60 kun limit):
{items_info}

Nima qilish kerak? Narx tushirish, aksiya o'tkazish yoki boshqa choralar?"""
    else:
        return f"""Как менеджер склада Uzum, дай совет (100 слов, на русском):

ТОВАРЫ С ИСТЕКАЮЩИМ СРОКОМ (лимит 60 дней):
{items_info}

Что делать? Снизить цену, провести акцию или другие меры?"""
