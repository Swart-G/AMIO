from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional, Set
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
from bs4 import BeautifulSoup
from pyvirtualdisplay import Display
import asyncio
import re
import logging

MAX_ITEMS = 50

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Unified Marketplace API", version="5.0.0")
_virtual_display = None


class ProductItem(BaseModel):
    name: Optional[str]
    url: Optional[str]
    price: Optional[str]
    rating: Optional[str]
    reviews: Optional[str]
    img_url: Optional[str]
    marketplace: str


class UnifiedProductsResponse(BaseModel):
    query: str
    count: int
    items: List[ProductItem]


class WebDriverPool:
    def __init__(self, pool_size: int = 2):
        self.pool_size = pool_size
        self._drivers = []
        self._available = None

    async def initialize(self):
        self._available = asyncio.Queue(self.pool_size)
        for _ in range(self.pool_size):
            driver = await asyncio.to_thread(self._new_driver)
            self._drivers.append(driver)
            await self._available.put(driver)

    @staticmethod
    def _new_driver():
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheet": 2,
        }
        options.add_experimental_option("prefs", prefs)
        driver = webdriver.Chrome(options=options)
        stealth(driver,
                languages=["ru-RU", "ru"],
                vendor="Google Inc.",
                platform="Linux x86_64",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True)
        return driver

    async def acquire(self):
        return await self._available.get()

    async def release(self, driver):
        await self._available.put(driver)

    def cleanup(self):
        for driver in self._drivers:
            try:
                driver.quit()
            except:
                pass


driver_pool = WebDriverPool(pool_size=4)


@app.on_event("startup")
async def startup_event():
    global _virtual_display
    try:
        _virtual_display = Display(visible=0, size=(1920, 1080))
        _virtual_display.start()
        logging.info("Virtual Display started successfully")
    except Exception as e:
        logging.error(f"Failed to start Virtual Display: {e}")
    await driver_pool.initialize()


@app.on_event("shutdown")
async def shutdown_event():
    driver_pool.cleanup()
    if _virtual_display:
        _virtual_display.stop()
        logging.info("Virtual Display stopped")


def valid_product_item(item: dict, seen: Set[str]) -> bool:
    return item["url"] and item["name"] and item["price"] and item["url"] not in seen and item["price"].isdigit()


def parse_wb(html: str, seen: Set[str], left: int) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("article", class_="product-card")
    marketplace = "wildberries"
    results = []
    for card in cards:
        try:
            lnk = card.find("a", class_="product-card__link")
            href = lnk.get("href") if lnk and lnk.get("href") else None
            url = (
                "https:" + href if href and href.startswith("//")
                else "https://www.wildberries.ru" + href if href and not href.startswith("http") else href
            )
            if not url or url in seen:
                continue

            name = None
            name_tag = card.find("span", class_="product-card__name")
            if name_tag:
                name = name_tag.get_text(strip=True)

            price = None
            price_block = card.find("ins", class_="price__lower-price") or card.find("span",
                                                                                     class_="price__lower-price")
            if price_block:
                _price = price_block.get_text()
                price = re.sub(r"[^\d]", "", _price)
            if not price:
                pm = card.find("span", class_="price__first-row")
                if pm: price = re.sub(r"[^\d]", "", pm.get_text())

            rating = None
            rt = card.find("span", class_=re.compile(r"address-rate-mini"))
            if rt:
                rating = rt.get_text(strip=True).replace('.', ',')
                if not re.match(r"\d+[.,]?\d*", rating):
                    rating = None

            reviews = None
            rv = card.find("span", class_="product-card__count")
            if rv:
                matches = re.findall(r"\d+", rv.get_text(strip=True))
                reviews = matches[0] if matches else None

            img_url = None
            img = card.find("img", class_="j-thumbnail")
            if img and img.has_attr("src"):
                src = img["src"]
                img_url = (
                    "https:" + src if src.startswith("//") else src
                )
            item = {
                "marketplace": marketplace,
                "name": name,
                "url": url,
                "price": price,
                "rating": rating,
                "reviews": reviews,
                "img_url": img_url
            }
            if valid_product_item(item, seen):
                seen.add(url)
                results.append(item)
                if len(results) >= left:
                    break
        except Exception:
            continue
    return results


