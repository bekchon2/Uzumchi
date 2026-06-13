"""
Uzum Seller OpenAPI wrapper.
"""
import asyncio
import logging
import datetime
import ssl
import aiohttp
import json

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.uzum.uz/api/seller-openapi"

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class UzumAPIError(Exception):
    pass

class UzumAuthError(UzumAPIError):
    pass

class UzumRateLimitError(UzumAPIError):
    pass


async def _get(endpoint: str, api_key: str, params: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            logger.info(f"GET {endpoint} → {resp.status}")
            if resp.status == 200:
                return await resp.json()
            elif resp.status in (401, 403):
                raise UzumAuthError(f"Auth error {resp.status}: {endpoint}")
            elif resp.status == 429:
                if retry > 0:
                    await asyncio.sleep(2)
                    return await _get(endpoint, api_key, params, retry - 1)
                raise UzumRateLimitError("Rate limit exceeded")
            else:
                text = await resp.text()
                raise UzumAPIError(f"HTTP {resp.status}: {text[:300]}")


async def _post(endpoint: str, api_key: str, payload: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 429:
                if retry > 0:
                    await asyncio.sleep(2)
                    return await _post(endpoint, api_key, payload, retry - 1)
                raise UzumRateLimitError("Rate limit exceeded")
            else:
                text = await resp.text()
                raise UzumAPIError(f"HTTP {resp.status}: {text[:200]}")


# ─── Shops ───────────────────────────────────────────────────────────────────

async def get_shops(api_key: str) -> list[dict]:
    data = await _get("/v1/shops", api_key)
    if isinstance(data, list):
        return data
    return data.get("shops", [])


# ─── Products ────────────────────────────────────────────────────────────────

async def get_products(api_key: str, shop_id: int) -> list[dict]:
    params = {"size": 100, "page": 0}
    try:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key, params)
    except UzumAPIError:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key)

    if isinstance(data, list):
        return data
    products = (
        data.get("productList")
        or data.get("products")
        or data.get("payload", {}).get("products", [])
        or []
    )
    # Debug: birinchi mahsulotning to'liq strukturasini log qilish
    if products:
        p = products[0]
        skus = p.get("skuList", [])
        if skus:
            logger.info(f"[DEBUG] First SKU keys: {list(skus[0].keys())}")
            # characteristics strukturasini log qilish
            chars = skus[0].get("characteristics") or skus[0].get("charValues") or []
            if chars:
                logger.info(f"[DEBUG] Characteristics sample: {json.dumps(chars[:2], ensure_ascii=False)}")
            else:
                # Boshqa possible key lar
                for key in skus[0]:
                    val = skus[0][key]
                    if isinstance(val, (list, dict)) and val:
                        logger.info(f"[DEBUG] SKU field '{key}': {json.dumps(val, ensure_ascii=False)[:200]}")
    return products


def calc_total_qty(product: dict) -> int:
    """Mahsulotning BARCHA SKU lari bo'yicha jami qoldiq."""
    total = 0
    for sku in product.get("skuList", []):
        total += int(sku.get("quantityActive") or 0)
    return total


def _get_sku_variant_name(sku: dict) -> str:
    """
    SKU dan rang/o'lcham nomini olish.
    Uzum API da turli formatlar bo'lishi mumkin.
    """
    # Format 1: characteristics = [{"charName": "Цвет", "charValue": "Красный"}]
    chars = sku.get("characteristics") or []
    if chars and isinstance(chars, list):
        vals = []
        for c in chars:
            if isinstance(c, dict):
                val = (
                    c.get("charValue") or c.get("value")
                    or c.get("name") or c.get("title") or ""
                )
                if val:
                    vals.append(str(val))
        if vals:
            return " / ".join(vals)

    # Format 2: charValues = [{"value": "Красный"}]
    char_values = sku.get("charValues") or []
    if char_values and isinstance(char_values, list):
        vals = []
        for c in char_values:
            if isinstance(c, dict):
                val = c.get("value") or c.get("title") or c.get("name") or ""
                if val:
                    vals.append(str(val))
        if vals:
            return " / ".join(vals)

    # Format 3: color, size to'g'ridan to'g'ri maydon
    color = sku.get("color") or sku.get("Color") or ""
    size = sku.get("size") or sku.get("Size") or ""
    if color or size:
        return " / ".join(filter(None, [str(color), str(size)]))

    # Format 4: title yoki name
    title = sku.get("title") or sku.get("name") or ""
    if title:
        return str(title)[:30]

    # Format 5: id bo'yicha
    sku_id = sku.get("id") or sku.get("skuId") or "?"
    return f"#{sku_id}"


