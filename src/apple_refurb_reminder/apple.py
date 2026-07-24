from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .models import Listing, ListingSummary

BASE_URL = "https://www.apple.com"
CATALOG_URL = f"{BASE_URL}/jp/shop/refurbished/mac/macbook-pro"
BOOTSTRAP_RE = re.compile(r"window\.REFURB_GRID_BOOTSTRAP\s*=\s*(\{.*?\});", re.DOTALL)
PRODUCT_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
DESCRIPTION_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
    re.DOTALL | re.IGNORECASE,
)


class ObservationError(RuntimeError):
    pass


def canonical_url(url: str) -> str:
    absolute = urljoin(BASE_URL, unescape(url))
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_catalog(html: str) -> list[ListingSummary]:
    match = BOOTSTRAP_RE.search(html)
    if not match:
        raise ObservationError("REFURB_GRID_BOOTSTRAP が見つかりません")
    try:
        payload = json.loads(match.group(1))
        tiles = payload["tiles"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ObservationError("カタログデータの構造が不正です") from exc
    if not isinstance(tiles, list):
        raise ObservationError("カタログ商品一覧が配列ではありません")
    listings: list[ListingSummary] = []
    for tile in tiles:
        try:
            part_number = str(tile["partNumber"]).upper()
            title = str(tile["title"]).strip()
            price = int(float(tile["price"]["currentPrice"]["raw_amount"]))
            url = canonical_url(str(tile["productDetailsUrl"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ObservationError("カタログ商品に必須項目がありません") from exc
        listings.append(ListingSummary(part_number, title, price, url))
    return listings


def _product_json_ld(html: str) -> dict[str, object]:
    for raw in PRODUCT_LD_RE.findall(html):
        try:
            value = json.loads(unescape(raw))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("@type") == "Product":
            return value
    raise ObservationError("商品 JSON-LD が見つかりません")


def _number(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _storage(text: str) -> str | None:
    match = re.search(r"(\d+)\s*(TB|GB)\s*SSD", text, re.IGNORECASE)
    return f"{match.group(1)}{match.group(2).upper()}" if match else None


def parse_detail(html: str, summary: ListingSummary) -> Listing:
    product = _product_json_ld(html)
    title = str(product.get("name") or summary.title)
    description_match = DESCRIPTION_RE.search(html)
    description = unescape(description_match.group(1)) if description_match else ""
    combined = f"{title} {description}".replace("\xa0", " ")
    chip_match = re.search(r"Apple\s+(M\d(?:\s+(?:Pro|Max|Ultra))?)\s*チップ", combined)
    color = str(product.get("color")) if product.get("color") else None
    return Listing(
        id=summary.id,
        title=title,
        price_jpy=summary.price_jpy,
        url=canonical_url(str(product.get("url") or summary.url)),
        product="MacBook Pro" if re.search(r"MacBook\s*Pro", title, re.IGNORECASE) else None,
        display_size_inches=_number(r"(\d+)\s*インチ", combined),
        chip=re.sub(r"\s+", " ", chip_match.group(1)).strip() if chip_match else None,
        cpu_cores=_number(r"(\d+)\s*コアCPU", combined),
        gpu_cores=_number(r"(\d+)\s*コアGPU", combined),
        memory_gb=_number(r"(\d+)\s*GB\s*ユニファイドメモリ", combined),
        storage=_storage(combined),
        color=color,
        keyboard="Magic Keyboard" if "Magic Keyboard" in combined else None,
    )


class AppleJapanAdapter:
    def __init__(
        self,
        *,
        timeout: float = 20,
        detail_concurrency: int = 3,
        fetcher: Callable[[str], str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.detail_concurrency = detail_concurrency
        self._fetcher = fetcher or self._fetch

    def _fetch(self, url: str) -> str:
        retryable = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = Request(
                    url,
                    headers={
                        "User-Agent": "AppleRefurbReminder/0.1 (+personal inventory monitor)",
                        "Accept-Language": "ja-JP,ja;q=0.9",
                    },
                )
                with urlopen(request, timeout=self.timeout) as response:
                    content_type = response.headers.get_content_type()
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        raise ObservationError(f"想定外の Content-Type: {content_type}")
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                last_error = exc
                if exc.code not in retryable:
                    break
            except (URLError, TimeoutError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep((2**attempt) + random.random())
        raise ObservationError(f"Apple リクエストに失敗しました: {last_error}")

    def observe(self) -> tuple[list[ListingSummary], list[Listing], dict[str, str]]:
        summaries = parse_catalog(self._fetcher(CATALOG_URL))
        candidates = [item for item in summaries if "MacBook Pro" in item.title]
        listings: list[Listing] = []
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=self.detail_concurrency) as executor:
            futures = {
                executor.submit(self._fetcher, summary.url): summary for summary in candidates
            }
            for future in as_completed(futures):
                summary = futures[future]
                try:
                    listings.append(parse_detail(future.result(), summary))
                except Exception as exc:  # one detail must not invalidate the catalog
                    errors[summary.id] = str(exc)
        listings.sort(key=lambda value: value.id)
        return summaries, listings, errors


def with_latest_summary(listing: Listing, summary: ListingSummary) -> Listing:
    return replace(listing, title=summary.title, price_jpy=summary.price_jpy, url=summary.url)
