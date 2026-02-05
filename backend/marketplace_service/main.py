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
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlencode
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup
from fastapi.responses import RedirectResponse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


try:
    from selenium_stealth import stealth
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False


try:
    from pyvirtualdisplay import Display
    HAS_XVFB = True
except Exception:
    HAS_XVFB = False


try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False


MAX_ITEMS = int(os.getenv("MAX_ITEMS", "120"))
DEFAULT_PAGE_ITEMS = int(os.getenv("PAGE_ITEMS", "24"))

ENABLE_CACHE = os.getenv("ENABLE_CACHE", "1") == "1"
CACHE_TTL = int(os.getenv("CACHE_TTL", "120"))

ENABLE_WB = os.getenv("ENABLE_WB", "1") == "1"
ENABLE_OZON = os.getenv("ENABLE_OZON", "1") == "1"
ENABLE_YM = os.getenv("ENABLE_YM", "1") == "1"

SEARCH_TOTAL_TIMEOUT = float(os.getenv("SEARCH_TOTAL_TIMEOUT", "5"))
WB_TASK_TIMEOUT = float(os.getenv("WB_TASK_TIMEOUT", "4.5"))
OZON_TASK_TIMEOUT = float(os.getenv("OZON_TASK_TIMEOUT", "4.5"))
YM_TASK_TIMEOUT = float(os.getenv("YM_TASK_TIMEOUT", "4.5"))

OZON_ITEMS = int(os.getenv("OZON_ITEMS", "15"))
OZON_BROWSER_LIMIT = int(os.getenv("OZON_BROWSER_LIMIT", "1"))
OZON_RETRIES = int(os.getenv("OZON_RETRIES", "2"))
OZON_MIN_ITEMS = int(os.getenv("OZON_MIN_ITEMS", "10"))
OZON_CACHE_TTL = int(os.getenv("OZON_CACHE_TTL", "300"))

OZON_WAIT_FIRST = float(os.getenv("OZON_WAIT_FIRST", "6"))
OZON_SCROLL_ROUNDS = int(os.getenv("OZON_SCROLL_ROUNDS", "20"))
OZON_SCROLL_PAUSE = float(os.getenv("OZON_SCROLL_PAUSE", "0.18"))
OZON_TILE_SELECTOR = os.getenv("OZON_TILE_SELECTOR", "div[class*='tile-root']")
OZON_WAIT_NEW_TILES = float(os.getenv("OZON_WAIT_NEW_TILES", "1.2"))
OZON_STAGNATION_LIMIT = int(os.getenv("OZON_STAGNATION_LIMIT", "7"))
OZON_SCROLL_STEP = int(os.getenv("OZON_SCROLL_STEP", "1500"))
OZON_PAGE_LOAD_STRATEGY = os.getenv("OZON_PAGE_LOAD_STRATEGY", "none")
OZON_DRIVER_REUSE = os.getenv("OZON_DRIVER_REUSE", "1") == "1"
OZON_FAST_JS_EXTRACT = os.getenv("OZON_FAST_JS_EXTRACT", "1") == "1"
OZON_TOTAL_BUDGET = float(os.getenv("OZON_TOTAL_BUDGET", "4.0"))
OZON_WARMUP = os.getenv("OZON_WARMUP", "1") == "1"

CHROME_BINARY = os.getenv("CHROME_BINARY")
CHROME_DRIVER_LOG = os.getenv("CHROME_DRIVER_LOG", os.devnull)
PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "60"))
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "1") == "1"
USE_XVFB = os.getenv("USE_XVFB", "1") == "1"
CHROME_BLOCK_IMAGES = os.getenv("CHROME_BLOCK_IMAGES", "0") == "1"
CHROME_BLOCK_STYLES = os.getenv("CHROME_BLOCK_STYLES", "1") == "1"

YM_ITEMS = int(os.getenv("YM_ITEMS", "20"))
YM_CONCURRENT_LIMIT = int(os.getenv("YM_CONCURRENT_LIMIT", "4"))
YM_API_TIMEOUT = float(os.getenv("YM_API_TIMEOUT", "4.0"))
YM_TOTAL_BUDGET = float(os.getenv("YM_TOTAL_BUDGET", "3.5"))
YM_MAX_RETRIES = int(os.getenv("YM_MAX_RETRIES", "2"))
YM_MAX_PAGES = int(os.getenv("YM_MAX_PAGES", "1"))
YM_CACHE_TTL = int(os.getenv("YM_CACHE_TTL", "300"))
YM_LR = os.getenv("YM_LR", "").strip()
YM_GPS = os.getenv("YM_GPS", "").strip()
YM_BASE_URL = os.getenv("YM_BASE_URL", "https://market.yandex.ru/search").strip()

WB_ITEMS = int(os.getenv("WB_ITEMS", "35"))
WB_CONCURRENT_LIMIT = int(os.getenv("WB_CONCURRENT_LIMIT", "4"))
WB_API_TIMEOUT = float(os.getenv("WB_API_TIMEOUT", "3.2"))
WB_MIN_INTERVAL = float(os.getenv("WB_MIN_INTERVAL", "0.45"))
WB_MAX_RETRIES = int(os.getenv("WB_MAX_RETRIES", "5"))
WB_BACKOFF_BASE = float(os.getenv("WB_BACKOFF_BASE", "1.5"))
WB_BACKOFF_MAX = float(os.getenv("WB_BACKOFF_MAX", "30"))
WB_TOTAL_BUDGET = float(os.getenv("WB_TOTAL_BUDGET", "3.5"))
WB_MAX_PAGES = int(os.getenv("WB_MAX_PAGES", "1"))

WB_API_VERSION = os.getenv("WB_API_VERSION", "v18")
WB_API_HOST = os.getenv("WB_API_HOST", "search.wb.ru")
WB_DEST = os.getenv("WB_DEST", "-1257786")
WB_SPP = int(os.getenv("WB_SPP", "30"))
WB_APP_TYPE = os.getenv("WB_APP_TYPE", "1")
WB_LANG = os.getenv("WB_LANG", "ru")
WB_CURR = os.getenv("WB_CURR", "rub")
WB_SORT = os.getenv("WB_SORT", "popular")
WB_IMAGE_EXT = os.getenv("WB_IMAGE_EXT", "webp").lstrip(".")
WB_USER_AGENTS = [
    u.strip()
    for u in os.getenv("WB_USER_AGENTS", "").split("||")
    if u.strip()
]
WB_PROXY_URLS = [
    p.strip()
    for p in os.getenv("WB_PROXY_URLS", "").split(",")
    if p.strip()
]
WB_IMAGE_HOSTS = [
    h.strip()
    for h in os.getenv("WB_IMAGE_HOSTS", "wbbasket.ru,wb.ru,wbcontent.net").split(",")
    if h.strip()
]
WB_IMAGE_SIZES = [
    s.strip()
    for s in os.getenv("WB_IMAGE_SIZES", "c246x328,c516x688,big,tm").split(",")
    if s.strip()
]

WB_GLOBAL_COOLDOWN = os.getenv("WB_GLOBAL_COOLDOWN", "1") == "1"
WB_429_COOLDOWN = float(os.getenv("WB_429_COOLDOWN", "2.0"))
WB_BLOCK_MAX_WAIT = float(os.getenv("WB_BLOCK_MAX_WAIT", "0.8"))
WB_CACHE_TTL = int(os.getenv("WB_CACHE_TTL", "300"))
WB_CACHE_STALE_TTL = int(os.getenv("WB_CACHE_STALE_TTL", "1800"))
WB_USE_IMAGE_PROXY = os.getenv("WB_USE_IMAGE_PROXY", "1") == "1"
WB_IMAGE_PROXY_TIMEOUT = float(os.getenv("WB_IMAGE_PROXY_TIMEOUT", "1.2"))
WB_IMAGE_PROXY_TTL = int(os.getenv("WB_IMAGE_PROXY_TTL", "3600"))
WB_IMAGE_PROXY_PROBE = os.getenv("WB_IMAGE_PROXY_PROBE", "1") == "1"
WB_IMAGE_PROBE_MAX_BASKETS = int(os.getenv("WB_IMAGE_PROBE_MAX_BASKETS", "12"))

