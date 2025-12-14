from fastapi import FastAPI, HTTPException, Query, Request
from typing import List, Optional, Set, Dict, Tuple

from pydantic import BaseModel

import asyncio
import logging
import os
import re
import time
import tempfile
import socket
import threading
import json
import random
import shutil

from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


# optional stealth
try:
    from selenium_stealth import stealth
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False


# optional xvfb (Linux without GUI, when running NOT headless)
try:
    from pyvirtualdisplay import Display
    HAS_XVFB = True
except Exception:
    HAS_XVFB = False


# ================= CONFIG =================

MAX_ITEMS = int(os.getenv("MAX_ITEMS", "100"))

ENABLE_CACHE = os.getenv("ENABLE_CACHE", "1") == "0"
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))

ENABLE_WB = os.getenv("ENABLE_WB", "1") == "1"
ENABLE_OZON = os.getenv("ENABLE_OZON", "1") == "1"

# ---------- Ozon Selenium ----------
OZON_ITEMS = int(os.getenv("OZON_ITEMS", "30"))
OZON_BROWSER_LIMIT = int(os.getenv("OZON_BROWSER_LIMIT", "1"))  # how many Chromes at once
OZON_RETRIES = int(os.getenv("OZON_RETRIES", "3"))
OZON_MIN_ITEMS = int(os.getenv("OZON_MIN_ITEMS", "20"))  # if got less -> retry with new browser

OZON_WAIT_FIRST = int(os.getenv("OZON_WAIT_FIRST", "25"))
OZON_SCROLL_ROUNDS = int(os.getenv("OZON_SCROLL_ROUNDS", "50"))
OZON_SCROLL_PAUSE = float(os.getenv("OZON_SCROLL_PAUSE", "1.0"))
OZON_TILE_SELECTOR = os.getenv("OZON_TILE_SELECTOR", "div[class*='tile-root']")
OZON_WAIT_NEW_TILES = int(os.getenv("OZON_WAIT_NEW_TILES", "10"))
OZON_STAGNATION_LIMIT = int(os.getenv("OZON_STAGNATION_LIMIT", "12"))
OZON_SCROLL_STEP = int(os.getenv("OZON_SCROLL_STEP", "1200"))

# Chrome runtime
CHROME_BINARY = os.getenv("CHROME_BINARY")
CHROME_DRIVER_LOG = os.getenv("CHROME_DRIVER_LOG", os.devnull)  # or "chromedriver.log"
PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "60"))
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "0") == "1"  # for Ozon
USE_XVFB = os.getenv("USE_XVFB", "1") == "1"

# ---------- WB HTTP (API) ----------
WB_ITEMS = int(os.getenv("WB_ITEMS", "70"))
WB_CONCURRENT_LIMIT = int(os.getenv("WB_CONCURRENT_LIMIT", "1"))
WB_API_TIMEOUT = int(os.getenv("WB_API_TIMEOUT", "30"))
WB_MIN_INTERVAL = float(os.getenv("WB_MIN_INTERVAL", "2.5"))
WB_MAX_RETRIES = int(os.getenv("WB_MAX_RETRIES", "6"))
WB_BACKOFF_BASE = float(os.getenv("WB_BACKOFF_BASE", "1.5"))
WB_BACKOFF_MAX = float(os.getenv("WB_BACKOFF_MAX", "30"))
WB_MAX_PAGES = int(os.getenv("WB_MAX_PAGES", "2"))

WB_API_VERSION = os.getenv("WB_API_VERSION", "v18")
WB_API_HOST = os.getenv("WB_API_HOST", "search.wb.ru")
WB_DEST = os.getenv("WB_DEST", "-1257786")
WB_SPP = int(os.getenv("WB_SPP", "30"))
WB_APP_TYPE = os.getenv("WB_APP_TYPE", "1")
WB_LANG = os.getenv("WB_LANG", "ru")
WB_CURR = os.getenv("WB_CURR", "rub")
WB_SORT = os.getenv("WB_SORT", "popular")

# Optional: shared WB cooldown (prevents hammering during ban-window)
WB_GLOBAL_COOLDOWN = os.getenv("WB_GLOBAL_COOLDOWN", "1") == "1"

