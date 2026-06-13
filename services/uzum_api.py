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
            logger.info(f"GET {endpoint} params={params} → {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                return data
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

    # SKU struktura debug — birinchi ishga tushganda log qilish
    if products:
        p = products[0]
        skus = p.get("skuList", [])
        if len(skus) > 1:
            # Ko'p SKU li mahsulotning strukturasini to'liq loglaymiz
            sku = skus[0]
            all_keys = list(sku.keys())
            logger.info(f"[SKU_DEBUG] keys: {all_keys}")
            # Barcha field larni tekshirish
            for key in all_keys:
                val = sku.get(key)
                if isinstance(val, (list, dict)) and val:
                    logger.info(f"[SKU_DEBUG] '{key}' = {json.dumps(val, ensure_ascii=False)[:300]}")
                elif isinstance(val, str) and len(val) > 1:
                    logger.info(f"[SKU_DEBUG] '{key}' = {val}")
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
    Uzum API da `characteristics` array bo'ladi:
    [{"charName": "Цвет", "charValue": "Красный"}, ...]
    """
    # Format 1 (asosiy): characteristics = [{"charName": "...", "charValue": "..."}]
    chars = sku.get("characteristics") or []
    if chars and isinstance(chars, list):
        vals = []
        for c in chars:
            if not isinstance(c, dict):
                continue
            val = (
                c.get("charValue") or c.get("value")
                or c.get("name") or c.get("title") or ""
            )
            if val and str(val).strip():
                vals.append(str(val).strip())
        if vals:
            return " / ".join(vals)

    # Format 2: charValues = [{"value": "..."}]
    char_values = sku.get("charValues") or []
    if char_values and isinstance(char_values, list):
        vals = []
        for c in char_values:
            if isinstance(c, dict):
                val = (
                    c.get("value") or c.get("title")
                    or c.get("name") or c.get("charValue") or ""
                )
                if val and str(val).strip():
                    vals.append(str(val).strip())
        if vals:
            return " / ".join(vals)

    # Format 3: to'g'ridan maydon
    for field in ["color", "Color", "colour", "size", "Size", "variant"]:
        val = sku.get(field)
        if val and str(val).strip() and str(val).strip().lower() not in ("none", "null", ""):
            return str(val).strip()

    # Format 4: title yoki name (lekin mahsulot nomidan farqli bo'lsa)
    title = sku.get("title") or sku.get("name") or ""
    if title:
        return str(title)[:40]

    # Oxirgi: ID
    sku_id = sku.get("id") or sku.get("skuId") or "?"
    return f"ID:{sku_id}"


def format_product_skus(product: dict, lang: str = "ru") -> str:
    """
    Mahsulotni barcha SKU variantlari bilan ko'rsatish.
    Ko'p SKU bo'lsa: faqat variantlar, nom BIR MARTA.
    """
    name = product.get("title") or product.get("name") or "—"
    skus = product.get("skuList", [])
    if not skus:
        return f"• {name[:50]}"

    from utils.helpers import stock_icon, safe_float, safe_int, short_name

    total_qty = sum(int(s.get("quantityActive") or 0) for s in skus)
    icon = stock_icon(total_qty)
    short = short_name(name, 45)

    if len(skus) == 1:
        sku = skus[0]
        qty = safe_int(sku.get("quantityActive"))
        price = safe_float(sku.get("price") or sku.get("purchasePrice"))
        avg = safe_float(sku.get("avgdsales"))
        days = safe_int(sku.get("forecastOutOfStock", 9999))
        days_str = str(days) if days < 9999 else "∞"
        if lang == "uz":
            return (
                f"{icon} <b>{short}</b>\n"
                f"   📊 Qoldiq: <b>{qty}</b> dona | 💰 {price:,.0f} so'm\n"
                f"   📈 Kunlik: {avg:.1f} | ⏳ {days_str} kun"
            )
        return (
            f"{icon} <b>{short}</b>\n"
            f"   📊 Остаток: <b>{qty}</b> шт. | 💰 {price:,.0f} сум\n"
            f"   📈 В день: {avg:.1f} | ⏳ {days_str} дн."
        )
    else:
        # Ko'p SKU: nom BIR MARTA, keyin variantlar
        header = (
            f"{icon} <b>{short}</b> (jami: <b>{total_qty}</b> dona)"
            if lang == "uz" else
            f"{icon} <b>{short}</b> (всего: <b>{total_qty}</b> шт.)"
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
    """GET /v1/finance/orders"""
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()
    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "limit": limit,
        "offset": offset,
    }
    return await _get("/v1/finance/orders", api_key, params)


async def get_fbs_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
) -> list[dict]:
    """
    Buyurtmalar olish.
    Strategiya:
    1. /v2/fbs/orders — FBS buyurtmalar (statuslar: AWAITING_PACKAGING, AWAITING_DELIVER, DELIVERED, CANCELLED)
    2. /v1/finance/orders — moliyaviy buyurtmalar (katta sana oraliqlar uchun)
    Log da to'liq raw javobni ko'rsatadi.
    """
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()

    # --- 1. FBS v2 ---
    try:
        # Swagger bo'yicha parametrlar: dateFrom, dateTo (ms), limit, offset
        params = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": 100,
            "offset": 0,
        }
        data = await _get("/v2/fbs/orders", api_key, params)

        # To'liq raw javobni loglash
        raw_str = json.dumps(data, ensure_ascii=False)[:800]
        logger.info(f"[ORDERS_RAW] /v2/fbs/orders response: {raw_str}")

        # Turli response formatlarini olish
        orders = None
        if isinstance(data, list):
            orders = data
        elif isinstance(data, dict):
            payload = data.get("payload") or {}
            orders = (
                payload.get("orders")
                or payload.get("orderList")
                or data.get("orders")
                or data.get("orderList")
                or data.get("content")
                or []
            )

        if orders:
            logger.info(f"[ORDERS] FBS v2: {len(orders)} ta. Status namunasi: {orders[0].get('status', '?')}")
            return orders
        logger.warning(f"[ORDERS] FBS v2 bo'sh. Data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    except UzumAuthError as e:
        logger.warning(f"[ORDERS] FBS v2 auth xato: {e}")
    except UzumAPIError as e:
        logger.warning(f"[ORDERS] FBS v2 API xato: {e}")

    # --- 2. Finance orders ---
    try:
        fin = await get_finance_orders(api_key, date_from, date_to)
        raw_str = json.dumps(fin, ensure_ascii=False)[:800]
        logger.info(f"[ORDERS_RAW] /v1/finance/orders response: {raw_str}")

        items = (
            fin.get("orderItems")
            or fin.get("orders")
            or fin.get("content")
            or []
        )
        if items:
            logger.info(f"[ORDERS] Finance: {len(items)} ta")
            return items
        logger.warning(f"[ORDERS] Finance bo'sh. Keys: {list(fin.keys())}")

    except UzumAuthError as e:
        logger.warning(f"[ORDERS] Finance auth xato: {e}")
    except Exception as e:
        logger.warning(f"[ORDERS] Finance xato: {e}")

    # --- 3. v1/order ---
    try:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 100}
        data = await _get("/v1/order", api_key, params)
        raw_str = json.dumps(data, ensure_ascii=False)[:500]
        logger.info(f"[ORDERS_RAW] /v1/order response: {raw_str}")

        orders = (
            data.get("orders") or data.get("orderList")
            or data.get("content")
            or (data if isinstance(data, list) else [])
        )
        if orders:
            logger.info(f"[ORDERS] v1/order: {len(orders)} ta")
            return orders

    except Exception as e:
        logger.warning(f"[ORDERS] v1/order xato: {e}")

    logger.error("[ORDERS] Barcha endpointlar bo'sh qaytdi!")
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
    except Exception as e:
        logger.warning(f"get_invoices error: {e}")
        return []


# ─── Returns ─────────────────────────────────────────────────────────────────

async def get_returns(api_key: str, date_from: int = None, date_to: int = None) -> list[dict]:
    """
    Qaytarmalar.
    Log da to'liq raw javob.
    """
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()

    params = {"dateFrom": date_from, "dateTo": date_to}

    for endpoint in ["/v1/return", "/v2/return"]:
        try:
            data = await _get(endpoint, api_key, params)
            raw_str = json.dumps(data, ensure_ascii=False)[:600]
            logger.info(f"[RETURNS_RAW] {endpoint} response: {raw_str}")

            if isinstance(data, list):
                if data:
                    logger.info(f"[RETURNS] {endpoint}: {len(data)} ta. Namuna: {list(data[0].keys())}")
                return data

            if isinstance(data, dict):
                items = (
                    data.get("payload")
                    or data.get("returns")
                    or data.get("content")
                    or data.get("items")
                    or data.get("data")
                    or []
                )
                if items:
                    logger.info(f"[RETURNS] {endpoint}: {len(items)} ta. Keys: {list(data.keys())}")
                    return items
                logger.warning(f"[RETURNS] {endpoint} bo'sh. Keys: {list(data.keys())}")

        except Exception as e:
            logger.warning(f"[RETURNS] {endpoint} xato: {e}")

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
    Buyurtmalar statistikasi.
    Uzum FBS statuslari: AWAITING_PACKAGING, AWAITING_DELIVER, DELIVERED, CANCELLED
    Finance statuslari: COMPLETED, CLOSED, RETURNED, PAID, ...
    """
    if orders:
        statuses = list({str(o.get("status") or o.get("orderStatus") or "?") for o in orders})
        logger.info(f"[ORDERS] Statuslar: {statuses}")

    total = len(orders)

    def has(o: dict, *kw) -> bool:
        st = str(o.get("status") or o.get("orderStatus") or "").upper()
        return any(k.upper() in st for k in kw)

    # Uzum FBS aniq statuslar
    delivered = sum(1 for o in orders if has(o, "DELIVER", "DONE", "COMPLET", "FINISH", "CLOSED", "PAID"))
    cancelled = sum(1 for o in orders if has(o, "CANCEL", "REJECT", "RETURN"))
    processing = sum(1 for o in orders if has(o, "PACKAG", "PROCESS", "PENDING", "WAIT", "NEW", "CREAT", "ACCEPT"))
    shipped = sum(1 for o in orders if has(o, "SHIP", "TRANSIT", "DELIVER_IN", "SENT", "COURIER"))

    revenue = 0.0
    for o in orders:
        if has(o, "DELIVER", "DONE", "COMPLET", "FINISH", "CLOSED", "PAID"):
            revenue += float(
                o.get("finalPrice") or o.get("price") or
                o.get("orderPrice") or o.get("totalPrice") or
                o.get("amount") or 0
            )

    return {
        "total": total,
        "delivered": delivered,
        "cancelled": cancelled,
        "processing": processing,
        "shipped": shipped,
        "revenue": revenue,
    }
