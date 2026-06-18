import asyncio
import logging
import os
from aiohttp import web
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database import init_db
from handlers.start import router as start_router
from handlers.analytics import router as analytics_router
from handlers.main_menu import router as main_menu_router
from handlers.missing_reports import router as missing_router
from services.scheduler import start_scheduler

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")  # Render avtomatik beradi
SELF_PING_INTERVAL = 10 * 60  # 10 daqiqa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def ping_handler(request):
    return web.Response(text="pong")


async def health_handler(request):
    return web.Response(text="OK")


async def self_ping():
    """
    Render free tier da xizmat uxlab qolmasligi uchun o'zini-o'zi ping qiladi.
    RENDER_EXTERNAL_URL bo'lmasa (local rejim) — xavfsiz no-op (faqat log).
    """
    if not RENDER_URL:
        logger.info("self-ping disabled (local mode)")
        return

    url = f"{RENDER_URL}/ping"
    logger.info(f"Self-ping started: {url}")
    while True:
        await asyncio.sleep(SELF_PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    logger.info(f"Self-ping: {resp.status}")
        except Exception as e:
            logger.warning(f"Self-ping error: {e}")


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in environment!")

    await init_db()

    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Router tartib muhim: analytics → start → main_menu → missing
    dp.include_router(analytics_router)
    dp.include_router(start_router)
    dp.include_router(main_menu_router)
    dp.include_router(missing_router)

    # APScheduler ishga tushirish
    scheduler = start_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started.")

    # aiohttp web server (ping/health + Render uchun)
    app = web.Application()
    app.router.add_get("/ping", ping_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

    # Self-ping keep-alive (Render free tier) — background task
    asyncio.create_task(self_ping())

    logger.info("Bot starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
