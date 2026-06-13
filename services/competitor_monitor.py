"""
Raqib narx monitoring.
Foydalanuvchi Uzum tovar sahifa URL sini beradi.
Bot o'sha tovarning shaxsiy kabinetdagi narxi bilan taqqoslaydi.
"""
import asyncio
import logging
import ssl
import re
import aiohttp

logger = logging.getLogger(__name__)

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,uz;q=0.7",
    "Origin": "https://uzum.uz",
    "Referer": "https://uzum.uz/",
}


def extract_product_id_from_url(url: str) -> str | None:
    """
    Uzum URL dan product ID ni ajratib olish.
    Formatlar:
    - https://uzum.uz/ru/product/nomi-123456
    - https://uzum.uz/uz/product/nomi-123456
    - https://uzum.uz/product/nomi-123456
    """
    url = url.strip()
    # Oxirgi raqam guruhini olish
    match = re.search(r'/product/[^/?#]*?-?(\d{5,})', url)
    if match:
        return match.group(1)
    # Faqat raqam
    match = re.search(r'(\d{5,})', url)
    if match:
        return match.group(1)
    return None


async def get_product_info_by_url(uzum_url: str) -> dict | None:
    """
    Uzum tovar sahifa URL dan tovar ma'lumotlarini olish.
    Returns: {"title": "...", "price": 99000, "min_price": 80000, "shop": "...", "rating": 4.8, "reviews": 120}
    """
    product_id = extract_product_id_from_url(uzum_url)
    if not product_id:
        logger.warning(f"Cannot extract product ID from URL: {uzum_url}")
        return None

    # Uzum public API dan ma'lumot olish
    api_urls = [
        f"https://api.uzum.uz/api/v2/product/{product_id}",
        f"https://api.uzum.uz/api/v1/product/{product_id}",
        f"https://api.uzum.uz/api/main/product/{product_id}",
    ]

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=HEADERS
    ) as session:
        for api_url in api_urls:
            try:
                await asyncio.sleep(0.5)
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            data = await resp.json(content_type=None)

                        # Response parse
                        product = data.get("payload") or data.get("product") or data
                        if isinstance(product, dict) and product:
                            title = (
                                product.get("title") or product.get("name")
                                or product.get("productName") or "—"
                            )
                            # Narxlar
                            skus = product.get("skuList") or product.get("skus") or []
                            prices = []
                            for s in skus:
                                p = (
                                    s.get("purchasePrice") or s.get("sellPrice")
                                    or s.get("price") or s.get("minSellPrice") or 0
                                )
                                if float(p) > 0:
                                    prices.append(float(p))

                            min_price = min(prices) if prices else 0
                            max_price = max(prices) if prices else 0
                            avg_price = sum(prices) / len(prices) if prices else 0

                            if not prices:
                                min_price = float(
                                    product.get("minSellPrice") or product.get("price")
                                    or product.get("sellPrice") or 0
                                )
                                avg_price = min_price
                                max_price = min_price

                            shop = product.get("shop") or product.get("seller") or {}
                            shop_name = (
                                shop.get("name") or shop.get("shopName")
                                if isinstance(shop, dict) else str(shop)
                            ) or "—"

                            rating = float(
                                product.get("rating") or product.get("avgRating")
                                or product.get("reviewRating") or 0
                            )
                            reviews = int(
                                product.get("reviewCount") or product.get("totalReviews")
                                or product.get("reviewsCount") or 0
                            )

                            logger.info(f"Product found: {title[:40]}, price: {min_price}")
                            return {
                                "title": str(title)[:60],
                                "price": avg_price,
                                "min_price": min_price,
                                "max_price": max_price,
                                "shop": shop_name,
                                "rating": rating,
                                "reviews": reviews,
                                "product_id": product_id,
                                "url": uzum_url,
                            }
                    else:
                        logger.debug(f"API {api_url} → {resp.status}")
            except Exception as e:
                logger.debug(f"Error {api_url}: {e}")
                continue

    logger.warning(f"Could not get product info for URL: {uzum_url}")
    return None


