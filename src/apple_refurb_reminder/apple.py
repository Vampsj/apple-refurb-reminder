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

from .matcher import could_match, needs_detail
from .models import Listing, ListingSummary, ProductCategory, Region, WatchRule
from .storefronts import Storefront, storefront

BASE_URL = "https://www.apple.com"
BOOTSTRAP_RE = re.compile(r"window\.REFURB_GRID_BOOTSTRAP\s*=\s*(\{.*?\});", re.DOTALL)
PRODUCT_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
DESCRIPTION_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
    re.DOTALL | re.IGNORECASE,
)
PARSER_VERSION = 1


class ObservationError(RuntimeError):
    pass


def canonical_url(url: str, base_url: str = BASE_URL) -> str:
    absolute = urljoin(base_url, unescape(url))
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_catalog(
    html: str,
    *,
    category: ProductCategory = ProductCategory.MAC,
    base_url: str = BASE_URL,
    currency: str = "JPY",
) -> list[ListingSummary]:
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
    if len(tiles) > 1000:
        raise ObservationError("Catalog item count is unexpectedly high")
    listings: list[ListingSummary] = []
    seen_ids: set[str] = set()
    for tile in tiles:
        try:
            part_number = str(tile["partNumber"]).upper()
            title = str(tile["title"]).strip()
            price = int(float(tile["price"]["currentPrice"]["raw_amount"]))
            url = canonical_url(str(tile["productDetailsUrl"]), base_url)
            dimensions = tile.get("filters", {}).get("dimensions", {})
            if not isinstance(dimensions, dict):
                dimensions = {}
        except (KeyError, TypeError, ValueError) as exc:
            raise ObservationError("カタログ商品に必須項目がありません") from exc
        if part_number in seen_ids:
            raise ObservationError(f"Duplicate Apple product ID: {part_number}")
        seen_ids.add(part_number)
        listings.append(
            ListingSummary(
                part_number,
                title,
                price,
                url,
                category,
                currency,
                {str(key): str(value) for key, value in dimensions.items()},
            )
        )
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


def _dimension_number(value: str | None) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else None


def _model_from_title(title: str, category: ProductCategory) -> str | None:
    patterns = {
        ProductCategory.MAC: (
            r"(MacBook\s+Pro|MacBook\s+Air|MacBook\s+Neo|"
            r"Mac\s+mini|Mac\s+Studio|Mac\s+Pro|iMac)"
        ),
        ProductCategory.IPHONE: r"(iPhone\s+\d+(?:\s+(?:Pro\s+Max|Pro|Plus|mini))?)",
        ProductCategory.IPAD: (
            r"(iPad\s+(?:Pro|Air|mini)\s+\d+(?:\.\d+)?"
            r"(?:-inch|\s*英寸|\s*吋|\s*インチ)|iPad\s+(?:Pro|Air|mini)|iPad)"
        ),
    }
    match = re.search(patterns[category], title, re.IGNORECASE)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def listing_from_summary(summary: ListingSummary) -> Listing:
    dimensions = summary.dimensions
    combined = summary.title.replace("\xa0", " ")
    chip_match = re.search(
        r"Apple\s+(M\d(?:\s+(?:Pro|Max|Ultra))?)\s*(?:chip|チップ|芯片|晶片)?",
        combined,
        re.IGNORECASE,
    )
    return Listing(
        id=summary.id,
        title=summary.title,
        price_amount=summary.price_amount,
        url=summary.url,
        product=_model_from_title(summary.title, summary.category),
        display_size_inches=_dimension_number(dimensions.get("dimensionScreensize"))
        or _number(r"(\d+)(?:-inch|\s*英寸|\s*吋|\s*インチ)", combined),
        chip=re.sub(r"\s+", " ", chip_match.group(1)).strip() if chip_match else None,
        cpu_cores=_number(r"(\d+)[-\s]*(?:Core\s+CPU|核中央处理器|核心\s*CPU|コアCPU)", combined),
        gpu_cores=_number(r"(\d+)[-\s]*(?:Core\s+GPU|核图形处理器|核心\s*GPU|コアGPU)", combined),
        memory_gb=_dimension_number(dimensions.get("tsMemorySize")),
        storage=(
            dimensions.get("dimensionCapacity", "").upper().replace("_", "")
            or _storage(combined)
        ),
        color=dimensions.get("dimensionColor"),
        connectivity=dimensions.get("dimensionconnectivity"),
        category=summary.category,
        currency=summary.currency,
    )