UA = os.getenv(
    "UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)

DUMP_HTML = os.getenv("DUMP_HTML", "0") == "1"


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("marketplace_service")

app = FastAPI(title="Unified Marketplace API", version="5.8.0")

_cache: Dict[str, Tuple[dict, datetime]] = {}

_virtual_display: Optional["Display"] = None

_ozon_sem = asyncio.Semaphore(OZON_BROWSER_LIMIT)
_wb_semaphore = asyncio.Semaphore(WB_CONCURRENT_LIMIT)

_wb_rate_lock = threading.Lock()
_wb_last_request_ts = 0.0

_wb_block_lock = threading.Lock()
_wb_blocked_until = 0.0


# ========================= MODELS =========================

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


# ========================= CACHE =========================

def get_from_cache(key: str) -> Optional[dict]:
    if not ENABLE_CACHE:
        return None
    item = _cache.get(key)
    if not item:
        return None
    data, ts = item
    if datetime.now() - ts < timedelta(seconds=CACHE_TTL):
        return data
    _cache.pop(key, None)
    return None


def set_to_cache(key: str, data: dict):
    if not ENABLE_CACHE:
        return
    _cache[key] = (data, datetime.now())


# ========================= HELPERS =========================

def digits_only(s: str) -> str:
    return re.sub(r"[^\d]", "", s or "")


def valid_product_item(item: dict, seen: Set[str]) -> bool:
    return (
        item.get("url")
        and item.get("name")
        and item.get("price")
        and item["url"] not in seen
        and isinstance(item.get("price"), str)
        and item["price"].isdigit()
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _mk_profile_dir(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=f"{prefix}-")


def _dump_html(prefix: str, html: str):
    if not DUMP_HTML:
        return
    try:
        p = tempfile.mkstemp(prefix=f"{prefix}-", suffix=".html")[1]
        with open(p, "w", encoding="utf-8") as f:
            f.write(html or "")
        logger.error("%s html dumped: %s (len=%s)", prefix, p, len(html or ""))
    except Exception:
        pass


def _looks_like_ozon_block(html: str, title: str) -> bool:
    t = (html or "").lower()
    tt = (title or "").lower()
    return (
        "доступ ограничен" in t
        or "доступ ограничен" in tt
        or "abt-challenge" in t
        or "captcha" in t
        or "we need to make sure" in t
    )


def _clean_spaces(s: str) -> str:
    return (s or "").replace("\u00a0", " ").strip()


def _first_src_from_srcset(srcset: str) -> str:
    if not srcset:
        return ""
    first = srcset.split(",")[0].strip()
    return first.split(" ")[0].strip()


# ========================= CHROME =========================

def _new_chrome_driver(profile_prefix: str) -> webdriver.Chrome:
    options = Options()

    if CHROME_HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    options.add_argument(f"user-agent={UA}")

    profile_dir = _mk_profile_dir(profile_prefix)
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--remote-debugging-port={_pick_free_port()}")

    if CHROME_BINARY:
        options.binary_location = CHROME_BINARY

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(log_output=CHROME_DRIVER_LOG)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    if HAS_STEALTH:
        stealth(
            driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {"headers": {"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}},
        )
    except Exception:
        pass

    setattr(driver, "_profile_dir", profile_dir)
    return driver


def _quit_chrome_driver(driver: webdriver.Chrome):
    try:
        driver.quit()
    except Exception:
        pass
    profile_dir = getattr(driver, "_profile_dir", None)
    if profile_dir and os.path.isdir(profile_dir):
        shutil.rmtree(profile_dir, ignore_errors=True)


# ========================= WB (HTTP API) =========================

def _wb_set_block(seconds: float):
    global _wb_blocked_until
    if not WB_GLOBAL_COOLDOWN:
        return
    until = time.time() + max(0.0, float(seconds))
    with _wb_block_lock:
        if until > _wb_blocked_until:
            _wb_blocked_until = until


def _wb_wait_if_blocked():
    if not WB_GLOBAL_COOLDOWN:
        return
    with _wb_block_lock:
        until = _wb_blocked_until
    now = time.time()
    if until > now:
        time.sleep(until - now)


def _wb_rate_sleep_if_needed():
    global _wb_last_request_ts
    _wb_wait_if_blocked()
    with _wb_rate_lock:
        now = time.time()
        wait = WB_MIN_INTERVAL - (now - _wb_last_request_ts)
        if wait > 0:
            time.sleep(wait)
        _wb_last_request_ts = time.time()


def _wb_urlopen_with_retry(req: UrlRequest) -> bytes:
    last_exc = None
    for attempt in range(WB_MAX_RETRIES):
        _wb_rate_sleep_if_needed()
        try:
            with urlopen(req, timeout=WB_API_TIMEOUT) as resp:
                return resp.read()
        except HTTPError as e:
            last_exc = e
            if getattr(e, "code", None) == 429:
                ra = e.headers.get("Retry-After")
                delay = None
                if ra:
                    try:
                        delay = float(ra)
                    except Exception:
                        delay = None
                if delay is None:
                    delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
                _wb_set_block(delay)
                logger.warning("WB 429 retry in %.2fs attempt %s/%s", delay, attempt + 1, WB_MAX_RETRIES)
                time.sleep(delay)
                continue
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            logger.warning("WB HTTP %s retry in %.2fs attempt %s/%s", getattr(e, "code", None), delay, attempt + 1, WB_MAX_RETRIES)
            time.sleep(delay)
            continue
        except (URLError, TimeoutError) as e:
            last_exc = e
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            time.sleep(delay)
            continue
        except Exception as e:
            last_exc = e
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            time.sleep(delay)
            continue
    raise last_exc


def _wb_img_url_from_nmid(nm_id: int) -> str:
    # Нужно как в примере: basket-XX.wbcontent.net + /images/big/1.webp
    # vol = nmId // 100000, part = nmId // 1000
    vol = nm_id // 100000
    part = nm_id // 1000
    basket = 1 + (vol % 30)  # эвристика 01..30
    return f"https://basket-{basket:02d}.wbcontent.net/vol{vol}/part{part}/{nm_id}/images/big/1.webp"


def _wb_extract_img_url(p: dict) -> str:
    # 1) готовые url
    for key in ("img_url", "imgUrl", "image", "imageUrl", "picUrl", "pic_url", "photo", "photoUrl", "image_url"):
        v = p.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()

    # 2) pics list
    pics = p.get("pics")
    if isinstance(pics, list) and pics:
        first = pics[0]
        if isinstance(first, str) and first.startswith("http"):
            return first.strip()
        if isinstance(first, dict):
            for k in ("url", "src", "image", "img", "big", "small"):
                vv = first.get(k)
                if isinstance(vv, str) and vv.startswith("http"):
                    return vv.strip()

    # 3) fallback по id/nmId
    nm_id = p.get("nmId") or p.get("id")
    try:
        nm_id = int(nm_id)
    except Exception:
        return ""
    return _wb_img_url_from_nmid(nm_id)


def _wb_api_collect_sync(query: str, limit: int) -> List[dict]:
    base = f"https://{WB_API_HOST}/exactmatch/{WB_LANG}/common/{WB_API_VERSION}/search"
    out: List[dict] = []
    seen: Set[str] = set()
    page = 1

    while len(out) < limit and page <= WB_MAX_PAGES:
        params = {
            "appType": WB_APP_TYPE,
            "curr": WB_CURR,
            "dest": WB_DEST,
            "lang": WB_LANG,
            "page": str(page),
            "query": query,
            "resultset": "catalog",
            "sort": WB_SORT,
            "spp": str(WB_SPP),
        }
        url = base + "?" + urlencode(params, quote_via=quote_plus)

        req = UrlRequest(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Referer": "https://www.wildberries.ru",
                "Origin": "https://www.wildberries.ru",
                "Connection": "close",
            },
        )

        raw = _wb_urlopen_with_retry(req)
        data = json.loads(raw.decode("utf-8", errors="ignore"))

        products = data.get("products")
        if products is None:
            products = (data.get("data") or {}).get("products")

        if not isinstance(products, list) or not products:
            break

        for p in products:
            try:
                pid = p.get("id") or p.get("nmId")
                name = p.get("name") or ""

                # цена в копейках
                product_price = None
                sizes = p.get("sizes")
                if isinstance(sizes, list) and sizes:
                    product_price = (sizes[0].get("price") or {}).get("product")
                if product_price is None:
                    product_price = (p.get("priceU") or p.get("salePriceU") or 0)

                price_rub = str(int(product_price) // 100) if int(product_price) > 0 else "0"

                link = f"https://www.wildberries.ru/catalog/{pid}/detail.aspx" if pid else ""
                # без округлений
                rating = str(p.get("rating")) if p.get("rating") is not None else ""
                reviews = str(p.get("feedbacks")) if p.get("feedbacks") is not None else ""
                img_url = _wb_extract_img_url(p)

                item = {
                    "marketplace": "wildberries",
                    "name": name,
                    "url": link,
                    "price": price_rub,
                    "rating": rating,
                    "reviews": reviews,
                    "img_url": img_url,
                }

                if valid_product_item(item, seen):
                    seen.add(item["url"])
                    out.append(item)
                    if len(out) >= limit:
                        break
            except Exception:
                continue

        page += 1

    return out[:limit]


async def collect_wb(query: str, limit: int) -> List[dict]:
    async with _wb_semaphore:
        try:
            return await asyncio.to_thread(_wb_api_collect_sync, query, limit)
        except Exception as e:
            logger.error("WB API failed: %s", e, exc_info=True)
            return []


# ========================= OZON (Selenium + BS4) =========================

def _extract_ozon_img(card) -> str:
    img = card.select_one("img")
    if not img:
        return ""
    src = (img.get("src") or "").strip()
    if src:
        return src
    return _first_src_from_srcset(img.get("srcset") or "")


def _extract_ozon_rating_reviews(card) -> Tuple[str, str]:
    # Надёжно: в твоём дампе рейтинг = span style "...textPremium" (например 4.9/5.0),
    # отзывы = span style "...textSecondary" (например 386/1 903/36). [file:2]
    rating = ""
    reviews = ""

    # 1) Самый надёжный путь: текстовые span по style (не зависит от классов p6b305-*)
    rating_el = card.select_one("span[style*='textPremium']")
    if rating_el:
        rating = _clean_spaces(rating_el.get_text(" ", strip=True)).replace(",", ".")
        # строгая валидация 1..5(.d)
        if not re.fullmatch(r"[1-5](?:\.\d)?", rating):
            rating = ""

    # отзывы часто идут как число (иногда с nbsp) в textSecondary
    # но textSecondary встречается и в других местах, поэтому берём первое подходящее "число отзывов"
    secondary = card.select("span[style*='textSecondary']")
    for el in secondary:
        t = _clean_spaces(el.get_text(" ", strip=True))
        d = digits_only(t)
        if not d:
            continue
        # отзывы обычно 1..500000 (под твои примеры 36, 386, 1903) [file:2]
        try:
            v = int(d)
        except Exception:
            continue
        if 0 <= v <= 500000:
            reviews = str(v)
            break

    # 2) Фолбэк: если Ozon отдал только JSON в data-state (в дампе это тоже есть) [file:2]
    if not rating or not reviews:
        # пробуем вытащить из сырого html карточки фрагменты "title":"4.9" / "title":"386"
        raw = str(card)
        if not rating:
            m = re.search(r'"title"\s*:\s*"([1-5](?:\.\d)?)\s*"', raw)
            if m:
                rating = m.group(1)
        if not reviews:
            m = re.search(r'"title"\s*:\s*"(\d[\d ]{0,10})\s*"', raw)
            if m:
                reviews = digits_only(m.group(1))

    return rating, reviews


def _parse_ozon_html(html: str, seen: Set[str], left: int) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=re.compile(r"tile-root"))
    results: List[dict] = []

    for card in cards:
        try:
            # URL
            lnk = card.find("a", class_=re.compile(r"tile-clickable-element")) or card.find("a", href=re.compile(r"^/product"))
            href = (lnk.get("href") or "").strip() if lnk else ""
            if not href:
                continue

            url = ("https://www.ozon.ru" + href.split("?")[0]) if not href.startswith("http") else href.split("?")[0]
            if not url or url in seen:
                continue

            # PRICE: берём первый tsHeadline500Medium внутри карточки (это “цена сейчас” в твоём примере) [file:2]
            price_tag = card.find("span", class_=re.compile(r"tsHeadline500Medium"))
            price = digits_only(price_tag.get_text(" ", strip=True)) if price_tag else ""
            if not price:
                continue

            # NAME: берём первый tsBody500Medium (в твоём html это заголовок) [file:2]
            name = ""
            name_tag = card.find("span", class_=re.compile(r"tsBody500Medium"))
            if name_tag:
                name = _clean_spaces(name_tag.get_text(" ", strip=True))
            if not name and lnk:
                name = _clean_spaces(lnk.get_text(" ", strip=True))

            img_url = _extract_ozon_img(card)
            rating, reviews = _extract_ozon_rating_reviews(card)

            item = {
                "marketplace": "ozon",
                "name": name or "",
                "url": url,
                "price": price,
                "rating": rating,
                "reviews": reviews,
                "img_url": img_url,
            }

            if valid_product_item(item, seen):
                seen.add(url)
                results.append(item)
                if len(results) >= left:
                    break
        except Exception:
            continue

    return results


def _wait_tiles_increase(driver: webdriver.Chrome, prev_count: int, timeout: int) -> bool:
    def cond(d):
        try:
            return len(d.find_elements(By.CSS_SELECTOR, OZON_TILE_SELECTOR)) > prev_count
        except Exception:
            return False

    try:
        WebDriverWait(driver, timeout).until(cond)
        return True
    except TimeoutException:
        return False


def _ozon_try_click_load_more(driver: webdriver.Chrome) -> bool:
    xpaths = [
        "//button[contains(., 'Показать ещё')]",
        "//button[contains(., 'Показать еще')]",
        "//button[contains(., 'Ещё')]",
        "//button[contains(., 'Еще')]",
    ]
    for xp in xpaths:
        try:
            btn = driver.find_element(By.XPATH, xp)
            if btn and btn.is_displayed():
                driver.execute_script("arguments[0].click()", btn)
                return True
        except Exception:
            pass
    return False


def _ozon_sync_collect(driver: webdriver.Chrome, query: str, limit: int) -> List[dict]:
    seen: Set[str] = set()
    results: List[dict] = []

    url = f"https://www.ozon.ru/search/?text={quote_plus(query)}&from_global=true"
    driver.get(url)
    time.sleep(2.0 + random.uniform(0.2, 0.8))

    html0 = driver.page_source or ""
    if _looks_like_ozon_block(html0, driver.title or ""):
        _dump_html("ozon-block", html0)
        return []

    WebDriverWait(driver, OZON_WAIT_FIRST).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, OZON_TILE_SELECTOR)) >= 1
    )

    stagnation = 0

    for _ in range(OZON_SCROLL_ROUNDS):
        html = driver.page_source or ""
        if _looks_like_ozon_block(html, driver.title or ""):
            _dump_html("ozon-block", html)
            break

        part = _parse_ozon_html(html, seen, left=limit - len(results))
        if part:
            results.extend(part)
            if len(results) >= limit:
                break

        prev_tiles = len(driver.find_elements(By.CSS_SELECTOR, OZON_TILE_SELECTOR))

        driver.execute_script("window.scrollBy(0, arguments[0])", OZON_SCROLL_STEP)

        grew = _wait_tiles_increase(driver, prev_tiles, timeout=OZON_WAIT_NEW_TILES)
        if not grew:
            if _ozon_try_click_load_more(driver):
                grew = _wait_tiles_increase(driver, prev_tiles, timeout=OZON_WAIT_NEW_TILES)

        if not grew:
            stagnation += 1
            if stagnation >= OZON_STAGNATION_LIMIT:
                break
        else:
            stagnation = 0

        time.sleep(OZON_SCROLL_PAUSE + random.uniform(0.05, 0.25))

    if len(results) < limit:
        html = driver.page_source or ""
        part = _parse_ozon_html(html, seen, left=limit - len(results))
        if part:
            results.extend(part)

    return results[:limit]


