import re
import json
import random
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
import aiohttp

# ── 設定區 ──────────────────────────────────────────────
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/你的webhook網址"

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

LOWEST_JSON = Path(__file__).parent / "lowest.json"
MAX_HISTORY = 5  # 每商品保留最低幾筆

# ── 隨機 UA ─────────────────────────────────────────────
def get_random_ua() -> str:
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)

# ── 爬蟲 ────────────────────────────────────────────────
def scrape_momo_price(url: str, page: Page) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('meta[property="product:price:amount"]', state="attached", timeout=15000)

    def get_meta(prop: str) -> str:
        el = page.query_selector(f'meta[property="{prop}"]')
        return el.get_attribute("content").strip() if el else ""

    return {
        "date":     datetime.now().strftime("%Y-%m-%d"),
        "title":    get_meta("og:title"),
        "price":    int(get_meta("product:price:amount")),
        "currency": get_meta("product:price:currency"),
        "url":      url,
    }

def update_lowest(history: dict, data: dict) -> tuple[int, int]:
    """
    更新 JSON，回傳 (歷史最低價, 價差)
    """
    key = data["url"]
    records: list[dict] = history.get(key, [])
    # 加入今日資料
    records.append({"date": data["date"], "price": data["price"]})
    # 依價格排序，只保留最低 MAX_HISTORY 筆
    records = sorted(records, key=lambda x: x["price"])[:MAX_HISTORY]
    history[key] = records

    LOWEST_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    lowest_price = records[0]["price"]
    diff = data["price"] - lowest_price
    return lowest_price, diff

# ── Discord Embed 推送 ───────────────────────────────────
async def send_discord(results: list[dict]) -> None:
    today = datetime.now().strftime("%Y/%m/%d")

    embeds = []
    for r in results:
        price     = r["price"]
        lowest    = r["lowest"]
        diff      = r["diff"]
        title     = r["title"]
        url       = r["url"]

        # 價差顏色：等於最低=綠、高於最低=紅
        color = 0x2ecc71 if diff == 0 else 0xe74c3c

        # 價差標示
        if diff == 0:
            diff_str = "✅ 目前為歷史最低價！"
        else:
            diff_str = f"⬆️ 高於最低價 **+{diff} 元**（最低曾 {lowest} 元）"

        embeds.append({
            "title": title[:200],
            "url": url,
            "color": color,
            "fields": [
                {"name": "💰 今日價格", "value": f"**{price} TWD**", "inline": True},
                {"name": "🏆 歷史最低", "value": f"**{lowest} TWD**",  "inline": True},
                {"name": "📊 價差",     "value": diff_str,             "inline": False},
            ],
            "footer": {"text": f"momo 每日價格追蹤 · {today}"}
        })

    # Discord 單次最多10個 embed
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(embeds), 10):
            payload = {"embeds": embeds[i:i+10]}
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status in (200, 204):
                    print(f"✅ Discord 推送成功（第{i//10+1}批）")
                else:
                    print(f"❌ Discord 推送失敗：{resp.status} {await resp.text()}")
            await asyncio.sleep(1)  # 避免rate limit

# ── 主程式 ──────────────────────────────────────────────
async def main():
    history = load_lowest()
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=get_random_ua())

        def block_images(route, req):
            if req.resource_type == "image":
                route.abort()
            else:
                route.continue_()

        context.route("**/*", block_images)
        page: Page = context.new_page()

        for i, url in enumerate(MOMO_URLS, 1):
            print(f"\n{'='*50}")
            print(f"🔍 [{i}/{len(MOMO_URLS)}] 抓取中... {url}")

            data = scrape_momo_price(url, page)
            lowest_price, diff = update_lowest(history, data)

            results.append({**data, "lowest": lowest_price, "diff": diff})

            print(f"📦 {data['title']}")
            print(f"💰 今日：{data['price']} TWD｜🏆 最低：{lowest_price} TWD｜差：{diff:+d}")

        browser.close()

    print(f"\n{'='*50}")
    print("📤 推送到 Discord...")
    await send_discord(results)
    print("🎉 全部完成！")

if __name__ == "__main__":
    asyncio.run(main())
