"""
Uzum Seller OpenAPI wrapper.
"""
import asyncio
import logging
import datetime
import ssl
import aiohttp
import json

from utils.helpers import safe_float, safe_int

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

_sku_debug_done = False  # Faqat bir marta log qilinsin


async def get_products(api_key: str, shop_id: int) -> list[dict]:
    global _sku_debug_done
    params = {"size": 100, "page": 0}
    try:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key, params)
    except UzumAPIError:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key)

    if isinstance(data, list):
        products = data
    else:
        products = (
            data.get("productList")
            or data.get("products")
            or data.get("payload", {}).get("products", [])
            or []
        )

    # SKU struktura debug — faqat ko'p SKU bo'lsa va birinchi marta
    if products and not _sku_debug_done:
        for p in products:
            skus = p.get("skuList", [])
            if len(skus) > 1:
                logger.info(f"[SKU_DEBUG] Mahsulot: {p.get('title', '?')[:40]}")
                logger.info(f"[SKU_DEBUG] SKU soni: {len(skus)}")
                sku = skus[0]
                logger.info(f"[SKU_DEBUG] SKU barcha keylar: {list(sku.keys())}")
                # Barcha fieldlarni loglaymiz
                for key, val in sku.items():
                    if val is not None and val != "" and val != 0:
                        logger.info(f"[SKU_DEBUG]   '{key}' = {json.dumps(val, ensure_ascii=False)[:200] if isinstance(val, (dict, list)) else val}")
                _sku_debug_done = True
                break

    return products


def calc_total_qty(product: dict) -> int:
    return sum(int(s.get("quantityActive") or 0) for s in product.get("skuList", []))


def _get_sku_variant_name(sku: dict, lang: str = "ru") -> str:
    """
    SKU dan variant nomini olish.
    Log da aniqlandi:
      characteristicsList = [
        {"characteristicTitle": {"uz": "Rang", "ru": "Цвет"},
         "characteristicValue": {"uz": "Alvon", "ru": "Алый"}}
      ]
      skuTitle = "АЛЫЙ"
    """

    # ✅ FORMAT 1 (aniq tasdiqlangan): characteristicsList
    char_list = sku.get("characteristicsList") or []
    if char_list and isinstance(char_list, list):
        vals = []
        for c in char_list:
            if not isinstance(c, dict):
                continue
            char_val = c.get("characteristicValue") or {}
            if isinstance(char_val, dict):
                # Foydalanuvchi tiliga mos qiymat
                val = char_val.get(lang) or char_val.get("ru") or char_val.get("uz") or ""
            else:
                val = str(char_val)
            if val and str(val).strip():
                vals.append(str(val).strip())
        if vals:
            return " / ".join(vals)

    # ✅ FORMAT 2: skuTitle (to'g'ridan SKU nomi)
    sku_title = sku.get("skuTitle") or ""
    if sku_title and str(sku_title).strip():
        return str(sku_title).strip()

    # Format 3: characteristics (eski format)
    chars = sku.get("characteristics") or []
    if chars and isinstance(chars, list):
        vals = []
        for c in chars:
            if isinstance(c, dict):
                val = c.get("charValue") or c.get("value") or c.get("name") or ""
            else:
                val = str(c) if c else ""
            if val and str(val).strip():
                vals.append(str(val).strip())
        if vals:
            return " / ".join(vals)

    # Format 4: charValues
    char_values = sku.get("charValues") or []
    if char_values and isinstance(char_values, list):
        vals = []
        for c in char_values:
            if isinstance(c, dict):
                val = c.get("value") or c.get("title") or c.get("name") or ""
            else:
                val = str(c) if c else ""
            if val and str(val).strip():
                vals.append(str(val).strip())
        if vals:
            return " / ".join(vals)

    # Format 5: sellerItemCode (sotuvchi o'z kodi)
    seller_code = sku.get("sellerItemCode") or ""
    if seller_code and str(seller_code).strip():
        return str(seller_code).strip()

    # Oxirgi: sku ID
    sku_id = sku.get("skuId") or sku.get("id") or "?"
    return f"#{sku_id}"


def format_product_skus(product: dict, lang: str = "ru") -> str:
    """Mahsulotni barcha SKU variantlari bilan ko'rsatish. Nom BIR MARTA."""
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
        # Ko'p SKU: nom BIR MARTA
        if lang == "uz":
            header = f"{icon} <b>{short}</b> (jami: <b>{total_qty}</b> dona)"
        else:
            header = f"{icon} <b>{short}</b> (всего: <b>{total_qty}</b> шт.)"
        lines = [header]
        for sku in skus:
            qty = int(sku.get("quantityActive") or 0)
            price = safe_float(sku.get("price") or sku.get("purchasePrice"))
            variant = _get_sku_variant_name(sku, lang)
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


