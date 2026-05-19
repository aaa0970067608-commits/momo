import re
import json
import random
import asyncio
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
import aiohttp

# 讀取環境變數中的 Discord Webhook URL
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# 設定檔案路徑
URL_FILE = Path("urls.txt")
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
    await asyncio.sleep(random.uniform(2, 5))  # 稍微縮短一點等待時間，保持效率
    for attempt in range(3):
        page = await context.new_page()
        try:
            await page.set_extra_http_headers({
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.momoshop.com.tw/",
            })
            # 增加 timeout 到 60 秒以應對慢速網路
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 等待價格標籤出現
            await page.wait_for_selector('meta[property="product:price:amount"]', state="attached", timeout=20000)
            
            async def get_meta(prop):
                el = await page.query_selector(f'meta[property="{prop}"]')
                return (await el.get_attribute("content")).strip() if el else ""
            
            title = await get_meta("og:title")
            price_str = await get_meta("product:price:amount")
            
            if not price_str:
                raise ValueError("無法取得價格資訊")

            result = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "title": title if title else "未知商品",
                "price": int(float(price_str)),
                "currency": await get_meta("product:price:currency") or "TWD",
                "url": url,
            }
            await page.close()
            return result
        except Exception as e:
            await page.close()
            print(f"⚠️ 第 {attempt+1} 次抓取失敗：{e}")
            if attempt < 2:
                wait = random.uniform(5, 10)
                await asyncio.sleep(wait)
            else:
                return None # 失敗三次後回傳 None，避免整台程式崩潰

def load_lowest():
    if LOWEST_JSON.exists():
        try:
            return json.loads(LOWEST_JSON.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def update_lowest(history, data):
    if not data: return None, None
    key = data["url"]
    records = history.get(key, [])
    records.append({"date": data["date"], "price": data["price"]})
    # 只保留最低的前幾名
    records = sorted(records, key=lambda x: x["price"])[:MAX_HISTORY]
    history[key] = records
    LOWEST_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    lowest_price = records[0]["price"]
    diff = data["price"] - lowest_price
    return lowest_price, diff

async def send_discord(results):
    if not results or not DISCORD_WEBHOOK_URL:
        print("⏭️ 沒有結果或未設定 Webhook，跳過推送。")
        return

    today = datetime.now().strftime("%Y/%m/%d")
    embeds = []
    for r in results:
        if not r: continue
        price = r["price"]
        lowest = r["lowest"]
        diff = r["diff"]
        
        # 決定顏色與價差文字
        if diff == 0:
            color = 0x2ecc71 # 綠色
            diff_str = "✅ 目前為歷史最低價！"
        else:
            color = 0xe74c3c # 紅色
            diff_str = f"⬆️ 高於最低價 +{diff} 元（最低曾 {lowest} 元）"

        embeds.append({
            "title": r["title"][:200],
            "url": r["url"],
            "color": color,
            "fields": [
                {"name": "💰 今日價格", "value": f"**{price} TWD**", "inline": True},
                {"name": "🏆 歷史最低", "value": f"**{lowest} TWD**", "inline": True},
                {"name": "📊 狀態", "value": diff_str, "inline": False},
            ],
            "footer": {"text": f"momo 每日價格追蹤 · {today}"}
        })

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(embeds), 10):
            payload = {"embeds": embeds[i:i+10]}
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status in (200, 204):
                    print(f"✅ Discord 推送成功")
                else:
                    print(f"❌ Discord 推送失敗：{resp.status}")
            await asyncio.sleep(1)

async def main():
    if not URL_FILE.exists():
        print("❌ 找不到 urls.txt，請建立檔案並放入網址。")
        return

    with open(URL_FILE, encoding="utf-8") as f:
        momo_urls = [line.strip() for line in f if line.strip()]

    history = load_lowest()
    results = []
    
    async with async_playwright() as p:
        # 啟動瀏覽器
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

        # 阻擋圖片與無用資源節省流量
        async def block_useless(route, req):
            if req.resource_type in ["image", "media", "font"]:
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", block_useless)

        for i, url in enumerate(momo_urls, 1):
            print(f"\n🔍 [{i}/{len(momo_urls)}] 檢查中...")
            data = await scrape_momo_price(url, context)
            if data:
                lowest_price, diff = update_lowest(history, data)
                results.append({**data, "lowest": lowest_price, "diff": diff})
                print(f"📦 {data['title'][:30]}...")
                print(f"💰 今日：{data['price']} | 🏆 最低：{lowest_price} | 價差：{diff}")
            else:
                print(f"❌ 無法抓取網址：{url}")
        
        await browser.close()

    print("\n📤 準備推送到 Discord...")
    await send_discord(results)
    print("🎉 任務完成！")

if __name__ == "__main__":
    asyncio.run(main())