def parse_regional_detail(html: str, summary: ListingSummary) -> Listing:
    catalog = listing_from_summary(summary)
    product = _product_json_ld(html)
    title = str(product.get("name") or summary.title)
    description_match = DESCRIPTION_RE.search(html)
    description = unescape(description_match.group(1)) if description_match else ""
    combined = f"{title} {description}".replace("\xa0", " ")
    summary_parts = urlsplit(summary.url)
    summary_base = f"{summary_parts.scheme}://{summary_parts.netloc}"
    chip_match = re.search(
        r"Apple\s+(M\d(?:\s+(?:Pro|Max|Ultra))?)\s*(?:chip|チップ|芯片|晶片)?",
        combined,
        re.IGNORECASE,
    )

    def localized_number(*patterns: str) -> int | None:
        return next(
            (value for pattern in patterns if (value := _number(pattern, combined)) is not None),
            None,
        )

    return replace(
        catalog,
        title=title,
        url=canonical_url(str(product.get("url") or summary.url), summary_base),
        product=catalog.product or _model_from_title(title, summary.category),
        display_size_inches=catalog.display_size_inches
        or localized_number(
            r"(\d+)(?:-inch|\s*英寸|\s*吋|\s*インチ)",
        ),
        chip=catalog.chip
        or (re.sub(r"\s+", " ", chip_match.group(1)).strip() if chip_match else None),
        cpu_cores=catalog.cpu_cores
        or localized_number(
            r"(\d+)[-\s]*Core\s+CPU",
            r"(\d+)\s*核中央处理器",
            r"(\d+)\s*核心\s*CPU",
            r"(\d+)\s*コアCPU",
        ),
        gpu_cores=catalog.gpu_cores
        or localized_number(
            r"(\d+)[-\s]*Core\s+GPU",
            r"(\d+)\s*核图形处理器",
            r"(\d+)\s*核心\s*GPU",
            r"(\d+)\s*コアGPU",
        ),
        memory_gb=catalog.memory_gb
        or localized_number(
            r"(\d+)\s*GB\s*unified memory",
            r"(\d+)\s*GB\s*统一内存",
            r"(\d+)\s*GB\s*統一記憶體",
            r"(\d+)\s*GB\s*ユニファイドメモリ",
        ),
        storage=catalog.storage or _storage(combined),
        color=catalog.color or (str(product.get("color")) if product.get("color") else None),
    )


class AppleRegionalAdapter:
    def __init__(
        self,
        region: Region | str,
        rules: tuple[WatchRule, ...],
        *,
        timeout: float = 20,
        detail_concurrency: int = 3,
        fetcher: Callable[[str], str] | None = None,
    ) -> None:
        self.store: Storefront = storefront(region)
        self.rules = rules
        self.timeout = timeout
        self.detail_concurrency = min(detail_concurrency, 3)
        self._fetcher = fetcher or self._fetch

    def _fetch(self, url: str) -> str:
        return _fetch_html(url, self.store.locale, self.timeout)

    def observe(
        self,
        *,
        cache: dict[str, dict[str, object]] | None = None,
        previous_catalog_ids: set[str] | None = None,
    ) -> tuple[list[ListingSummary], list[Listing], dict[str, str]]:
        cache = cache if cache is not None else {}
        previous_catalog_ids = previous_catalog_ids or set()
        categories = {rule.category for rule in self.rules}
        summaries: list[ListingSummary] = []
        errors: dict[str, str] = {}
        for category in sorted(categories, key=lambda value: value.value):
            try:
                html = self._fetcher(self.store.catalog_url(category))
                summaries.extend(
                    parse_catalog(
                        html,
                        category=category,
                        base_url=self.store.base_url,
                        currency=self.store.currency,
                    )
                )
            except Exception as exc:
                errors[f"category:{category.value}"] = str(exc)
        pairs = [
            (summary, listing_from_summary(summary))
            for summary in summaries
        ]
        summaries = [summary for summary, listing in pairs if listing.product is not None]
        listings = [listing for _summary, listing in pairs if listing.product is not None]
        summary_by_id = {summary.id: summary for summary in summaries}
        listing_by_id = {listing.id: listing for listing in listings}
        detail_ids = {
            listing.id
            for listing in listings
            if any(needs_detail(rule, listing) for rule in self.rules)
        }
        fetch_ids: set[str] = set()
        for listing_id in detail_ids:
            record = cache.get(listing_id)
            reappeared = listing_id not in previous_catalog_ids
            if (
                record
                and record.get("parser_version") == PARSER_VERSION
                and not reappeared
                and isinstance(record.get("listing"), dict)
            ):
                cached = Listing.from_dict(record["listing"])
                listing_by_id[listing_id] = with_latest_summary(
                    cached, summary_by_id[listing_id]
                )
            else:
                fetch_ids.add(listing_id)
        with ThreadPoolExecutor(max_workers=self.detail_concurrency) as executor:
            futures = {
                executor.submit(self._fetcher, summary_by_id[listing_id].url): listing_id
                for listing_id in fetch_ids
            }
            for future in as_completed(futures):
                listing_id = futures[future]
                try:
                    parsed = parse_regional_detail(
                        future.result(), summary_by_id[listing_id]
                    )
                    listing_by_id[listing_id] = parsed
                    cache[listing_id] = {
                        "parser_version": PARSER_VERSION,
                        "listing": parsed.to_dict(),
                    }
                except Exception as exc:
                    errors[listing_id] = str(exc)
                    del listing_by_id[listing_id]
        listings = [
            listing
            for listing in listing_by_id.values()
            if any(could_match(rule, listing) for rule in self.rules)
        ]
        listings.sort(key=lambda value: (value.category.value, value.id))
        return summaries, listings, errors


def _fetch_html(url: str, locale: str, timeout: float) -> str:
    retryable = {429, 500, 502, 503, 504}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "AppleRefurbReminder/1.0 (+open-source inventory monitor)",
                    "Accept-Language": f"{locale},*;q=0.5",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ObservationError(f"Unexpected Content-Type: {content_type}")
                return response.read().decode("utf-8")
        except HTTPError as exc:
            last_error = exc
            if exc.code not in retryable:
                break
        except (URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep((2**attempt) + random.random())
    raise ObservationError(f"Apple request failed: {last_error}")


def with_latest_summary(listing: Listing, summary: ListingSummary) -> Listing:
    return replace(
        listing,
        title=summary.title,
        price_amount=summary.price_amount,
        url=summary.url,
    )