def format_product_skus(product: dict, lang: str = "ru") -> str:
    """
    Mahsulotni barcha SKU variantlari bilan ko'rsatish.
    """
    name = product.get("title") or product.get("name") or "—"
    skus = product.get("skuList", [])
    if not skus:
        return f"• {name[:50]}"

    from utils.helpers import stock_icon, safe_float, safe_int, short_name

    total_qty = sum(int(s.get("quantityActive") or 0) for s in skus)
    icon = stock_icon(total_qty)

    if len(skus) == 1:
        sku = skus[0]
        qty = safe_int(sku.get("quantityActive"))
        price = safe_float(sku.get("price") or sku.get("purchasePrice"))
        avg = safe_float(sku.get("avgdsales"))
        days = safe_int(sku.get("forecastOutOfStock", 9999))
        days_str = str(days) if days < 9999 else "∞"
        if lang == "uz":
            return (
                f"{icon} <b>{short_name(name, 45)}</b>\n"
                f"   📊 Qoldiq: <b>{qty}</b> dona | 💰 {price:,.0f} so'm\n"
                f"   📈 Kunlik: {avg:.1f} | ⏳ {days_str} kun"
            )
        return (
            f"{icon} <b>{short_name(name, 45)}</b>\n"
            f"   📊 Остаток: <b>{qty}</b> шт. | 💰 {price:,.0f} сум\n"
            f"   📈 В день: {avg:.1f} | ⏳ {days_str} дн."
        )
    else:
        # Ko'p SKU
        header = (
            f"{icon} <b>{short_name(name, 45)}</b> (jami: <b>{total_qty}</b> dona)"
            if lang == "uz" else
            f"{icon} <b>{short_name(name, 45)}</b> (всего: <b>{total_qty}</b> шт.)"
        )
        lines = [header]
        for sku in skus:
            qty = int(sku.get("quantityActive") or 0)
            price = safe_float(sku.get("price") or sku.get("purchasePrice"))
            variant = _get_sku_variant_name(sku)
            sku_icon = stock_icon(qty)
            if lang == "uz":
                lines.append(f"   {sku_icon} {variant}: <b>{qty}</b> dona | {price:,.0f} so'm")
            else:
                lines.append(f"   {sku_icon} {variant}: <b>{qty}</b> шт. | {price:,.0f} сум")
        return "\n".join(lines)


# ─── Orders ──────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def _days_ago_ms(days: int) -> int:
    dt = datetime.datetime.now() - datetime.timedelta(days=days)
    return int(dt.timestamp() * 1000)


async def get_finance_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to, "limit": limit, "offset": offset}
    return await _get("/v1/finance/orders", api_key, params)


async def get_fbs_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
) -> list[dict]:
    """
    Buyurtmalar olish. Barcha endpointlarni sinab ko'radi.
    MUHIM: Buyurtma statuslari turlicha bo'lishi mumkin — barcha variantlarni loglaydi.
    """
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()

    # 1. FBS v2
    try:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 100, "offset": 0}
        data = await _get("/v2/fbs/orders", api_key, params)
        orders = (
            data.get("payload", {}).get("orders", [])
            or data.get("orders", [])
            or (data if isinstance(data, list) else [])
        )
        if orders:
            # Debug: birinchi buyurtma strukturasini ko'rish
            logger.info(f"[DEBUG] FBS v2 order sample keys: {list(orders[0].keys())}")
            logger.info(f"[DEBUG] FBS v2 order status sample: {orders[0].get('status')}")
            logger.info(f"[DEBUG] FBS v2 orders count: {len(orders)}")
            return orders
        logger.info(f"[DEBUG] FBS v2 returned empty, payload: {json.dumps(data, ensure_ascii=False)[:500]}")
    except (UzumAuthError, UzumAPIError) as e:
        logger.warning(f"FBS v2 failed: {e}")

    # 2. Finance orders
    try:
        fin = await get_finance_orders(api_key, date_from, date_to)
        items = fin.get("orderItems", []) or []
        if items:
            logger.info(f"[DEBUG] Finance order sample keys: {list(items[0].keys())}")
            logger.info(f"[DEBUG] Finance order status: {items[0].get('status')}")
        logger.info(f"Finance orders count: {len(items)}")
        # Finance orders ham qaytaramiz, hatto bo'sh bo'lsa ham
        return items
    except Exception as e:
        logger.warning(f"Finance orders failed: {e}")

    # 3. v1 order
    try:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 100}
        data = await _get("/v1/order", api_key, params)
        orders = (
            data.get("orders", [])
            or data.get("orderList", [])
            or (data if isinstance(data, list) else [])
        )
        if orders:
            logger.info(f"[DEBUG] v1/order sample: {list(orders[0].keys())}")
        logger.info(f"v1/order count: {len(orders)}")
        return orders
    except Exception as e:
        logger.warning(f"v1/order failed: {e}")

    return []