UA = os.getenv(
    "UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)

DUMP_HTML = os.getenv("DUMP_HTML", "0") == "1"


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("marketplace_service")

app = FastAPI(title="Unified Marketplace API", version="10.0.0")

_cache: Dict[str, Tuple[dict, datetime]] = {}
_cache_lock = threading.RLock()

_virtual_display: Optional["Display"] = None

_ozon_sem = asyncio.Semaphore(OZON_BROWSER_LIMIT)
_wb_semaphore = asyncio.Semaphore(WB_CONCURRENT_LIMIT)
_ym_semaphore = asyncio.Semaphore(YM_CONCURRENT_LIMIT)

_wb_rate_lock = threading.Lock()
_wb_last_request_ts = 0.0

_wb_block_lock = threading.Lock()
_wb_blocked_until = 0.0

_wb_cache: Dict[str, Tuple[List[dict], datetime]] = {}
_wb_cache_lock = threading.RLock()

_ozon_cache: Dict[str, Tuple[List[dict], datetime]] = {}
_ozon_cache_lock = threading.RLock()

_ym_cache: Dict[str, Tuple[List[dict], datetime]] = {}
_ym_cache_lock = threading.RLock()

_wb_img_cache: Dict[str, Tuple[str, datetime]] = {}
_wb_img_cache_lock = threading.RLock()

_wb_inflight_lock = asyncio.Lock()
_wb_inflight_tasks: Dict[str, asyncio.Task] = {}

_ozon_driver_lock = threading.RLock()
_ozon_driver: Optional[webdriver.Chrome] = None


class ProductItem(BaseModel):
    name: Optional[str]
    url: Optional[str]
    price: Optional[str]
    rating: Optional[str]
    reviews: Optional[str]
    img_url: Optional[str]
    image_urls: Optional[List[str]] = None
    marketplace: str


class UnifiedProductsResponse(BaseModel):
    query: str
    count: int
    items: List[ProductItem]
    offset: int = 0
    limit: int = 0
    total: Optional[int] = None
    has_more: Optional[bool] = None


def get_from_cache(key: str) -> Optional[dict]:
    if not ENABLE_CACHE:
        return None
    with _cache_lock:
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
    now = datetime.now()
    with _cache_lock:
        _cache[key] = (data, now)


def _wb_cache_get(query: str, allow_stale: bool = False) -> Optional[List[dict]]:
    if WB_CACHE_TTL <= 0:
        return None
    now = datetime.now()
    with _wb_cache_lock:
        item = _wb_cache.get(query)
        if not item:
            return None
        data, ts = item
        age = (now - ts).total_seconds()
        if age <= WB_CACHE_TTL:
            return data
        if allow_stale and age <= WB_CACHE_STALE_TTL:
            return data
        if age > WB_CACHE_STALE_TTL:
            _wb_cache.pop(query, None)
        return None


def _wb_cache_set(query: str, items: List[dict]):
    if WB_CACHE_TTL <= 0:
        return
    with _wb_cache_lock:
        _wb_cache[query] = (items, datetime.now())


def _ozon_cache_get(query: str) -> Optional[List[dict]]:
    if OZON_CACHE_TTL <= 0:
        return None
    now = datetime.now()
    with _ozon_cache_lock:
        item = _ozon_cache.get(query)
        if not item:
            return None
        data, ts = item
        if (now - ts).total_seconds() <= OZON_CACHE_TTL:
            return data
        _ozon_cache.pop(query, None)
        return None


def _ozon_cache_set(query: str, items: List[dict]):
    if OZON_CACHE_TTL <= 0:
        return
    with _ozon_cache_lock:
        _ozon_cache[query] = (items, datetime.now())

def _ym_cache_get(query: str) -> Optional[List[dict]]:
    if YM_CACHE_TTL <= 0:
        return None
    now = datetime.now()
    with _ym_cache_lock:
        item = _ym_cache.get(query)
        if not item:
            return None
        data, ts = item
        if (now - ts).total_seconds() <= YM_CACHE_TTL:
            return data
        _ym_cache.pop(query, None)
        return None


def _ym_cache_set(query: str, items: List[dict]):
    if YM_CACHE_TTL <= 0:
        return
    with _ym_cache_lock:
        _ym_cache[query] = (items, datetime.now())


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


def _calc_market_limit(target: int, market_max: int, enabled_count: int) -> int:
    if target <= 0:
        return 0
    base = max(1, int((target + max(1, enabled_count) - 1) / max(1, enabled_count)))
    buffer = 2
    return min(int(market_max), base + buffer)


def _merge_items(existing: List[dict], new_items: List[dict], max_items: int) -> List[dict]:
    if not existing:
        return new_items[:max_items]
    out = list(existing)
    seen = {it.get("url") for it in existing if isinstance(it, dict)}
    for item in new_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
        if len(out) >= max_items:
            break
    return out[:max_items]


def _looks_like_ym_block(html: str, title: str = "") -> bool:
    t = (html or "").lower()
    tt = (title or "").lower()
    return (
        "smartcaptcha" in t
        or "showcaptcha" in t
        or "yandex smartcaptcha" in t
        or "captcha" in t
        or "access denied" in t
        or "captcha" in tt
        or "smartcaptcha" in tt
    )


def _normalize_ym_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        u = "https://market.yandex.ru" + u
    u = u.split("#", 1)[0].split("?", 1)[0]
    return u


def _normalize_ym_image_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://market.yandex.ru" + u
    return u


def _first_src_from_srcset(srcset: str) -> str:
    if not srcset:
        return ""
    best_url = ""
    best_score = -1.0
    fallback_last = ""

    for raw in (srcset or "").split(","):
        part = (raw or "").strip()
        if not part:
            continue
        chunks = part.split()
        url = (chunks[0] or "").strip() if chunks else ""
        if not url:
            continue
        fallback_last = url
        score = 0.0
        if len(chunks) >= 2:
            desc = (chunks[1] or "").strip().lower()
            try:
                if desc.endswith("w"):
                    score = float(int(desc[:-1]))
                elif desc.endswith("x"):
                    score = float(desc[:-1]) * 1000.0
            except Exception:
                score = 0.0
        if score >= best_score:
            best_score = score
            best_url = url

    return best_url or fallback_last


def _parse_compact_number(text: str) -> Optional[int]:
    if not text:
        return None
    raw = (text or "").replace("\u00a0", " ").replace("\u202f", " ").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw)
    m = re.search(r"(\d+(?:[.,]\d+)?)(k|тыс\.?|млн|m)?", compact, re.IGNORECASE)
    if not m:
        return None
    num_raw = (m.group(1) or "").replace(",", ".")
    suffix = (m.group(2) or "").lower()
    try:
        value = float(num_raw)
    except Exception:
        return None
    if suffix in ("k", "тыс", "тыс."):
        value *= 1000.0
    elif suffix in ("m", "млн"):
        value *= 1000000.0
    return int(round(value))


def _ym_extract_rating_reviews(card) -> Tuple[str, str]:
    rating = ""
    reviews = ""

    rating_el = card.select_one('[data-auto="reviews"]')
    if not rating_el:
        return rating, reviews

    rating_val = rating_el.select_one(".ds-rating__value") or rating_el
    rating_text = _clean_spaces(rating_val.get_text(" ", strip=True)).replace(",", ".")
    if rating_text:
        m = re.search(r"[1-5](?:\.\d)?", rating_text)
        if m:
            rating = m.group(0)

    full_text = _clean_spaces(rating_el.get_text(" ", strip=True))
    if full_text:
        m = re.search(r"\(([^)]+)\)", full_text)
        if m:
            v = _parse_compact_number(m.group(1))
            if v is not None:
                reviews = str(v)
        if not reviews:
            nums = re.findall(r"\d+(?:[.,]\d+)?\s*(?:k|тыс\.?|млн|m)?", full_text, re.IGNORECASE)
            if len(nums) >= 2:
                v = _parse_compact_number(nums[1])
                if v is not None:
                    reviews = str(v)
            if not reviews:
                v = _parse_compact_number(full_text)
                if v is not None:
                    reviews = str(v)

    return rating, reviews


