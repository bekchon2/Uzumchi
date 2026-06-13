"""
Raqib narx monitoring.
Foydalanuvchi Uzum tovar sahifa URL sini beradi.
"""
import asyncio
import logging
import ssl
import re
import json
import aiohttp

logger = logging.getLogger(__name__)

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://uzum.uz/",
    "Origin": "https://uzum.uz",
    "x-iid": "00000000-0000-0000-0000-000000000001",
}


def extract_product_id_from_url(url: str) -> str | None:
    url = url.strip()
    match = re.search(r'/product/[^/?#]+-(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/product/(\d+)', url)
    if match:
        return match.group(1)
    match = re.search(r'[^\d](\d{5,})', url)
    if match:
        return match.group(1)
    return None


def _extract_prices_from_product(product: dict) -> list[float]:
    """
    Uzum product JSON dan barcha narxlarni olish.
    Log da to'liq payload strukturasi ko'rinadi.
    """
    prices = []

    # Log — birinchi marta to'liq ko'rish uchun
    logger.info(f"[COMP_PARSE] product keys: {list(product.keys())}")

    # 1. skuList — asosiy
    sku_list = (
        product.get("skuList")
        or product.get("skus")
        or product.get("offers")
        or []
    )
    if sku_list:
        logger.info(f"[COMP_PARSE] skuList[0] keys: {list(sku_list[0].keys()) if sku_list else []}")
        for sku in sku_list:
            for key in ["purchasePrice", "sellPrice", "price", "minSellPrice",
                        "salePrice", "currentPrice", "fullPrice", "cost"]:
                val = sku.get(key)
                if val:
                    try:
                        v = float(val)
                        if v > 100:  # so'mda bo'ladi
                            prices.append(v)
                            break
                    except Exception:
                        pass

    # 2. To'g'ridan product ichida
    for key in ["minSellPrice", "price", "sellPrice", "currentPrice",
                "minPrice", "maxPrice", "salePrice", "minFullPrice", "maxSalePrice"]:
        val = product.get(key)
        if val:
            try:
                v = float(val)
                if v > 100:
                    prices.append(v)
            except Exception:
                pass

    # 3. Characteristicsdan emas — balki boshqa nested field
    for key in product:
        val = product[key]
        if isinstance(val, dict):
            for sub_key in ["price", "sellPrice", "minPrice", "cost"]:
                sub_val = val.get(sub_key)
                if sub_val:
                    try:
                        v = float(sub_val)
                        if v > 100:
                            prices.append(v)
                    except Exception:
                        pass

    # Takrorlanganlarni olib tashlash
    prices = list(set(prices))
    logger.info(f"[COMP_PARSE] Topilgan narxlar: {prices}")
    return prices


