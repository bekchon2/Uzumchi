"""
Raqib narx monitoring.
Foydalanuvchi Uzum tovar sahifa URL sini beradi.
Bot o'sha tovarning narxini Uzum API dan oladi.
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

# Brauzer kabi headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://uzum.uz/",
    "Origin": "https://uzum.uz",
    "x-iid": "00000000-0000-0000-0000-000000000001",
}


def extract_product_id_from_url(url: str) -> str | None:
    """
    Uzum URL dan product ID ajratish.
    https://uzum.uz/ru/product/tovar-nomi-2855035?skuId=...
    → "2855035"
    """
    url = url.strip()
    # /product/slug-12345 formatidan
    match = re.search(r'/product/[^/?#]+-(\d+)', url)
    if match:
        return match.group(1)
    # Oxirgi raqam bloki
    match = re.search(r'/product/(\d+)', url)
    if match:
        return match.group(1)
    # Xohlagan 5+ raqam
    match = re.search(r'[^\d](\d{5,})', url)
    if match:
        return match.group(1)
    return None


def extract_sku_id_from_url(url: str) -> str | None:
    """URL dan skuId parametrini olish."""
    match = re.search(r'[?&]skuId=(\d+)', url)
    return match.group(1) if match else None


async def get_product_info_by_url(uzum_url: str) -> dict | None:
    """
    Uzum tovar URL dan tovar ma'lumotlarini olish.
    """
    product_id = extract_product_id_from_url(uzum_url)
    if not product_id:
        logger.warning(f"URL dan ID ajratilmadi: {uzum_url}")
        return None

    logger.info(f"[COMPETITOR] Product ID: {product_id}, URL: {uzum_url}")

    # API endpointlar — brauzer kabi so'rov
    api_urls = [
        f"https://api.uzum.uz/api/v2/product/{product_id}",
        f"https://api.uzum.uz/api/v1/product/{product_id}",
        f"https://api.uzum.uz/api/product/{product_id}",
    ]

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=HEADERS
    ) as session:
        for api_url in api_urls:
            try:
                await asyncio.sleep(1.0)
                async with session.get(
                    api_url,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    logger.info(f"[COMPETITOR] {api_url} → {resp.status}")
                    if resp.status != 200:
                        continue
                    try:
                        data = await resp.json()
                    except Exception:
                        data = await resp.json(content_type=None)

                    logger.info(f"[COMPETITOR] Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

                    # Response parse
                    product = (
                        data.get("payload")
                        or data.get("product")
                        or (data if isinstance(data, dict) else None)
                    )
                    if not product or not isinstance(product, dict):
                        continue

                    title = (
                        product.get("title") or product.get("name")
                        or product.get("productName") or "—"
                    )

                    # Narxlar
                    skus = product.get("skuList") or product.get("skus") or []
                    prices = []
                    for s in skus:
                        p_val = (
                            s.get("purchasePrice") or s.get("sellPrice")
                            or s.get("price") or s.get("minSellPrice") or 0
                        )
                        try:
                            v = float(p_val)
                            if v > 0:
                                prices.append(v)
                        except Exception:
                            pass

                    if not prices:
                        for key in ["minSellPrice", "price", "sellPrice", "currentPrice", "minPrice"]:
                            val = product.get(key)
                            if val:
                                try:
                                    v = float(val)
                                    if v > 0:
                                        prices.append(v)
                                        break
                                except Exception:
                                    pass

                    if not prices:
                        logger.warning(f"[COMPETITOR] Narx topilmadi: {product_id}")
                        continue

                    min_price = min(prices)
                    max_price = max(prices)
                    avg_price = sum(prices) / len(prices)

                    shop = product.get("shop") or product.get("seller") or {}
                    shop_name = (
                        shop.get("name") or shop.get("shopName") or shop.get("title")
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

                    logger.info(f"[COMPETITOR] OK: {title[:30]}, min={min_price}, shop={shop_name}")
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

            except asyncio.TimeoutError:
                logger.warning(f"[COMPETITOR] Timeout: {api_url}")
            except Exception as e:
                logger.warning(f"[COMPETITOR] Xato {api_url}: {e}")

    logger.warning(f"[COMPETITOR] Barcha endpointlar ishlamadi: {product_id}")
    return None


async def check_saved_urls(
    api_key: str,
    my_products: list[dict],
    saved_urls: list[dict],
    lang: str = "ru"
) -> str:
    """
    Saqlangan URL lar bo'yicha narx taqqoslash.
    """
    if not saved_urls:
        if lang == "uz":
            return (
                "📋 Kuzatilayotgan tovarlar yo'q.\n\n"
                "🔗 URL qo'shish uchun «URL qo'shish» tugmasini bosing."
            )
        return (
            "📋 Нет отслеживаемых товаров.\n\n"
            "🔗 Нажмите «Добавить URL» чтобы добавить товар."
        )

    header = "🔍 <b>Narx monitoringi</b>\n\n" if lang == "uz" else "🔍 <b>Мониторинг цен</b>\n\n"
    lines = [header]

    for item in saved_urls:
        product_name = item.get("product_name") or "—"
        uzum_url = item.get("uzum_url") or ""

        # Mening narximni topish
        my_price = 0.0
        for p in my_products:
            p_title = (p.get("title") or p.get("name") or "").lower()
            if (
                product_name.lower() in p_title
                or p_title in product_name.lower()
                or any(word in p_title for word in product_name.lower().split()[:2])
            ):
                for sku in p.get("skuList", [])[:1]:
                    my_price = float(sku.get("price") or sku.get("purchasePrice") or 0)
                break

        # Bozor narxini olish
        info = await get_product_info_by_url(uzum_url)
        await asyncio.sleep(0.5)

        if info:
            market_min = info.get("min_price") or info.get("price") or 0
            market_max = info.get("max_price") or market_min
            rating = info.get("rating", 0)
            reviews = info.get("reviews", 0)
            shop = info.get("shop", "—")

            if my_price > 0 and market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                if abs(pct) < 3:
                    icon = "🟡"
                elif my_price < market_min:
                    icon = "🟢"
                else:
                    icon = "🔴"
                diff_str = f" ({pct:+.0f}%)"
            else:
                icon = "⚪"
                diff_str = ""

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
                f"   {no_data}\n"
                f"   <code>{uzum_url[:50]}</code>"
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
            f"✅ <b>Saqlandi:</b> {product_name}",
            f"",
            f"📦 <b>Uzumdagi tovar:</b>",
            f"   {title[:50]}",
            f"   🏪 {shop}",
        ]
        if rating > 0:
            lines.append(f"   ⭐ {rating:.1f} ({reviews} sharh)")
        lines.append(f"")
        lines.append(f"💰 <b>Narxlar:</b>")
        if market_min > 0:
            lines.append(f"   Minimal: {market_min:,.0f} so'm")
        if market_max > market_min:
            lines.append(f"   Maksimal: {market_max:,.0f} so'm")
        if my_price > 0:
            lines.append(f"   Mening: {my_price:,.0f} so'm")
            if market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"\n✅ Narxingiz bozordan {abs(pct):.0f}% arzon!")
                elif pct > 10:
                    lines.append(f"\n⚠️ Narxingiz bozordan {pct:.0f}% qimmat")
                else:
                    lines.append(f"\n🟡 Narxingiz bozor bilan teng")
    else:
        lines = [
            f"✅ <b>Сохранено:</b> {product_name}",
            f"",
            f"📦 <b>Товар на Uzum:</b>",
            f"   {title[:50]}",
            f"   🏪 {shop}",
        ]
        if rating > 0:
            lines.append(f"   ⭐ {rating:.1f} ({reviews} отз.)")
        lines.append(f"")
        lines.append(f"💰 <b>Цены:</b>")
        if market_min > 0:
            lines.append(f"   Минимум: {market_min:,.0f} сум")
        if market_max > market_min:
            lines.append(f"   Максимум: {market_max:,.0f} сум")
        if my_price > 0:
            lines.append(f"   Моя: {my_price:,.0f} сум")
            if market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"\n✅ Ваша цена на {abs(pct):.0f}% ниже рынка!")
                elif pct > 10:
                    lines.append(f"\n⚠️ Ваша цена на {pct:.0f}% выше рынка")
                else:
                    lines.append(f"\n🟡 Ваша цена на уровне рынка")

    return "\n".join(lines)
