"""
run.py — Verbose logging bilan botni ishga tushirish.
"""
import asyncio
import logging
import sys

# Verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# aiogram va aiohttp loglarini kamaytirish
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)

from main import main

if __name__ == "__main__":
    print("=" * 50)
    print("  Uzum Seller Bot — JoyKid")
    print("  Starting with verbose logging...")
    print("=" * 50)
    asyncio.run(main())
