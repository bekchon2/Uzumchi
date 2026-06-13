"""
run.py — Verbose logging bilan botni ishga tushirish.
"""
import asyncio
import logging
import sys

# Asosiy logging — INFO darajada
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Keraksiz verbose loglarni o'chirish
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)

from main import main

if __name__ == "__main__":
    print("=" * 50)
    print("  Uzum Seller Bot — JoyKid")
    print("  Starting...")
    print("=" * 50)
    asyncio.run(main())