async def collect_ozon(query: str, limit: int) -> List[dict]:
    async with _ozon_sem:
        need_min = min(limit, OZON_MIN_ITEMS)

        for attempt in range(OZON_RETRIES):
            driver = await asyncio.to_thread(_new_chrome_driver, "ozon-profile")
            try:
                items = await asyncio.to_thread(_ozon_sync_collect, driver, query, limit)
                if len(items) >= need_min:
                    return items
                if attempt < OZON_RETRIES - 1:
                    time.sleep(2.0 + random.uniform(0.5, 1.5))
                    continue
                return items
            except Exception as e:
                logger.error("Ozon collect failed: %s", e, exc_info=True)
                if attempt < OZON_RETRIES - 1:
                    time.sleep(2.0 + random.uniform(0.5, 1.5))
                    continue
                return []
            finally:
                await asyncio.to_thread(_quit_chrome_driver, driver)


# ========================= APP LIFECYCLE =========================

@app.on_event("startup")
async def startup_event():
    global _virtual_display
    if USE_XVFB and not CHROME_HEADLESS and os.name != "nt" and not os.environ.get("DISPLAY") and HAS_XVFB:
        _virtual_display = Display(visible=0, size=(1920, 1080))
        _virtual_display.start()
        logger.info("Xvfb started. DISPLAY=%s", os.environ.get("DISPLAY"))


