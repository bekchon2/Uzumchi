"""
Ikki tilli tarjima moduli: O'zbek (uz) va Rus (ru).
"""

TEXTS = {
    # ── Onboarding ──────────────────────────────────────────────────────────
    "welcome": {
        "uz": (
            "👋 <b>Assalomu alaykum!</b>\n\n"
            "Bu bot Uzum Seller sotuvchi paneli uchun.\n"
            "Tilni tanlang:"
        ),
        "ru": (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Этот бот для продавцов Uzum Seller.\n"
            "Выберите язык:"
        ),
    },
    "lang_selected": {
        "uz": "✅ Til: O'zbek tili tanlandi.",
        "ru": "✅ Язык: Русский выбран.",
    },
    "ask_api_key": {
        "uz": (
            "🔑 <b>Uzum Seller API kalitingizni kiriting:</b>\n\n"
            "📌 API kalitni qayerdan olish:\n"
            "1. seller.uzum.uz ga kiring\n"
            "2. Sozlamalar → API kalitlar\n"
            "3. Yangi kalit yarating\n\n"
            "⚠️ Xabaringiz kiritilgandan keyin o'chirilib, xavfsizlik ta'minlanadi."
        ),
        "ru": (
            "🔑 <b>Введите ваш API ключ Uzum Seller:</b>\n\n"
            "📌 Где взять API ключ:\n"
            "1. Зайдите на seller.uzum.uz\n"
            "2. Настройки → API ключи\n"
            "3. Создайте новый ключ\n\n"
            "⚠️ Ваше сообщение будет удалено для безопасности."
        ),
    },
    "api_checking": {
        "uz": "⏳ Kalit tekshirilmoqda...",
        "ru": "⏳ Проверяю ключ...",
    },
    "api_invalid": {
        "uz": "❌ <b>API kalit noto'g'ri!</b>\nQaytadan kiriting:",
        "ru": "❌ <b>Неверный API ключ!</b>\nВведите снова:",
    },
    "api_success": {
        "uz": "✅ <b>API kalit tasdiqlandi!</b>\nDo'kon: <b>{shop_name}</b>",
        "ru": "✅ <b>API ключ подтверждён!</b>\nМагазин: <b>{shop_name}</b>",
    },
    "setup_complete": {
        "uz": "🎉 <b>Sozlash tugadi!</b> Asosiy menyuga xush kelibsiz.",
        "ru": "🎉 <b>Настройка завершена!</b> Добро пожаловать в главное меню.",
    },

    # ── Main menu ────────────────────────────────────────────────────────────
    "main_menu": {
        "uz": "🏠 <b>Asosiy menyu</b>\nDo'kon: <b>{shop_name}</b>",
        "ru": "🏠 <b>Главное меню</b>\nМагазин: <b>{shop_name}</b>",
    },
    "loading": {
        "uz": "⏳ Ma'lumotlar yuklanmoqda...",
        "ru": "⏳ Загружаю данные...",
    },
    "error_api": {
        "uz": "❌ <b>API xatosi:</b> {error}\n\nAPI kalitingizni tekshiring.",
        "ru": "❌ <b>Ошибка API:</b> {error}\n\nПроверьте ваш API ключ.",
    },
    "no_data": {
        "uz": "📭 Ma'lumot topilmadi.",
        "ru": "📭 Данные не найдены.",
    },

    # ── Products ─────────────────────────────────────────────────────────────
    "products_title": {
        "uz": "📦 <b>Mahsulotlarim</b> ({count} ta):",
        "ru": "📦 <b>Мои товары</b> ({count} шт.):",
    },
    "product_item": {
        "uz": (
            "{icon} <b>{name}</b>\n"
            "   📊 Qoldiq: <b>{qty}</b> dona\n"
            "   💰 Narx: {price:,.0f} so'm\n"
            "   📈 Kunlik: {avg:.1f} ta | ⏳ {days} kun"
        ),
        "ru": (
            "{icon} <b>{name}</b>\n"
            "   📊 Остаток: <b>{qty}</b> шт.\n"
            "   💰 Цена: {price:,.0f} сум\n"
            "   📈 В день: {avg:.1f} шт. | ⏳ {days} дн."
        ),
    },

    # ── Orders ───────────────────────────────────────────────────────────────
    "orders_title": {
        "uz": "🛒 <b>Buyurtmalar</b> (so'nggi 24 soat):",
        "ru": "🛒 <b>Заказы</b> (за последние 24 часа):",
    },
    "orders_summary": {
        "uz": (
            "📊 Jami: <b>{total}</b>\n"
            "✅ Yetkazildi: <b>{delivered}</b>\n"
            "🔄 Jarayonda: <b>{processing}</b>\n"
            "🚚 Yo'lda: <b>{shipped}</b>\n"
            "❌ Bekor qilindi: <b>{cancelled}</b>\n"
            "💰 Tushum: <b>{revenue:,.0f} so'm</b>"
        ),
        "ru": (
            "📊 Всего: <b>{total}</b>\n"
            "✅ Доставлено: <b>{delivered}</b>\n"
            "🔄 В обработке: <b>{processing}</b>\n"
            "🚚 В пути: <b>{shipped}</b>\n"
            "❌ Отменено: <b>{cancelled}</b>\n"
            "💰 Выручка: <b>{revenue:,.0f} сум</b>"
        ),
    },

    # ── Storage ──────────────────────────────────────────────────────────────
    "storage_title": {
        "uz": "🏭 <b>Omborxona holati</b>",
        "ru": "🏭 <b>Состояние склада</b>",
    },
    "storage_free_limit": {
        "uz": "ℹ️ Uzum 60 kun bepul saqlaydi.",
        "ru": "ℹ️ Uzum хранит бесплатно 60 дней.",
    },
    "storage_free_header": {
        "uz": "⏳ <b>Bepul saqlash (60 kun):</b>",
        "ru": "⏳ <b>Бесплатное хранение (60 дней):</b>",
    },
    "storage_free_summary": {
        "uz": "📊 Eng kam qolgan: <b>{min_left}</b> kun | ⚠️ Xavf ostida: <b>{at_risk}</b> ta",
        "ru": "📊 Мин. осталось: <b>{min_left}</b> дн. | ⚠️ Под риском: <b>{at_risk}</b>",
    },
    "storage_free_item": {
        "uz": "{icon} #{invoice_number}: {free_days_left} kun qoldi ({qty} dona)",
        "ru": "{icon} #{invoice_number}: осталось {free_days_left} дн. ({qty} шт.)",
    },
    "storage_free_unavailable": {
        "uz": "ℹ️ Bepul saqlash ma'lumoti hozir mavjud emas.",
        "ru": "ℹ️ Данные о бесплатном хранении сейчас недоступны.",
    },

    # ── Reports ──────────────────────────────────────────────────────────────
    "report_today": {
        "uz": "📊 <b>Bugungi hisobot</b>",
        "ru": "📊 <b>Отчёт за сегодня</b>",
    },
    "report_weekly": {
        "uz": "📈 <b>Haftalik hisobot</b> (so'nggi 7 kun)",
        "ru": "📈 <b>Недельный отчёт</b> (последние 7 дней)",
    },
    "report_monthly": {
        "uz": "📅 <b>Oylik hisobot</b> (so'nggi 30 kun)",
        "ru": "📅 <b>Месячный отчёт</b> (последние 30 дней)",
    },
    "low_stock_header": {
        "uz": "⚠️ <b>Kam qolgan tovarlar:</b>",
        "ru": "⚠️ <b>Товары с низким остатком:</b>",
    },
    "out_of_stock_header": {
        "uz": "🚫 <b>Tugagan tovarlar:</b>",
        "ru": "🚫 <b>Закончившиеся товары:</b>",
    },

    # ── Report 403 product-based fallback (shared: daily / weekly / monthly) ──
    "report_fallback_summary": {
        "uz": (
            "📊 <b>Mahsulot asosidagi taxminiy hisobot</b>\n"
            "📦 Jami sotilgan: <b>{total_sold}</b> dona\n"
            "↩️ Qaytarilgan: <b>{total_returned}</b> dona\n"
            "💰 Taxminiy tushum: <b>{total_revenue:,.0f} so'm</b>\n"
            "🗂 Tovar turlari: <b>{products_count}</b> ta\n"
            "⚠️ Kam qolgan: <b>{low_stock_count}</b> | 🚫 Tugagan: <b>{out_count}</b>"
        ),
        "ru": (
            "📊 <b>Приблизительный отчёт по товарам</b>\n"
            "📦 Всего продано: <b>{total_sold}</b> шт.\n"
            "↩️ Возвращено: <b>{total_returned}</b> шт.\n"
            "💰 Ориентировочная выручка: <b>{total_revenue:,.0f} сум</b>\n"
            "🗂 Видов товаров: <b>{products_count}</b> шт.\n"
            "⚠️ Мало: <b>{low_stock_count}</b> | 🚫 Закончились: <b>{out_count}</b>"
        ),
    },
    "report_fallback_note": {
        "uz": (
            "⚠️ <i>Buyurtma/moliya ma'lumotlari uchun API kalitga ruxsat berilmagan — "
            "ko'rsatilgan raqamlar tovar ma'lumotlaridan olingan taxminiy qiymatlar.</i>"
        ),
        "ru": (
            "⚠️ <i>Доступ к данным заказов/финансов для API-ключа не предоставлен — "
            "показанные цифры приблизительные, рассчитаны из данных о товарах.</i>"
        ),
    },

    # ── Returns ──────────────────────────────────────────────────────────────
    "returns_title": {
        "uz": "↩️ <b>Qaytarmalar</b> (so'nggi 30 kun):",
        "ru": "↩️ <b>Возвраты</b> (за 30 дней):",
    },
    "returns_today_new": {
        "uz": "🆕 Bugungi yangi qaytarmalar: <b>{count}</b>",
        "ru": "🆕 Новых возвратов сегодня: <b>{count}</b>",
    },

    # ── Settings ─────────────────────────────────────────────────────────────
    "settings_title": {
        "uz": "⚙️ <b>Sozlamalar</b>",
        "ru": "⚙️ <b>Настройки</b>",
    },
    "settings_info": {
        "uz": (
            "👤 Foydalanuvchi: @{username}\n"
            "🏪 Faol do'kon: <b>{shop_name}</b> (ID: {shop_id})\n"
            "🌐 Til: O'zbek 🇺🇿\n"
            "🔑 API kalit: {key_status}"
        ),
        "ru": (
            "👤 Пользователь: @{username}\n"
            "🏪 Активный магазин: <b>{shop_name}</b> (ID: {shop_id})\n"
            "🌐 Язык: Русский 🇷🇺\n"
            "🔑 API ключ: {key_status}"
        ),
    },
    "key_set": {
        "uz": "✅ O'rnatilgan",
        "ru": "✅ Установлен",
    },
    "key_not_set": {
        "uz": "❌ O'rnatilmagan",
        "ru": "❌ Не установлен",
    },

    # ── Multi-shop ────────────────────────────────────────────────────────────
    "shop_select_title": {
        "uz": "🏪 <b>Do'koningizni tanlang:</b>",
        "ru": "🏪 <b>Выберите ваш магазин:</b>",
    },
    "shop_switched": {
        "uz": "✅ Do'kon o'zgartirildi: <b>{shop_name}</b>",
        "ru": "✅ Магазин переключён: <b>{shop_name}</b>",
    },
    "shop_single": {
        "uz": "ℹ️ Sizda faqat bitta do'kon mavjud.",
        "ru": "ℹ️ У вас только один магазин.",
    },

    # ── Competitor ────────────────────────────────────────────────────────────
    "competitor_title": {
        "uz": "🔍 <b>Raqib narx monitoring</b>",
        "ru": "🔍 <b>Мониторинг цен конкурентов</b>",
    },
    "competitor_ask_name": {
        "uz": "🔍 Mahsulot nomini kiriting (qidirish uchun):",
        "ru": "🔍 Введите название товара для поиска:",
    },
    "competitor_searching": {
        "uz": "🔍 Raqiblar narxi tekshirilmoqda...",
        "ru": "🔍 Ищу цены конкурентов...",
    },
    "competitor_not_found": {
        "uz": "❌ Raqiblar topilmadi.",
        "ru": "❌ Конкуренты не найдены.",
    },
    "competitor_blocked_note": {
        "uz": (
            "⚠️ Avtomatik narx olinmadi (Uzum cloud IP larni bloklaydi). "
            "Aniq taqqoslash uchun UZ IP/proxy kerak."
        ),
        "ru": (
            "⚠️ Автоцена недоступна (Uzum блокирует облачные IP). "
            "Для точного сравнения нужен UZ IP/прокси."
        ),
    },
    "competitor_manual_prompt": {
        "uz": "✍️ Raqobatchi narxini qo'lda kiriting (faqat raqam, so'mda):",
        "ru": "✍️ Введите цену конкурента вручную (только число, в сумах):",
    },
    "competitor_manual_invalid": {
        "uz": "❌ Noto'g'ri qiymat. Faqat musbat raqam yuboring.",
        "ru": "❌ Неверное значение. Отправьте только положительное число.",
    },

    # ── AI ────────────────────────────────────────────────────────────────────
    "ai_title": {
        "uz": "🤖 <b>AI Maslahatchi (Gemini)</b>",
        "ru": "🤖 <b>AI Советник (Gemini)</b>",
    },
    "ai_thinking": {
        "uz": "🤖 Gemini tahlil qilmoqda...",
        "ru": "🤖 Gemini анализирует...",
    },
    "ai_ask_question": {
        "uz": "💬 Savolingizni yozing (savdo, narx, strategiya haqida):",
        "ru": "💬 Введите ваш вопрос (о продажах, ценах, стратегии):",
    },
    "ai_no_key": {
        "uz": "⚠️ Gemini AI ulangan emas. GEMINI_API_KEY sozlamalarini tekshiring.",
        "ru": "⚠️ Gemini AI не подключён. Проверьте настройку GEMINI_API_KEY.",
    },

    # ── Buttons ───────────────────────────────────────────────────────────────
    "btn_products": {"uz": "📦 Mahsulotlarim", "ru": "📦 Мои товары"},
    "btn_orders": {"uz": "🛒 Buyurtmalar", "ru": "🛒 Заказы"},
    "btn_storage": {"uz": "🏭 Ombor", "ru": "🏭 Склад"},
    "btn_report": {"uz": "📊 Hisobot", "ru": "📊 Отчёт"},
    "btn_weekly": {"uz": "📈 Haftalik", "ru": "📈 Недельный"},
    "btn_monthly": {"uz": "📅 Oylik", "ru": "📅 Месячный"},
    "btn_returns": {"uz": "↩️ Qaytarmalar", "ru": "↩️ Возвраты"},
    "btn_settings": {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки"},
    "btn_competitor": {"uz": "🔍 Raqib narxlar", "ru": "🔍 Цены конкурентов"},
    "btn_ai": {"uz": "🤖 AI Maslahat", "ru": "🤖 AI Совет"},
    "btn_switch_shop": {"uz": "🏪 Do'kon almashtirish", "ru": "🏪 Сменить магазин"},
    "btn_change_key": {"uz": "🔑 API kalit o'zgartirish", "ru": "🔑 Изменить API ключ"},
    "btn_change_lang": {"uz": "🌐 Tilni o'zgartirish", "ru": "🌐 Сменить язык"},
    "btn_back": {"uz": "🔙 Orqaga", "ru": "🔙 Назад"},
    "btn_refresh": {"uz": "🔄 Yangilash", "ru": "🔄 Обновить"},
    "btn_ai_sales": {"uz": "📊 Savdo tahlili", "ru": "📊 Анализ продаж"},
    "btn_ai_storage": {"uz": "🏭 Ombor tavsiyasi", "ru": "🏭 Совет по складу"},
    "btn_ai_question": {"uz": "💬 Savol berish", "ru": "💬 Задать вопрос"},

    # ── Scheduler: morning report ─────────────────────────────────────────────
    "sched_morning_title": {
        "uz": "🌅 <b>Ertalabki hisobot</b>",
        "ru": "🌅 <b>Утренний отчёт</b>",
    },
    "sched_morning_body": {
        "uz": (
            "📦 Kecha buyurtmalar: <b>{total}</b>\n"
            "✅ Yetkazildi: <b>{delivered}</b>\n"
            "❌ Bekor qilindi: <b>{cancelled}</b>\n"
            "💰 Tushum: <b>{revenue:,.0f} so'm</b>"
        ),
        "ru": (
            "📦 Заказов вчера: <b>{total}</b>\n"
            "✅ Доставлено: <b>{delivered}</b>\n"
            "❌ Отменено: <b>{cancelled}</b>\n"
            "💰 Выручка: <b>{revenue:,.0f} сум</b>"
        ),
    },
    "sched_morning_storage": {
        "uz": (
            "🏭 Ombor holati:\n"
            "  💸 Pullik saqlash: {paid} ta\n"
            "  🚨 Xavfli: {alert} ta\n"
            "  ⚠️ Ogohlantirish: {warn} ta\n"
            "  ✅ Yaxshi: {ok} ta"
        ),
        "ru": (
            "🏭 Состояние склада:\n"
            "  💸 Платное хранение: {paid} шт.\n"
            "  🚨 Критично: {alert} шт.\n"
            "  ⚠️ Предупреждение: {warn} шт.\n"
            "  ✅ Норма: {ok} шт."
        ),
    },

    # ── Scheduler: storage alerts ─────────────────────────────────────────────
    "sched_storage_header": {
        "uz": "🚨 <b>Ombor ogohlantirishi!</b>",
        "ru": "🚨 <b>Внимание: склад!</b>",
    },
    "sched_storage_line": {
        "uz": "{icon} Nakładnoy #{invoice_number}: {days} kun saqlangan, {qty} dona",
        "ru": "{icon} Накладная #{invoice_number}: хранится {days} дн., {qty} шт.",
    },

    # ── Scheduler: delivered ──────────────────────────────────────────────────
    "sched_delivered": {
        "uz": "✅ <b>{count} ta buyurtma yetkazildi!</b>\nHaridor tovarni qabul qildi.",
        "ru": "✅ <b>{count} заказ(ов) доставлено!</b>\nПокупатель получил товар.",
    },
    "sched_delivered_detail": {
        "uz": (
            "📦 <b>{name}</b>\n"
            "🔖 SKU: {sku}\n"
            "💰 Narx: {price:,.0f} so'm\n"
            "📋 Komissiya: {commission:,.0f} so'm\n"
            "✅ Foyda: {profit:,.0f} so'm\n"
            "📅 Qabul qilindi: {date}"
        ),
        "ru": (
            "📦 <b>{name}</b>\n"
            "🔖 SKU: {sku}\n"
            "💰 Цена: {price:,.0f} сум\n"
            "📋 Комиссия: {commission:,.0f} сум\n"
            "✅ Прибыль: {profit:,.0f} сум\n"
            "📅 Получено: {date}"
        ),
    },

    # ── Scheduler: rating ─────────────────────────────────────────────────────
    "sched_rating": {
        "uz": (
            "⭐ <b>Do'kon reytingi past!</b>\n"
            "Do'kon: {shop_name}\n"
            "Reyting: <b>{rating}</b> / 5.0\n"
            "Iltimos, mijozlar shikoyatlarini ko'rib chiqing."
        ),
        "ru": (
            "⭐ <b>Рейтинг магазина низкий!</b>\n"
            "Магазин: {shop_name}\n"
            "Рейтинг: <b>{rating}</b> / 5.0\n"
            "Пожалуйста, проверьте жалобы покупателей."
        ),
    },

    # ── Scheduler: forecast ───────────────────────────────────────────────────
    "sched_forecast_header": {
        "uz": "📉 <b>Tovar tugash ogohlantirishilari:</b>",
        "ru": "📉 <b>Предупреждение о заканчивающихся товарах:</b>",
    },
    "sched_forecast_line": {
        "uz": "{icon} {name}: {days} kun qoldi",
        "ru": "{icon} {name}: осталось {days} дн.",
    },

    # ── Scheduler: returns ────────────────────────────────────────────────────
    "sched_returns": {
        "uz": (
            "↩️ <b>{count} ta yangi qaytarma!</b>\n"
            "Qaytarmalarni ko'rish uchun /start → Qaytarmalar"
        ),
        "ru": (
            "↩️ <b>{count} новых возврата!</b>\n"
            "Для просмотра: /start → Возвраты"
        ),
    },

    # ── Reports: weekly / monthly bodies ──────────────────────────────────────
    "report_weekly_body": {
        "uz": (
            "📦 Jami buyurtmalar: <b>{total}</b>\n"
            "✅ Yetkazildi: <b>{delivered}</b>\n"
            "❌ Bekor qilindi: <b>{cancelled}</b>\n"
            "💰 Tushum: <b>{revenue:,.0f} so'm</b>"
        ),
        "ru": (
            "📦 Всего заказов: <b>{total}</b>\n"
            "✅ Доставлено: <b>{delivered}</b>\n"
            "❌ Отменено: <b>{cancelled}</b>\n"
            "💰 Выручка: <b>{revenue:,.0f} сум</b>"
        ),
    },
    "report_weekly_daily_header": {
        "uz": "📊 <b>Kunlik:</b>",
        "ru": "📊 <b>По дням:</b>",
    },
    "report_monthly_body": {
        "uz": (
            "📦 Jami buyurtmalar: <b>{total}</b>\n"
            "✅ Yetkazildi: <b>{delivered}</b>\n"
            "❌ Bekor: <b>{cancelled}</b>\n"
            "💰 Tushum: <b>{revenue:,.0f} so'm</b>"
        ),
        "ru": (
            "📦 Всего заказов: <b>{total}</b>\n"
            "✅ Доставлено: <b>{delivered}</b>\n"
            "❌ Отменено: <b>{cancelled}</b>\n"
            "💰 Выручка: <b>{revenue:,.0f} сум</b>"
        ),
    },
    "report_monthly_weeks_header": {
        "uz": "<b>Haftalar bo'yicha:</b>",
        "ru": "<b>По неделям:</b>",
    },

    # ── Finance overlay (shared: orders, daily, weekly, monthly) ──────────────
    "finance_commission": {
        "uz": "📋 Komissiya: <b>{commission:,.0f} so'm</b>",
        "ru": "📋 Комиссия: <b>{commission:,.0f} сум</b>",
    },
    "finance_logistics": {
        "uz": "🚚 Logistika: <b>{logistics:,.0f} so'm</b>",
        "ru": "🚚 Логистика: <b>{logistics:,.0f} сум</b>",
    },
    "finance_net_profit": {
        "uz": "✅ Sof foyda: <b>{profit:,.0f} so'm</b>",
        "ru": "✅ Чистая прибыль: <b>{profit:,.0f} сум</b>",
    },
    "finance_margin": {
        "uz": "📊 Rentabellik: <b>{margin:.1f}%</b>",
        "ru": "📊 Рентабельность: <b>{margin:.1f}%</b>",
    },

    # ── Daily product report (09:00 digest) ───────────────────────────────────
    "product_report_title": {
        "uz": "🌅 <b>Kunlik mahsulot hisoboti</b>",
        "ru": "🌅 <b>Ежедневный отчёт по товарам</b>",
    },
    "product_report_body": {
        "uz": (
            "📦 Aktiv mahsulotlar: <b>{total_active}</b> ta\n"
            "📊 Umumiy qoldiq: <b>{total_stock}</b> dona\n"
            "⚠️ Kam qolgan: <b>{low_count}</b> ta\n"
            "🚫 Tugagan: <b>{out_count}</b> ta"
        ),
        "ru": (
            "📦 Активных товаров: <b>{total_active}</b> шт.\n"
            "📊 Общий остаток: <b>{total_stock}</b> шт.\n"
            "⚠️ Мало осталось: <b>{low_count}</b> шт.\n"
            "🚫 Закончились: <b>{out_count}</b> шт."
        ),
    },
    "product_report_item": {
        "uz": "• {name}: <b>{qty}</b> dona",
        "ru": "• {name}: <b>{qty}</b> шт.",
    },

    # ── Per-sale push (quantity-decrease detection) ───────────────────────────
    "sale_push_title": {
        "uz": "🔔 <b>Yangi sotuv!</b>",
        "ru": "🔔 <b>Новая продажа!</b>",
    },
    "sale_push_item": {
        "uz": (
            "📦 <b>{product}</b>\n"
            "🎨 Variant: {variant}\n"
            "🛒 Sotildi: <b>{sold}</b> dona\n"
            "📊 Qoldiq: <b>{remaining}</b> dona"
        ),
        "ru": (
            "📦 <b>{product}</b>\n"
            "🎨 Вариант: {variant}\n"
            "🛒 Продано: <b>{sold}</b> шт.\n"
            "📊 Остаток: <b>{remaining}</b> шт."
        ),
    },
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Tarjima olish.
    :param key: TEXTS lug'atidagi kalit
    :param lang: 'uz' yoki 'ru'
    :param kwargs: format uchun parametrlar
    """
    entry = TEXTS.get(key, {})
    text = entry.get(lang, entry.get("ru", f"[{key}]"))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
