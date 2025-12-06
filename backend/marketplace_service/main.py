from fastapi import FastAPI, HTTPException, Query, Request
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
from datetime import datetime, timedelta

# ================= КОНФИГУРАЦИЯ =================
MAX_ITEMS = 50          # Максимум товаров в ответе
CONCURRENT_LIMIT = 5    # Максимум одновременных запросов браузеров
ENABLE_CACHE = True     # ВКЛ/ВЫКЛ кэширование (True/False)
CACHE_TTL = 60          # Время жизни кэша в секундах
# ================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unified Marketplace API", version="5.1.4")

_virtual_display = None
_cache = {}

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
    def __init__(self, pool_size: int = 4):
        self.pool_size = pool_size
        self._drivers = []
        self._available = None
        self._semaphore = None

    async def initialize(self):
        self._available = asyncio.Queue(self.pool_size)
        self._semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
        for _ in range(self.pool_size):
            driver = await asyncio.to_thread(self._new_driver)
            self._drivers.append(driver)
            await self._available.put(driver)
        logger.info(f"WebDriverPool initialized with {self.pool_size} drivers")

    @staticmethod
    def _new_driver():
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080") # Важно для Ozon
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Эмуляция реального пользователя
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        options.add_argument(f'user-agent={user_agent}')

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheet": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        
        driver = webdriver.Chrome(options=options)
        
        stealth(driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True)
        
        return driver

    async def acquire(self):
        return await self._available.get()

    async def release(self, driver):
        # ОЧИСТКА ПЕРЕД ВОЗВРАТОМ
        def clean_driver(d):
            try:
                d.delete_all_cookies()
            except Exception:
                pass # Если драйвер завис, это обработается позже

        await asyncio.to_thread(clean_driver, driver)
        await self._available.put(driver)

    async def get_with_semaphore(self):
        await self._semaphore.acquire()
        return await self.acquire()

    async def release_with_semaphore(self, driver):
        await self.release(driver)
        self._semaphore.release()

    def cleanup(self):
        for driver in self._drivers:
            try:
                driver.quit()
            except:
                pass
        logger.info("WebDriverPool cleaned up")

driver_pool = WebDriverPool(pool_size=4)

@app.on_event("startup")
async def startup_event():
    global _virtual_display
    try:
        _virtual_display = Display(visible=0, size=(1920, 1080))
        _virtual_display.start()
        logger.info("Virtual Display started successfully")
    except Exception as e:
        logger.error(f"Failed to start Virtual Display: {e}")

    await driver_pool.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    driver_pool.cleanup()
    if _virtual_display:
        _virtual_display.stop()
        logger.info("Virtual Display stopped")

def valid_product_item(item: dict, seen: Set[str]) -> bool:
    return (
        item.get("url") and 
        item.get("name") and 
        item.get("price") and 
        item["url"] not in seen and 
        isinstance(item.get("price"), str) and
        item["price"].isdigit()
    )

def get_from_cache(key: str) -> Optional[dict]:
    """Получить результат из кэша"""
    if not ENABLE_CACHE:
        return None
        
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now() - timestamp < timedelta(seconds=CACHE_TTL):
            logger.info(f"Cache hit for key: {key}")
            return data
        else:
            del _cache[key]
    return None

def set_to_cache(key: str, data: dict):
    """Сохранить результат в кэш"""
    if not ENABLE_CACHE:
        return

    _cache[key] = (data, datetime.now())

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
                else "https://www.wildberries.ru" + href if href and not href.startswith("http")
                else href
            )

            if not url or url in seen:
                continue

            name = None
            name_tag = card.find("span", class_="product-card__name")
            if name_tag:
                name = name_tag.get_text(strip=True)

            price = None
            price_block = card.find("ins", class_="price__lower-price") or card.find("span", class_="price__lower-price")
            if price_block:
                _price = price_block.get_text()
                price = re.sub(r"[^\d]", "", _price)
            
            if not price:
                pm = card.find("span", class_="price__first-row")
                if pm:
                    price = re.sub(r"[^\d]", "", pm.get_text())

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
                img_url = "https:" + src if src.startswith("//") else src

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

        except Exception as e:
            logger.debug(f"Error parsing WB card: {e}")
            continue

    return results