def _ym_extract_image_candidates(card) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def add(v: Optional[str]):
        if not isinstance(v, str):
            return
        u = _normalize_ym_image_url(v)
        if not u or u in seen or u.startswith("data:"):
            return
        seen.add(u)
        candidates.append(u)

    img = card.select_one("img")
    if img:
        add(img.get("src"))
        add(img.get("data-src"))
        add(img.get("data-original"))
        add(_first_src_from_srcset(img.get("srcset") or ""))
        add(_first_src_from_srcset(img.get("data-srcset") or ""))

    for s in card.select("picture source[srcset], source[srcset], picture source[data-srcset], source[data-srcset]"):
        add(_first_src_from_srcset(s.get("srcset") or ""))
        add(_first_src_from_srcset(s.get("data-srcset") or ""))

    return candidates


def _new_chrome_driver(profile_prefix: str) -> webdriver.Chrome:
    options = Options()

    try:
        options.page_load_strategy = (OZON_PAGE_LOAD_STRATEGY or "eager").strip()
    except Exception:
        pass

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
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    if CHROME_BLOCK_IMAGES:
        prefs["profile.managed_default_content_settings.images"] = 2
    if CHROME_BLOCK_STYLES:
        prefs["profile.managed_default_content_settings.stylesheet"] = 2
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
        try:
            blocked_urls: List[str] = []
            if CHROME_BLOCK_IMAGES:
                blocked_urls.extend(
                    ["*.jpg*", "*.jpeg*", "*.png*", "*.webp*", "*.gif*", "*.svg*"]
                )
            if CHROME_BLOCK_STYLES:
                blocked_urls.append("*.css*")
            blocked_urls.extend(
                ["*.woff*", "*.woff2*", "*.ttf*", "*.otf*", "*.mp4*", "*.m4s*", "*.mp3*"]
            )
            if blocked_urls:
                driver.execute_cdp_cmd(
                    "Network.setBlockedURLs",
                    {
                        "urls": blocked_urls,
                    },
                )
        except Exception:
            pass
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


def _wb_set_block(seconds: float):
    global _wb_blocked_until
    if not WB_GLOBAL_COOLDOWN:
        return
    until = time.time() + max(0.0, float(seconds))
    with _wb_block_lock:
        if until > _wb_blocked_until:
            _wb_blocked_until = until


def _wb_block_remaining() -> float:
    with _wb_block_lock:
        until = _wb_blocked_until
    return max(0.0, until - time.time())


def _wb_wait_if_blocked(deadline_ts: float):
    if not WB_GLOBAL_COOLDOWN:
        return
    while True:
        if time.time() >= deadline_ts:
            return
        now = time.time()
        with _wb_block_lock:
            until = _wb_blocked_until
        remaining = until - now
        if remaining <= 0:
            return
        time.sleep(min(remaining, WB_BLOCK_MAX_WAIT, max(0.0, deadline_ts - time.time())))


def _wb_rate_sleep_if_needed(deadline_ts: float):
    global _wb_last_request_ts
    if time.time() >= deadline_ts:
        return
    _wb_wait_if_blocked(deadline_ts)
    with _wb_rate_lock:
        now = time.time()
        wait = WB_MIN_INTERVAL - (now - _wb_last_request_ts)
        if wait > 0:
            time.sleep(min(wait, max(0.0, deadline_ts - time.time())))
        _wb_last_request_ts = time.time()

def _wb_retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    ra = value.strip()
    if not ra:
        return None
    try:
        return max(0.0, float(ra))
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(ra)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0.0, (dt.astimezone(timezone.utc) - now).total_seconds())
    except Exception:
        return None


def _wb_pick_user_agent() -> str:
    if WB_USER_AGENTS:
        return random.choice(WB_USER_AGENTS)
    return UA


def _wb_pick_proxy() -> Optional[str]:
    if WB_PROXY_URLS:
        return random.choice(WB_PROXY_URLS)
    return None


def _wb_apply_user_agent(req: UrlRequest, ua: str):
    if not ua:
        return
    try:
        req.headers["User-agent"] = ua
        req.headers["User-Agent"] = ua
    except Exception:
        pass
    try:
        req.unredirected_hdrs["User-agent"] = ua
        req.unredirected_hdrs["User-Agent"] = ua
    except Exception:
        pass


def _wb_requests_fetch(req: UrlRequest, timeout: float, proxy_url: Optional[str] = None) -> bytes:
    if not HAS_REQUESTS:
        raise URLError("requests not available")
    headers = dict(req.header_items() or [])
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    resp = requests.get(req.full_url, headers=headers, timeout=timeout, proxies=proxies)
    if int(resp.status_code) in (200, 206, 304):
        return resp.content
    raise HTTPError(req.full_url, resp.status_code, resp.reason, resp.headers, None)


def _wb_urlopen_with_retry(req: UrlRequest, deadline_ts: float) -> bytes:
    last_exc = None
    for attempt in range(WB_MAX_RETRIES):
        if time.time() >= deadline_ts:
            break
        if WB_GLOBAL_COOLDOWN and _wb_block_remaining() > 0:
            time.sleep(min(_wb_block_remaining(), max(0.0, deadline_ts - time.time())))
            if time.time() >= deadline_ts:
                break
        _wb_rate_sleep_if_needed(deadline_ts)
        _wb_apply_user_agent(req, _wb_pick_user_agent())
        try:
            remaining = max(0.1, float(deadline_ts - time.time()))
            timeout = min(float(WB_API_TIMEOUT), remaining)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as e:
            last_exc = e
            if getattr(e, "code", None) == 429:
                if WB_PROXY_URLS and HAS_REQUESTS and time.time() < deadline_ts:
                    try:
                        remaining = max(0.1, float(deadline_ts - time.time()))
                        timeout = min(float(WB_API_TIMEOUT), remaining)
                        proxy_url = _wb_pick_proxy()
                        if proxy_url:
                            return _wb_requests_fetch(req, timeout=timeout, proxy_url=proxy_url)
                    except Exception as e2:
                        last_exc = e2
                delay = _wb_retry_after_seconds(e.headers.get("Retry-After"))
                if delay is None:
                    delay = WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.35, 0.9)
                cooldown_floor = min(float(WB_429_COOLDOWN), 1.2)
                delay = min(float(WB_BACKOFF_MAX), max(float(delay), cooldown_floor))
                _wb_set_block(delay)
                time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
                continue
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
        except (URLError, TimeoutError) as e:
            last_exc = e
            if HAS_REQUESTS and time.time() < deadline_ts:
                try:
                    remaining = max(0.1, float(deadline_ts - time.time()))
                    timeout = min(float(WB_API_TIMEOUT), remaining)
                    return _wb_requests_fetch(req, timeout=timeout)
                except Exception as e2:
                    last_exc = e2
                if WB_PROXY_URLS and time.time() < deadline_ts:
                    try:
                        proxy_url = _wb_pick_proxy()
                        if proxy_url:
                            return _wb_requests_fetch(req, timeout=timeout, proxy_url=proxy_url)
                    except Exception as e3:
                        last_exc = e3
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
        except Exception as e:
            last_exc = e
            delay = min(WB_BACKOFF_MAX, WB_BACKOFF_BASE ** (attempt + 1) + random.uniform(0.2, 0.9))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
    if HAS_REQUESTS and time.time() < deadline_ts:
        try:
            remaining = max(0.1, float(deadline_ts - time.time()))
            timeout = min(float(WB_API_TIMEOUT), remaining)
            return _wb_requests_fetch(req, timeout=timeout)
        except Exception as e:
            last_exc = e
        if WB_PROXY_URLS and time.time() < deadline_ts:
            try:
                proxy_url = _wb_pick_proxy()
                if proxy_url:
                    return _wb_requests_fetch(req, timeout=timeout, proxy_url=proxy_url)
            except Exception as e2:
                last_exc = e2
    raise last_exc