async def get_fbs_orders_period(api_key: str, days: int = 7) -> list[dict]:
    return await get_fbs_orders(
        api_key,
        date_from=_days_ago_ms(days),
        date_to=_now_ms(),
    )


# ─── Invoices ────────────────────────────────────────────────────────────────

async def get_invoices(api_key: str, shop_id: int) -> list[dict]:
    try:
        data = await _get(f"/v1/shop/{shop_id}/invoice", api_key)
        if isinstance(data, list):
            return data
        return data.get("invoices") or data.get("payload", []) or []
    except UzumAPIError as e:
        logger.warning(f"get_invoices error: {e}")
        return []


# ─── Returns ─────────────────────────────────────────────────────────────────

async def get_returns(api_key: str, date_from: int = None, date_to: int = None) -> list[dict]:
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()

    params = {"dateFrom": date_from, "dateTo": date_to}

    # 1. /v1/return
    try:
        data = await _get("/v1/return", api_key, params)
        if isinstance(data, list):
            logger.info(f"[DEBUG] Returns list, count: {len(data)}")
            if data:
                logger.info(f"[DEBUG] Return sample: {json.dumps(data[0], ensure_ascii=False)[:400]}")
            return data
        items = (
            data.get("payload", [])
            or data.get("returns", [])
            or data.get("content", [])
            or data.get("items", [])
            or []
        )
        logger.info(f"[DEBUG] Returns keys: {list(data.keys())}, count: {len(items)}")
        if items:
            logger.info(f"[DEBUG] Return sample: {json.dumps(items[0], ensure_ascii=False)[:400]}")
            return items
        # Bo'sh bo'lsa ham qaytaramiz
        return items
    except Exception as e:
        logger.warning(f"get_returns /v1/return error: {e}")

    # 2. /v2/return
    try:
        data = await _get("/v2/return", api_key, params)
        if isinstance(data, list):
            return data
        items = data.get("payload", []) or data.get("returns", []) or []
        logger.info(f"Returns /v2/return: {len(items)}")
        return items
    except Exception as e:
        logger.warning(f"get_returns /v2/return error: {e}")

    return []


async def get_today_returns(api_key: str) -> list[dict]:
    return await get_returns(api_key, date_from=_days_ago_ms(1))


# ─── Finance expenses ────────────────────────────────────────────────────────

async def get_expenses(api_key: str, date_from: int = None, date_to: int = None) -> dict | None:
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to}
    try:
        return await _get("/v1/finance/expenses", api_key, params)
    except Exception:
        return None


# ─── Price update ────────────────────────────────────────────────────────────

async def send_price_data(api_key: str, shop_id: int, price_data: list[dict]) -> dict:
    return await _post(f"/v1/product/{shop_id}/sendPriceData", api_key, {"priceData": price_data})


# ─── Orders summary ──────────────────────────────────────────────────────────

def summarize_orders(orders: list[dict]) -> dict:
    """
    Buyurtmalardan statistika. Status field turlicha bo'lishi mumkin.
    Barcha statuslarni loglaydi (debug uchun).
    """
    if orders:
        statuses = list({o.get("status", "?") for o in orders})
        logger.info(f"[DEBUG] Order statuses found: {statuses}")

    total = len(orders)

    # Status nomlariga tolerant yondashuv
    def match(o: dict, *keywords) -> bool:
        st = str(o.get("status") or o.get("orderStatus") or "").upper()
        return any(k in st for k in keywords)

    delivered = sum(1 for o in orders if match(o, "DELIVER", "DONE", "COMPLETED", "FINISH"))
    cancelled = sum(1 for o in orders if match(o, "CANCEL", "REJECT", "RETURN"))
    processing = sum(1 for o in orders if match(o, "PROCESS", "PENDING", "WAIT", "NEW", "CREATED"))
    shipped = sum(1 for o in orders if match(o, "SHIP", "TRANSIT", "WAY", "SENT"))

    # Tushum: yetkazilgan + yetkazilishi aniq bo'lganlar
    revenue = 0.0
    for o in orders:
        if match(o, "DELIVER", "DONE", "COMPLETED"):
            revenue += float(
                o.get("finalPrice") or o.get("price") or
                o.get("orderPrice") or o.get("totalPrice") or 0
            )

    return {
        "total": total,
        "delivered": delivered,
        "cancelled": cancelled,
        "processing": processing,
        "shipped": shipped,
        "revenue": revenue,
    }