def parse_ozon(html: str, seen: Set[str], left: int) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=lambda x: x and "tile-root" in x)
    if not cards:
        cards = soup.find_all("div", attrs={"data-widget": "searchResultsV2"})
    marketplace = "ozon"
    results = []
    for card in cards:
        try:
            lnk = card.find("a", href=re.compile(r"/product/"))
            href = lnk.get("href") if lnk and lnk.get("href") else None
            url = ("https://ozon.ru" + href if href and not href.startswith("http") else href)
            if not url or url in seen:
                continue

            name = None
            name_tag = card.find("span", class_=lambda x: x and "tsBody" in x)
            if name_tag:
                name = name_tag.get_text(strip=True)
            elif lnk:
                name = lnk.get_text(strip=True)

            price = None
            price_block = card.find("span", {"data-test-id": "price-current"})
            if price_block:
                price_str = price_block.get_text()
                price = re.sub(r"[^\d]", "", price_str) if price_str else None
            else:
                price_tag = card.find("span", class_=re.compile(r"price"))
                price_text = price_tag.get_text() if price_tag else card.get_text()
                pm = re.search(r"(\d[\d\s\u2009\xa0]*\d)\s*₽", price_text)
                if pm: price = re.sub(r"[^\d]", "", pm.group(1)) if pm.group(1) else None

            rating = None
            rating_tag = card.find("span", class_=re.compile(r"rating"))
            if rating_tag:
                rating = rating_tag.get_text(strip=True).replace('.', ',')
                if not re.match(r"\d+[.,]?\d*", rating):
                    rating = None
            # fallback: ищем по всем спанам
            if not rating:
                for s in card.find_all("span"):
                    match = re.match(r"\d+[.,]\d+", s.get_text())
                    if match:
                        rating = match.group(0).replace('.', ',')
                        break

            reviews = None
            for s in card.find_all("span"):
                txt = s.get_text().lower()
                if "отзыв" in txt:
                    nums = re.findall(r"\d+", txt)
                    if nums:
                        reviews = nums[0]
                        break

            img_url = None
            img = card.find("img")
            if img and img.has_attr("src"):
                src = img["src"]
                img_url = (
                    "https:" + src if src.startswith("//") else src
                )
            item = {
                "marketplace": marketplace,
                "name": name,
                "url": url,
                "price": price,
                "rating": rating,
                "reviews": reviews,
                "img_url": img_url
            }
            if valid_product_item(item, seen):
                seen.add(url)
                results.append(item)
                if len(results) >= left:
                    break
        except Exception:
            continue
    return results


async def collect_wb(driver, query: str, limit=MAX_ITEMS):
    seen = set()
    results = []
    # Первый запрос: популярные
    for sort in ["popular", "rate"]:
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?page=1&sort={sort}&search={query}"
        await asyncio.to_thread(driver.get, url)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article.product-card"))
            )
        except Exception:
            pass
        html = driver.page_source
        left = limit - len(results)
        if left <= 0:
            break
        res = parse_wb(html, seen, left)
        results.extend(res)
    return results[:limit]


async def collect_ozon(driver, query: str, limit=MAX_ITEMS):
    seen = set()
    results = []
    # Первый — стандартно, второй — с сортировкой по рейтингу
    for sorting in [None, "rating"]:
        url = f"https://www.ozon.ru/search/?text={query}&from_global=true"
        if sorting:
            url += f"&sorting={sorting}"
        await asyncio.to_thread(driver.get, url)
        try:
            WebDriverWait(driver, 8).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "div[class*='tile-root']")) > 0
            )
        except Exception:
            pass
        html = driver.page_source
        left = limit - len(results)
        if left <= 0:
            break
        res = parse_ozon(html, seen, left)
        results.extend(res)
    return results[:limit]


@app.get("/api/products", response_model=UnifiedProductsResponse)
async def get_products(
        q: str = Query(..., description="Название или ключевые слова товара")
):
    if not isinstance(q, str) or not q:
        raise HTTPException(status_code=400, detail="Параметр 'q' обязателен")
    drivers = []
    try:
        for _ in range(2):
            drivers.append(await driver_pool.acquire())
        tasks = [
            collect_wb(drivers[0], q, MAX_ITEMS),
            collect_ozon(drivers[1], q, MAX_ITEMS)
        ]
        results = await asyncio.gather(*tasks)
        all_items = [ProductItem(**item) for part in results for item in part]
    finally:
        for d in drivers:
            await driver_pool.release(d)
    # Лимитируем на уровне ответа - не больше 50 карточек на всё
    return UnifiedProductsResponse(query=q, count=len(all_items), items=all_items[:MAX_ITEMS])


@app.get("/health")
def health():
    return {"status": "ok", "version": "5.0.2"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