def _wb_basket_base_candidates(vol: int) -> List[int]:
    candidates: List[int] = []

    def add(b: int):
        if 1 <= b <= 99 and b not in candidates:
            candidates.append(b)

    for denom in (100, 200):
        base = int((int(vol) // denom) + 1)
        add(base)

    if not candidates:
        add(1)
    return candidates


def _wb_basket_from_nmid(nm_id: int) -> int:
    vol = nm_id // 100000
    bases = _wb_basket_base_candidates(vol)
    return bases[0] if bases else 1


def _wb_basket_candidates_from_vol(vol: int) -> List[int]:
    candidates: List[int] = []
    bases = _wb_basket_base_candidates(vol)

    def add(b: int):
        if 1 <= b <= 99 and b not in candidates:
            candidates.append(b)

    if 1000 <= vol < 6000:
        deltas = (0, 2, 3, 1, 4, -1)
    elif 6000 <= vol < 8000:
        deltas = (0, -1, 1, -2, 2, 3)
    else:
        deltas = (0, 1, -1, 2, 3)

    for base in bases:
        for delta in deltas:
            add(int(base + delta))

    if not candidates:
        for base in bases:
            add(base)
    return candidates


def _wb_basket_candidates_from_nmid(nm_id: int) -> List[int]:
    vol = int(nm_id) // 100000
    return _wb_basket_candidates_from_vol(vol)


def _wb_basket_probe_order(vol: int) -> List[int]:
    candidates: List[int] = []
    bases = _wb_basket_base_candidates(vol)

    def add(b: int):
        if 1 <= b <= 99 and b not in candidates:
            candidates.append(b)

    for b in _wb_basket_candidates_from_vol(vol):
        add(b)

    if 1000 <= vol < 6000:
        extra = (5, 6, 7, 8, 9, 10, -2, -3)
    elif 6000 <= vol < 9000:
        extra = (-2, -3, -4, 2, 3, 4, 5)
    else:
        extra = (2, 3, 4, -2, -3, 5, 6)

    for base in bases:
        for delta in extra:
            add(int(base + delta))

    return candidates


def _wb_image_hosts() -> List[str]:
    hosts_raw = WB_IMAGE_HOSTS or ["wbbasket.ru", "wbcontent.net", "wb.ru"]
    allowed_suffixes = ("wbbasket.ru", "wbcontent.net", "wb.ru")
    hosts: List[str] = []
    for h in hosts_raw:
        normalized = (h or "").strip().lower()
        if not normalized:
            continue
        if normalized.endswith(allowed_suffixes) and normalized not in hosts:
            hosts.append(normalized)
    if not hosts:
        hosts = ["wbbasket.ru"]
    return hosts


def _wb_image_exts() -> List[str]:
    raw = (WB_IMAGE_EXT or "").strip()
    parts = [p.strip().lstrip(".") for p in re.split(r"[ ,;]+", raw) if p.strip()]
    if not parts:
        parts = ["webp"]
    for ext in ("webp", "jpg", "jpeg"):
        if ext not in parts:
            parts.append(ext)
    return parts


def _wb_img_url_from_nmid(nm_id: int, basket: int, ext: str, host_suffix: str, size: str) -> str:
    vol = nm_id // 100000
    part = nm_id // 1000
    size_dir = (size or "big").strip() or "big"
    suffix = (host_suffix or "wbbasket.ru").strip()
    return f"https://basket-{basket:02d}.{suffix}/vol{vol}/part{part}/{nm_id}/images/{size_dir}/1.{ext}"


def _wb_image_candidates(p: dict) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def add_url(value: str):
        if not isinstance(value, str):
            return
        url = value.strip()
        if not url.startswith("http") or url in seen:
            return
        seen.add(url)
        candidates.append(url)

    for key in ("img_url", "imgUrl", "image", "imageUrl", "picUrl", "pic_url", "photo", "photoUrl", "image_url"):
        add_url(p.get(key))

    pics = p.get("pics")
    if isinstance(pics, list) and pics:
        first = pics[0]
        if isinstance(first, str):
            add_url(first)
        if isinstance(first, dict):
            for k in ("url", "src", "image", "img", "big", "small"):
                add_url(first.get(k))

    nm_id = p.get("nmId") or p.get("id")
    try:
        nm_id = int(nm_id)
    except Exception:
        nm_id = None

    if nm_id:
        baskets: List[int] = []
        img_basket = p.get("img") or p.get("imgId") or p.get("img_id")
        try:
            img_basket = int(img_basket) if img_basket is not None else None
        except Exception:
            img_basket = None
        if img_basket and 1 <= img_basket <= 99:
            baskets.append(img_basket)

        for b in _wb_basket_candidates_from_nmid(nm_id):
            if b not in baskets:
                baskets.append(b)

        hosts = _wb_image_hosts()[:2]
        sizes = (WB_IMAGE_SIZES or ["c246x328", "c516x688", "big", "tm"])[:2]
        exts = _wb_image_exts()[:2]

        for basket in baskets:
            for host in hosts:
                for size in sizes:
                    for ext in exts:
                        add_url(_wb_img_url_from_nmid(nm_id, basket, ext, host, size))

    return candidates


def _wb_extract_img_url(p: dict) -> str:
    candidates = _wb_image_candidates(p)
    return candidates[0] if candidates else ""


def _wb_proxy_url(nm_id: int, size: str) -> str:
    size_clean = (size or "").strip() or "c246x328"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", size_clean):
        size_clean = "c246x328"
    return f"/api/wb-image/{int(nm_id)}?size={quote_plus(size_clean)}"


def _wb_proxy_url_with_basket(nm_id: int, size: str, basket: Optional[int]) -> str:
    base = _wb_proxy_url(nm_id, size)
    try:
        b = int(basket) if basket is not None else None
    except Exception:
        b = None
    if b and 1 <= b <= 99:
        return base + f"&b={int(b)}"
    return base


def _wb_img_cache_get(key: str) -> Optional[str]:
    now = datetime.now()
    with _wb_img_cache_lock:
        item = _wb_img_cache.get(key)
        if not item:
            return None
        url, ts = item
        if (now - ts).total_seconds() <= max(0, int(WB_IMAGE_PROXY_TTL)):
            return url
        _wb_img_cache.pop(key, None)
        return None


def _wb_img_cache_set(key: str, url: str):
    ttl = int(WB_IMAGE_PROXY_TTL)
    if ttl <= 0:
        return
    with _wb_img_cache_lock:
        _wb_img_cache[key] = (url, datetime.now())


def _wb_probe_image_url(nm_id: int, size: str, basket_hint: Optional[int] = None) -> Optional[str]:
    vol = int(nm_id) // 100000
    part = int(nm_id) // 1000
    size_dir = (size or "c246x328").strip() or "c246x328"
    exts = _wb_image_exts()
    hosts = _wb_image_hosts()

    try:
        bh = int(basket_hint) if basket_hint is not None else None
    except Exception:
        bh = None

    baskets: List[int] = []
    if bh and 1 <= bh <= 99:
        baskets.append(int(bh))
    for b in _wb_basket_probe_order(vol):
        if b not in baskets:
            baskets.append(b)
    max_baskets = max(1, int(WB_IMAGE_PROBE_MAX_BASKETS))
    baskets = baskets[:max_baskets]

    ua = _wb_pick_user_agent()
    for basket in baskets:
        for host in hosts[:2]:
            for ext in exts:
                url = (
                    f"https://basket-{basket:02d}.{host}/vol{vol}/part{part}/"
                    f"{int(nm_id)}/images/{size_dir}/1.{ext}"
                )
                try:
                    req = UrlRequest(
                        url,
                        method="HEAD",
                        headers={
                            "User-Agent": ua,
                            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                            "Connection": "close",
                        },
                    )
                    with urlopen(req, timeout=WB_IMAGE_PROXY_TIMEOUT) as resp:
                        code = getattr(resp, "status", None) or 200
                    if int(code) in (200, 206, 304):
                        return url
                except HTTPError:
                    continue
                except Exception:
                    continue

    return None


def _wb_api_collect_sync(query: str, limit: int) -> List[dict]:
    deadline_ts = time.time() + max(0.5, float(WB_TOTAL_BUDGET))
    base = f"https://{WB_API_HOST}/exactmatch/{WB_LANG}/common/{WB_API_VERSION}/search"
    out: List[dict] = []
    seen: Set[str] = set()
    page = 1

    while len(out) < limit and page <= WB_MAX_PAGES:
        if time.time() >= deadline_ts:
            break
        ua = _wb_pick_user_agent()
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
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Referer": "https://www.wildberries.ru/",
                "Origin": "https://www.wildberries.ru",
                "Connection": "close",
            },
        )

        raw = _wb_urlopen_with_retry(req, deadline_ts=deadline_ts)
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

                product_price = None
                sizes = p.get("sizes")
                if isinstance(sizes, list) and sizes:
                    product_price = (sizes[0].get("price") or {}).get("product")
                if product_price is None:
                    product_price = (p.get("priceU") or p.get("salePriceU") or 0)

                price_rub = str(int(product_price) // 100) if int(product_price) > 0 else "0"

                link = f"https://www.wildberries.ru/catalog/{pid}/detail.aspx" if pid else ""
                rating = str(p.get("rating")) if p.get("rating") is not None else ""
                reviews = str(p.get("feedbacks")) if p.get("feedbacks") is not None else ""
                img_candidates = _wb_image_candidates(p)
                image_urls = list(img_candidates)
                if WB_USE_IMAGE_PROXY and pid:
                    img_basket = p.get("img") or p.get("imgId") or p.get("img_id")
                    try:
                        img_basket = int(img_basket) if img_basket is not None else None
                    except Exception:
                        img_basket = None
                    proxy_url = _wb_proxy_url_with_basket(
                        int(pid),
                        size=(WB_IMAGE_SIZES[0] if WB_IMAGE_SIZES else "c246x328"),
                        basket=img_basket,
                    )
                    if img_basket and 1 <= img_basket <= 99:
                        ext = _wb_image_exts()[0]
                        host = _wb_image_hosts()[0]
                        img_url = _wb_img_url_from_nmid(
                            int(pid),
                            int(img_basket),
                            ext,
                            host,
                            (WB_IMAGE_SIZES[0] if WB_IMAGE_SIZES else "c246x328"),
                        )
                    else:
                        img_url = proxy_url
                    if proxy_url and proxy_url not in image_urls:
                        image_urls.insert(0, proxy_url)
                else:
                    img_url = image_urls[0] if image_urls else ""

                item = {
                    "marketplace": "wildberries",
                    "name": name,
                    "url": link,
                    "price": price_rub,
                    "rating": rating,
                    "reviews": reviews,
                    "img_url": img_url,
                    "image_urls": image_urls or None,
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
    query_str = (query or "").strip()
    cache_key = query_str.casefold()
    cached = _wb_cache_get(cache_key)
    if cached is not None and len(cached) >= limit:
        return cached[:limit]

    if WB_GLOBAL_COOLDOWN and _wb_block_remaining() > 0:
        cached = _wb_cache_get(cache_key, allow_stale=True)
        if cached is not None:
            return cached[:limit]

    inflight_key = f"{cache_key}:{int(limit)}"

    async with _wb_inflight_lock:
        task = _wb_inflight_tasks.get(inflight_key)
        if task is None:
            async def _run() -> List[dict]:
                async with _wb_semaphore:
                    return await asyncio.to_thread(_wb_api_collect_sync, query_str, limit)

            task = asyncio.create_task(_run())
            _wb_inflight_tasks[inflight_key] = task

    try:
        items = await asyncio.shield(task)
        _wb_cache_set(cache_key, items)
        return items[:limit]
    except HTTPError as e:
        if getattr(e, "code", None) == 429:
            logger.warning("WB API rate limited (429). Serving cached results if available.")
            cached = _wb_cache_get(cache_key, allow_stale=True)
            if cached is not None:
                return cached[:limit]
            return []
        logger.error("WB API failed: %s", e, exc_info=True)
        cached = _wb_cache_get(cache_key, allow_stale=True)
        if cached is not None:
            return cached[:limit]
        return []
    except Exception as e:
        if getattr(e, "code", None) == 429:
            logger.warning("WB API rate limited (429). Serving cached results if available.")
            cached = _wb_cache_get(cache_key, allow_stale=True)
            if cached is not None:
                return cached[:limit]
            return []
        logger.error("WB API failed: %s", e, exc_info=True)
        cached = _wb_cache_get(cache_key, allow_stale=True)
        if cached is not None:
            return cached[:limit]
        return []
    finally:
        if task.done():
            async with _wb_inflight_lock:
                if _wb_inflight_tasks.get(inflight_key) is task:
                    _wb_inflight_tasks.pop(inflight_key, None)


def _ym_build_search_url(query: str, page: int) -> str:
    params = {"text": query}
    if page and int(page) > 1:
        params["page"] = str(int(page))
    if YM_LR:
        params["lr"] = YM_LR
    if YM_GPS:
        params["gps"] = YM_GPS
    return YM_BASE_URL + "?" + urlencode(params, quote_via=quote_plus)


def _ym_urlopen_with_retry(req: UrlRequest, deadline_ts: float) -> bytes:
    last_exc = None
    for attempt in range(max(1, int(YM_MAX_RETRIES))):
        if time.time() >= deadline_ts:
            break
        try:
            remaining = max(0.1, float(deadline_ts - time.time()))
            timeout = min(float(YM_API_TIMEOUT), remaining)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as e:
            last_exc = e
            delay = min(2.5, 0.6 + (attempt + 1) * 0.5 + random.uniform(0.1, 0.4))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
        except (URLError, TimeoutError) as e:
            last_exc = e
            delay = min(2.0, 0.4 + (attempt + 1) * 0.4 + random.uniform(0.1, 0.4))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
        except Exception as e:
            last_exc = e
            delay = min(2.0, 0.4 + (attempt + 1) * 0.4 + random.uniform(0.1, 0.4))
            time.sleep(min(delay, max(0.0, deadline_ts - time.time())))
            continue
    raise last_exc


def _ym_parse_card(card) -> Optional[dict]:
    link_el = card.select_one('a[data-auto="snippet-link"]') or card.select_one("a[href*='/card/']")
    if not link_el:
        return None
    href = (link_el.get("href") or "").strip()
    if not href:
        return None
    url = _normalize_ym_url(href)
    if not url:
        return None

    name_el = card.select_one('[data-auto="snippet-title"]') or link_el
    name = _clean_spaces(name_el.get_text(" ", strip=True)) if name_el else ""

    price_el = card.select_one('[data-auto="snippet-price-current"]')
    price = digits_only(price_el.get_text(" ", strip=True)) if price_el else ""
    if not price:
        return None

    rating, reviews = _ym_extract_rating_reviews(card)
    image_urls = _ym_extract_image_candidates(card)
    img_url = image_urls[0] if image_urls else ""

    return {
        "marketplace": "yandex_market",
        "name": name or "",
        "url": url,
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "img_url": img_url,
        "image_urls": image_urls or None,
    }


def _ym_extract_items_from_html(html: str, limit: int) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('article[data-auto="searchOrganic"]')
    if not cards:
        cards = soup.select('article[data-auto="searchPromo"], article[data-auto="searchSponsored"]')
    if not cards:
        cards = soup.select('[data-zone-name="productSnippet"]')

    seen: Set[str] = set()
    results: List[dict] = []
    for card in cards:
        try:
            item = _ym_parse_card(card)
            if not item:
                continue
            if valid_product_item(item, seen):
                seen.add(item["url"])
                results.append(item)
                if len(results) >= limit:
                    break
        except Exception:
            continue
    return results[:limit]


def _ym_collect_sync(query: str, limit: int) -> List[dict]:
    deadline_ts = time.time() + max(0.5, float(YM_TOTAL_BUDGET))
    out: List[dict] = []
    seen: Set[str] = set()
    page = 1

    while len(out) < limit and page <= YM_MAX_PAGES:
        if time.time() >= deadline_ts:
            break
        url = _ym_build_search_url(query, page)
        req = UrlRequest(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Connection": "close",
            },
        )
        raw = _ym_urlopen_with_retry(req, deadline_ts=deadline_ts)
        html = raw.decode("utf-8", errors="ignore")
        items = _ym_extract_items_from_html(html, limit)
        if not items and _looks_like_ym_block(html):
            _dump_html("ym-block", html)
            break
        if not items:
            break
        for item in items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            out.append(item)
            if len(out) >= limit:
                break
        page += 1

    return out[:limit]


async def collect_ym(query: str, limit: int) -> List[dict]:
    query_str = (query or "").strip()
    if not query_str:
        return []
    cached = _ym_cache_get(query_str)
    if cached is not None and len(cached) >= limit:
        return cached[:limit]

    async with _ym_semaphore:
        try:
            items = await asyncio.to_thread(_ym_collect_sync, query_str, limit)
            _ym_cache_set(query_str, items)
            return items[:limit]
        except Exception as e:
            logger.error("Yandex Market collect failed: %s", e, exc_info=True)
            return []


def _ozon_get_reusable_driver() -> webdriver.Chrome:
    global _ozon_driver
    if not OZON_DRIVER_REUSE:
        return _new_chrome_driver("ozon-profile")
    with _ozon_driver_lock:
        if _ozon_driver is None:
            _ozon_driver = _new_chrome_driver("ozon-profile")
        return _ozon_driver


def _ozon_release_driver(driver: webdriver.Chrome, *, ok: bool):
    global _ozon_driver
    if not OZON_DRIVER_REUSE:
        _quit_chrome_driver(driver)
        return
    if ok:
        return
    with _ozon_driver_lock:
        if _ozon_driver is driver:
            _ozon_driver = None
    _quit_chrome_driver(driver)


def _ozon_warmup_sync():
    driver = _ozon_get_reusable_driver()
    ok = False
    try:
        driver.get("https://www.ozon.ru/")
        time.sleep(0.2)
        ok = True
    except Exception:
        ok = False
    finally:
        _ozon_release_driver(driver, ok=ok)


def _ozon_fast_extract_items(driver: webdriver.Chrome, limit: int) -> List[dict]:
    js = """
    function bestFromSrcset(srcset) {
      if (!srcset) return '';
      const parts = ('' + srcset).split(',').map(s => (s || '').trim()).filter(Boolean);
      let bestUrl = '';
      let bestScore = -1;
      let lastUrl = '';
      for (const p of parts) {
        const chunks = p.split(/\\s+/).filter(Boolean);
        if (!chunks.length) continue;
        const url = (chunks[0] || '').trim();
        if (!url) continue;
        lastUrl = url;
        let score = 0;
        if (chunks.length >= 2) {
          const d = (chunks[1] || '').trim().toLowerCase();
          const mW = d.match(/^(\\d+)w$/);
          const mX = d.match(/^(\\d+(?:\\.\\d+)?)x$/);
          if (mW) score = parseInt(mW[1], 10);
          else if (mX) score = Math.round(parseFloat(mX[1]) * 1000);
        }
        if (score >= bestScore) {
          bestScore = score;
          bestUrl = url;
        }
      }
      return bestUrl || lastUrl || '';
    }

	    function looksPlaceholder(url, alt) {
	      const u = (url || '').toLowerCase();
	      const a = (alt || '').toLowerCase();
	      if (!u) return true;
	      if (u.startsWith('data:')) return true;
	      if (a.includes('фотосесс')) return true;
	      return (
	        u.includes('na_fotosess') ||
	        u.includes('fotosess') ||
	        u.includes('photoshoot') ||
	        u.includes('no_photo') ||
        u.includes('no-photo')
      );
    }

    function normalizeUrl(url) {
      let u = (url || '').trim();
      if (!u) return '';
      if (u.startsWith('//')) u = 'https:' + u;
      return u;
    }

    const selector = arguments[0];
    const lim = arguments[1];
    const tiles = Array.from(document.querySelectorAll(selector));
    const out = [];
    for (const t of tiles) {
      if (out.length >= lim) break;
      const a = t.querySelector('a[class*="tile-clickable-element"]') || t.querySelector('a[href^="/product"]');
      const href = a ? (a.getAttribute('href') || '') : '';
      if (!href) continue;

      const priceEl = t.querySelector('span[class*="tsHeadline500Medium"]');
      const priceText = priceEl ? (priceEl.textContent || '') : '';

      const nameEl = t.querySelector('span[class*="tsBody500Medium"]');
      const nameText = nameEl ? (nameEl.textContent || '') : (a ? (a.textContent || '') : '');

      const img = t.querySelector('img');
      const candidates = [];
      const seen = new Set();
      function add(v) {
        const u = normalizeUrl(v);
        if (!u || seen.has(u)) return;
        seen.add(u);
        candidates.push(u);
      }
      if (img) {
        add(img.currentSrc);
        add(img.src);
        add(img.getAttribute('src'));
        add(img.getAttribute('data-src'));
        add(img.getAttribute('data-original'));
        add(bestFromSrcset(img.getAttribute('srcset')));
        add(bestFromSrcset(img.getAttribute('data-srcset')));
      }
      const sources = t.querySelectorAll(
        'picture source[srcset], source[srcset], picture source[data-srcset], source[data-srcset]'
      );
      for (const s of sources) {
        add(bestFromSrcset(s.getAttribute('srcset')));
        add(bestFromSrcset(s.getAttribute('data-srcset')));
      }
      let imgUrl = '';
      const alt = img ? (img.getAttribute('alt') || '') : '';
      for (const c of candidates) {
        if (!looksPlaceholder(c, alt)) { imgUrl = c; break; }
      }

      let rating = '';
      let reviews = '';
      const ratingEl = t.querySelector('span[style*="textPremium"]');
      if (ratingEl) rating = (ratingEl.textContent || '').trim();
      const reviewEls = t.querySelectorAll('span[style*="textSecondary"]');
      for (const el of reviewEls) {
        const txt = (el.textContent || '').trim();
        const digits = txt.replace(/[^0-9]/g, '');
        if (digits) { reviews = digits; break; }
      }

      out.push({ href, priceText, nameText, imgUrl, imgUrls: candidates, rating, reviews });
    }
    return out;
    """
    try:
        raw = driver.execute_script(js, OZON_TILE_SELECTOR, int(limit)) or []
    except Exception:
        return []

    out: List[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        href = (r.get("href") or "").strip()
        if not href:
            continue
        url = ("https://www.ozon.ru" + href.split("?")[0]) if href.startswith("/") else href.split("?")[0]
        price = digits_only(r.get("priceText") or "")
        if not price:
            continue
        name = _clean_spaces(r.get("nameText") or "")
        img_url = (r.get("imgUrl") or "").strip()
        img_urls_raw = r.get("imgUrls")
        image_urls: List[str] = []
        if isinstance(img_urls_raw, list):
            for v in img_urls_raw:
                if isinstance(v, str):
                    u = v.strip()
                    if u and u not in image_urls:
                        image_urls.append(u)
        filtered_urls = [u for u in image_urls if not _looks_like_ozon_placeholder_url(u)]
        if filtered_urls:
            image_urls = filtered_urls
            if not img_url or _looks_like_ozon_placeholder_url(img_url):
                img_url = filtered_urls[0]
        elif not img_url and image_urls:
            img_url = image_urls[0]
        rating = _clean_spaces(r.get("rating") or "").replace(",", ".")
        if rating and not re.fullmatch(r"[1-5](?:\.\d)?", rating):
            rating = ""
        reviews = digits_only(r.get("reviews") or "")

        out.append(
            {
                "marketplace": "ozon",
                "name": name or "",
                "url": url,
                "price": price,
                "rating": rating,
                "reviews": reviews,
                "img_url": img_url,
                "image_urls": image_urls or None,
            }
        )
    return out


def _looks_like_ozon_placeholder_url(url: str, alt: str = "") -> bool:
    u = (url or "").strip().lower()
    a = (alt or "").strip().lower()
    if not u:
        return True
    if u.startswith("data:"):
        return True
    if "фотосесс" in a:
        return True
    return (
        "na_fotosess" in u
        or "fotosess" in u
        or "photoshoot" in u
        or "no_photo" in u
        or "no-photo" in u
    )


def _normalize_ozon_image_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return u


def _extract_ozon_image_candidates(card) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def add(v: Optional[str]):
        if not isinstance(v, str):
            return
        u = _normalize_ozon_image_url(v)
        if not u or u in seen:
            return
        seen.add(u)
        candidates.append(u)

    img = card.select_one("img")
    alt = (img.get("alt") or "") if img else ""
    if img:
        add(img.get("src"))
        add(img.get("data-src"))
        add(img.get("data-original"))
        add(_first_src_from_srcset(img.get("srcset") or ""))
        add(_first_src_from_srcset(img.get("data-srcset") or ""))

    for s in card.select("picture source[srcset], source[srcset], picture source[data-srcset], source[data-srcset]"):
        add(_first_src_from_srcset(s.get("srcset") or ""))
        add(_first_src_from_srcset(s.get("data-srcset") or ""))

    filtered = [u for u in candidates if not _looks_like_ozon_placeholder_url(u, alt=alt)]
    return filtered or candidates


def _extract_ozon_img(card) -> str:
    candidates = _extract_ozon_image_candidates(card)
    return candidates[0] if candidates else ""


def _extract_ozon_rating_reviews(card) -> Tuple[str, str]:
    rating = ""
    reviews = ""

    rating_el = card.select_one("span[style*='textPremium']")
    if rating_el:
        rating = _clean_spaces(rating_el.get_text(" ", strip=True)).replace(",", ".")
        if not re.fullmatch(r"[1-5](?:\.\d)?", rating):
            rating = ""

    for el in card.select("span[style*='textSecondary']"):
        d = digits_only(_clean_spaces(el.get_text(" ", strip=True)))
        if not d:
            continue
        try:
            v = int(d)
        except Exception:
            continue
        if 0 <= v <= 500000:
            reviews = str(v)
            break

    return rating, reviews


def _parse_ozon_tile_html(tile_html: str) -> Optional[dict]:
    soup = BeautifulSoup(tile_html, "html.parser")
    card = soup.find("div", class_=re.compile(r"tile-root"))
    if not card:
        return None

    lnk = card.find("a", class_=re.compile(r"tile-clickable-element")) or card.find("a", href=re.compile(r"^/product"))
    href = (lnk.get("href") or "").strip() if lnk else ""
    if not href:
        return None

    url = ("https://www.ozon.ru" + href.split("?")[0]) if not href.startswith("http") else href.split("?")[0]

    price_tag = card.find("span", class_=re.compile(r"tsHeadline500Medium"))
    price = digits_only(price_tag.get_text(" ", strip=True)) if price_tag else ""
    if not price:
        return None

    name = ""
    name_tag = card.find("span", class_=re.compile(r"tsBody500Medium"))
    if name_tag:
        name = _clean_spaces(name_tag.get_text(" ", strip=True))
    if not name and lnk:
        name = _clean_spaces(lnk.get_text(" ", strip=True))

    image_urls = _extract_ozon_image_candidates(card)
    img_url = image_urls[0] if image_urls else ""
    rating, reviews = _extract_ozon_rating_reviews(card)

    return {
        "marketplace": "ozon",
        "name": name or "",
        "url": url,
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "img_url": img_url,
        "image_urls": image_urls or None,
    }


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


def _ozon_sync_collect(driver: webdriver.Chrome, query: str, limit: int, deadline_ts: float) -> List[dict]:
    seen: Set[str] = set()
    results: List[dict] = []

    if time.time() >= deadline_ts:
        return []

    url = f"https://www.ozon.ru/search/?text={quote_plus(query)}&from_global=true"
    driver.get(url)
    time.sleep(0.15 + random.uniform(0.05, 0.15))

    if time.time() >= deadline_ts:
        return []

    html0 = driver.page_source or ""
    if _looks_like_ozon_block(html0, driver.title or ""):
        _dump_html("ozon-block", html0)
        return []

    wait_first = min(float(OZON_WAIT_FIRST), max(0.1, float(deadline_ts - time.time())))
    try:
        WebDriverWait(driver, wait_first).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, OZON_TILE_SELECTOR)) >= 1
        )
    except TimeoutException:
        html = driver.page_source or ""
        if _looks_like_ozon_block(html, driver.title or ""):
            _dump_html("ozon-block", html)
        return results[:limit]

    if OZON_FAST_JS_EXTRACT:
        extracted = _ozon_fast_extract_items(driver, limit=limit)
        for item in extracted:
            try:
                if valid_product_item(item, seen):
                    seen.add(item["url"])
                    results.append(item)
            except Exception:
                continue
        if len(results) >= limit:
            return results[:limit]

    stagnation = 0
    processed = 0

    for _ in range(OZON_SCROLL_ROUNDS):
        if time.time() >= deadline_ts:
            break
        tiles = driver.find_elements(By.CSS_SELECTOR, OZON_TILE_SELECTOR)
        if not tiles:
            break

        new_tiles = tiles[processed:]
        if new_tiles:
            for el in new_tiles:
                try:
                    tile_html = el.get_attribute("outerHTML") or ""
                    item = _parse_ozon_tile_html(tile_html)
                    if not item:
                        continue
                    if valid_product_item(item, seen):
                        seen.add(item["url"])
                        results.append(item)
                        if len(results) >= limit:
                            return results[:limit]
                except Exception:
                    continue
            processed = len(tiles)
            stagnation = 0
        else:
            stagnation += 1
            if stagnation >= OZON_STAGNATION_LIMIT:
                break

        prev_tiles = len(tiles)
        driver.execute_script("window.scrollBy(0, arguments[0])", OZON_SCROLL_STEP)

        remaining = float(deadline_ts - time.time())
        if remaining <= 0:
            break

        grew = _wait_tiles_increase(driver, prev_tiles, timeout=min(float(OZON_WAIT_NEW_TILES), remaining))
        if not grew:
            if _ozon_try_click_load_more(driver):
                remaining = float(deadline_ts - time.time())
                if remaining <= 0:
                    break
                _wait_tiles_increase(driver, prev_tiles, timeout=min(float(OZON_WAIT_NEW_TILES), remaining))

        time.sleep(min(float(OZON_SCROLL_PAUSE + random.uniform(0.03, 0.10)), max(0.0, deadline_ts - time.time())))

    return results[:limit]