async def get_fbs_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
) -> list[dict]:
    """
    Buyurtmalar olish. 5 ta endpoint sinab ko'riladi.
    Agar hamma 403 bo'lsa — bo'sh list qaytaradi.
    """
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()

    endpoints = [
        ("/v2/fbs/orders",
         {"dateFrom": date_from, "dateTo": date_to, "limit": 100, "offset": 0},
         lambda d: (d.get("payload", {}).get("orders") or d.get("orders") or
                    (d if isinstance(d, list) else []))),
        ("/v1/finance/orders",
         {"dateFrom": date_from, "dateTo": date_to, "limit": 100, "offset": 0},
         lambda d: (d.get("orderItems") or d.get("orders") or d.get("content") or
                    (d if isinstance(d, list) else []))),
        ("/v1/order/list",
         {"dateFrom": date_from, "dateTo": date_to, "limit": 100},
         lambda d: (d.get("orders") or d.get("orderList") or
                    (d if isinstance(d, list) else []))),
        ("/v1/order",
         {"dateFrom": date_from, "dateTo": date_to, "limit": 100},
         lambda d: (d.get("orders") or d.get("orderList") or
                    (d if isinstance(d, list) else []))),
        ("/v2/order",
         {"dateFrom": date_from, "dateTo": date_to, "limit": 100},
         lambda d: (d.get("orders") or d.get("payload", {}).get("orders") or
                    (d if isinstance(d, list) else []))),
    ]

    for endpoint, params, extractor in endpoints:
        try:
            data = await _get(endpoint, api_key, params)
            orders = extractor(data)
            if orders and isinstance(orders, list) and len(orders) > 0:
                logger.info(f"[ORDERS] ✅ {endpoint}: {len(orders)} ta buyurtma")
                return orders
            else:
                raw = json.dumps(data, ensure_ascii=False)[:300]
                logger.info(f"[ORDERS] {endpoint}: bo'sh. Raw: {raw}")
        except UzumAuthError:
            logger.warning(f"[ORDERS] {endpoint}: 403 ruxsat yo'q")
        except Exception as e:
            logger.warning(f"[ORDERS] {endpoint}: {e}")

    logger.warning("[ORDERS] Hamma endpoint 403 — ruxsat kerak!")
    return []


async def get_sales_stats_from_products(api_key: str, shop_id: int) -> dict:
    """
    API buyurtmalar uchun ruxsat bermasa — mahsulot SKU lardan
    quantitySold asosida sotuv statistikasini hisoblash.
    Bu taxminiy ma'lumot.
    """
    try:
        products = await get_products(api_key, shop_id)
        total_sold = 0
        total_returned = 0
        total_revenue = 0.0
        low_stock_count = 0
        out_count = 0

        for p in products:
            for sku in p.get("skuList", []):
                sold = int(sku.get("quantitySold") or 0)
                returned = int(sku.get("quantityReturned") or 0)
                price = float(sku.get("price") or sku.get("purchasePrice") or 0)
                qty = int(sku.get("quantityActive") or 0)
                avg = float(sku.get("avgdsales") or 0)

                total_sold += sold
                total_returned += returned
                total_revenue += sold * price

                if qty == 0:
                    out_count += 1
                elif qty <= 5:
                    low_stock_count += 1

        return {
            "total_sold": total_sold,
            "total_returned": total_returned,
            "total_revenue": total_revenue,
            "low_stock_count": low_stock_count,
            "out_count": out_count,
            "products_count": len(products),
        }
    except Exception as e:
        logger.warning(f"get_sales_stats_from_products: {e}")
        return {}


async def get_fbs_orders_period(api_key: str, days: int = 7) -> list[dict]:
    return await get_fbs_orders(
        api_key,
        date_from=_days_ago_ms(days),
        date_to=_now_ms(),
    )


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


# ─── Invoices ────────────────────────────────────────────────────────────────

async def get_invoices(api_key: str, shop_id: int) -> list[dict]:
    try:
        data = await _get(f"/v1/shop/{shop_id}/invoice", api_key)
        if isinstance(data, list):
            return data
        return data.get("invoices") or data.get("payload", []) or []
    except Exception as e:
        logger.warning(f"get_invoices: {e}")
        return []


# ─── Returns ─────────────────────────────────────────────────────────────────