def parse_ozon(html: str, seen: Set[str], left: int) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=lambda x: x and "tile-root" in x)
    marketplace = "ozon"
    results = []

    for card in cards:
        try:
            lnk = card.find("a", href=re.compile(r"/product/"))
            href = lnk.get("href") if lnk and lnk.get("href") else None
            url = "https://ozon.ru" + href.split("?")[0] if href and not href.startswith("http") else href

            if not url or url in seen:
                continue

            name = None
            name_container = card.find("div", class_=re.compile(r"bq03_0_4-a"))
            if name_container:
                name_span = name_container.find("span", class_=re.compile(r"tsBody500Medium"))
                if name_span:
                    name = name_span.get_text(strip=True)

            if not name:
                name_link = card.find("a", class_=re.compile(r"iv124"))
                if name_link:
                    name_div = name_link.find("div", class_=re.compile(r"bq03_0_4-a"))
                    if name_div:
                        name = name_div.get_text(strip=True)

            price = None
            price_tag = card.find("span", class_=re.compile(r"tsHeadline500Medium"))
            if price_tag:
                price_text = price_tag.get_text()
                price = re.sub(r"[^\d]", "", price_text)

            rating = None
            for s in card.find_all("span"):
                style = s.get("style", "")
                if "textPremium" in style:
                    text = s.get_text(strip=True)
                    match = re.match(r"(\d+[.,]\d+|\d+)", text)
                    if match:
                        rating = match.group(1).replace('.', ',')
                        break

            reviews = None
            for s in card.find_all("span"):
                style = s.get("style", "")
                if "textSecondary" in style:
                    txt = s.get_text()
                    txt_clean = re.sub(r"[\s\u00a0\u2009]+", "", txt)
                    nums = re.findall(r"\d+", txt_clean)
                    if nums:
                        reviews = nums[0]
                        break

            img_url = None
            img = card.find("img", class_=re.compile(r"u5i24|b95"))
            if img and img.has_attr("src"):
                src = img["src"]
                img_url = "https:" + src if src.startswith("//") else src

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

        except Exception as e:
            logger.debug(f"Error parsing Ozon card: {e}")
            continue

    return results

async def collect_wb(driver, query: str, limit=MAX_ITEMS):
    seen = set()
    results = []
    
    try:
        for sort in ["popular", "rate"]:
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?page=1&sort={sort}&search={query}"
            
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(driver.get, url),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Wildberries timeout for query: {query}")
                continue
            
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

    except Exception as e:
        logger.error(f"Error in collect_wb: {e}")

    return results[:limit]

async def collect_ozon(driver, query: str, limit=MAX_ITEMS):
    seen = set()
    results = []

    try:
        for sorting in [None, "rating"]:
            url = f"https://www.ozon.ru/search/?text={query}&from_global=true"
            if sorting:
                url += f"&sorting={sorting}"

            try:
                await asyncio.wait_for(
                    asyncio.to_thread(driver.get, url),
                    timeout=20.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Ozon timeout for query: {query}")
                continue

            wait_time = 12
            retries = 3
            success = False

            for attempt in range(retries):
                try:
                    WebDriverWait(driver, wait_time).until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, "div[class*='tile-root']")) > 5
                    )
                    success = True
                    break
                except Exception:
                    if attempt < retries - 1:
                        await asyncio.sleep(2)

            if not success:
                logger.warning(f"Ozon failed to load elements after {retries} attempts")

            html = driver.page_source
            left = limit - len(results)

            if left <= 0:
                break

            res = parse_ozon(html, seen, left)
            results.extend(res)

    except Exception as e:
        logger.error(f"Error in collect_ozon: {e}")

    return results[:limit]

@app.get("/api/products", response_model=UnifiedProductsResponse)
async def get_products(
    request: Request,
    q: str = Query(..., description="Название или ключевые слова товара")
):
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(status_code=400, detail="Параметр 'q' обязателен")

    q = q.strip()
    
    # 1. Проверяем кэш (если включен)
    cache_key = f"products:{q}"
    cached = get_from_cache(cache_key)
    if cached:
        return UnifiedProductsResponse(**cached)

    driver1 = None
    driver2 = None

    try:
        # 2. Ограничиваем конкурентные запросы
        driver1 = await driver_pool.get_with_semaphore()
        driver2 = await driver_pool.get_with_semaphore()

        start_time = datetime.now()
        
        tasks = [
            collect_wb(driver1, q, MAX_ITEMS),
            collect_ozon(driver2, q, MAX_ITEMS)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_items = []
        for part in results:
            if isinstance(part, Exception):
                logger.error(f"Task failed with exception: {part}")
                continue
            if isinstance(part, list):
                all_items.extend([ProductItem(**item) for item in part])

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Query: {q}, Items: {len(all_items)}, Time: {elapsed:.2f}s")

        final_items = all_items[:MAX_ITEMS]
        
        response_data = {
            "query": q,
            "count": len(final_items),
            "items": final_items
        }
        
        # 3. Сохраняем в кэш (если включен)
        set_to_cache(cache_key, {
            "query": q,
            "count": len(final_items),
            "items": [item.dict() for item in final_items]
        })
        
        return UnifiedProductsResponse(**response_data)

    except Exception as e:
        logger.error(f"Error in get_products: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    finally:
        if driver1:
            await driver_pool.release_with_semaphore(driver1)
        if driver2:
            await driver_pool.release_with_semaphore(driver2)

@app.get("/health")
def health():
    return {"status": "ok", "version": "5.1.4"}

@app.get("/cache-stats")
def cache_stats():
    """Статистика кэша"""
    return {
        "cache_enabled": ENABLE_CACHE,
        "cache_size": len(_cache),
        "cache_ttl": CACHE_TTL,
        "concurrent_limit": CONCURRENT_LIMIT
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
