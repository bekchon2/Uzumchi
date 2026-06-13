"""
Raqib narx monitoring servisi.
Uzum ochiq sayt API orqali mahsulot narxlarini qidiradi.
"""
import asyncio
import logging
import ssl
import aiohttp

logger = logging.getLogger(__name__)

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Uzum public API endpointlari (ro'yxatdan sinab o'tiladi)
SEARCH_ENDPOINTS = [
    {
        "url": "https://api.uzum.uz/api/v2/search/products",
        "params": lambda q, n: {"query": q, "size": n, "page": 0},
        "products_key": lambda d: d.get("payload", {}).get("products", []) if isinstance(d, dict) else [],
    },
    {
        "url": "https://api.uzum.uz/api/main/search/product",
        "params": lambda q, n: {"keyword": q, "size": n, "page": 0},
        "products_key": lambda d: d.get("payload", {}).get("products", []) if isinstance(d, dict) else [],
    },
    {
        "url": "https://api.uzum.uz/api/v1/search",
        "params": lambda q, n: {"query": q, "limit": n},
        "products_key": lambda d: (
            d.get("products", []) or d.get("items", [])
            if isinstance(d, dict) else (d if isinstance(d, list) else [])
        ),
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,uz;q=0.7",
    "Origin": "https://uzum.uz",
    "Referer": "https://uzum.uz/",
}


async def search_products_by_name(query: str, limit: int = 20) -> list[dict]:
    """
    Uzum katalogidan mahsulot qidirish. Bir nechta endpoint sinab ko'riladi.
    """
    await asyncio.sleep(0.5)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=HEADERS
    ) as session:
        for ep in SEARCH_ENDPOINTS:
            try:
                params = ep["params"](query, limit)
                async with session.get(
                    ep["url"], params=params,
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            data = await resp.json(content_type=None)

                        products = ep["products_key"](data)
                        if products:
                            logger.info(f"Competitor search OK: {ep['url']} → {len(products)} items")
                            return products
                        else:
                            logger.info(f"Empty result from {ep['url']}, keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    else:
                        logger.warning(f"Competitor search {ep['url']} → HTTP {resp.status}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout: {ep['url']}")
            except Exception as e:
                logger.warning(f"Error {ep['url']}: {e}")

    logger.warning(f"All endpoints failed for '{query}'")
    return []


async def get_product_prices(product_name: str, limit: int = 15) -> list[dict]:
    """
    Mahsulot nomi bo'yicha bozor narxlarini olish.
    """
    products = await search_products_by_name(product_name, limit=limit)
    result = []

    for p in products:
        try:
            # Narx — turli formatlarda bo'lishi mumkin
            price = None
            for sku in (p.get("skuList") or p.get("skus") or []):
                val = (
                    sku.get("purchasePrice") or sku.get("sellPrice")
                    or sku.get("price") or sku.get("salePrice")
                )
                if val and float(val) > 0:
                    price = float(val)
                    break

            if price is None:
                price = float(
                    p.get("minSellPrice") or p.get("sellPrice") or p.get("price")
                    or p.get("minPrice") or p.get("currentPrice") or 0
                )

            if price <= 0:
                continue

            title = str(p.get("title") or p.get("name") or p.get("productName") or "—")[:60]
            shop = p.get("shop") or p.get("seller") or {}
            shop_name = (
                shop.get("name") or shop.get("shopName") or shop.get("title")
                if isinstance(shop, dict) else str(shop)
            ) or "—"
            rating = float(p.get("rating") or p.get("reviewRating") or p.get("avgRating") or 0)

            result.append({
                "title": title,
                "price": price,
                "shop": str(shop_name)[:40],
                "rating": rating,
                "product_id": p.get("id"),
            })
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            continue

    return result


def format_competitor_report(
    my_product_name: str,
    my_price: float,
    competitors: list[dict],
    lang: str = "ru"
) -> str:
    """Raqib narxlari tahlili."""
    if not competitors:
        return (
            f"🔍 <b>{my_product_name[:40]}</b>\n\nRaqiblar topilmadi."
            if lang == "uz" else
            f"🔍 <b>{my_product_name[:40]}</b>\n\nКонкуренты не найдены."
        )

    sorted_c = sorted(competitors, key=lambda x: x["price"])
    min_p = sorted_c[0]["price"]
    max_p = sorted_c[-1]["price"]
    avg_p = sum(c["price"] for c in sorted_c) / len(sorted_c)
    cheaper = sum(1 for c in sorted_c if c["price"] < my_price) if my_price > 0 else 0
    pricier = sum(1 for c in sorted_c if c["price"] > my_price * 1.05) if my_price > 0 else 0

    if lang == "uz":
        lines = [
            f"🔍 <b>Raqib narx tahlili</b>",
            f"📦 <b>{my_product_name[:40]}</b>",
        ]
        if my_price > 0:
            lines.append(f"💰 Mening narxim: <b>{my_price:,.0f} so'm</b>")
        lines += [
            f"",
            f"📊 <b>Bozor ({len(sorted_c)} raqib):</b>",
            f"  🟢 Eng arzon: {min_p:,.0f} so'm",
            f"  🟡 O'rtacha: {avg_p:,.0f} so'm",
            f"  🔴 Eng qimmat: {max_p:,.0f} so'm",
        ]
        if my_price > 0:
            if my_price <= min_p * 1.05:
                lines.append("✅ Siz bozorda eng arzon!")
            elif my_price > avg_p * 1.1:
                diff = ((my_price / avg_p) - 1) * 100
                lines.append(f"⚠️ Narxingiz o'rtachadan {diff:.0f}% yuqori")
            else:
                lines.append("🟡 Narxingiz raqobatbardosh")
            lines.append(f"💡 Sizdan arzon: {cheaper} ta | Sizdan qimmat: {pricier} ta")

        lines.append("\n<b>Top-5 raqib:</b>")
        for i, c in enumerate(sorted_c[:5], 1):
            if my_price > 0:
                icon = "🟢" if c["price"] < my_price else ("🟡" if c["price"] <= my_price * 1.05 else "🔴")
            else:
                icon = f"{i}."
            stars = f" ⭐{c['rating']:.1f}" if c["rating"] > 0 else ""
            lines.append(f"{icon} {c['shop']}: <b>{c['price']:,.0f}</b> so'm{stars}")
    else:
        lines = [
            f"🔍 <b>Анализ цен конкурентов</b>",
            f"📦 <b>{my_product_name[:40]}</b>",
        ]
        if my_price > 0:
            lines.append(f"💰 Моя цена: <b>{my_price:,.0f} сум</b>")
        lines += [
            f"",
            f"📊 <b>Рынок ({len(sorted_c)} конк.):</b>",
            f"  🟢 Минимум: {min_p:,.0f} сум",
            f"  🟡 Среднее: {avg_p:,.0f} сум",
            f"  🔴 Максимум: {max_p:,.0f} сум",
        ]
        if my_price > 0:
            if my_price <= min_p * 1.05:
                lines.append("✅ Вы на минимуме рынка!")
            elif my_price > avg_p * 1.1:
                diff = ((my_price / avg_p) - 1) * 100
                lines.append(f"⚠️ Цена выше среднего на {diff:.0f}%")
            else:
                lines.append("🟡 Цена конкурентоспособна")
            lines.append(f"💡 Дешевле вас: {cheaper} | Дороже вас: {pricier}")

        lines.append("\n<b>Топ-5 конкурентов:</b>")
        for i, c in enumerate(sorted_c[:5], 1):
            if my_price > 0:
                icon = "🟢" if c["price"] < my_price else ("🟡" if c["price"] <= my_price * 1.05 else "🔴")
            else:
                icon = f"{i}."
            stars = f" ⭐{c['rating']:.1f}" if c["rating"] > 0 else ""
            lines.append(f"{icon} {c['shop']}: <b>{c['price']:,.0f}</b> сум{stars}")

    return "\n".join(lines)