@app.on_event("shutdown")
async def shutdown_event():
    global _virtual_display
    if _virtual_display:
        try:
            _virtual_display.stop()
        except Exception:
            pass
        _virtual_display = None
        logger.info("Xvfb stopped")


# ========================= API =========================

@app.get("/api/products", response_model=UnifiedProductsResponse)
async def get_products(request: Request, q: str = Query(..., description="Search query")):
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(status_code=400, detail="Invalid q")

    q = q.strip()
    cache_key = f"products:{q}"
    cached = get_from_cache(cache_key)
    if cached:
        return UnifiedProductsResponse(**cached)

    tasks = []
    if ENABLE_WB:
        tasks.append(collect_wb(q, WB_ITEMS))
    if ENABLE_OZON:
        tasks.append(collect_ozon(q, OZON_ITEMS))

    if not tasks:
        raise HTTPException(status_code=500, detail="No marketplaces enabled")

    start_time = datetime.now()
    parts = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: List[ProductItem] = []
    for part in parts:
        if isinstance(part, Exception):
            logger.error("Task failed: %s", part, exc_info=True)
            continue
        all_items.extend(ProductItem(**item) for item in part)

    final_items = all_items[:MAX_ITEMS]
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("Query=%s items=%s time=%.2fs", q, len(final_items), elapsed)

    payload = {
        "query": q,
        "count": len(final_items),
        "items": [it.model_dump() for it in final_items],
    }
    set_to_cache(cache_key, payload)
    return UnifiedProductsResponse(query=q, count=len(final_items), items=final_items)


@app.get("/health")
def health():
    return {"status": "ok", "version": "5.8.0"}


@app.get("/cache-stats")
def cache_stats():
    return {
        "cache_enabled": ENABLE_CACHE,
        "cache_size": len(_cache),
        "cache_ttl": CACHE_TTL,
        "enable_wb": ENABLE_WB,
        "enable_ozon": ENABLE_OZON,
        "wb_items": WB_ITEMS,
        "ozon_items": OZON_ITEMS,
        "chrome_headless": CHROME_HEADLESS,
        "use_xvfb": USE_XVFB,
        "has_xvfb": HAS_XVFB,
        "has_stealth": HAS_STEALTH,
        "wb_concurrent_limit": WB_CONCURRENT_LIMIT,
        "ozon_browser_limit": OZON_BROWSER_LIMIT,
        "ozon_min_items": OZON_MIN_ITEMS,
        "ozon_wait_new_tiles": OZON_WAIT_NEW_TILES,
        "ozon_stagnation_limit": OZON_STAGNATION_LIMIT,
        "wb_global_cooldown": WB_GLOBAL_COOLDOWN,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8002")))