async def get_returns(api_key: str, date_from: int = None, date_to: int = None) -> list[dict]:
    if date_from is None:
        date_from = _days_ago_ms(90)
    if date_to is None:
        date_to = _now_ms()

    params = {"dateFrom": date_from, "dateTo": date_to}

    for endpoint in ["/v1/return", "/v2/return"]:
        try:
            data = await _get(endpoint, api_key, params)
            raw = json.dumps(data, ensure_ascii=False)[:500]
            logger.info(f"[RETURNS] {endpoint}: {raw}")

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                items = (
                    data.get("payload") or data.get("returns")
                    or data.get("content") or data.get("items") or []
                )
                if items:
                    return items
        except Exception as e:
            logger.warning(f"[RETURNS] {endpoint}: {e}")

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
    return await _post(
        f"/v1/product/{shop_id}/sendPriceData", api_key, {"priceData": price_data}
    )


# ─── Orders summary ──────────────────────────────────────────────────────────

def summarize_orders(orders: list[dict]) -> dict:
    if orders:
        statuses = list({str(o.get("status") or o.get("orderStatus") or "?") for o in orders})
        logger.info(f"[ORDERS] Statuslar: {statuses}")

    total = len(orders)

    def has(o: dict, *kw) -> bool:
        st = str(o.get("status") or o.get("orderStatus") or "").upper()
        return any(k.upper() in st for k in kw)

    delivered = sum(1 for o in orders if has(o,
        "DELIVER", "DONE", "COMPLET", "FINISH", "CLOSED", "PAID", "RECEIVED"))
    cancelled = sum(1 for o in orders if has(o,
        "CANCEL", "REJECT", "RETURN", "REFUND"))
    processing = sum(1 for o in orders if has(o,
        "PACKAG", "PROCESS", "PENDING", "WAIT", "NEW", "CREAT", "ACCEPT",
        "AWAITING", "CONFIRM"))
    shipped = sum(1 for o in orders if has(o,
        "SHIP", "TRANSIT", "DELIVER_IN", "SENT", "COURIER", "WAY"))

    revenue = 0.0
    for o in orders:
        if has(o, "DELIVER", "DONE", "COMPLET", "FINISH", "CLOSED", "PAID", "RECEIVED"):
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



# ─── Finance orders: parsing + aggregation (additive) ─────────────────────────
# These functions are ADDED for the finance-overlay reporting feature. They consume
# the raw dict returned by `get_finance_orders` (Uzumchi signature) and do NOT change
# any existing contract (get_products / summarize_orders / parse_invoices remain as-is).

def extract_finance_orders(data) -> list[dict]:
    """
    `/v1/finance/orders` javobidan buyurtma elementlarini ajratib olish.
    `orderItems` / `orders` / `items` / `content` kalitlarini tekshiradi,
    yalang'och list ham qabul qilinadi.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    return (
        data.get("orderItems")
        or data.get("orders")
        or data.get("items")
        or data.get("content")
        or []
    )


def parse_finance_order(raw: dict) -> dict:
    """
    Bitta finance-order elementini normallashtirish.
    Barcha raqamli maydonlar 0 ga (amount esa 1 ga) default bo'ladi.
    """
    if not isinstance(raw, dict):
        raw = {}
    return {
        "id":            str(raw.get("id") or ""),
        "order_id":      str(raw.get("orderId") or ""),
        "status":        raw.get("status") or "",
        "date":          safe_int(raw.get("date")),
        "date_issued":   safe_int(raw.get("dateIssued")),
        "sell_price":    safe_float(raw.get("sellPrice") or raw.get("sellerPrice")),
        "commission":    safe_float(raw.get("commission")),
        "seller_profit": safe_float(raw.get("sellerProfit")),
        "logistics":     safe_float(raw.get("logisticDeliveryFee")),
        "amount":        safe_int(raw.get("amount") or 1, 1),
        "sku_title":     raw.get("skuTitle") or "",
        "product_title": raw.get("productTitle") or "",
    }


def summarize_finance_orders(finance_raw) -> dict:
    """
    Finance-orderlar bo'yicha agregatlar.
    Returns:
        {count, revenue, commission, logistics, net_profit, margin_pct}
    margin_pct = net_profit / revenue * 100 (revenue == 0 bo'lsa 0).
    """
    items = [parse_finance_order(o) for o in extract_finance_orders(finance_raw)]
    revenue = sum(o["sell_price"] for o in items)
    commission = sum(o["commission"] for o in items)
    logistics = sum(o["logistics"] for o in items)
    net_profit = sum(o["seller_profit"] for o in items)
    margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0
    return {
        "count": len(items),
        "revenue": revenue,
        "commission": commission,
        "logistics": logistics,
        "net_profit": net_profit,
        "margin_pct": margin_pct,
    }