async def collect_ozon(query: str, limit: int) -> List[dict]:
    cached = _ozon_cache_get(query)
    if cached is not None and len(cached) >= limit:
        return cached[:limit]

    def _ozon_collect_sync(q: str, lim: int) -> List[dict]:
        deadline_ts = time.time() + max(0.5, float(OZON_TOTAL_BUDGET))
        need_min = min(lim, OZON_MIN_ITEMS)
        last_items: List[dict] = []

        for attempt in range(OZON_RETRIES):
            if time.time() >= deadline_ts:
                break
            driver = _ozon_get_reusable_driver()
            ok = False
            try:
                items = _ozon_sync_collect(driver, q, lim, deadline_ts=deadline_ts)
                last_items = items
                ok = True
                if len(items) >= need_min:
                    return items
            except Exception as e:
                logger.error("Ozon collect failed: %s", e, exc_info=True)
            finally:
                _ozon_release_driver(driver, ok=ok)

            if attempt < OZON_RETRIES - 1:
                time.sleep(min(0.6 + random.uniform(0.1, 0.3), max(0.0, deadline_ts - time.time())))

        return last_items[:lim]

    async with _ozon_sem:
        try:
            items = await asyncio.to_thread(_ozon_collect_sync, query, limit)
            _ozon_cache_set(query, items)
            return items
        except Exception as e:
            logger.error("Ozon collect failed: %s", e, exc_info=True)
            return []


