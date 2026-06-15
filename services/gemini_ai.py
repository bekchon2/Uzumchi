"""
AI maslahatchi servisi (provider-agnostic).

Bir nechta provayderni qo'llab-quvvatlaydi: Groq -> OpenRouter -> Gemini.
Ommaviy kirish nuqtasi `ask_gemini(prompt, lang)` nomi saqlangan, shuning uchun
handlerlar o'zgartirilishi shart emas.
"""
import logging
import ssl
import aiohttp
import os
import json
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    # Defense-in-depth: ensure .env is loaded even if this module is imported
    # before main.py calls load_dotenv(). Idempotent — safe to call repeatedly.
    load_dotenv()
except Exception:  # pragma: no cover - dotenv always present in this project
    pass

logger = logging.getLogger(__name__)

# NOTE: Provider env vars (GROQ_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY /
# AI_PROVIDER / *_MODEL) are read at CALL TIME inside `_all_providers()` and
# `_select_providers()` — NOT captured into module-level constants here. Reading
# at import time was the root cause of the "AI not configured" bug: `main.py`
# calls `load_dotenv()` *after* importing the handlers that import this module,
# so import-time reads saw an empty environment.

# Permissive SSL (kept for Gemini host, as before, to reach it from restricted hosts).
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


@dataclass(frozen=True)
class ProviderConfig:
    name: str            # "groq" | "openrouter" | "gemini"
    api_key: str
    endpoint: str
    model: str
    kind: str            # "openai" | "gemini"


def _all_providers() -> dict[str, ProviderConfig]:
    """Build the set of *configured* providers (those whose key is non-empty).

    Env vars (keys AND models) are read lazily here via `os.getenv` at CALL TIME,
    so values loaded by `load_dotenv()` after this module is imported are honored.
    """
    groq_key = os.getenv("GROQ_API_KEY", "")
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    gem_key = os.getenv("GEMINI_API_KEY", "")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    or_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    gem_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    out: dict[str, ProviderConfig] = {}
    if groq_key:
        out["groq"] = ProviderConfig(
            "groq", groq_key,
            "https://api.groq.com/openai/v1/chat/completions",
            groq_model, "openai",
        )
    if or_key:
        out["openrouter"] = ProviderConfig(
            "openrouter", or_key,
            "https://openrouter.ai/api/v1/chat/completions",
            or_model, "openai",
        )
    if gem_key:
        out["gemini"] = ProviderConfig(
            "gemini", gem_key,
            f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent",
            gem_model, "gemini",
        )
    return out


def _select_providers() -> list[ProviderConfig]:
    """Ordered provider list: Groq -> OpenRouter -> Gemini, filtered to configured.

    When AI_PROVIDER names an available provider, return exactly that one.
    Empty list when nothing is configured. `AI_PROVIDER` is read at call time.
    """
    available = _all_providers()
    if not available:
        return []
    provider = os.getenv("AI_PROVIDER", "").strip().lower()
    if provider and provider in available:
        return [available[provider]]
    order = ["groq", "openrouter", "gemini"]
    return [available[name] for name in order if name in available]


async def _call_openai_compatible(cfg: ProviderConfig, prompt: str) -> str:
    """Groq + OpenRouter share the OpenAI chat-completions schema (default TLS)."""
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    async with aiohttp.ClientSession() as session:  # default TLS for these hosts
        async with session.post(
            cfg.endpoint, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                # Log status + body (first ~300 chars); never log the API key.
                logger.error(f"{cfg.name} {resp.status}: {body[:300]}")
                raise RuntimeError(f"{cfg.name} HTTP {resp.status}")
            data = json.loads(body)
            return (data["choices"][0]["message"]["content"] or "").strip()


async def _call_gemini(cfg: ProviderConfig, prompt: str) -> str:
    """Google Gemini generateContent (v1beta); key as query param, permissive SSL."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    ) as session:
        async with session.post(
            cfg.endpoint, params={"key": cfg.api_key}, json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                # Log status + body (first ~300 chars); never log the API key.
                logger.error(f"gemini {resp.status}: {body[:300]}")
                raise RuntimeError(f"gemini HTTP {resp.status}")
            data = json.loads(body)
            cands = data.get("candidates", [])
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                if parts:
                    return (parts[0].get("text", "") or "").strip()
            return ""


async def ask_gemini(prompt: str, lang: str = "ru") -> str:
    """
    Provider-agnostic completion. Name kept for call-site compatibility.

    No API-key format check: any non-empty provider key is usable.
    Returns the first non-empty answer; falls back across providers; returns a
    localized message when no provider is configured or all providers fail.
    """
    providers = _select_providers()
    if not providers:
        # No network call when nothing is configured.
        if lang == "uz":
            return (
                "⚠️ AI sozlanmagan. .env ga GROQ_API_KEY (yoki OPENROUTER_API_KEY / "
                "GEMINI_API_KEY) qo'shing."
            )
        return (
            "⚠️ AI не настроен. Добавьте GROQ_API_KEY (или OPENROUTER_API_KEY / "
            "GEMINI_API_KEY) в .env."
        )

    last_error = ""
    for cfg in providers:
        try:
            if cfg.kind == "openai":
                text = await _call_openai_compatible(cfg, prompt)
            else:
                text = await _call_gemini(cfg, prompt)
            if text:
                return text
            last_error = f"{cfg.name}: empty response"
            logger.warning(f"AI provider {cfg.name} returned empty response")
        except Exception as e:
            last_error = f"{cfg.name}: {e}"
            logger.error(f"AI provider {cfg.name} failed: {e}")
            continue  # try next configured provider

    logger.error(f"All AI providers failed. Last: {last_error}")
    if lang == "uz":
        return "⚠️ AI javob bermadi. Keyinroq urinib ko'ring."
    return "⚠️ AI не ответил. Попробуйте позже."


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
