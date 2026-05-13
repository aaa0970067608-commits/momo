import re
import json
import random
import asyncio
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
import aiohttp

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

with open("urls.txt", encoding="utf-8") as f:
    MOMO_URLS = [line.strip() for line in f if line.strip()]

LOWEST_JSON = Path("lowest.json")
MAX_HISTORY = 5

def get_random_ua():
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)

async def scrape_momo_price(url, context):
    await asyncio.sleep(random.uniform(3, 6))
    for attempt in range(3):
        page = await context.new_page()
        try:
            await page.set_extra_http_headers({
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.momoshop.com.tw/",
            })
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector('meta[property="product:price:amount"]', state="attached", timeout=20000)
            async def get_meta(prop):
                el = await page.query_selector(f'meta[property="{prop}"]')
                return (await el.get_attribute("content")).strip() if el else ""
            result = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "title": await get_meta("og:title"),
                "price": int(await get_meta("product:price:amount")),
                "currency": await get_meta("product:price:currency"),
                "url": url,
            }
            await page.close()
            return result
        except Exception as e:
            await page.close()
            print(f"⚠️ 第{attempt+1}次失敗：{e}")
            if attempt < 2:
                wait = random.uniform(10, 20)
                print(f"⏳ 等待 {wait:.0f} 秒後重試...")
                await asyncio.sleep(wait)
            else:
                raise

def load_lowest():
    if LOWEST_JSON.exists():
        return json.loads(LOWEST_JSON.read_text(encoding="utf-8"))
    return {}

def update_lowest(history, data):
    key = data["url"]
    records = history.get(key, [])
    records.append({"date": data["date"], "price": data["price"]})
    records = sorted(records, key=lambda x: x["price"])[:MAX_HISTORY]
    history[key] = records
    LOWEST_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    lowest_price = records[0]["price"]
    diff = data["price"] - lowest_price
    return lowest_price, diff

async def send_discord(results):
    today = datetime.now().strftime("%Y/%m/%d")
    embeds = []
    for r in results:
        price = r["price"]
        lowest = r["lowest"]
        diff = r["diff"]
        title = r["title"]
        url = r["url"]
        color = 0x2ecc71 if diff == 0 else 0xe74c3c
        diff_str = "✅ 目前為歷史最低價！" if diff == 0 else f"⬆️ 高於最低價 +{diff} 元（最低曾 {lowest} 元）"
        embeds.append({
            "title": title[:200],
            "url": url,
            "color": color,
            "fields": [
                {"name": "💰 今日價格", "value": f"**{price} TWD**", "inline": True},
                {"name": "🏆 歷史最低", "value": f"**{lowest} TWD**", "inline": True},
                {"name": "📊 價差", "value": diff_str, "inline": False},
            ],
            "footer": {"text": f"momo 每日價格追蹤 · {today}"}
        })
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(embeds), 10):
            payload = {"embeds": embeds[i:i+10]}
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status in (200, 204):
                    print(f"✅ Discord 推送成功（第{i//10+1}批）")
                else:
                    print(f"❌ Discord 推送失敗：{resp.status} {await resp.text()}")
            await asyncio.sleep(1)

async def main():
    history = load_lowest()
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=get_random_ua(),
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1280, "height": 800},
        )
        async def block_images(route, req):
            if req.resource_type == "image":
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", block_images)
        for i, url in enumerate(MOMO_URLS, 1):
            print(f"\n{'='*50}")
            print(f"🔍 [{i}/{len(MOMO_URLS)}] 抓取中... {url}")
            data = await scrape_momo_price(url, context)
            lowest_price, diff = update_lowest(history, data)
            results.append({**data, "lowest": lowest_price, "diff": diff})
            print(f"📦 {data['title']}")
            print(f"💰 今日：{data['price']} TWD｜🏆 最低：{lowest_price} TWD｜差：{diff:+d}")
        await browser.close()
    print(f"\n{'='*50}")
    print("📤 推送到 Discord...")
    await send_discord(results)
    print("🎉 全部完成！")

if __name__ == "__main__":
    asyncio.run(main())