@app.on_event("startup")
async def startup_event():
    global _virtual_display
    if USE_XVFB and not CHROME_HEADLESS and os.name != "nt" and not os.environ.get("DISPLAY") and HAS_XVFB:
        _virtual_display = Display(visible=0, size=(1920, 1080))
        _virtual_display.start()
        logger.info("Xvfb started. DISPLAY=%s", os.environ.get("DISPLAY"))
    if ENABLE_OZON and OZON_DRIVER_REUSE and OZON_WARMUP:
        try:
            await asyncio.to_thread(_ozon_warmup_sync)
            logger.info("Ozon warmup completed")
        except Exception as e:
            logger.warning("Ozon warmup failed: %s", e)


@app.on_event("shutdown")
async def shutdown_event():
    global _virtual_display
    global _ozon_driver
    if _ozon_driver is not None:
        try:
            _quit_chrome_driver(_ozon_driver)
        except Exception:
            pass
        _ozon_driver = None
    if _virtual_display:
        try:
            _virtual_display.stop()
        except Exception:
            pass
        _virtual_display = None
        logger.info("Xvfb stopped")


@app.get("/api/products", response_model=UnifiedProductsResponse)
async def get_products(
    request: Request,
    q: str = Query(..., description="Search query"),
    limit: Optional[int] = Query(None, ge=1, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(status_code=400, detail="Invalid q")

    q = re.sub(r"\s+", " ", q).strip()
    page_limit = int(limit) if limit is not None else int(DEFAULT_PAGE_ITEMS)
    page_limit = max(1, min(int(page_limit), int(MAX_ITEMS)))
    page_offset = max(0, int(offset))
    if page_offset >= int(MAX_ITEMS):
        return UnifiedProductsResponse(
            query=q,
            count=0,
            items=[],
            offset=page_offset,
            limit=page_limit,
            total=0,
            has_more=False,
        )

    target = min(int(MAX_ITEMS), page_offset + page_limit)
    cache_key = f"products:{q.casefold()}"
    cached = get_from_cache(cache_key)
    cached_items = None
    if cached and isinstance(cached, dict):
        cached_items = cached.get("items")
        if isinstance(cached_items, list) and len(cached_items) >= target:
            slice_items = cached_items[page_offset : page_offset + page_limit]
            items_models: List[ProductItem] = []
            for item in slice_items:
                try:
                    items_models.append(ProductItem(**item))
                except Exception:
                    continue
            total = len(cached_items)
            returned_count = len(items_models)
            has_more = returned_count > 0 and (page_offset + returned_count) < int(MAX_ITEMS)
            return UnifiedProductsResponse(
                query=q,
                count=len(items_models),
                items=items_models,
                offset=page_offset,
                limit=page_limit,
                total=total,
                has_more=has_more,
            )

    task_coros = []
    enabled_markets = 0
    if ENABLE_WB:
        enabled_markets += 1
    if ENABLE_YM:
        enabled_markets += 1
    if ENABLE_OZON:
        enabled_markets += 1

    if ENABLE_WB:
        wb_limit = _calc_market_limit(target, WB_ITEMS, enabled_markets)
        task_coros.append(collect_wb(q, wb_limit))
    if ENABLE_YM:
        ym_limit = _calc_market_limit(target, YM_ITEMS, enabled_markets)
        task_coros.append(collect_ym(q, ym_limit))
    if ENABLE_OZON:
        ozon_limit = _calc_market_limit(target, OZON_ITEMS, enabled_markets)
        task_coros.append(collect_ozon(q, ozon_limit))

    if not task_coros:
        raise HTTPException(status_code=500, detail="No marketplaces enabled")

    start_time = datetime.now()
    parts: List[object] = await asyncio.gather(*task_coros, return_exceptions=True)

    item_lists: List[List[ProductItem]] = []
    for part in parts:
        if isinstance(part, Exception):
            logger.error("Task failed: %s", part, exc_info=True)
            continue
        items: List[ProductItem] = []
        for item in part:
            try:
                items.append(ProductItem(**item))
            except Exception:
                continue
        if items:
            item_lists.append(items)

    final_items: List[ProductItem] = []
    idx = 0
    while len(final_items) < target and any(idx < len(items) for items in item_lists):
        for items in item_lists:
            if idx < len(items):
                final_items.append(items[idx])
                if len(final_items) >= target:
                    break
        idx += 1
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("Query=%s items=%s time=%.2fs", q, len(final_items), elapsed)

    new_items_data = [it.model_dump() for it in final_items]
    merged_items = _merge_items(cached_items or [], new_items_data, max_items=target)

    payload = {
        "query": q,
        "count": len(merged_items),
        "items": merged_items,
    }
    set_to_cache(cache_key, payload)

    slice_items = merged_items[page_offset : page_offset + page_limit]
    items_models: List[ProductItem] = []
    for item in slice_items:
        try:
            items_models.append(ProductItem(**item))
        except Exception:
            continue
    total = len(merged_items)
    returned_count = len(slice_items)
    has_more = returned_count > 0 and (page_offset + returned_count) < int(MAX_ITEMS)
    return UnifiedProductsResponse(
        query=q,
        count=len(items_models),
        items=items_models,
        offset=page_offset,
        limit=page_limit,
        total=total,
        has_more=has_more,
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": "10.0.0"}


@app.get("/api/wb-image/{nm_id}")
def wb_image(nm_id: int, size: str = Query("c246x328"), b: Optional[int] = Query(None)):
    size_clean = (size or "").strip() or "c246x328"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", size_clean):
        raise HTTPException(status_code=400, detail="Invalid size")

    cache_key = f"{int(nm_id)}:{size_clean}"
    cached = _wb_img_cache_get(cache_key)
    if cached:
        return RedirectResponse(url=cached, status_code=302)

    hosts = _wb_image_hosts()
    host = hosts[0]

    basket_hint = None
    try:
        basket_hint = int(b) if b is not None else None
    except Exception:
        basket_hint = None

    cache_ok = False
    if WB_IMAGE_PROXY_PROBE:
        url = _wb_probe_image_url(int(nm_id), size_clean, basket_hint=basket_hint)
        cache_ok = True
    elif basket_hint and 1 <= basket_hint <= 99:
        ext = _wb_image_exts()[0]
        url = _wb_img_url_from_nmid(int(nm_id), int(basket_hint), ext, host, size_clean)
        cache_ok = True
    else:
        ext = _wb_image_exts()[0]
        basket = _wb_basket_from_nmid(int(nm_id))
        url = _wb_img_url_from_nmid(int(nm_id), int(basket), ext, host, size_clean)
    if not url:
        raise HTTPException(status_code=404, detail="Image not found")

    if cache_ok:
        _wb_img_cache_set(cache_key, url)
    return RedirectResponse(url=url, status_code=302)


@app.get("/cache-stats")
def cache_stats():
    return {
        "cache_enabled": ENABLE_CACHE,
        "cache_size": len(_cache),
        "cache_ttl": CACHE_TTL,
        "enable_wb": ENABLE_WB,
        "enable_ozon": ENABLE_OZON,
        "enable_ym": ENABLE_YM,
        "wb_items": WB_ITEMS,
        "ym_items": YM_ITEMS,
        "ozon_items": OZON_ITEMS,
        "search_total_timeout": SEARCH_TOTAL_TIMEOUT,
        "wb_task_timeout": WB_TASK_TIMEOUT,
        "ozon_task_timeout": OZON_TASK_TIMEOUT,
        "ym_task_timeout": YM_TASK_TIMEOUT,
        "wb_api_timeout": WB_API_TIMEOUT,
        "ym_api_timeout": YM_API_TIMEOUT,
        "wb_total_budget": WB_TOTAL_BUDGET,
        "ym_total_budget": YM_TOTAL_BUDGET,
        "chrome_headless": CHROME_HEADLESS,
        "use_xvfb": USE_XVFB,
        "has_xvfb": HAS_XVFB,
        "has_stealth": HAS_STEALTH,
        "wb_concurrent_limit": WB_CONCURRENT_LIMIT,
        "ym_concurrent_limit": YM_CONCURRENT_LIMIT,
        "ozon_browser_limit": OZON_BROWSER_LIMIT,
        "ozon_min_items": OZON_MIN_ITEMS,
        "ozon_total_budget": OZON_TOTAL_BUDGET,
        "ozon_wait_first": OZON_WAIT_FIRST,
        "ozon_wait_new_tiles": OZON_WAIT_NEW_TILES,
        "ozon_stagnation_limit": OZON_STAGNATION_LIMIT,
        "ozon_page_load_strategy": OZON_PAGE_LOAD_STRATEGY,
        "ozon_driver_reuse": OZON_DRIVER_REUSE,
        "ozon_fast_js_extract": OZON_FAST_JS_EXTRACT,
        "wb_global_cooldown": WB_GLOBAL_COOLDOWN,
        "wb_cache_size": len(_wb_cache),
        "wb_cache_ttl": WB_CACHE_TTL,
        "wb_cache_stale_ttl": WB_CACHE_STALE_TTL,
        "wb_429_cooldown": WB_429_COOLDOWN,
        "wb_block_max_wait": WB_BLOCK_MAX_WAIT,
        "wb_block_remaining": round(_wb_block_remaining(), 2),
        "wb_image_ext": WB_IMAGE_EXT,
        "wb_use_image_proxy": WB_USE_IMAGE_PROXY,
        "wb_image_proxy_timeout": WB_IMAGE_PROXY_TIMEOUT,
        "wb_image_proxy_ttl": WB_IMAGE_PROXY_TTL,
        "wb_image_proxy_probe": WB_IMAGE_PROXY_PROBE,
        "wb_image_probe_max_baskets": WB_IMAGE_PROBE_MAX_BASKETS,
        "wb_image_proxy_cache_size": len(_wb_img_cache),
        "ozon_cache_ttl": OZON_CACHE_TTL,
        "ozon_cache_size": len(_ozon_cache),
        "ym_max_pages": YM_MAX_PAGES,
        "ym_cache_ttl": YM_CACHE_TTL,
        "ym_cache_size": len(_ym_cache),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8002")))