async def check_saved_urls(api_key: str, my_products: list[dict], saved_urls: list[dict], lang: str = "ru") -> str:
    """
    Saqlangan URL lar bo'yicha narx taqqoslash.
    my_products — shaxsiy kabinet mahsulotlari
    saved_urls — DB da saqlangan URL lar
    """
    if not saved_urls:
        if lang == "uz":
            return "📋 Kuzatilayotgan tovarlar yo'q.\n\n🔗 URL qo'shish uchun tugmani bosing."
        return "📋 Нет отслеживаемых товаров.\n\n🔗 Нажмите кнопку чтобы добавить URL."

    lines = [
        "🔍 <b>Narx monitoringi</b>" if lang == "uz" else "🔍 <b>Мониторинг цен</b>",
        f"{'(kuzatilayotgan tovarlar)' if lang == 'uz' else '(отслеживаемые товары)'}",
        ""
    ]

    for item in saved_urls:
        product_name = item.get("product_name") or "—"
        uzum_url = item.get("uzum_url") or ""

        # Mening narximni topish
        my_price = 0.0
        for p in my_products:
            p_name = (p.get("title") or p.get("name") or "").lower()
            if product_name.lower() in p_name or p_name in product_name.lower():
                for sku in p.get("skuList", [])[:1]:
                    my_price = float(sku.get("price") or sku.get("purchasePrice") or 0)
                break

        # Uzum sahifadan narx olish
        info = await get_product_info_by_url(uzum_url)
        await asyncio.sleep(0.5)

        if info:
            market_price = info["min_price"] or info["price"]
            diff = ""
            if my_price > 0 and market_price > 0:
                pct = ((my_price - market_price) / market_price) * 100
                if abs(pct) < 3:
                    icon = "🟡"
                    diff = f" (teng)" if lang == "uz" else f" (равно)"
                elif my_price < market_price:
                    icon = "🟢"
                    diff = f" (-{abs(pct):.0f}%)" if lang == "uz" else f" (-{abs(pct):.0f}%)"
                else:
                    icon = "🔴"
                    diff = f" (+{pct:.0f}%)"
            else:
                icon = "⚪"

            if lang == "uz":
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Mening: {my_price:,.0f} | Bozor min: {market_price:,.0f}{diff}\n"
                    f"   🏪 {info['shop']} | ⭐{info['rating']:.1f} ({info['reviews']} sharh)"
                )
            else:
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Моя: {my_price:,.0f} | Рынок мин: {market_price:,.0f}{diff}\n"
                    f"   🏪 {info['shop']} | ⭐{info['rating']:.1f} ({info['reviews']} отз.)"
                )
        else:
            no_data = "Ma'lumot olinmadi" if lang == "uz" else "Данные не получены"
            lines.append(
                f"⚠️ <b>{product_name[:30]}</b>\n"
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
    """Bitta URL bo'yicha taqqoslash hisoboti."""
    market_min = info.get("min_price", 0) or info.get("price", 0)
    market_max = info.get("max_price", 0) or market_min
    rating = info.get("rating", 0)
    reviews = info.get("reviews", 0)
    shop = info.get("shop", "—")
    title = info.get("title", product_name)

    if lang == "uz":
        lines = [
            f"🔍 <b>Narx taqqoslash</b>",
            f"📦 <b>{title[:50]}</b>",
            f"",
        ]
        if my_price > 0:
            lines.append(f"💰 <b>Mening narxim:</b> {my_price:,.0f} so'm")
        lines += [
            f"🏪 <b>Uzum bozori:</b>",
            f"   Min: {market_min:,.0f} | Max: {market_max:,.0f} so'm",
            f"   Do'kon: {shop}",
            f"   ⭐ {rating:.1f} ({reviews} sharh)",
        ]
        if my_price > 0 and market_min > 0:
            pct = ((my_price - market_min) / market_min) * 100
            if pct < -3:
                lines.append(f"\n✅ Narxingiz bozordan {abs(pct):.0f}% arzon — yaxshi!")
            elif pct > 10:
                lines.append(f"\n⚠️ Narxingiz bozordan {pct:.0f}% qimmat")
            else:
                lines.append(f"\n🟡 Narxingiz bozor bilan teng")
    else:
        lines = [
            f"🔍 <b>Анализ цены</b>",
            f"📦 <b>{title[:50]}</b>",
            f"",
        ]
        if my_price > 0:
            lines.append(f"💰 <b>Моя цена:</b> {my_price:,.0f} сум")
        lines += [
            f"🏪 <b>Рынок Uzum:</b>",
            f"   Мин: {market_min:,.0f} | Макс: {market_max:,.0f} сум",
            f"   Магазин: {shop}",
            f"   ⭐ {rating:.1f} ({reviews} отз.)",
        ]
        if my_price > 0 and market_min > 0:
            pct = ((my_price - market_min) / market_min) * 100
            if pct < -3:
                lines.append(f"\n✅ Ваша цена на {abs(pct):.0f}% ниже рынка — хорошо!")
            elif pct > 10:
                lines.append(f"\n⚠️ Ваша цена на {pct:.0f}% выше рынка")
            else:
                lines.append(f"\n🟡 Ваша цена на уровне рынка")

    return "\n".join(lines)