async def get_product_info_by_url(uzum_url: str) -> dict | None:
    product_id = extract_product_id_from_url(uzum_url)
    if not product_id:
        logger.warning(f"URL dan ID ajratilmadi: {uzum_url}")
        return None

    logger.info(f"[COMPETITOR] Product ID: {product_id}")

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=HEADERS
    ) as session:
        # Ishlagan endpoint: /api/product/{id}
        api_url = f"https://api.uzum.uz/api/product/{product_id}"
        try:
            await asyncio.sleep(0.8)
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                logger.info(f"[COMPETITOR] {api_url} → {resp.status}")
                if resp.status != 200:
                    # 400 bo'lsa lang parametr bilan urinib ko'r
                    async with session.get(
                        f"{api_url}?lang=ru",
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp2:
                        logger.info(f"[COMPETITOR] {api_url}?lang=ru → {resp2.status}")
                        if resp2.status != 200:
                            return None
                        resp = resp2

                try:
                    data = await resp.json()
                except Exception:
                    data = await resp.json(content_type=None)

                logger.info(f"[COMPETITOR] Top-level keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

                # payload ni olish
                payload = data.get("payload") or data
                if not isinstance(payload, dict):
                    logger.warning(f"[COMPETITOR] payload dict emas: {type(payload)}")
                    return None

                # To'liq payload log (birinchi marta)
                logger.info(f"[COMPETITOR] payload keys: {list(payload.keys())}")

                # Narxlarni olish
                prices = _extract_prices_from_product(payload)

                if not prices:
                    # Fallback: barcha nested dict larni tekshirish
                    logger.warning(f"[COMPETITOR] Narx topilmadi, payload to'liq: {json.dumps(payload, ensure_ascii=False)[:1000]}")
                    return None

                min_price = min(prices)
                max_price = max(prices)

                # Tovar nomi
                title = (
                    payload.get("title") or payload.get("name")
                    or payload.get("productName") or "—"
                )

                # Do'kon
                shop = payload.get("shop") or payload.get("seller") or payload.get("store") or {}
                if isinstance(shop, dict):
                    shop_name = (
                        shop.get("name") or shop.get("shopName")
                        or shop.get("title") or "—"
                    )
                else:
                    shop_name = str(shop) or "—"

                # Reyting
                rating = float(
                    payload.get("rating") or payload.get("avgRating")
                    or payload.get("reviewRating") or 0
                )
                reviews = int(
                    payload.get("reviewCount") or payload.get("totalReviews")
                    or payload.get("reviewsCount") or 0
                )

                logger.info(f"[COMPETITOR] OK: '{title[:30]}', min={min_price}, shop={shop_name}")
                return {
                    "title": str(title)[:60],
                    "price": (min_price + max_price) / 2,
                    "min_price": min_price,
                    "max_price": max_price,
                    "shop": shop_name,
                    "rating": rating,
                    "reviews": reviews,
                    "product_id": product_id,
                    "url": uzum_url,
                }

        except asyncio.TimeoutError:
            logger.warning(f"[COMPETITOR] Timeout: {api_url}")
        except Exception as e:
            logger.warning(f"[COMPETITOR] Xato: {e}")

    return None


async def check_saved_urls(
    api_key: str,
    my_products: list[dict],
    saved_urls: list[dict],
    lang: str = "ru"
) -> str:
    if not saved_urls:
        if lang == "uz":
            return "📋 Kuzatilayotgan tovarlar yo'q.\n\n🔗 «URL qo'shish» tugmasini bosing."
        return "📋 Нет отслеживаемых товаров.\n\n🔗 Нажмите «Добавить URL»."

    header = "🔍 <b>Narx monitoringi</b>\n\n" if lang == "uz" else "🔍 <b>Мониторинг цен</b>\n\n"
    lines = [header]

    for item in saved_urls:
        product_name = item.get("product_name") or "—"
        uzum_url = item.get("uzum_url") or ""

        my_price = 0.0
        for p in my_products:
            p_title = (p.get("title") or p.get("name") or "").lower()
            pn_lower = product_name.lower()
            if pn_lower in p_title or p_title in pn_lower:
                for sku in p.get("skuList", [])[:1]:
                    my_price = float(sku.get("price") or sku.get("purchasePrice") or 0)
                break

        info = await get_product_info_by_url(uzum_url)
        await asyncio.sleep(0.5)

        if info:
            market_min = info.get("min_price") or info.get("price") or 0
            rating = info.get("rating", 0)
            reviews = info.get("reviews", 0)
            shop = info.get("shop", "—")

            if my_price > 0 and market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                icon = "🟡" if abs(pct) < 3 else ("🟢" if my_price < market_min else "🔴")
                diff_str = f" ({pct:+.0f}%)"
            else:
                icon, diff_str = "⚪", ""

            stars = f" ⭐{rating:.1f}" if rating > 0 else ""
            rev_str = f" ({reviews} отз.)" if reviews > 0 else ""

            if lang == "uz":
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Mening: {my_price:,.0f} | Bozor: {market_min:,.0f}{diff_str}\n"
                    f"   🏪 {shop}{stars}{rev_str}"
                )
            else:
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Моя: {my_price:,.0f} | Рынок мин: {market_min:,.0f}{diff_str}\n"
                    f"   🏪 {shop}{stars}{rev_str}"
                )
        else:
            no_data = "Ma'lumot olinmadi" if lang == "uz" else "Данные не получены"
            lines.append(
                f"❓ <b>{product_name[:30]}</b>\n"
                f"   {no_data}"
            )
        lines.append("")

    return "\n".join(lines).strip()


def format_single_product_report(
    product_name: str,
    my_price: float,
    info: dict,
    lang: str = "ru"
) -> str:
    market_min = info.get("min_price", 0) or info.get("price", 0)
    market_max = info.get("max_price", 0) or market_min
    rating = info.get("rating", 0)
    reviews = info.get("reviews", 0)
    shop = info.get("shop", "—")
    title = info.get("title", product_name)

    if lang == "uz":
        lines = [
            f"✅ <b>Saqlandi: {product_name}</b>", "",
            f"📦 {title[:50]}",
            f"🏪 {shop}",
        ]
        if rating > 0:
            lines.append(f"⭐ {rating:.1f} ({reviews} sharh)")
        lines += ["", "💰 <b>Narxlar:</b>"]
        if market_min > 0:
            lines.append(f"   Min: {market_min:,.0f} so'm")
        if market_max > market_min:
            lines.append(f"   Max: {market_max:,.0f} so'm")
        if my_price > 0:
            lines.append(f"   Mening: {my_price:,.0f} so'm")
            if market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"✅ Narxingiz bozordan {abs(pct):.0f}% arzon!")
                elif pct > 10:
                    lines.append(f"⚠️ Narxingiz bozordan {pct:.0f}% qimmat")
                else:
                    lines.append("🟡 Narxingiz bozor bilan teng")
    else:
        lines = [
            f"✅ <b>Сохранено: {product_name}</b>", "",
            f"📦 {title[:50]}",
            f"🏪 {shop}",
        ]
        if rating > 0:
            lines.append(f"⭐ {rating:.1f} ({reviews} отз.)")
        lines += ["", "💰 <b>Цены:</b>"]
        if market_min > 0:
            lines.append(f"   Мин: {market_min:,.0f} сум")
        if market_max > market_min:
            lines.append(f"   Макс: {market_max:,.0f} сум")
        if my_price > 0:
            lines.append(f"   Моя: {my_price:,.0f} сум")
            if market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"✅ Ваша цена на {abs(pct):.0f}% ниже рынка!")
                elif pct > 10:
                    lines.append(f"⚠️ Ваша цена на {pct:.0f}% выше рынка")
                else:
                    lines.append("🟡 Ваша цена на уровне рынка")

    return "\n".join(lines)
