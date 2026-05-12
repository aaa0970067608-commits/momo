import re
import json
import random
import asyncio
import os
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
import aiohttp

# ── 設定區 ──────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]  # ✅ 從環境變數讀取

MOMO_URLS = [
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=10228197",  # 舒潔衛生紙
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=8084433",   # 菲力濕紙巾
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=11236766",  # Kotex
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=8391956",   # ITO洗臉巾
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=10893852",  # 韓國Wimarn
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=9920508",   # BHK's葉黃素
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=9884553",   # BHK's魚油
    "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=9244191",   # BHK's紅麴
]

LOWEST_JSON = Path("lowest.json")
MAX_HISTORY = 5

# ── 隨機 UA ─────────────────────────────────────────────
def get_random_ua() -> str:
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)
