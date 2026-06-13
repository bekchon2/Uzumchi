"""
Raqib narx monitoring.
Foydalanuvchi Uzum tovar sahifa URL sini beradi.
Bot tovar nomini HTML dan avtomatik oladi, narxni API dan oladi.
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

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://uzum.uz/",
    "Origin": "https://uzum.uz",
    "x-iid": "00000000-0000-0000-0000-000000000001",
}

HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def extract_product_id_from_url(url: str) -> str | None:
    """
    Uzum URL dan product ID ajratish.
    https://uzum.uz/ru/product/tovar-nomi-2855035?skuId=...  → "2855035"
    """
    url = url.strip()
    # /product/slug-12345 formatidan
    match = re.search(r'/product/[^/?#]+-(\d{4,})', url)
    if match:
        return match.group(1)
    # /product/12345
    match = re.search(r'/product/(\d{4,})', url)
    if match:
        return match.group(1)
    # URL da xohlagan 6+ raqam
    match = re.search(r'(\d{6,})', url)
    if match:
        return match.group(1)
    return None


async def get_product_title_from_html(url: str) -> str | None:
    """
    Uzum tovar sahifasining HTML dan tovar nomini olish.
    <title> yoki og:title yoki h1 tagidan.
    """
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
            headers=HTML_HEADERS
        ) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"HTML fetch {url} → {resp.status}")
                    return None
                html = await resp.text()

                # 1. og:title meta tag (eng ishonchli)
                match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    logger.info(f"[COMP] og:title: {title[:50]}")
                    return title

                # 2. <title> tegi
                match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    # " | Uzum" yoki " - Uzum" ni olib tashlash
                    title = re.sub(r'\s*[|–-]\s*Uzum.*$', '', title, flags=re.IGNORECASE).strip()
                    if title and len(title) > 5:
                        logger.info(f"[COMP] title tag: {title[:50]}")
                        return title

                # 3. JSON-LD strukturali ma'lumotlar
                match = re.search(r'"name"\s*:\s*"([^"]{5,})"', html)
                if match:
                    title = match.group(1).strip()
                    logger.info(f"[COMP] JSON-LD name: {title[:50]}")
                    return title

    except Exception as e:
        logger.warning(f"[COMP] HTML fetch error: {e}")
    return None


async def get_product_info_by_url(uzum_url: str) -> dict | None:
    """
    Uzum tovar URL dan to'liq ma'lumot olish:
    1. HTML sahifadan tovar nomini olish
    2. API dan narx va statistikani olish
    """
    product_id = extract_product_id_from_url(uzum_url)
    if not product_id:
        logger.warning(f"[COMP] URL dan ID ajratilmadi: {uzum_url}")
        return None

    logger.info(f"[COMP] Product ID: {product_id}, URL: {uzum_url}")

    # Parallel ravishda HTML va API dan olish
    html_task = asyncio.create_task(get_product_title_from_html(uzum_url))
    api_task = asyncio.create_task(_get_product_from_api(product_id))

    title_from_html = await html_task
    api_data = await api_task

    if api_data:
        # API ma'lumoti bor — HTML nomini birlashtirish
        if title_from_html and not api_data.get("title") or api_data.get("title") == "—":
            api_data["title"] = title_from_html
        return api_data

    # API ishlamadi — HTML dan nom, narx yo'q
    if title_from_html:
        logger.info(f"[COMP] Faqat HTML nom topildi: {title_from_html[:40]}")
        return {
            "title": title_from_html[:60],
            "price": 0,
            "min_price": 0,
            "max_price": 0,
            "shop": "—",
            "rating": 0,
            "reviews": 0,
            "product_id": product_id,
            "url": uzum_url,
            "html_only": True,  # Faqat HTML dan olindi
        }

    return None


async def _get_product_from_api(product_id: str) -> dict | None:
    """API dan tovar ma'lumotlarini olish."""
    api_endpoints = [
        f"https://api.uzum.uz/api/product/{product_id}",
        f"https://api.uzum.uz/api/v2/product/{product_id}",
        f"https://api.uzum.uz/api/product/{product_id}?lang=ru",
    ]

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=API_HEADERS
    ) as session:
        for api_url in api_endpoints:
            try:
                await asyncio.sleep(0.5)
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    logger.info(f"[COMP] {api_url} → {resp.status}")
                    if resp.status != 200:
                        continue

                    try:
                        data = await resp.json()
                    except Exception:
                        data = await resp.json(content_type=None)

                    # payload null bo'lsa — tovar yashirilgan
                    raw_payload = data.get("payload")
                    if raw_payload is None:
                        logger.warning(f"[COMP] payload=null: tovar yashirilgan yoki mavjud emas")
                        continue

                    payload = raw_payload if isinstance(raw_payload, dict) else data
                    if not isinstance(payload, dict) or not payload:
                        continue

                    logger.info(f"[COMP] payload keys: {list(payload.keys())[:10]}")

                    prices = _extract_prices(payload)
                    if not prices:
                        logger.warning(f"[COMP] Narx topilmadi, payload keys: {list(payload.keys())}")
                        continue

                    min_p = min(prices)
                    max_p = max(prices)

                    title = (
                        payload.get("title") or payload.get("name")
                        or payload.get("productName") or "—"
                    )
                    shop = payload.get("shop") or payload.get("seller") or {}
                    shop_name = (
                        shop.get("name") or shop.get("shopName")
                        if isinstance(shop, dict) else str(shop)
                    ) or "—"
                    rating = float(payload.get("rating") or payload.get("avgRating") or 0)
                    reviews = int(payload.get("reviewCount") or payload.get("totalReviews") or 0)

                    return {
                        "title": str(title)[:60],
                        "price": (min_p + max_p) / 2,
                        "min_price": min_p,
                        "max_price": max_p,
                        "shop": shop_name,
                        "rating": rating,
                        "reviews": reviews,
                        "product_id": product_id,
                        "url": "",
                    }

            except asyncio.TimeoutError:
                logger.warning(f"[COMP] Timeout: {api_url}")
            except Exception as e:
                logger.warning(f"[COMP] {api_url}: {e}")

    return None


def _extract_prices(payload: dict) -> list[float]:
    """Payload dan barcha narxlarni olish."""
    prices = []

    # skuList
    for sku in (payload.get("skuList") or payload.get("skus") or []):
        for key in ["purchasePrice", "sellPrice", "price", "minSellPrice",
                    "salePrice", "currentPrice", "fullPrice", "cost"]:
            val = sku.get(key)
            if val:
                try:
                    v = float(val)
                    if v > 100:
                        prices.append(v)
                        break
                except Exception:
                    pass

    # To'g'ridan
    for key in ["minSellPrice", "price", "sellPrice", "currentPrice",
                "minPrice", "maxPrice", "salePrice"]:
        val = payload.get(key)
        if val:
            try:
                v = float(val)
                if v > 100:
                    prices.append(v)
            except Exception:
                pass

    return list(set(prices))


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
